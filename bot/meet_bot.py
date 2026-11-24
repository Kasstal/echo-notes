"""Google Meet bot. CLI: python meet_bot.py --url ... --session-id ...

A headed Chrome with a persistent profile joins the call as a visible participant, and
capture.js records the remote audio into data/sessions/{id}/raw.webm.
Run `python meet_bot.py --setup` once to sign the bot's Google account into that profile.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

BOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = BOT_DIR.parent
load_dotenv(REPO_ROOT / ".env", override=False)

MEET_PREFIX = "https://meet.google.com/"
PAGE_LOAD_TIMEOUT_S = 60
ADMISSION_TIMEOUT_S = 5 * 60
POLL_S = 1.0
ALONE_LEAVE_S = 60
# Remote audio has to show up this soon after joining, or the capture is not working.
FIRST_AUDIO_TIMEOUT_S = 90

# Meet's markup changes often, so every selector the bot relies on lives here. Each one is a
# regex matched against an accessible name (aria-label or visible text) of the English UI;
# english_url() makes Meet use English whatever the bot account's language is.
SELECTORS = {
    # Meet's "get notifications on your desktop" bubble can cover the pre-join buttons.
    "dismiss": re.compile(r"^(Not now|Got it|Dismiss)$", re.I),
    # Pre-join toggles. The label names what a click will do, so "Turn off ..." means it is on.
    "mic_on": re.compile(r"^Turn off microphone", re.I),
    "cam_on": re.compile(r"^Turn off camera", re.I),
    # Name field on the guest pre-join screen, shown when the profile is not signed in.
    "name_input": re.compile(r"^Your name$", re.I),
    "join": re.compile(r"^(Join now|Ask to join|Join here too)$", re.I),
    # When the bot's account is already in the call on another device, Meet offers only
    # "Switch here" (which would take the call away from that device) and hides
    # "Join here too" in this menu.
    "other_ways": re.compile(r"^Other ways to join", re.I),
    # The in-call toolbar's hang-up button. Meet shows it in the waiting room too, so being in
    # the call also needs the waiting text below to be gone.
    "leave": re.compile(r"^Leave call$", re.I),
    # Toolbar button that opens the participant list; its badge holds the participant count.
    "people": re.compile(r"^(People|Show everyone)", re.I),
    # Waiting-room text after "Ask to join".
    "waiting": re.compile(r"Asking to (be let in|join)|lets you in|brings you into the call|^Connecting", re.I),
    # Meet refused the join or put up a challenge. The bot reports the text and stops.
    "refused": re.compile(
        r"You can't join this (video )?call|denied your request|removed from the (meeting|call)"
        r"|Check your meeting code|Invalid video call name|This meeting has ended"
        r"|unusual traffic|not a robot|Verify it's you|browser or app may not be secure",
        re.I,
    ),
}


class BotError(Exception):
    """A failure that ends the session with a readable error."""


class Stopped(Exception):
    """The backend asked the bot to stop (SIGTERM), e.g. because the session was deleted."""


def _on_sigterm(signum, frame):
    raise Stopped()


def log(event: str) -> None:
    # stdout goes to the session's session.log when the backend starts the bot.
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} bot: {event}", flush=True)


def report(session_id: str, *, file_path: Path | None = None, error: str | None = None) -> None:
    """Tell the backend the bot is done, with either the recording path or an error."""
    url = f"{os.getenv('BACKEND_URL', 'http://127.0.0.1:8000').rstrip('/')}/api/sessions/{session_id}/bot-finished"
    body = {"file_path": str(file_path) if file_path else None, "error": error}
    try:
        resp = requests.post(url, json=body, timeout=15)
        log(f"reported to backend: HTTP {resp.status_code}")
    except requests.RequestException as exc:
        log(f"could not reach backend at {url}: {exc}")


def _visible(locator) -> bool:
    try:
        return locator.first.is_visible()
    except PlaywrightError:
        return False


def _button(page: Page, key: str):
    name = SELECTORS[key]
    # Some choices ("Join here too") are menu items rather than buttons.
    return page.get_by_role("button", name=name).or_(page.get_by_role("menuitem", name=name))


def in_call(page: Page) -> bool:
    return _visible(_button(page, "leave")) and not _visible(page.get_by_text(SELECTORS["waiting"]))


def _check_refused(page: Page) -> None:
    if page.url.startswith("https://accounts.google.com"):
        raise BotError("Meet asked the bot to sign in; run `python bot/meet_bot.py --setup` and sign in")
    refused = page.get_by_text(SELECTORS["refused"])
    if _visible(refused):
        raise BotError(f"Meet refused the join: {refused.first.inner_text().strip()}")


def english_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "hl"] + [("hl", "en")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def join(page: Page, url: str, display_name: str) -> None:
    """Open the Meet link, turn microphone and camera off, click join and wait to be admitted."""
    page.goto(english_url(url), wait_until="domcontentloaded")
    log("opened meeting page")

    deadline = time.monotonic() + PAGE_LOAD_TIMEOUT_S
    while not _visible(_button(page, "join")):
        _check_refused(page)
        other_ways = _button(page, "other_ways")
        if _visible(other_ways):
            other_ways.first.click()
            log("account is already in the call elsewhere; opening other ways to join")
            page.wait_for_timeout(1000)
            continue
        if time.monotonic() > deadline:
            raise BotError(f"no join button after {PAGE_LOAD_TIMEOUT_S} s; the Meet page may have changed")
        page.wait_for_timeout(POLL_S * 1000)

    dismiss = _button(page, "dismiss")
    if _visible(dismiss):
        dismiss.first.click()
        log("closed a Meet popup")

    name_input = page.get_by_role("textbox", name=SELECTORS["name_input"])
    if _visible(name_input):
        name_input.first.fill(display_name)
        log(f"not signed in; joining as guest named {display_name!r}")

    for key, what in (("mic_on", "microphone"), ("cam_on", "camera")):
        toggle = _button(page, key)
        if _visible(toggle):
            toggle.first.click()
            log(f"turned {what} off")
        else:
            log(f"{what} already off")

    join_button = _button(page, "join").first
    label = join_button.inner_text().strip()
    join_button.click()
    log(f"clicked {label!r}")

    deadline = time.monotonic() + ADMISSION_TIMEOUT_S
    announced_wait = False
    confirmed_at = None
    while True:
        _check_refused(page)
        if in_call(page):
            # Meet can flash the in-call view while still connecting; trust it after 3 s.
            confirmed_at = confirmed_at or time.monotonic()
            if time.monotonic() - confirmed_at >= 3:
                break
        else:
            confirmed_at = None
            if not announced_wait and _visible(page.get_by_text(SELECTORS["waiting"])):
                log("in the waiting room; someone in the call has to admit the bot")
                announced_wait = True
        if time.monotonic() > deadline:
            raise BotError("not admitted")
        page.wait_for_timeout(POLL_S * 1000)
    log("joined the call")


def _save_page(page: Page, session_dir: Path) -> None:
    # Meet's refusal screens change without notice; keep what the bot saw for debugging.
    try:
        page.screenshot(path=str(session_dir / "bot_error.png"))
        text = " ".join(page.locator("body").inner_text().split())
        log(f"page said: {text[:400]}")
    except PlaywrightError:
        pass


def participant_count(page: Page) -> int | None:
    """Participants in the call, from the People button's badge; None if it cannot be read."""
    button = _button(page, "people")
    if not _visible(button):
        return None
    try:
        text = " ".join([button.first.get_attribute("aria-label") or "", button.first.inner_text()])
    except PlaywrightError:
        return None
    numbers = re.findall(r"\d+", text)
    return int(numbers[-1]) if numbers else None


class Recording:
    """Appends the base64 slices capture.js sends to raw.webm, so a crash keeps partial audio."""

    def __init__(self, path: Path):
        self.path = path
        self.bytes = 0
        path.write_bytes(b"")

    def add(self, chunk_b64: str) -> None:
        data = base64.b64decode(chunk_b64)
        with self.path.open("ab") as f:
            f.write(data)
        if self.bytes == 0:
            log("receiving audio")
        self.bytes += len(data)


def capture_status(page: Page) -> dict:
    try:
        return page.evaluate("() => window.__echonotes ? window.__echonotes.status() : null") or {}
    except PlaywrightError:
        return {}


def stop_capture(page: Page) -> None:
    try:
        page.evaluate("() => window.__echonotes && window.__echonotes.stop()")
    except PlaywrightError as exc:
        log(f"could not flush the last audio slice: {str(exc).splitlines()[0]}")


def stay(page: Page, recording: Recording, max_minutes: float) -> str:
    """Record until the call ends, the bot is alone for ALONE_LEAVE_S, or max_minutes pass."""
    started = time.monotonic()
    until = started + max_minutes * 60
    alone_since = None
    last_count = None
    announced = False
    next_status = started
    while True:
        if not _visible(_button(page, "leave")):
            return "the call ended"
        now = time.monotonic()
        if now >= until:
            return f"reached the {max_minutes:g}-minute limit"
        if not announced and capture_status(page).get("recording"):
            log("recording remote audio")
            announced = True
        if recording.bytes == 0 and now - started > FIRST_AUDIO_TIMEOUT_S:
            status = capture_status(page)
            raise BotError(f"joined the call but no audio arrived in {FIRST_AUDIO_TIMEOUT_S} s (capture: {status})")
        if now >= next_status:
            log(f"capture: {capture_status(page)}")
            next_status = now + 30
        count = participant_count(page)
        if count != last_count:
            log(f"participants: {count if count is not None else 'unknown'}")
            last_count = count
        if count == 1:
            alone_since = alone_since or now
            if now - alone_since >= ALONE_LEAVE_S:
                return f"alone in the call for {ALONE_LEAVE_S} s"
        else:
            alone_since = None
        page.wait_for_timeout(2000)


def leave(page: Page) -> None:
    leave_button = _button(page, "leave")
    if _visible(leave_button):
        leave_button.first.click()
        log("left the call")


def _channel() -> str | None:
    # Google refuses to sign in to Playwright's bundled Chromium ("This browser or app may not
    # be secure"), and Meet then refuses a signed-out guest. Installed Chrome accepts the sign-in.
    channel = os.getenv("BOT_BROWSER", "chrome").strip()
    return None if channel in ("", "chromium") else channel


def _launch(p, profile_dir: Path):
    profile_dir.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel=_channel(),
        headless=False,
        args=[
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            # The mixing AudioContext in capture.js starts without a click on the page.
            "--autoplay-policy=no-user-gesture-required",
        ],
        viewport=None,
    )


def _chrome_binary() -> str | None:
    candidates = {
        "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "win32": [os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                  os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")],
    }.get(sys.platform, [])
    found = [c for c in candidates if Path(c).is_file()]
    return found[0] if found else shutil.which("google-chrome") or shutil.which("google-chrome-stable")


def setup(profile_dir: Path) -> None:
    """Open the bot profile on Google sign-in so a person can sign the bot account in by hand."""
    chrome = _chrome_binary() if _channel() == "chrome" else None
    if chrome:
        # A plain Chrome window, not one driven by Playwright, so the sign-in is an ordinary one.
        # --use-mock-keychain matches what Playwright passes later; otherwise the saved cookies
        # are encrypted with a key the bot's browser cannot read and it starts signed out.
        profile_dir.mkdir(parents=True, exist_ok=True)
        log(f"profile {profile_dir}: sign in to the bot's Google account, then quit Chrome (Cmd+Q / close all windows)")
        subprocess.run([chrome, f"--user-data-dir={profile_dir}", "--use-mock-keychain", "--no-first-run",
                        "--no-default-browser-check", "https://accounts.google.com/"], check=False)
        log("profile saved")
        return
    with sync_playwright() as p:
        context = _launch(p, profile_dir)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://accounts.google.com/")
        log(f"profile {profile_dir}: sign in to the bot's Google account, then close the window")
        page.wait_for_event("close", timeout=0)
        context.close()
    log("profile saved")


def run(args: argparse.Namespace, profile_dir: Path) -> int:
    session_dir = Path(os.getenv("DATA_DIR", REPO_ROOT / "data")) / "sessions" / args.session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    display_name = os.getenv("BOT_DISPLAY_NAME", "EchoNotes Notetaker (recording)")

    recording = Recording(session_dir / "raw.webm")
    signal.signal(signal.SIGTERM, _on_sigterm)

    with sync_playwright() as p:
        context = _launch(p, profile_dir)
        log(f"launched browser ({_channel() or 'chromium'})")
        context.add_init_script(path=str(BOT_DIR / "capture.js"))
        context.expose_function("echonotesChunk", recording.add)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            join(page, args.url, display_name)
            reason = stay(page, recording, args.max_minutes)
            log(f"leaving: {reason}")
            stop_capture(page)
            leave(page)
        except Stopped:
            log("stopped by the backend")
            stop_capture(page)
            leave(page)
            return 1
        except BotError as exc:
            stop_capture(page)
            log(f"error: {exc}")
            _save_page(page, session_dir)
            report(args.session_id, error=str(exc))
            return 1
        except PlaywrightError as exc:
            if page.is_closed():
                log("browser window was closed")
            else:
                log(f"error: {exc}")
            report(args.session_id, error=f"Bot browser failed: {str(exc).splitlines()[0]}")
            return 1
        finally:
            try:
                context.close()
            except PlaywrightError:
                pass

    if recording.bytes == 0:
        report(args.session_id, error="The bot was in the call but recorded no audio")
        return 1
    log(f"recorded {recording.bytes / 1e6:.1f} MB to {recording.path.name}")
    report(args.session_id, file_path=recording.path)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="EchoNotes Google Meet bot")
    parser.add_argument("--url", help="Google Meet link")
    parser.add_argument("--session-id", help="EchoNotes session id")
    parser.add_argument("--max-minutes", type=int, default=int(os.getenv("BOT_MAX_MINUTES", "90")))
    parser.add_argument("--setup", action="store_true", help="sign the bot account into its profile")
    args = parser.parse_args()

    profile_dir = Path(os.getenv("BOT_PROFILE_DIR", "bot/profile"))
    if not profile_dir.is_absolute():
        profile_dir = REPO_ROOT / profile_dir

    if args.setup:
        setup(profile_dir)
        return
    if not args.url or not args.session_id:
        parser.error("--url and --session-id are required")
    if not args.url.startswith(MEET_PREFIX):
        parser.error(f"--url must start with {MEET_PREFIX}")
    sys.exit(run(args, profile_dir))


if __name__ == "__main__":
    main()

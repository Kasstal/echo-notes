"""Google Meet bot. CLI: python meet_bot.py --url ... --session-id ...

A headed Chromium with a persistent profile joins the call as a visible participant.
Run `python meet_bot.py --setup` once to sign the bot's Google account into that profile.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env", override=False)

MEET_PREFIX = "https://meet.google.com/"
PAGE_LOAD_TIMEOUT_S = 60
ADMISSION_TIMEOUT_S = 5 * 60
POLL_S = 1.0

# Meet's markup changes often, so every selector the bot relies on lives here. Each one is a
# regex matched against an accessible name (aria-label or visible text) of the English UI.
SELECTORS = {
    # Pre-join toggles. The label names what a click will do, so "Turn off ..." means it is on.
    "mic_on": re.compile(r"^Turn off microphone", re.I),
    "cam_on": re.compile(r"^Turn off camera", re.I),
    # Name field on the guest pre-join screen, shown when the profile is not signed in.
    "name_input": re.compile(r"^Your name$", re.I),
    "join": re.compile(r"^(Join now|Ask to join)$", re.I),
    # Present only once the bot is inside the call.
    "leave": re.compile(r"^Leave call$", re.I),
    # Waiting-room text after "Ask to join".
    "waiting": re.compile(r"Asking to (be let in|join)|lets you in|brings you into the call", re.I),
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
    return page.get_by_role("button", name=SELECTORS[key])


def _check_refused(page: Page) -> None:
    if page.url.startswith("https://accounts.google.com"):
        raise BotError("Meet asked the bot to sign in; run `python bot/meet_bot.py --setup` and sign in")
    refused = page.get_by_text(SELECTORS["refused"])
    if _visible(refused):
        raise BotError(f"Meet refused the join: {refused.first.inner_text().strip()}")


def join(page: Page, url: str, display_name: str) -> None:
    """Open the Meet link, turn microphone and camera off, click join and wait to be admitted."""
    page.goto(url, wait_until="domcontentloaded")
    log("opened meeting page")

    deadline = time.monotonic() + PAGE_LOAD_TIMEOUT_S
    while not _visible(_button(page, "join")):
        _check_refused(page)
        if time.monotonic() > deadline:
            raise BotError(f"no join button after {PAGE_LOAD_TIMEOUT_S} s; the Meet page may have changed")
        page.wait_for_timeout(POLL_S * 1000)

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
    while not _visible(_button(page, "leave")):
        _check_refused(page)
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


def leave(page: Page) -> None:
    leave_button = _button(page, "leave")
    if _visible(leave_button):
        leave_button.first.click()
        log("left the call")


def _launch(p, profile_dir: Path):
    profile_dir.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,
        args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
        viewport=None,
    )


def setup(profile_dir: Path) -> None:
    """Open the bot profile on Google sign-in so a person can sign the bot account in by hand."""
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

    with sync_playwright() as p:
        context = _launch(p, profile_dir)
        log("launched browser")
        page = context.pages[0] if context.pages else context.new_page()
        try:
            join(page, args.url, display_name)
            # TODO: step 2 records remote audio here; step 3 adds the leave conditions.
            until = time.monotonic() + args.max_minutes * 60
            while time.monotonic() < until and _visible(_button(page, "leave")):
                page.wait_for_timeout(5000)
            leave(page)
        except BotError as exc:
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

    report(args.session_id, error="Bot joined and left, but audio recording is not built yet")
    return 1


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

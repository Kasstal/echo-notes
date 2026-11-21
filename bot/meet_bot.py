"""Google Meet bot. CLI: python meet_bot.py --url ... --session-id ...

Playwright-driven headed Chromium joins a Meet call, records remote audio, and
hands the recording to the pipeline. Stub for M0 — implemented in the Bot
milestone (M5).
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="EchoNotes Google Meet bot")
    parser.add_argument("--url", required=True, help="Google Meet link")
    parser.add_argument("--session-id", required=True, help="EchoNotes session id")
    parser.add_argument("--max-minutes", type=int, default=90)
    parser.parse_args()
    raise NotImplementedError("Bot is implemented in milestone M5")


if __name__ == "__main__":
    main()

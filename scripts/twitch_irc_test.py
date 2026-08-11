"""Quick Twitch IRC smoke test.

Reads the OAuth token from .secrets/twitch_oauth.txt by default.
Pass --token-file, --channel, and --username to override.
"""

import argparse
import os
import time
from pathlib import Path

from qoresence.agents.twitch_client import TwitchIRCClient


def _load_token(token_file: str | None) -> str:
    if token_file:
        p = Path(token_file)
    else:
        p = Path(".secrets/twitch_oauth.txt")
    if not p.exists():
        raise FileNotFoundError(f"Token file not found: {p}")
    token = p.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    if not token.lower().startswith("oauth:"):
        token = f"oauth:{token}"
    return token


def main() -> None:
    parser = argparse.ArgumentParser(description="Twitch IRC smoke test")
    parser.add_argument(
        "--channel", default=os.environ.get("QORESENCE_TWITCH_CHANNEL") or "<your_channel>"
    )
    parser.add_argument(
        "--username", default=os.environ.get("QORESENCE_TWITCH_BOT_USERNAME") or "<your_bot>"
    )
    parser.add_argument(
        "--token-file",
        default=os.environ.get("QORESENCE_TWITCH_TOKEN_FILE") or ".secrets/twitch_oauth.txt",
    )
    parser.add_argument(
        "--message", default="Qoresence ClutchBot test — hello from the local agent 🤖"
    )
    args = parser.parse_args()

    if args.channel == "<your_channel>" or args.username == "<your_bot>":
        print(
            "Set --channel and --username or the QORESENCE_TWITCH_CHANNEL / QORESENCE_TWITCH_BOT_USERNAME env vars.",
            flush=True,
        )
        return

    token = _load_token(args.token_file)
    client = TwitchIRCClient(
        username=args.username,
        oauth_token=token,
        channel=args.channel,
        min_interval_s=2.0,
    )
    if client.start():
        print("IRC connected, waiting for ready...", flush=True)
        if client._ready_event.wait(10):
            print("Ready. Sending test message...", flush=True)
            client.send_message(args.message)
            print("Sent. Waiting 10s for delivery, then exiting...", flush=True)
            time.sleep(10)
            print(
                f"Done. Check https://www.twitch.tv/{args.channel}/chat for the message.",
                flush=True,
            )
        else:
            print("Ready timeout.", flush=True)
    else:
        print("Failed to start IRC client.", flush=True)


if __name__ == "__main__":
    main()

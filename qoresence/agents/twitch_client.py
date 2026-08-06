"""
Minimal synchronous Twitch IRC client for ClutchBot.

Uses a background thread and an outbound message queue so the rest of
Qoresence stays synchronous. Implements Twitch IRC rate limits.
"""

from __future__ import annotations

import logging
import queue
import re
import socket
import ssl
import threading
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

IRC_HOST = "irc.chat.twitch.tv"
IRC_PORT = 6697

# Twitch rate limits for IRC PRIVMSG:
# - regular users: 20 messages / 30 seconds
# - moderators: 100 messages / 30 seconds
# We default to 1 msg / 2 s to be safe and well under normal limits.
DEFAULT_MIN_INTERVAL_S = 2.0


@dataclass
class IRCMessage:
    """Parsed Twitch IRC message."""
    raw: str
    tags: dict[str, str]
    prefix: str
    command: str
    params: list[str]
    trailing: str


class TwitchIRCClient:
    """Synchronous-ish Twitch IRC client running in its own thread."""

    def __init__(
        self,
        username: str,
        oauth_token: str,
        channel: str,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
    ):
        self.username = username.lower().strip()
        self.oauth_token = self._normalize_token(oauth_token)
        self.channel = channel.lower().strip().lstrip("#")
        self.min_interval_s = min_interval_s

        self._sock: ssl.SSLSocket | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._outbound: queue.Queue[str] = queue.Queue()
        self._last_send_time = 0.0
        self._ready_event = threading.Event()

    @staticmethod
    def _normalize_token(token: str) -> str:
        token = token.strip()
        if token.lower().startswith("oauth:"):
            return token
        return f"oauth:{token}"

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Connect and start the IRC reader/writer thread."""
        if self._running:
            return True

        try:
            self._connect()
        except OSError as e:
            log.error(f"Twitch IRC connection failed: {e}")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._run, name="clutchbot-irc", daemon=True)
        self._thread.start()

        # Wait for the connection to finish registration (max 5s)
        if not self._ready_event.wait(timeout=5.0):
            log.warning("Twitch IRC did not report ready within 5s")

        log.info(f"Twitch IRC client started as {self.username} in #{self.channel}")
        return True

    def stop(self) -> None:
        """Disconnect and stop the IRC thread."""
        self._running = False
        self._ready_event.clear()
        try:
            if self._sock:
                self._send_raw("QUIT :Qoresence ClutchBot signing off\r\n")
        except OSError:
            pass
        finally:
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("Twitch IRC client stopped")

    def send_message(self, message: str) -> bool:
        """Queue a PRIVMSG to the configured channel."""
        if not self._running or not self._ready_event.is_set():
            log.warning("Twitch IRC not ready; dropping message")
            return False

        if len(message) > 500:
            # Twitch chat message length limit is 500 chars
            message = message[:500]

        try:
            self._outbound.put_nowait(message)
            return True
        except queue.Full:
            log.warning("Twitch IRC outbound queue full")
            return False

    def is_ready(self) -> bool:
        return self._ready_event.is_set() and self._running

    # ──────────────────────────────────────────────────────────────────────────
    # INTERNALS
    # ──────────────────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        context = ssl.create_default_context()
        sock = socket.create_connection((IRC_HOST, IRC_PORT), timeout=10)
        self._sock = context.wrap_socket(sock, server_hostname=IRC_HOST)
        self._sock.settimeout(None)

        # Request Twitch tags/commands
        self._send_raw("CAP REQ :twitch.tv/tags twitch.tv/commands\r\n")
        self._send_raw(f"PASS {self.oauth_token}\r\n")
        self._send_raw(f"NICK {self.username}\r\n")
        self._send_raw(f"JOIN #{self.channel}\r\n")

    def _run(self) -> None:
        """Main loop: read incoming + send queued messages."""
        while self._running:
            try:
                self._drain_outbound()
                self._read_and_process()
            except OSError as e:
                log.error(f"Twitch IRC socket error: {e}")
                self._reconnect()
            except Exception as e:
                log.error(f"Twitch IRC unexpected error: {e}")
                time.sleep(1.0)

    def _reconnect(self) -> None:
        """Attempt a single reconnect."""
        if not self._running:
            return
        log.info("Twitch IRC reconnecting in 3s...")
        time.sleep(3.0)
        try:
            if self._sock:
                try:
                    self._sock.close()
                except OSError:
                    pass
            self._ready_event.clear()
            self._connect()
        except OSError as e:
            log.error(f"Twitch IRC reconnect failed: {e}")

    def _send_raw(self, data: str) -> None:
        if self._sock is None:
            raise OSError("No socket")
        try:
            self._sock.sendall(data.encode("utf-8"))
        except OSError:
            raise

    def _send_privmsg(self, message: str) -> None:
        channel = f"#{self.channel}"
        self._send_raw(f"PRIVMSG {channel} :{message}\r\n")

    def _drain_outbound(self) -> None:
        try:
            message = self._outbound.get(timeout=0.1)
        except queue.Empty:
            return

        elapsed = time.time() - self._last_send_time
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)

        self._send_privmsg(message)
        self._last_send_time = time.time()

    def _read_and_process(self) -> None:
        if self._sock is None:
            raise OSError("No socket")

        # Non-blocking with a short timeout so outbound stays responsive
        self._sock.settimeout(0.2)
        try:
            data = self._sock.recv(4096)
        except TimeoutError:
            return
        except ssl.SSLError as e:
            if "read operation timed out" in str(e).lower():
                return
            raise
        finally:
            self._sock.settimeout(None)

        if not data:
            raise OSError("IRC server closed connection")

        text = data.decode("utf-8", errors="replace")
        for line in text.split("\r\n"):
            if not line:
                continue
            self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        msg = self._parse_line(line)

        if msg.command == "PING":
            payload = msg.params[0] if msg.params else "tmi.twitch.tv"
            self._send_raw(f"PONG :{payload}\r\n")
            return

        if msg.command == "001":
            # Welcome / registration complete
            self._ready_event.set()
            log.info("Twitch IRC registered successfully")
            return

        if msg.command == "PRIVMSG":
            # Could be used for commands later
            sender = self._parse_sender(msg.prefix)
            log.debug(f"Twitch chat from {sender}: {msg.trailing}")
            return

        if msg.command in ("NOTICE", "HOSTTARGET", "CLEARCHAT", "CLEARMSG"):
            log.debug(f"Twitch IRC {msg.command}: {msg.trailing or msg.params}")
            return

        log.debug(f"Twitch IRC: {line[:200]}")

    @staticmethod
    def _parse_line(line: str) -> IRCMessage:
        """Parse a single IRC line into tags, prefix, command, params, trailing."""
        tags: dict[str, str] = {}
        prefix = ""
        command = ""
        params: list[str] = []
        trailing = ""

        rest = line

        # Tags: @badge-info=;badges=... :...
        if rest.startswith("@"):
            tag_part, rest = rest.split(" ", 1)
            tag_part = tag_part[1:]
            for tag in tag_part.split(";"):
                if "=" in tag:
                    k, v = tag.split("=", 1)
                    tags[k] = v
                else:
                    tags[tag] = ""

        # Prefix
        if rest.startswith(":"):
            prefix, rest = rest[1:].split(" ", 1)

        # Command + params
        if " :" in rest:
            pre, trailing = rest.split(" :", 1)
            parts = pre.split()
        else:
            parts = rest.split()
            trailing = ""

        if parts:
            command = parts[0]
            params = parts[1:]

        return IRCMessage(
            raw=line,
            tags=tags,
            prefix=prefix,
            command=command,
            params=params,
            trailing=trailing,
        )

    @staticmethod
    def _parse_sender(prefix: str) -> str:
        """Extract nickname from 'nick!user@host'."""
        match = re.match(r"([^!]+)", prefix)
        return match.group(1) if match else prefix

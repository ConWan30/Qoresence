"""mDNS/Bonjour broadcast for the Mobile Glass — LAN auto-discovery.

Broadcasts ``_qoresence._tcp.local.`` so a phone on the same Wi-Fi can find
the PC without typing an IP or scanning a QR. Local-first: only advertises
when the deck is bound to a non-loopback address (``--deck-bind 0.0.0.0``).

Optional dependency: ``zeroconf`` (``pip install 'qoresence[glass]'``).
If absent, this module silently no-ops — the glass still works via QR/URL.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Any

log = logging.getLogger(__name__)

_SERVICE_TYPE = "_qoresence._tcp.local."
_runtime: Any = None
_lock = threading.Lock()


def _guess_lan_ip() -> str | None:
    """Best-effort LAN IPv4 of this host. None if not resolvable."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        return str(ip) if ip and not str(ip).startswith("127.") else None
    except Exception:
        return None
    finally:
        sock.close()


def _friendly_name() -> str:
    """Couch-friendly label, e.g. 'Qoresence — DESKTOP-FOO'."""
    try:
        import platform

        node = platform.node() or "PC"
        node = node.split(".")[0]
    except Exception:
        node = "PC"
    return f"Qoresence — {node}"


def is_loopback_bind(host: str | None) -> bool:
    h = str(host or "").strip().lower()
    return h in {"", "127.0.0.1", "localhost", "::1", "[::1]"}


def start_mdns(port: int, host: str | None = None) -> bool:
    """Start broadcasting _qoresence._tcp on the LAN. No-op on loopback-only.

    Returns True if advertising started, False otherwise (loopback, no zeroconf,
    or no LAN IP).
    """
    global _runtime
    if is_loopback_bind(host):
        log.debug("mDNS skipped: deck is loopback-only")
        return False
    try:
        from zeroconf import IPVersion, ServiceInfo, Zeroconf
    except ImportError:
        log.info(
            "mDNS auto-discovery unavailable — install 'qoresence[glass]' to enable "
            "LAN auto-pairing. Mobile glass still works via QR/URL."
        )
        return False

    lan_ip = _guess_lan_ip()
    if not lan_ip:
        log.warning("mDNS skipped: could not resolve LAN IP")
        return False

    with _lock:
        if _runtime is not None:
            return True  # already running
        try:
            zc = Zeroconf(ip_version=IPVersion.V4Only)
            info = ServiceInfo(
                type_=_SERVICE_TYPE,
                name=f"{_friendly_name()}.{_SERVICE_TYPE}",
                addresses=[socket.inet_aton(lan_ip)],
                port=int(port),
                properties={
                    b"path": b"/mobile.html",
                    b"ver": b"1",
                    b"host_ip": lan_ip.encode("utf-8"),
                },
                server=f"{socket.gethostname()}.local.",
            )
            zc.register_service(info)
            _runtime = {"zc": zc, "info": info}
            log.info(
                "mDNS advertising %s on %s:%s (LAN: %s) — phones on Wi-Fi can auto-pair",
                _SERVICE_TYPE,
                lan_ip,
                port,
                lan_ip,
            )
            return True
        except Exception as e:
            log.warning("mDNS start failed: %s", e)
            try:
                if "_runtime" in dir() and _runtime is not None:
                    _runtime = None
            except Exception:
                pass
            return False


def stop_mdns() -> None:
    global _runtime
    with _lock:
        rt = _runtime
        _runtime = None
    if rt is None:
        return
    try:
        zc = rt.get("zc")
        info = rt.get("info")
        if zc and info:
            zc.unregister_service(info)
        if zc:
            zc.close()
        log.info("mDNS advertising stopped")
    except Exception as e:
        log.debug("mDNS stop failed: %s", e)


def discovery_info(port: int, host: str | None = None) -> dict[str, Any]:
    """Local service info for /api/discover — useful for PWA pairing + debug."""
    lan_ip = _guess_lan_ip() if not is_loopback_bind(host) else None
    return {
        "service": _SERVICE_TYPE,
        "name": _friendly_name() if lan_ip else None,
        "host": lan_ip,
        "port": int(port),
        "path": "/mobile.html",
        "url": f"http://{lan_ip}:{int(port)}/mobile.html" if lan_ip else None,
        "lan": bool(lan_ip),
        "advertising": _runtime is not None,
    }

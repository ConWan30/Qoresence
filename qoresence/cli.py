"""
Qoresence CLI — Phase 9 Production Entry Point

Unified command-line interface for running Qoresence lobes.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path

# Held open so a second --play cannot race before Deck binds
_PILOT_LOCK_SOCK: socket.socket | None = None

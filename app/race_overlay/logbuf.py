"""Keeps the last lines the program printed, so the Help tab can show them (no terminal needed)."""

import sys
import threading
import time
from collections import deque

_LINES = deque(maxlen=2000)
_LOCK = threading.Lock()
_PARTIAL = {"stdout": "", "stderr": ""}


class _Tee:
    """Passes everything on to the real stream and also remembers complete lines."""

    def __init__(self, real, name):
        self._real = real
        self._name = name

    def write(self, text):
        try:
            if self._real is not None:
                self._real.write(text)
        except Exception:
            pass
        try:
            with _LOCK:
                buf = _PARTIAL[self._name] + text
                *done, _PARTIAL[self._name] = buf.split("\n")
                stamp = time.strftime("%H:%M:%S")
                for line in done:
                    _LINES.append("%s  %s" % (stamp, line))
        except Exception:
            pass
        return len(text)

    def flush(self):
        try:
            if self._real is not None:
                self._real.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return bool(self._real is not None and self._real.isatty())
        except Exception:
            return False

    def __getattr__(self, name):          # fileno(), encoding ... come from the real stream
        if self._real is None:
            raise AttributeError(name)
        return getattr(self._real, name)


def install():
    """Call once at start-up. Safe to call twice."""
    for name in ("stdout", "stderr"):
        cur = getattr(sys, name)
        if not isinstance(cur, _Tee):
            setattr(sys, name, _Tee(cur, name))


def add(line):
    with _LOCK:
        _LINES.append("%s  %s" % (time.strftime("%H:%M:%S"), line))


def lines():
    with _LOCK:
        return list(_LINES)

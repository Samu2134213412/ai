"""Console output that survives a legacy code page.

Windows gives a *redirected* stdout the process code page rather than UTF-8 —
cp1252 on a German install — and printing a check mark to it raises
UnicodeEncodeError. That is not a cosmetic problem: the exception propagates
out of the startup banner and kills the process before it ever serves a
request. It happened the moment Jarvis started this server with its output
going to a log file:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2713'

Two defences, because either one alone can be unavailable:

1. Reconfigure the streams to UTF-8 with replacement. This fixes every string
   the program prints, not just the ones we remembered to guard.
2. Where a stream cannot be reconfigured, fall back to ASCII marks, so the
   symbols we control cannot kill the process either.
"""

from __future__ import annotations

import sys


def make_output_robust() -> None:
    """Point stdout and stderr at UTF-8, replacing what cannot be encoded.

    Called once at start-up. Failures are ignored on purpose: a stream that
    refuses to be reconfigured is exactly the case the ASCII fallback below
    covers, and the program must not die while making its output safer.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - platform dependent
            pass


def supports(text: str, stream=None) -> bool:
    """Can this stream encode that text, as it is configured right now?

    The stream is a parameter rather than always ``sys.stdout`` so the
    decision can be exercised against a real cp1252 stream in a test, without
    reaching into module globals.
    """
    target = sys.stdout if stream is None else stream
    encoding = getattr(target, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def marks(preferred: dict[str, str], fallback: dict[str, str],
          stream=None) -> dict[str, str]:
    """Pick the symbol set this stream can actually print."""
    return preferred if supports("".join(preferred.values()), stream) else fallback

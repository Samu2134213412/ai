"""Startup output on a console that cannot encode UTF-8.

This reproduces a real crash. Jarvis starts this server with its output
redirected to a log file; Windows then hands that stream the process code
page (cp1252 on a German install), and the banner's check mark raised
UnicodeEncodeError, killing the process with exit code 1 before it served a
single request:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2713'
"""

from __future__ import annotations

import io
import sys

import pytest

from codepilot import console, doctor
from codepilot.__main__ import _mark


@pytest.fixture
def cp1252_stdout(monkeypatch):
    """A stream that behaves like a redirected stdout on German Windows.

    Handed to the code under test explicitly: pytest reinstalls its own
    sys.stdout for the call phase, so patching the global would not hold.
    """
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="")
    monkeypatch.setattr("codepilot.__main__._MARKS", None)
    monkeypatch.setattr("codepilot.doctor._MARK", None)
    return stream, raw


def test_a_check_mark_really_does_kill_cp1252(cp1252_stdout):
    """The premise: without the fix this is fatal, not cosmetic."""
    stream, _ = cp1252_stdout
    with pytest.raises(UnicodeEncodeError):
        stream.write("✓")
        stream.flush()


def test_marks_fall_back_to_ascii(cp1252_stdout):
    stream, raw = cp1252_stdout

    print(f"  {_mark(True, stream)} Claude Code", file=stream)
    print(f"  {_mark(False, stream)} Ollama", file=stream)
    stream.flush()

    ausgabe = raw.getvalue().decode("cp1252")
    assert "✓" not in ausgabe and "✗" not in ausgabe
    assert "Claude Code" in ausgabe and "Ollama" in ausgabe


def test_doctor_marks_fall_back_too(cp1252_stdout):
    stream, raw = cp1252_stdout

    for status in (doctor.PASS, doctor.FAIL, doctor.WARN, doctor.SKIP):
        print(doctor._mark(status, stream), file=stream)
    stream.flush()

    assert raw.getvalue().decode("cp1252")  # nothing raised, something printed


def test_utf8_console_keeps_the_nice_symbols(monkeypatch):
    monkeypatch.setattr("codepilot.__main__._MARKS", None)
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="")

    assert _mark(True, stream) == "✓"
    assert _mark(False, stream) == "✗"


def test_supports_reports_the_given_stream():
    assert console.supports("✓", io.TextIOWrapper(io.BytesIO(), encoding="cp1252")) is False
    assert console.supports("✓", io.TextIOWrapper(io.BytesIO(), encoding="utf-8")) is True


def test_make_output_robust_switches_the_stream(monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))

    console.make_output_robust()

    assert sys.stdout.encoding.lower().replace("-", "") == "utf8"
    sys.stdout.write("✓ geht jetzt")
    sys.stdout.flush()
    assert "✓" in raw.getvalue().decode("utf-8")


def test_make_output_robust_survives_a_stream_without_reconfigure(monkeypatch):
    """A replaced stdout (pytest's capture, a logging shim) must not crash it."""
    class Schlicht:
        encoding = "cp1252"

        def write(self, _text):
            return 0

    monkeypatch.setattr(sys, "stdout", Schlicht())
    monkeypatch.setattr(sys, "stderr", Schlicht())

    console.make_output_robust()  # darf nicht werfen

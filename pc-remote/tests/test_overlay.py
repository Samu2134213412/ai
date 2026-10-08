import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import overlay  # noqa: E402
import server  # noqa: E402


def test_visibility_window():
    assert not overlay.visible(100.0, 0.0)          # never controlled
    assert overlay.visible(100.0, 99.0)             # just now
    assert not overlay.visible(100.0, 100.0 - overlay.HOLD_S - 0.1)  # faded out


def test_ring_colors_valid_and_pulse():
    a, b = overlay.ring_colors(0.0), overlay.ring_colors(0.25)
    assert len(a) == 5 and all(len(c) == 7 and c[0] == "#" for c in a) and a != b


def test_dispatch_marks_phone_activity():
    class B:
        def __getattr__(self, n):
            return lambda *a: None
    server.last_control[0] = 0.0
    server.dispatch(B(), "click", {})
    assert server.last_control[0] > 0
    server.last_control[0] = 0.0
    server.dispatch(B(), "open_url", {"url": "https://x.y"})  # not a pointer action
    assert server.last_control[0] == 0.0

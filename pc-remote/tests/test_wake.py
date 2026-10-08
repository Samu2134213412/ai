import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import wake  # noqa: E402


def test_magic_packet():
    p = wake.magic_packet("aa:bb:cc:dd:ee:ff")
    assert len(p) == 102 and p[:6] == b"\xff" * 6 and p[6:12] == bytes.fromhex("aabbccddeeff")


def test_bad_mac():
    with pytest.raises(ValueError):
        wake.magic_packet("zz")

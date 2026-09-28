import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_real_platform_calls():
    from tide_agent.win import WinPlatform
    p = WinPlatform()
    assert p.processes()
    assert any(a.up for a in p.adapters().values())
    assert isinstance(p.internet(), bool)
    assert isinstance(p.removable_drives(), set)
    assert isinstance(p.clipboard_seq(), int)
    shot = p.screenshot()
    assert shot is None or shot[:2] == b"\xff\xd8"

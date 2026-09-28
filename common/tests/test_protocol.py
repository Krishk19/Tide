import time
from tide_common.protocol import Signal, Kind, msg, SEVERITY_RANK


def test_signal_defaults_ts_to_now():
    before = time.time()
    s = Signal(kind=Kind.WINDOW, data={"process": "code.exe"})
    assert before <= s.ts <= time.time()


def test_msg_builds_typed_dict():
    assert msg("heartbeat", state="live") == {"t": "heartbeat", "state": "live"}


def test_severity_rank_orders():
    assert SEVERITY_RANK["info"] < SEVERITY_RANK["medium"] < SEVERITY_RANK["high"] < SEVERITY_RANK["critical"]

from typing import NamedTuple

from tide_server.classify.heuristics import Verdict

AUTO_ACT_LABELS = frozenset({"ai_assistant", "communication", "remote_or_file_share"})


class Decision(NamedTuple):
    action: str      # none | close_tab | kill
    severity: str    # info | medium | high | critical
    flag: bool


def decide(v: Verdict, is_browser: bool, auto_act_min: float = 0.90) -> Decision:
    if v.source == "jev" and v.label in AUTO_ACT_LABELS and v.confidence >= auto_act_min:
        return Decision("close_tab" if is_browser else "kill", "critical", True)
    if v.violation >= 0.80:
        return Decision("none", "high", True)
    if v.violation >= 0.60:
        return Decision("none", "medium", True)
    return Decision("none", "info", False)

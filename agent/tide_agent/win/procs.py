import psutil

from tide_agent.platform import ProcInfo
from tide_agent.win.windows import pe_info


def processes() -> dict[int, ProcInfo]:
    out = {}
    for p in psutil.process_iter(["pid", "name", "exe"]):
        exe = p.info.get("exe") or ""
        desc, orig = pe_info(exe) if exe else ("", "")
        out[p.info["pid"]] = ProcInfo(p.info["pid"], p.info.get("name") or "", exe, desc, orig)
    return out


def kill(pid: int) -> None:
    try:
        p = psutil.Process(pid)
        p.terminate()
        p.wait(1)
    except psutil.TimeoutExpired:
        p.kill()
    except psutil.Error:
        pass

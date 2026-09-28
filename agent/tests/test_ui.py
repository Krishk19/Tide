from tide_agent.ui.headless import HeadlessUI


def test_headless_prints_each_call():
    lines = []
    ui = HeadlessUI(out=lines.append)
    ui.show_join("10.10.0.1", None)
    ui.show_preflight([{"id": "internet", "label": "Offline", "detail": "", "state": "ok"}])
    ui.block("ChatGPT — closed", False)
    ui.done(3, "10:58")
    assert lines == ["[join] server=10.10.0.1", "[preflight] ok:Offline", "[block] ChatGPT — closed",
                     "[done] 3 files at 10:58"]

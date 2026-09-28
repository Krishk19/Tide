# pyinstaller agent/tide-agent.spec  ->  dist/tide-agent.exe
a = Analysis(["tide_agent/__main__.py"], pathex=["."],
             datas=[("tide_agent/ui/web", "tide_agent/ui/web")],
             hiddenimports=["tide_agent.win", "uiautomation", "webview.platforms.edgechromium"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="tide-agent", console=False, onefile=True,
          icon="../design/tide.ico")

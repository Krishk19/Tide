from tide_agent.win import browser, capture, devices, input, net, procs, windows


class WinPlatform:
    foreground = staticmethod(windows.foreground)
    browser_host = staticmethod(browser.browser_host)
    processes = staticmethod(procs.processes)
    kill = staticmethod(procs.kill)
    adapters = staticmethod(net.adapters)
    internet = staticmethod(net.internet)
    lan_peers = staticmethod(net.lan_peers)
    removable_drives = staticmethod(devices.removable_drives)
    clipboard_seq = staticmethod(devices.clipboard_seq)
    clipboard_text = staticmethod(devices.clipboard_text)
    close_tab = staticmethod(input.close_tab)
    screenshot = staticmethod(capture.screenshot)

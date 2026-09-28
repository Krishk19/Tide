from tide_common.policy import Policy, PRESETS, DENY_HOSTS, host_match, display_app


def test_from_apps_maps_catalog_names_to_processes():
    p = Policy.from_apps(["VS Code", "Wireshark"])
    assert "code.exe" in p.allowed_processes
    assert "wireshark.exe" in p.allowed_processes


def test_always_allowed_and_case_insensitive():
    p = Policy.from_apps([])
    assert p.is_allowed_process("Explorer.EXE")
    assert not p.is_allowed_process("code.exe")


def test_roundtrip_dict():
    p = Policy.from_apps(PRESETS["networking"], server_ip="10.10.0.1", internet="blocked")
    assert Policy.from_dict(p.to_dict()) == p


def test_internet_defaults_to_allowed():
    assert not Policy.from_apps([]).internet_blocked
    assert Policy.from_dict({}).internet == "allowed"
    assert Policy.from_apps([], internet="blocked").internet_blocked


def test_host_match_matches_subdomains_not_suffixes():
    assert host_match("chatgpt.com", DENY_HOSTS) == "ChatGPT"
    assert host_match("www.chatgpt.com", DENY_HOSTS) == "ChatGPT"
    assert host_match("notchatgpt.com", DENY_HOSTS) is None


def test_display_app():
    assert display_app("Code.exe") == "VS Code"
    assert display_app("weird.exe") == "weird"

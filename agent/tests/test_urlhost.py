from tide_agent.urlhost import host_from_value


def test_host_from_value():
    assert host_from_value("chatgpt.com") == "chatgpt.com"
    assert host_from_value("https://www.Poe.com/chat/x") == "www.poe.com"
    assert host_from_value("") == ""
    assert host_from_value("file:///C:/Exam/22BCS107/setA.pdf") == ""
    assert host_from_value("edge://newtab") == ""
    assert host_from_value("localhost:5173/x") == "localhost"

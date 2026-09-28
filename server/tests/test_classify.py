import json

import httpx
import pytest

from tide_common.protocol import Kind, Signal
from tide_server.classify.describe import cache_key, describe
from tide_server.classify.heuristics import classify_heuristic
from tide_server.classify.jev import JevClassifier, JevError
from tide_server.classify.pipeline import Pipeline

APPS = ["VS Code", "Wireshark"]
POE = Signal(kind=Kind.WINDOW, data={"process": "chrome.exe", "title": "Fast AI Chat - Poe",
                                     "host": "poe.com", "description": "Google Chrome"})

JEV_REPLY = {
    "id": "gen-dec-1", "model": "typesafe/jev-1.13-20260917", "provider": "TypeSafe",
    "answers": {
        "activity": {"type": "choice", "choice": "ai_assistant", "confidence": 0.81,
                     "probabilities": {"ai_assistant": 0.96, "web_lookup": 0.03, "other": 0.01}},
        "violation": {"type": "noul", "noul": 0.97},
    },
    "usage": {"input_tokens": 300, "output_tokens": 20, "cost": 0.00001},
}


def jev_with(handler):
    return JevClassifier("https://openrouter.ai/api/alpha/decisions", "k", "~typesafe/jev-latest",
                         client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_describe_includes_policy_and_event():
    text = describe(POE, APPS)
    assert "allowed = VS Code, Wireshark" in text
    assert 'title:   "Fast AI Chat - Poe"' in text and "host:    poe.com" in text


def test_cache_key_ignores_title_for_browsers():
    other_page = Signal(kind=Kind.WINDOW, data={**POE.data, "title": "Another chat - Poe"})
    assert cache_key(POE) == cache_key(other_page) == "chrome.exe|poe.com"


def test_heuristic_never_confident_enough_to_act():
    v = classify_heuristic(describe(POE, APPS))
    assert v.label == "ai_assistant" and v.source == "heuristic" and v.confidence <= 0.70
    assert classify_heuristic("process: game.exe title: Solitaire").label == "other"


def test_jev_request_body_shape():
    body = jev_with(lambda r: None).request_body("STATE")
    assert body["model"] == "~typesafe/jev-latest" and body["state"] == "STATE"
    assert body["questions"]["activity"]["type"] == "choice"
    assert "ai_assistant" in body["questions"]["activity"]["criteria"]
    assert body["questions"]["violation"]["type"] == "noul"
    assert set(body["questions"]["violation"]["criteria"]) == {"true", "false"}


def test_jev_parse_uses_choice_probability():
    v = JevClassifier.parse(JEV_REPLY)
    assert (v.label, v.confidence, v.violation, v.source) == ("ai_assistant", 0.96, 0.97, "jev")
    assert v.raw["jev_confidence"] == 0.81


async def test_jev_http_call_sends_auth():
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=JEV_REPLY)

    v = await jev_with(handler).classify("STATE")
    assert seen["auth"] == "Bearer k" and seen["body"]["state"] == "STATE"
    assert v.label == "ai_assistant"


async def test_jev_http_error_raises():
    with pytest.raises(JevError):
        await jev_with(lambda r: httpx.Response(500, text="boom")).classify("STATE")


async def test_pipeline_caches_jev_answers():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=JEV_REPLY)

    p = Pipeline(jev_with(handler))
    first = await p.classify(POE, APPS)
    second = await p.classify(POE, APPS)
    assert len(calls) == 1 and not first.cached and second.cached and second.source == "jev"


async def test_pipeline_falls_back_to_heuristics_on_jev_failure_and_retries_later():
    """Review focus #5."""
    p = Pipeline(jev_with(lambda r: httpx.Response(503)))
    v = await p.classify(POE, APPS)
    assert v.source == "heuristic" and cache_key(POE) not in p.cache


async def test_pipeline_without_key_is_heuristics_mode():
    p = Pipeline(None)
    assert p.mode == "heuristics"
    assert (await p.classify(POE, APPS)).source == "heuristic"

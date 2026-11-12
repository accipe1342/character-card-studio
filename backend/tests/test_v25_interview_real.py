"""Interview and Trim through the REAL model request code (generator._request), against a small OpenAI-compatible
server that answers the way real models do: proper JSON, JSON in code fences, plain text with a "Name:" label,
another key name, a bare quoted string, and server errors."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import assist_tools as A
import generator

CARD = {"name": "Mara", "description": "Mara is a courier in a rainy port. She hates being late.",
        "personality": "Dry, quick, loyal to Tomas.", "scenario": "", "structured_profile": {"with_strangers": "Curt."}}
SEEN, REPLIES = [], []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        status, content = REPLIES.pop(0)
        out = json.dumps({"choices": [{"message": {"content": content}}], "usage": {}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


@pytest.fixture(autouse=True)
def real_request(server, monkeypatch):
    monkeypatch.setattr(A, "_request", generator._request)          # undo any fake from other test files
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", server)
    monkeypatch.setattr(generator, "_RETRY_BACKOFF_SECONDS", [0, 0])
    SEEN.clear(); REPLIES.clear()


def ask(client, H, msgs, **kw):
    return client.post("/api/interview", json={"card": CARD, "provider": "local", "model": "m", "messages": msgs, **kw}, headers=H)


@pytest.mark.parametrize("content,expected", [
    ('{"reply": "Keep up, I have a drop at nine."}', "Keep up, I have a drop at nine."),
    ('```json\n{"reply": "Keep up."}\n```', "Keep up."),
    ('Mara: "Keep up. Rain waits for nobody."', "Keep up. Rain waits for nobody."),
    ('**Mara:** Keep up.', "Keep up."),
    ('*She shrugs.* Late again? Figures.', "*She shrugs.* Late again? Figures."),
    ('{"response": "Ask quick."}', "Ask quick."),
    ('"Ask quick."', "Ask quick."),
    ('Sure! {"reply": "Fine. Ask."}', "Fine. Ask."),
])
def test_interview_replies_from_real_shaped_models(client, H, content, expected):
    REPLIES.append((200, content))
    r = ask(client, H, [{"role": "user", "content": "Who are you?"}])
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["reply"] == expected


def test_what_the_model_is_sent(client, H):
    REPLIES.append((200, '{"reply": "Tomas. Who else."}'))
    msgs = [{"role": "user", "content": "Who are you?"}, {"role": "char", "content": "Mara. Courier."},
            {"role": "user", "content": "Who do you trust?"}]
    assert ask(client, H, msgs).get_json()["reply"] == "Tomas. Who else."
    sent = SEEN[-1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user"]
    sysmsg, user = sent[0]["content"], sent[1]["content"]
    assert sysmsg.startswith("You are Mara.") and "hates being late" in sysmsg and "loyal to Tomas" in sysmsg and "Curt." in sysmsg
    assert "INTERVIEWER: Who are you?\nMARA: Mara. Courier.\nINTERVIEWER: Who do you trust?" in user
    assert user.rstrip().endswith("Answer the last question as Mara.")


def test_long_chats_keep_the_last_12_turns(client, H):
    REPLIES.append((200, '{"reply": "Still here."}'))
    msgs = [{"role": "user" if i % 2 == 0 else "char", "content": f"turn {i}"} for i in range(30)] + [{"role": "user", "content": "last?"}]
    ask(client, H, msgs)
    user = SEEN[-1]["messages"][1]["content"]
    assert "turn 18" not in user and "turn 19" in user and "last?" in user


def test_check_against_notes(client, H):
    msgs = [{"role": "user", "content": "Late?"}, {"role": "char", "content": "I love being late."}]
    REPLIES.append((200, '{"issues": ["Says she loves being late; the notes say she hates it."], "verdict": "One slip."}'))
    r = ask(client, H, msgs, check=True).get_json()
    assert r["issues"] == ["Says she loves being late; the notes say she hates it."] and r["verdict"] == "One slip."
    REPLIES.append((200, '{"issues": "Says she loves being late.", "verdict": "Slip."}'))   # a string, not a list
    assert ask(client, H, msgs, check=True).get_json()["issues"] == ["Says she loves being late."]
    REPLIES.append((200, "Mostly consistent, but she claims to love being late."))       # plain text
    r = ask(client, H, msgs, check=True).get_json()
    assert r["issues"] == [] and "love being late" in r["verdict"]
    assert "NOTES:" in SEEN[-1]["messages"][1]["content"] and "INTERVIEW:" in SEEN[-1]["messages"][1]["content"]


def test_errors_are_readable(client, H):
    for _ in range(3):
        REPLIES.append((503, "{}"))                                 # provider down: 3 tries, then a clear message
    r = ask(client, H, [{"role": "user", "content": "Hi"}])
    assert r.status_code == 502 and "model call failed" in r.get_json()["error"].lower()
    REPLIES.append((200, '{"reply": ""}'))
    r = ask(client, H, [{"role": "user", "content": "Hi"}])
    assert r.status_code == 502 and "no reply" in r.get_json()["error"]


def test_trim_through_the_real_request(client, H):
    long = "Mara is a courier who knows every alley and every shortcut in the port. " * 30
    REPLIES.append((200, '{"text": "Mara, a courier, knows every alley and shortcut in the port."}'))
    r = client.post("/api/trim", json={"text": long, "target_tokens": 60, "provider": "local", "model": "m"}, headers=H).get_json()
    assert r["text"].startswith("Mara, a courier") and r["tokens_after"] < r["tokens_before"]
    REPLIES.append((200, "Mara, a courier, knows every alley in the port."))           # plain text
    r = client.post("/api/trim", json={"text": long, "target_tokens": 60, "provider": "local", "model": "m"}, headers=H).get_json()
    assert r["text"] == "Mara, a courier, knows every alley in the port."

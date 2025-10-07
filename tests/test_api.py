import os
import uuid
import sys
import pytest

from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("LLM_API_KEY", "")
@pytest.fixture()
def client(tmp_path):
    # Point DB to a writable temp path
    db_url = f"sqlite:///{tmp_path}/test.db"
    os.environ["DATABASE_URL"] = db_url
    # Import app with this DB URL
    from importlib import reload
    import app.core.config as cfg
    import app.db.database as dbmod
    import app.db.models as models
    reload(cfg)
    reload(dbmod)
    reload(models)
    import app.main as mainmod
    reload(mainmod)
    from app.main import app  # type: ignore
    with TestClient(app) as c:
        yield c



def test_root_and_health(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "app" in r.json()
    r = client.get("/health")
    assert r.status_code == 200


def test_user_crud_and_chat_flow(client, tmp_path):
    # Create user
    ext = f"test-{uuid.uuid4().hex[:8]}"
    r = client.post("/users/", json={"external_id": ext})
    assert r.status_code == 201, r.text
    user = r.json()
    user_id = user["id"]

    # List users
    r = client.get("/users/?skip=0&limit=5")
    assert r.status_code == 200
    users = r.json()
    assert any(u["id"] == user_id for u in users)

    # Get user
    r = client.get(f"/users/{user_id}")
    assert r.status_code == 200

    # Update user
    r = client.put(f"/users/{user_id}", json={"external_id": ext + "-upd"})
    assert r.status_code == 200
    assert r.json()["external_id"].endswith("-upd")

    # Create chat session
    r = client.post("/chat/sessions", json={"user_id": user_id, "title": "Test"})
    assert r.status_code == 200
    session = r.json()
    session_id = session["id"]

    # List sessions
    r = client.get(f"/chat/sessions/{user_id}")
    assert r.status_code == 200
    assert any(s["id"] == session_id for s in r.json()["sessions"])

    # History empty
    r = client.get(f"/chat/sessions/{session_id}/messages")
    assert r.status_code == 200
    assert r.json()["messages"] == []

    # Send message (uses stub LLM)
    r = client.post(f"/chat/sessions/{session_id}/messages", json={"message": "hello"})
    assert r.status_code == 200
    out = r.json()
    assert "reply" in out

    # History has two messages now
    r = client.get(f"/chat/sessions/{session_id}/messages")
    assert r.status_code == 200
    assert len(r.json()["messages"]) >= 2

    # Legacy chat without session_id
    r = client.post("/chat", json={"message": "ping"})
    assert r.status_code == 200

    # Archive session
    r = client.delete(f"/chat/sessions/{session_id}")
    assert r.status_code == 200

    # Delete user
    r = client.delete(f"/users/{user_id}")
    assert r.status_code == 200
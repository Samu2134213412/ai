"""WebSocket auth, live delivery and replay-after-reconnect."""

from __future__ import annotations

import asyncio

import pytest

from codepilot import events as E


@pytest.fixture
def session_row(client, paired, git_project, db):
    project = client.post("/api/projects",
                          json={"name": "Demo", "path": str(git_project)}).json()["project"]
    return db.create_session(id="sess-1", project_id=project["id"], prompt="do a thing",
                             status="running", model="qwen3-coder:30b",
                             permission_mode="manual")


def test_websocket_rejects_missing_credential(client):
    with client.websocket_connect("/ws") as ws:
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["code"] == "unauthorized"


def test_websocket_rejects_bad_credential(client):
    with client.websocket_connect("/ws?token=garbage") as ws:
        assert ws.receive_json()["code"] == "unauthorized"


def test_websocket_streams_live_events(client, paired, session_row, app):
    hub = app.state.hub
    with client.websocket_connect(f"/ws?token={paired}&session=sess-1") as ws:
        assert ws.receive_json()["type"] == "connected"
        assert ws.receive_json()["type"] == "replay_complete"

        ws.send_json({"action": "ping"})
        assert ws.receive_json()["type"] == "pong"

        portal = ws.portal  # starlette TestClient's anyio portal
        portal.call(hub.publish, "sess-1", E.ASSISTANT_MESSAGE, {"text": "hello"})
        event = ws.receive_json()
        assert event["type"] == "event"          # envelope
        assert event["event_type"] == E.ASSISTANT_MESSAGE
        assert event["payload"]["text"] == "hello"
        assert event["seq"] == 1


def test_replay_after_reconnect_loses_nothing(client, paired, session_row, app):
    """The phone disconnects, work continues, and it catches up on return."""
    hub = app.state.hub
    db = app.state.db

    # Events that happened while nobody was connected.
    with client.websocket_connect(f"/ws?token={paired}&session=sess-1") as ws:
        ws.receive_json(); ws.receive_json()
        portal = ws.portal
        for i in range(3):
            portal.call(hub.publish, "sess-1", E.ASSISTANT_MESSAGE, {"text": f"m{i}"})
            ws.receive_json()

    # More events with the socket closed.
    asyncio.run(_publish_offline(hub, 3))

    # Reconnect from seq 2: we must get 4, 5, 6 and nothing earlier.
    with client.websocket_connect(f"/ws?token={paired}&session=sess-1&after=2") as ws:
        assert ws.receive_json()["type"] == "connected"
        seqs = []
        while True:
            message = ws.receive_json()
            if message["type"] == "replay_complete":
                assert message["last_seq"] == 6
                break
            seqs.append(message["seq"])
        assert seqs == [3, 4, 5, 6]

    assert len(db.get_events("sess-1")) == 6


async def _publish_offline(hub, count):
    for i in range(count):
        await hub.publish("sess-1", E.TOOL_STARTED,
                          {"tool_use_id": f"t{i}", "tool_name": "Read", "input": {}})


def test_raw_events_are_hidden_unless_verbose(client, paired, session_row, app):
    hub = app.state.hub
    asyncio.run(hub.publish("sess-1", E.RAW, {"kind": "stream_event", "line": {}}))
    asyncio.run(hub.publish("sess-1", E.ASSISTANT_MESSAGE, {"text": "visible"}))

    with client.websocket_connect(f"/ws?token={paired}&session=sess-1") as ws:
        ws.receive_json()
        types = []
        while True:
            message = ws.receive_json()
            if message["type"] == "replay_complete":
                break
            types.append(message["payload"])
        assert types == [{"text": "visible"}]

    with client.websocket_connect(f"/ws?token={paired}&session=sess-1&verbose=1") as ws:
        ws.receive_json()
        count = 0
        while True:
            message = ws.receive_json()
            if message["type"] == "replay_complete":
                break
            count += 1
        assert count == 2


def test_wildcard_subscription_sees_all_sessions(client, paired, session_row, app):
    hub = app.state.hub
    with client.websocket_connect(f"/ws?token={paired}") as ws:
        assert ws.receive_json()["type"] == "connected"
        ws.portal.call(hub.publish, "sess-1", E.SESSION_STATUS, {"phase": "requesting"})
        event = ws.receive_json()
        assert event["session_id"] == "sess-1"

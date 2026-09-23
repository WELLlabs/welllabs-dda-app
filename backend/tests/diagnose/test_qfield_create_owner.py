"""QField Cloud project create must not pass login email as owner."""

from unittest.mock import MagicMock

from app.modules.diagnose.services import qfield_sync


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_create_omits_owner_when_none():
    client = MagicMock()
    client._request.return_value = _FakeResp({"id": "p1", "name": "diagnose-x"})
    out = qfield_sync._create_qfield_cloud_project(client, "diagnose-x", None)
    assert out["id"] == "p1"
    args, kwargs = client._request.call_args
    assert args[0] == "POST"
    assert "owner" not in kwargs["data"]


def test_get_or_create_skips_email_owner():
    client = MagicMock()
    client.list_projects.return_value = []
    client._request.side_effect = [
        _FakeResp({"username": "real_user"}),  # auth/user
        _FakeResp({"id": "p2", "name": "diagnose-x"}),  # create
    ]
    project = qfield_sync._get_or_create_project(
        client, "diagnose-x", owner="someone@example.com"
    )
    assert project["id"] == "p2"
    create_calls = [
        c for c in client._request.call_args_list if c.args and c.args[0] == "POST"
    ]
    assert len(create_calls) == 1
    assert "owner" not in create_calls[0].kwargs["data"]


def test_get_or_create_retries_without_owner_on_404():
    client = MagicMock()
    client.list_projects.return_value = []
    client._request.side_effect = [
        _FakeResp({"username": "real_user"}),  # auth/user
        Exception(
            'Requested "https://app.qfield.cloud/api/v1/projects/" and got "404 Not Found": '
            '{ "code": "object_not_found", "message": "Object not found" }'
        ),
        _FakeResp({"id": "p2", "name": "diagnose-Periyakulam-Theni-TN-MSSRF"}),
    ]

    project = qfield_sync._get_or_create_project(
        client,
        "diagnose-Periyakulam-Theni-TN-MSSRF",
        owner="MissingOrg",
    )
    assert project["id"] == "p2"
    create_calls = [
        c for c in client._request.call_args_list if c.args and c.args[0] == "POST"
    ]
    assert len(create_calls) == 2
    assert create_calls[0].kwargs["data"]["owner"] == "MissingOrg"
    assert "owner" not in create_calls[-1].kwargs["data"]


def test_create_error_message_explains_owner_404():
    msg = qfield_sync._qfield_create_error_message(
        "diagnose-x",
        Exception('got "404 Not Found": { "code": "object_not_found" }'),
    )
    assert "owner username" in msg.lower() or "organization" in msg.lower()
    assert "Names may contain only letters" not in msg

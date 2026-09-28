import base64
import json

import pytest
from botocore.exceptions import ClientError


def queue_messages(sqs, url):
    return sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", [])


def test_valid_command_and_redelivery(system, payload, event_factory):
    ingress, store, sqs, url, _ = system
    event = event_factory(payload)
    result = ingress.handle(event)
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["outcome"] == "queued"
    assert json.loads(ingress.handle(event)["body"])["outcome"] == "duplicate"
    messages = queue_messages(sqs, url)
    assert len(messages) == 1
    job = json.loads(messages[0]["Body"])
    assert job == {
        "delivery_id": "delivery-1",
        "installation_id": 100,
        "repo": "team/sandbox",
        "pr": 1,
        "comment_id": 200,
        "commenter": "alex",
        "command": "review",
        "args": [],
    }
    item = store.deliveries.get_item(Key={"delivery_id": "delivery-1"})["Item"]
    assert item["status"] == "queued" and item["expires_at"] == 1000 + 7 * 86400
    assert "lease_token" not in item


@pytest.mark.parametrize("change", ["bot", "issue", "edited", "text", "other_trigger", "event"])
def test_ignored_events(system, payload, event_factory, change):
    ingress, store, sqs, url, _ = system
    event_type = "issue_comment"
    if change == "bot":
        payload["sender"]["type"] = "Bot"
    elif change == "issue":
        del payload["issue"]["pull_request"]
    elif change == "edited":
        payload["action"] = "edited"
    elif change == "text":
        payload["comment"]["body"] = "hello"
    elif change == "other_trigger":
        payload["comment"]["body"] = "@bandwidth-reviewer-dev-alex review"
    else:
        event_type = "push"
    assert ingress.handle(event_factory(payload, event=event_type))["statusCode"] == 200
    assert not queue_messages(sqs, url)
    assert store.deliveries.scan()["Count"] == 0


def test_bad_signature_and_raw_body_integrity(system, payload, event_factory):
    ingress, _, sqs, url, _ = system
    event = event_factory(payload)
    event["body"] += " "
    assert ingress.handle(event)["statusCode"] == 401
    assert not queue_messages(sqs, url)


def test_base64_unicode_payload(system, payload, event_factory):
    ingress, _, _, _, _ = system
    payload["comment"]["body"] += "\nMore context: café"
    event = event_factory(payload)
    event["body"] = base64.b64encode(event["body"].encode()).decode()
    event["isBase64Encoded"] = True
    assert ingress.handle(event)["statusCode"] == 200


@pytest.mark.parametrize("body", ["{", "[]", "null"])
def test_signed_invalid_json(system, event_factory, body):
    assert system[0].handle(event_factory({}, raw=body))["statusCode"] == 400


def test_missing_delivery(system, payload, event_factory):
    event = event_factory(payload)
    del event["headers"]["X-GitHub-Delivery"]
    assert system[0].handle(event)["statusCode"] == 400


@pytest.mark.parametrize("event_type", ["installation", "installation_repositories"])
def test_installation_record_idempotent(system, event_factory, event_type):
    ingress, store, sqs, url, _ = system
    event = event_factory({"installation": {"id": 100}, "action": "created"}, event=event_type)
    assert ingress.handle(event)["statusCode"] == 200
    assert ingress.handle(event)["statusCode"] == 200
    assert store.runs.scan()["Count"] == 1
    assert not queue_messages(sqs, url)


def test_active_pending_lease_and_expired_takeover(system, payload, event_factory):
    ingress, store, sqs, url, clock = system
    state, _ = store.claim("delivery-1")
    assert state == "claimed"
    assert ingress.handle(event_factory(payload))["statusCode"] == 503
    assert not queue_messages(sqs, url)
    clock[0] += 30
    assert ingress.handle(event_factory(payload))["statusCode"] == 200
    assert len(queue_messages(sqs, url)) == 1


def test_stale_claim_cannot_complete_after_takeover(system):
    _, store, _, _, clock = system
    _, old_token = store.claim("delivery-1")
    clock[0] += 30
    _, new_token = store.claim("delivery-1")
    with pytest.raises(ClientError):
        store.complete("delivery-1", old_token, "stale-message")
    store.complete("delivery-1", new_token, "current-message")


def test_enqueue_failure_is_immediately_recoverable(system, payload, event_factory, monkeypatch):
    ingress, store, sqs, url, _ = system
    send = sqs.send_message

    def fail(**kwargs):
        raise RuntimeError("sensitive exception contents")

    monkeypatch.setattr(sqs, "send_message", fail)
    assert ingress.handle(event_factory(payload))["statusCode"] == 503
    assert (
        store.deliveries.get_item(Key={"delivery_id": "delivery-1"})["Item"]["status"] == "pending"
    )
    monkeypatch.setattr(sqs, "send_message", send)
    assert ingress.handle(event_factory(payload))["statusCode"] == 200
    assert len(queue_messages(sqs, url)) == 1


def test_crash_after_send_is_recoverable_with_same_delivery_id(
    system, payload, event_factory, monkeypatch
):
    ingress, store, sqs, url, clock = system
    complete = store.complete

    def fail(*args):
        raise RuntimeError("write failed after SQS accepted")

    monkeypatch.setattr(store, "complete", fail)
    assert ingress.handle(event_factory(payload))["statusCode"] == 503
    clock[0] += 30
    monkeypatch.setattr(store, "complete", complete)
    assert ingress.handle(event_factory(payload))["statusCode"] == 200
    messages = queue_messages(sqs, url)
    assert len(messages) == 2
    assert {json.loads(m["Body"])["delivery_id"] for m in messages} == {"delivery-1"}


def test_expired_ttl_is_not_reliant_on_background_deletion(system):
    _, store, _, _, clock = system
    _, token = store.claim("delivery-1")
    store.complete("delivery-1", token, "message")
    clock[0] += 7 * 86400
    assert store.claim("delivery-1")[0] == "claimed"


def test_logs_do_not_include_body_signature_or_secret(system, payload, event_factory, caplog):
    payload["comment"]["body"] += " --token=ghp_DO_NOT_LOG_THIS"
    event = event_factory(payload)
    assert system[0].handle(event)["statusCode"] == 200
    assert "delivery-1" in caplog.text
    assert "DO_NOT_LOG_THIS" not in caplog.text
    assert "test-secret" not in caplog.text
    assert event["headers"]["X-Hub-Signature-256"] not in caplog.text


def test_unknown_command_is_queued_for_worker(system, payload, event_factory):
    ingress, _, sqs, url, _ = system
    payload["comment"]["body"] = "@bandwidth-reviewer-dev revew --full"
    assert ingress.handle(event_factory(payload))["statusCode"] == 200
    job = json.loads(queue_messages(sqs, url)[0]["Body"])
    assert job["command"] == "revew" and job["args"] == ["--full"]

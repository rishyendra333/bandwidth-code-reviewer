import hashlib
import hmac
import json

import boto3
import pytest
from moto import mock_aws

from reviewer.ingress import Ingress
from reviewer.settings import Settings
from reviewer.storage import DeliveryStore


@pytest.fixture
def system(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-west-2")
        for name, keys in (("deliveries", ["delivery_id"]), ("runs", ["pk", "sk"])):
            ddb.create_table(
                TableName=name,
                BillingMode="PAY_PER_REQUEST",
                AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k in keys],
                KeySchema=[
                    {"AttributeName": k, "KeyType": "HASH" if i == 0 else "RANGE"}
                    for i, k in enumerate(keys)
                ],
            )
        sqs = boto3.client("sqs", region_name="us-west-2")
        url = sqs.create_queue(QueueName="review")["QueueUrl"]
        clock = [1000.0]
        store = DeliveryStore(ddb, "deliveries", "runs", clock=lambda: clock[0])
        settings = Settings(
            "@bandwidth-reviewer-dev", url, "deliveries", "runs", webhook_secret="test-secret"
        )
        yield Ingress(settings, store, sqs), store, sqs, url, clock


@pytest.fixture
def payload():
    return {
        "action": "created",
        "installation": {"id": 100},
        "repository": {"full_name": "team/sandbox"},
        "issue": {"number": 1, "pull_request": {}},
        "sender": {"type": "User"},
        "comment": {"id": 200, "body": "@bandwidth-reviewer-dev review", "user": {"login": "alex"}},
    }


@pytest.fixture
def event_factory():
    def make(payload, delivery="delivery-1", event="issue_comment", raw=None):
        body = raw if raw is not None else json.dumps(payload, ensure_ascii=False)
        signature = "sha256=" + hmac.new(b"test-secret", body.encode(), hashlib.sha256).hexdigest()
        return {
            "headers": {
                "X-GitHub-Delivery": delivery,
                "X-GitHub-Event": event,
                "X-Hub-Signature-256": signature,
            },
            "body": body,
        }

    return make

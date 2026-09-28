import argparse
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from reviewer.local import load_env
from scripts.aws_env import owner_session

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def post(
    url: str, secret: str, delivery: str, payload: dict[str, Any], valid: bool = True
) -> tuple[int, dict[str, Any]]:
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": delivery,
            "X-GitHub-Event": "issue_comment",
            "X-Hub-Signature-256": signature if valid else "bad",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


def scenarios(url: str, secret: str, trigger: str) -> str:
    delivery = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "action": "created",
        "installation": {"id": 1},
        "repository": {"full_name": "team/week1-smoke"},
        "issue": {"number": 1, "pull_request": {}},
        "sender": {"type": "User"},
        "comment": {"id": 1, "body": f"{trigger} review", "user": {"login": "week1-smoke"}},
    }
    code, body = post(url, secret, delivery, payload)
    assert (code, body["outcome"]) == (200, "queued"), (code, body)
    code, body = post(url, secret, delivery, payload)
    assert (code, body["outcome"]) == (200, "duplicate"), (code, body)
    assert post(url, secret, str(uuid.uuid4()), payload, valid=False)[0] == 401
    payload["sender"]["type"] = "Bot"
    assert post(url, secret, str(uuid.uuid4()), payload)[1]["outcome"] == "bot_sender"
    payload["sender"]["type"] = "User"
    payload["comment"]["body"] = "unrelated comment"
    assert post(url, secret, str(uuid.uuid4()), payload)[1]["outcome"] == "no_command"
    return delivery


def local() -> None:
    build = ROOT / ".build"
    build.mkdir(exist_ok=True)
    port, moto_port = free_port(), free_port()
    while moto_port == port:
        moto_port = free_port()
    secret = uuid.uuid4().hex
    env = dict(
        os.environ,
        WEBHOOK_SECRET=secret,
        TRIGGER="@week1-smoke",
        SMEE_URL="",
        BEDROCK="fake",
        INGRESS_PORT=str(port),
        MOTO_PORT=str(moto_port),
    )
    with (build / "local-e2e.log").open("w") as logs:
        process = subprocess.Popen(
            [sys.executable, "-m", "reviewer.local"], cwd=ROOT, env=env, stdout=logs, stderr=logs
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Local server exited; inspect .build/local-e2e.log")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Local startup timed out") from None
                    time.sleep(0.1)
            delivery = scenarios(f"http://127.0.0.1:{port}/webhook", secret, "@week1-smoke")
            deadline = time.monotonic() + 5
            while "stub_consumed" not in (build / "local-e2e.log").read_text():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Local worker did not consume the job")
                time.sleep(0.1)
            print(json.dumps({"outcome": "local_e2e_passed", "delivery_id": delivery}))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def aws() -> None:
    session, account = owner_session()
    outputs = json.loads((ROOT / ".build/outputs.json").read_text())
    values = {key: item["value"] for key, item in outputs.items()}
    if values["hosting_account_id"] != account or values["region"] != "us-west-2":
        raise SystemExit("Outputs do not match the hosting account and Oregon region")
    secret = session.client("secretsmanager").get_secret_value(
        SecretId=values["webhook_secret_arn"]
    )["SecretString"]
    delivery = scenarios(values["webhook_url"], secret, values["trigger"])
    item = (
        session.resource("dynamodb")
        .Table(values["deliveries_table"])
        .get_item(Key={"delivery_id": delivery}, ConsistentRead=True)["Item"]
    )
    assert item["status"] == "queued"
    sqs = session.client("sqs")
    matches: dict[str, Any] = {}
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        for message in sqs.receive_message(
            QueueUrl=values["queue_url"],
            WaitTimeSeconds=1,
            MaxNumberOfMessages=10,
            VisibilityTimeout=30,
        ).get("Messages", []):
            if json.loads(message["Body"]).get("delivery_id") == delivery:
                matches[message["MessageId"]] = message
            else:
                sqs.change_message_visibility(
                    QueueUrl=values["queue_url"],
                    ReceiptHandle=message["ReceiptHandle"],
                    VisibilityTimeout=0,
                )
    assert len(matches) == 1, "Expected one smoke-test job; inspect the delivery and queue"
    for message in matches.values():
        sqs.delete_message(QueueUrl=values["queue_url"], ReceiptHandle=message["ReceiptHandle"])
    print(
        json.dumps(
            {
                "outcome": "aws_e2e_passed",
                "delivery_id": delivery,
                "message_id": item["message_id"],
                "account_id": account,
            }
        )
    )


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["local", "aws"], default="local")
    args = parser.parse_args()
    local() if args.mode == "local" else aws()


if __name__ == "__main__":
    main()

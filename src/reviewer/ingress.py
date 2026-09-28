import base64
import hashlib
import hmac
import json
import logging
import time
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from pydantic import ValidationError

from reviewer.core.commands import parse_command
from reviewer.core.models import Job
from reviewer.settings import Settings
from reviewer.storage import DeliveryStore

logger = logging.getLogger("reviewer.ingress")
logger.setLevel(logging.INFO)


class Ingress:
    def __init__(self, settings: Settings, store: DeliveryStore, sqs: Any, secrets: Any = None):
        self.settings = settings
        self.store = store
        self.sqs = sqs
        self.secrets = secrets
        self._secret = ""
        self._secret_until = 0.0

    def secret(self) -> str:
        if self.settings.webhook_secret:
            return self.settings.webhook_secret
        if time.monotonic() >= self._secret_until:
            self._secret = self.secrets.get_secret_value(SecretId=self.settings.webhook_secret_arn)[
                "SecretString"
            ]
            if not self._secret:
                raise ValueError("Webhook secret is empty")
            self._secret_until = time.monotonic() + 300
        return self._secret

    def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        delivery = headers.get("x-github-delivery", "")
        if not isinstance(delivery, str) or not delivery or len(delivery) > 128:
            return self.response(400, "missing_delivery", "", started)
        try:
            body = event.get("body") or ""
            raw = (
                base64.b64decode(body, validate=True)
                if event.get("isBase64Encoded")
                else body.encode("utf-8")
            )
        except (ValueError, TypeError, AttributeError):
            return self.response(400, "invalid_body", delivery, started)
        try:
            signature = (
                "sha256=" + hmac.new(self.secret().encode(), raw, hashlib.sha256).hexdigest()
            )
        except Exception:
            return self.response(503, "secret_unavailable", delivery, started)
        supplied = headers.get("x-hub-signature-256", "")
        if (
            not isinstance(supplied, str)
            or not supplied.isascii()
            or not hmac.compare_digest(signature, supplied)
        ):
            return self.response(401, "invalid_signature", delivery, started)
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("Expected object")
        except (ValueError, UnicodeDecodeError):
            return self.response(400, "invalid_json", delivery, started)
        event_name = headers.get("x-github-event", "")
        if event_name in ("installation", "installation_repositories"):
            try:
                self.store.record_installation(delivery, payload, event_name)
            except (KeyError, ValueError, TypeError):
                return self.response(400, "invalid_installation", delivery, started)
            except Exception:
                return self.response(503, "installation_write_failed", delivery, started)
            return self.response(200, "installation_recorded", delivery, started)
        if event_name != "issue_comment" or payload.get("action") != "created":
            return self.response(200, "ignored_event", delivery, started)
        try:
            if "pull_request" not in payload["issue"]:
                return self.response(200, "not_a_pr", delivery, started)
            if payload["sender"]["type"] == "Bot":
                return self.response(200, "bot_sender", delivery, started)
            command = parse_command(payload["comment"]["body"], self.settings.trigger)
            if command is None:
                return self.response(200, "no_command", delivery, started)
            job = Job(
                delivery_id=delivery,
                installation_id=payload["installation"]["id"],
                repo=payload["repository"]["full_name"],
                pr=payload["issue"]["number"],
                comment_id=payload["comment"]["id"],
                commenter=payload["comment"]["user"]["login"],
                command=command.name,
                args=command.args,
            )
        except (KeyError, TypeError, ValueError, AttributeError, ValidationError):
            return self.response(400, "invalid_comment", delivery, started)
        try:
            state, token = self.store.claim(delivery)
        except Exception:
            return self.response(503, "claim_failed", delivery, started)
        if state == "queued":
            return self.response(200, "duplicate", delivery, started)
        if state == "busy":
            return self.response(503, "delivery_pending", delivery, started)
        try:
            message = self.sqs.send_message(
                QueueUrl=self.settings.queue_url, MessageBody=job.model_dump_json()
            )
        except Exception:
            try:
                self.store.release(delivery, token)
            except Exception:
                pass  # The lease expires even if release fails.
            return self.response(503, "enqueue_failed", delivery, started)
        try:
            self.store.complete(delivery, token, message["MessageId"])
        except Exception:
            return self.response(503, "completion_failed", delivery, started)
        return self.response(200, "queued", delivery, started, message_id=message["MessageId"])

    @staticmethod
    def response(
        code: int, outcome: str, delivery: str, started: float, **metadata: str
    ) -> dict[str, Any]:
        # Fixed log fields: never include payloads, signatures, secrets, args, or exception text.
        logger.info(
            json.dumps(
                {
                    "delivery_id": delivery,
                    "outcome": outcome,
                    "status": code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    **metadata,
                }
            )
        )
        return {
            "statusCode": code,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"outcome": outcome, "delivery_id": delivery, **metadata}),
        }


@lru_cache(maxsize=1)
def service() -> Ingress:
    settings = Settings.from_env()
    config = Config(
        connect_timeout=1, read_timeout=1, retries={"mode": "standard", "total_max_attempts": 1}
    )
    kwargs: dict[str, Any] = {"region_name": settings.region, "config": config}
    if settings.endpoint_url:
        kwargs.update(
            endpoint_url=settings.endpoint_url,
            aws_access_key_id="local",
            aws_secret_access_key="local",
        )
    return Ingress(
        settings,
        DeliveryStore(
            boto3.resource("dynamodb", **kwargs), settings.deliveries_table, settings.runs_table
        ),
        boto3.client("sqs", **kwargs),
        boto3.client("secretsmanager", **kwargs),
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        return service().handle(event)
    except Exception:
        return Ingress.response(503, "configuration_unavailable", "", time.monotonic())

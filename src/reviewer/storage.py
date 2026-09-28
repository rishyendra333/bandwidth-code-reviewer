import time
import uuid
from collections.abc import Callable
from typing import Any, Literal

from botocore.exceptions import ClientError


class DeliveryStore:
    def __init__(
        self, dynamodb: Any, deliveries: str, runs: str, clock: Callable[[], float] = time.time
    ):
        self.deliveries = dynamodb.Table(deliveries)
        self.runs = dynamodb.Table(runs)
        self.clock = clock

    def claim(self, delivery_id: str) -> tuple[Literal["claimed", "queued", "busy"], str]:
        now = int(self.clock())
        token = str(uuid.uuid4())
        try:
            self.deliveries.put_item(
                Item={
                    "delivery_id": delivery_id,
                    "status": "pending",
                    "lease_token": token,
                    "lease_until": now + 30,
                    "expires_at": now + 7 * 86400,
                },
                ConditionExpression=(
                    "attribute_not_exists(delivery_id) OR expires_at <= :now OR "
                    "(#status = :pending AND lease_until <= :now)"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":now": now, ":pending": "pending"},
            )
            return "claimed", token
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            item = self.deliveries.get_item(
                Key={"delivery_id": delivery_id}, ConsistentRead=True
            ).get("Item", {})
            if item.get("status") == "queued" and int(item.get("expires_at", 0)) > now:
                return "queued", ""
            return "busy", ""

    def complete(self, delivery_id: str, token: str, message_id: str) -> None:
        self.deliveries.update_item(
            Key={"delivery_id": delivery_id},
            UpdateExpression=(
                "SET #status = :queued, message_id = :message, queued_at = :now "
                "REMOVE lease_until, lease_token"
            ),
            ConditionExpression="lease_token = :token AND #status = :pending",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":queued": "queued",
                ":pending": "pending",
                ":token": token,
                ":message": message_id,
                ":now": int(self.clock()),
            },
        )

    def release(self, delivery_id: str, token: str) -> None:
        self.deliveries.update_item(
            Key={"delivery_id": delivery_id},
            UpdateExpression="SET lease_until = :now",
            ConditionExpression="lease_token = :token AND #status = :pending",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":now": int(self.clock()),
                ":token": token,
                ":pending": "pending",
            },
        )

    def record_installation(self, delivery_id: str, payload: dict[str, Any], event: str) -> None:
        installation_id = int(payload["installation"]["id"])
        try:
            self.runs.put_item(
                Item={
                    "pk": f"INSTALLATION#{installation_id}",
                    "sk": f"EVENT#{delivery_id}",
                    "event": event,
                    "action": str(payload.get("action", "")),
                    "installation_id": installation_id,
                    "created_at": int(self.clock()),
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

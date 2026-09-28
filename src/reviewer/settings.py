import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    trigger: str
    queue_url: str
    deliveries_table: str
    runs_table: str
    webhook_secret_arn: str = ""
    webhook_secret: str = ""
    region: str = "us-west-2"
    endpoint_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            trigger=os.environ.get("TRIGGER", "@bandwidth-reviewer-dev"),
            queue_url=os.environ["QUEUE_URL"],
            deliveries_table=os.environ["DELIVERIES_TABLE"],
            runs_table=os.environ["RUNS_TABLE"],
            webhook_secret_arn=os.environ.get("WEBHOOK_SECRET_ARN", ""),
            webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
            region=os.environ.get("AWS_REGION", "us-west-2"),
            endpoint_url=os.environ.get("AWS_ENDPOINT_URL"),
        )

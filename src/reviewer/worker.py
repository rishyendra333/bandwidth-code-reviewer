import json
import logging
from typing import Any

from reviewer.core.models import Job

logger = logging.getLogger("reviewer.worker")


def consume_stub(body: str) -> dict[str, Any]:
    job = Job.model_validate_json(body)
    result = {
        "delivery_id": job.delivery_id,
        "repo": job.repo,
        "pr": job.pr,
        "outcome": "stub_consumed",
        "bedrock": "fake",
    }
    logger.info(json.dumps(result))
    return result

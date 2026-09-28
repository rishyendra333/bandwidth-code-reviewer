import json
import os

from reviewer.local import load_env
from scripts.aws_env import owner_session


def main() -> None:
    load_env()
    if os.environ.get("BEDROCK_APPROVED", "false").lower() != "true":
        raise SystemExit("Bedrock is gated: record Bandwidth model/region approval first")
    model = os.environ.get("BEDROCK_MODEL_ID", "")
    if not model:
        raise SystemExit("Set the approved BEDROCK_MODEL_ID or inference profile ID")
    session, _ = owner_session()
    result = session.client("bedrock-runtime").converse(
        modelId=model,
        messages=[{"role": "user", "content": [{"text": "Reply with OK."}]}],
        inferenceConfig={"maxTokens": 8, "temperature": 0},
    )
    print(json.dumps({"outcome": "bedrock_access_verified", "usage": result.get("usage", {})}))


if __name__ == "__main__":
    main()

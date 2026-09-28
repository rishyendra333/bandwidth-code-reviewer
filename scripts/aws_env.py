import os
import re
from typing import Any

import boto3

from reviewer.local import load_env


def hosting_account() -> str:
    load_env()
    account = os.environ.get("HOSTING_ACCOUNT_ID", "")
    if not re.fullmatch(r"[0-9]{12}", account):
        raise SystemExit("Set HOSTING_ACCOUNT_ID to your 12-digit hosting account ID in .env")
    if os.environ.get("AWS_REGION", "us-west-2") != "us-west-2":
        raise SystemExit("This development deployment is restricted to us-west-2")
    return account


def owner_session() -> tuple[Any, str]:
    account = hosting_account()
    session = boto3.Session(
        profile_name=os.environ.get("AWS_PROFILE", "default"), region_name="us-west-2"
    )
    identity = session.client("sts").get_caller_identity()
    if identity["Account"] != account:
        raise SystemExit("AWS profile points to a different account; no deployment was performed")
    return session, account

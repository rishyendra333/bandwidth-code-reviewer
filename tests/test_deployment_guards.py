from unittest.mock import Mock

import pytest

from scripts import aws_env, bedrock_smoke, deploy


def test_wrong_account_stops_before_deployment(monkeypatch):
    monkeypatch.setenv("HOSTING_ACCOUNT_ID", "516647891652")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    fake_session = Mock()
    fake_session.client.return_value.get_caller_identity.return_value = {"Account": "111122223333"}
    monkeypatch.setattr(aws_env.boto3, "Session", lambda **kwargs: fake_session)
    with pytest.raises(SystemExit, match="different account"):
        aws_env.owner_session()


def test_wrong_region_stops_before_aws_calls(monkeypatch):
    monkeypatch.setenv("HOSTING_ACCOUNT_ID", "516647891652")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    with pytest.raises(SystemExit, match="us-west-2"):
        aws_env.hosting_account()


def test_bedrock_blocked_without_approval(monkeypatch):
    monkeypatch.setenv("BEDROCK_APPROVED", "false")
    monkeypatch.setattr(
        bedrock_smoke, "owner_session", lambda: pytest.fail("AWS must not be called")
    )
    with pytest.raises(SystemExit, match="gated"):
        bedrock_smoke.main()


def test_changed_package_rejects_saved_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy, "BUILD", tmp_path)
    monkeypatch.setattr(deploy, "commit", lambda: "reviewed-commit")
    (tmp_path / "dev.tfplan").write_bytes(b"saved-plan")
    (tmp_path / "ingress.zip").write_bytes(b"original-package")
    deploy.write_receipt("dev", "516647891652")
    deploy.check_receipt("dev", "516647891652")
    (tmp_path / "ingress.zip").write_bytes(b"changed-package")
    with pytest.raises(SystemExit, match="package changed"):
        deploy.check_receipt("dev", "516647891652")

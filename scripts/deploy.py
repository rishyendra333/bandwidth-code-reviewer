import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from scripts.aws_env import owner_session
from scripts.build_lambda import main as build_lambda

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".build"
TF = os.environ.get("TERRAFORM", "terraform")


def run_tf(folder: str, *args: str) -> None:
    subprocess.run([TF, f"-chdir={ROOT / 'infra' / folder}", *args], check=True)


def backend_file(account: str, folder: str) -> Path:
    path = BUILD / f"{folder}-backend.hcl"
    path.write_text(
        f'bucket = "bandwidth-reviewer-tfstate-{account}-us-west-2"\n'
        f'key = "{folder}/terraform.tfstate"\nregion = "us-west-2"\n'
        f'use_lockfile = true\nallowed_account_ids = ["{account}"]\n'
    )
    return path


def commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def require_reviewed_tree() -> None:
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if status.strip():
        raise SystemExit("Commit reviewed changes before planning/deploying the shared environment")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_receipt(folder: str, account: str) -> None:
    receipt = {
        "account_id": account,
        "region": "us-west-2",
        "git_commit": commit(),
        "plan_sha256": digest(BUILD / f"{folder}.tfplan"),
    }
    if folder == "dev":
        receipt["zip_sha256"] = digest(BUILD / "ingress.zip")
    (BUILD / f"{folder}-plan.json").write_text(json.dumps(receipt, indent=2) + "\n")


def check_receipt(folder: str, account: str) -> None:
    path = BUILD / f"{folder}-plan.json"
    if not path.exists():
        raise SystemExit("Create and review a saved plan first")
    receipt = json.loads(path.read_text())
    if (
        receipt["account_id"] != account
        or receipt["region"] != "us-west-2"
        or receipt["git_commit"] != commit()
        or receipt["plan_sha256"] != digest(BUILD / f"{folder}.tfplan")
    ):
        raise SystemExit("Plan no longer matches the account or reviewed commit; create a new plan")
    if folder == "dev" and receipt["zip_sha256"] != digest(BUILD / "ingress.zip"):
        raise SystemExit("Lambda package changed after planning; create a new plan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["bootstrap-plan", "bootstrap-apply", "plan", "apply", "outputs"]
    )
    args = parser.parse_args()
    session, account = owner_session()
    BUILD.mkdir(exist_ok=True)
    if args.action == "outputs":
        result = subprocess.check_output(
            [TF, f"-chdir={ROOT / 'infra/dev'}", "output", "-json"], text=True
        )
        (BUILD / "outputs.json").write_text(result)
        print("Wrote .build/outputs.json (resource identifiers only)")
        return
    require_reviewed_tree()
    if args.action.startswith("bootstrap"):
        remote = ROOT / "infra/bootstrap/backend.tf"
        if args.action == "bootstrap-plan":
            exists = False
            try:
                session.client("s3").head_bucket(
                    Bucket=f"bandwidth-reviewer-tfstate-{account}-us-west-2"
                )
                exists = True
            except Exception as exc:
                code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
                if code not in ("404", "NoSuchBucket", "NotFound"):
                    raise SystemExit(
                        "Cannot determine state-bucket access; check owner permissions"
                    ) from None
            if exists:
                remote.write_text('terraform {\n  backend "s3" {}\n}\n')
                backend = backend_file(account, "bootstrap")
                run_tf("bootstrap", "init", "-input=false", f"-backend-config={backend}")
            else:
                if remote.exists():
                    raise SystemExit(
                        "Remote backend configured but bucket missing; investigate state"
                    )
                run_tf("bootstrap", "init", "-input=false")
            run_tf("bootstrap", "validate")
            run_tf(
                "bootstrap",
                "plan",
                f"-var=hosting_account_id={account}",
                f"-out={BUILD / 'bootstrap.tfplan'}",
            )
            write_receipt("bootstrap", account)
        else:
            check_receipt("bootstrap", account)
            run_tf("bootstrap", "apply", str(BUILD / "bootstrap.tfplan"))
            if not remote.exists():
                remote.write_text('terraform {\n  backend "s3" {}\n}\n')
                backend = backend_file(account, "bootstrap")
                run_tf("bootstrap", "init", "-migrate-state", f"-backend-config={backend}")
            print("Bootstrap state is now remote; retain state backups until verified")
        return
    if args.action == "plan":
        variables = ROOT / "infra/dev/dev.tfvars"
        if not variables.exists():
            raise SystemExit(
                "Copy infra/dev/dev.tfvars.example to dev.tfvars and configure identities"
            )
        build_lambda()
        backend = backend_file(account, "dev")
        run_tf("dev", "init", "-input=false", f"-backend-config={backend}")
        run_tf("dev", "validate")
        run_tf(
            "dev",
            "plan",
            "-var-file=dev.tfvars",
            f"-var=hosting_account_id={account}",
            f"-out={BUILD / 'dev.tfplan'}",
        )
        write_receipt("dev", account)
        print("Review this saved plan, then run make deploy")
    elif args.action == "apply":
        check_receipt("dev", account)
        run_tf("dev", "apply", str(BUILD / "dev.tfplan"))
        result = subprocess.check_output(
            [TF, f"-chdir={ROOT / 'infra/dev'}", "output", "-json"], text=True
        )
        (BUILD / "outputs.json").write_text(result)
        receipt = json.loads((BUILD / "dev-plan.json").read_text())
        receipt["outputs"] = {k: v["value"] for k, v in json.loads(result).items()}
        (BUILD / "deployment.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print("Applied saved plan; outputs and deployment receipt are in .build/")
        print("Populate the webhook secret, then make e2e MODE=aws; see INSTALL.md")


if __name__ == "__main__":
    main()

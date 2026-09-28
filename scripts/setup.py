import argparse
import re
import shutil
import subprocess
import sys

TOOLS = {
    "git": "brew install git",
    "rg": "brew install ripgrep",
    "docker": "Install Docker Desktop: https://docs.docker.com/desktop/setup/install/mac-install/",
    "node": "brew install node",
    "uv": "brew install uv",
    "aws": "brew install awscli (AWS CLI >= 2.32.0)",
    "terraform": "Install Terraform >= 1.10: https://developer.hashicorp.com/terraform/install",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args()
    required = set(TOOLS) - ({"aws", "terraform"} if args.local_only else set())
    missing = [tool for tool in sorted(required) if not shutil.which(tool)]
    if sys.version_info[:2] != (3, 12):
        print("Python 3.12 required: brew install python@3.12")
        raise SystemExit(1)
    for tool in missing:
        print(f"Missing {tool}: {TOOLS[tool]}")
    if missing:
        raise SystemExit(1)
    if not args.local_only:
        for tool, minimum in (("aws", (2, 32, 0)), ("terraform", (1, 10, 0))):
            text = subprocess.check_output([tool, "--version"], text=True)
            match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
            version = tuple(map(int, match.groups())) if match else (0, 0, 0)
            if version < minimum or (tool == "terraform" and version[0] != 1):
                raise SystemExit(f"Unsupported {tool} version. {TOOLS[tool]}")
    subprocess.run(["uv", "sync", "--frozen"], check=True)
    subprocess.run(["npm", "ci", "--ignore-scripts"], check=True)
    subprocess.run(["uv", "run", "pre-commit", "install"], check=True)
    print("Setup complete. Copy .env.example to .env, set your trigger and secret, then make dev.")


if __name__ == "__main__":
    main()

import os
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    terraform = os.environ.get("TERRAFORM", "terraform")
    # Mock Terraform applies never contact AWS. Their local package fixture is temporary.
    package = ROOT / ".build/ingress.zip"
    package.parent.mkdir(exist_ok=True)
    created = not package.exists()
    if created:
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("handler.py", "# Terraform mock-test fixture; not deployable\n")
    try:
        for folder in ("bootstrap", "dev"):
            subprocess.run([terraform, f"-chdir={ROOT / 'infra' / folder}", "test"], check=True)
    finally:
        if created:
            package.unlink()


if __name__ == "__main__":
    main()

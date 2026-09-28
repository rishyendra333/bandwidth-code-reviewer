import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    build = ROOT / ".build"
    build.mkdir(exist_ok=True)
    with (build / "requirements.txt").open("w") as requirements:
        subprocess.run(
            ["uv", "export", "--frozen", "--no-dev", "--no-emit-project"],
            cwd=ROOT,
            stdout=requirements,
            check=True,
        )
    script = (
        "import pathlib,shutil,subprocess,zipfile; "
        "target=pathlib.Path('/asset/package'); "
        "shutil.rmtree(target,ignore_errors=True); target.mkdir(); "
        "subprocess.run(['python','-m','pip','install','--require-hashes','-r',"
        "'/asset/requirements.txt','--target',str(target)],check=True); "
        "shutil.copytree('/project/src/reviewer',target/'reviewer',dirs_exist_ok=True); "
        "shutil.copy('/project/functions/ingress/handler.py',target/'handler.py'); "
        "archive=zipfile.ZipFile('/asset/ingress.zip','w',zipfile.ZIP_DEFLATED); "
        "files=[p for p in sorted(target.rglob('*')) "
        "if p.is_file() and '__pycache__' not in p.parts]; "
        'exec("for p in files:\\n'
        " info=zipfile.ZipInfo(str(p.relative_to(target)),(1980,1,1,0,0,0))\\n"
        " info.compress_type=zipfile.ZIP_DEFLATED\\n"
        " info.external_attr=0o644 << 16\\n"
        ' archive.writestr(info,p.read_bytes())"); archive.close()'
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/amd64",
            "--entrypoint",
            "python",
            "-v",
            f"{ROOT}:/project:ro",
            "-v",
            f"{build}:/asset",
            "public.ecr.aws/lambda/python:3.12",
            "-c",
            script,
        ],
        check=True,
    )
    print("Built .build/ingress.zip for Linux x86_64 / Python 3.12")


if __name__ == "__main__":
    main()

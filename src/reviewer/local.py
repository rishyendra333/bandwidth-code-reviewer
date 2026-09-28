import base64
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import boto3

from reviewer.ingress import lambda_handler, service
from reviewer.worker import consume_stub


def load_env(path: Path = Path(".env")) -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if sep:
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


class Adapter(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/webhook":
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if size < 0 or size > 2 * 1024 * 1024:
            self.send_error(413)
            return
        raw = self.rfile.read(size)
        result = lambda_handler(
            {
                "body": base64.b64encode(raw).decode(),
                "isBase64Encoded": True,
                "headers": dict(self.headers),
            },
            None,
        )
        body = result["body"].encode()
        self.send_response(result["statusCode"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass  # Ingress already logs safe correlation fields.


def poll_worker(sqs: Any, queue_url: str, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            messages = sqs.receive_message(QueueUrl=queue_url, WaitTimeSeconds=1).get(
                "Messages", []
            )
            for message in messages:
                consume_stub(message["Body"])
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
        except Exception:
            logging.getLogger("reviewer.local").warning("local_worker_poll_failed")
            stop.wait(1)


def main() -> None:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not os.environ.get("WEBHOOK_SECRET"):
        raise SystemExit("Set WEBHOOK_SECRET in your ignored .env before running make dev")
    if os.environ.get("BEDROCK", "fake") != "fake":
        raise SystemExit("Week 1 worker is a fake client; use make bedrock-smoke after approval")
    port = int(os.environ.get("MOTO_PORT", "5001"))
    ingress_port = int(os.environ.get("INGRESS_PORT", "8000"))
    endpoint = f"http://127.0.0.1:{port}"
    children: list[subprocess.Popen[Any]] = []
    stop = threading.Event()
    server = None
    try:
        children.append(
            subprocess.Popen(
                [sys.executable, "-m", "moto.server", "-H", "127.0.0.1", "-p", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        deadline = time.monotonic() + 10
        while True:
            if children[0].poll() is not None:
                raise RuntimeError("Moto failed to start; check MOTO_PORT")
            try:
                with urllib.request.urlopen(endpoint, timeout=0.5):
                    break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() > deadline:
                    raise RuntimeError("Moto startup timed out") from None
                time.sleep(0.1)
        kwargs = {
            "region_name": "us-west-2",
            "endpoint_url": endpoint,
            "aws_access_key_id": "local",
            "aws_secret_access_key": "local",
        }
        ddb = boto3.client("dynamodb", **kwargs)
        for name, keys in (("local-deliveries", ["delivery_id"]), ("local-runs", ["pk", "sk"])):
            ddb.create_table(
                TableName=name,
                BillingMode="PAY_PER_REQUEST",
                AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k in keys],
                KeySchema=[
                    {"AttributeName": k, "KeyType": "HASH" if i == 0 else "RANGE"}
                    for i, k in enumerate(keys)
                ],
            )
        sqs = boto3.client("sqs", **kwargs)
        queue = sqs.create_queue(QueueName="local-review-jobs")["QueueUrl"]
        os.environ.update(
            AWS_ENDPOINT_URL=endpoint,
            AWS_REGION="us-west-2",
            QUEUE_URL=queue,
            DELIVERIES_TABLE="local-deliveries",
            RUNS_TABLE="local-runs",
        )
        service.cache_clear()
        server = ThreadingHTTPServer(("127.0.0.1", ingress_port), Adapter)
        threading.Thread(target=poll_worker, args=(sqs, queue, stop), daemon=True).start()
        smee = os.environ.get("SMEE_URL", "")
        if smee:
            executable = Path("node_modules/.bin/smee")
            if not executable.exists():
                raise RuntimeError("Run npm ci to install the pinned smee client")
            children.append(
                subprocess.Popen(
                    [
                        str(executable),
                        "--url",
                        smee,
                        "--target",
                        f"http://127.0.0.1:{ingress_port}/webhook",
                    ]
                )
            )
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        logging.info(
            json.dumps(
                {
                    "outcome": "local_ready",
                    "port": ingress_port,
                    "smee": bool(smee),
                    "bedrock": "fake",
                }
            )
        )
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if server:
            server.server_close()
        for child in reversed(children):
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()

"""Build, inspect, smoke-test, and stop the image using only Python's standard library."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import uuid

PROJECT = Path(__file__).resolve().parents[1]


def docker(*arguments, capture=True, timeout=60):
    """Pass separate arguments to Docker; never construct a shell command."""
    result = subprocess.run(
        ["docker", *arguments], cwd=PROJECT, check=True, text=True,
        capture_output=capture, timeout=timeout,
    )
    return result.stdout.strip() if capture else ""


def inspect_container(container):
    return json.loads(docker("inspect", container))[0]


def fetch(base_url, path):
    """Keep HTTP error responses available so status and JSON can be checked."""
    try:
        response = urlopen(base_url + path, timeout=35)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read(), response.headers


def check(condition, message):
    if not condition:
        raise RuntimeError("Check failed: " + message)
    print("PASS:", message, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Also require a real GitHub response for octocat.")
    parser.add_argument("--image", default="gist-api:local", help="Name for the locally built image.")
    args = parser.parse_args()
    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "image": args.image, "live_github_requested": args.live, "passed": False}
    container = None
    try:
        if shutil.which("docker") is None:
            raise RuntimeError("Docker CLI was not found. Install/start Docker Desktop, then rerun this check.")
        docker("info", timeout=20)
        print("Building the image; the Dockerfile also runs every automated test...", flush=True)
        docker("build", "--pull", "-t", args.image, ".", capture=False, timeout=600)
        image = json.loads(docker("image", "inspect", args.image))[0]
        report.update(image_id=image["Id"], image_size_bytes=image["Size"],
                      architecture=image["Architecture"])
        print(f"Image size: {image['Size'] / 1024 / 1024:.1f} MiB (local, uncompressed)")
        check(image["Config"]["User"] == "10001:10001", "Image defaults to a non-root user")
        runtime_check = (
            "import importlib.util, os; from pathlib import Path; "
            "assert os.geteuid() == 10001; "
            "assert Path('/app/app.py').stat().st_uid == 0; "
            "assert not os.access('/app/app.py', os.W_OK); "
            "assert importlib.util.find_spec('pip') is None; "
            "assert not Path('/app/tests').exists(); "
            "assert not Path('/app/docs').exists()"
        )
        docker("run", "--rm", "--read-only", "--entrypoint", "python", args.image, "-c", runtime_check)
        check(True, "Application files are root-owned/read-only; tests, docs and duplicate pip are absent")

        arguments = ["run", "-d", "--name", "gist-api-check-" + uuid.uuid4().hex[:10],
                     "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,mode=1777",
                     "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                     "--pids-limit", "128", "--memory", "256m", "--cpus", "1",
                     "--publish", "127.0.0.1::8080"]
        if os.getenv("GITHUB_TOKEN"):
            arguments += ["--env", "GITHUB_TOKEN"]
        container = docker(*arguments, args.image)
        state = inspect_container(container)
        port = state["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostPort"]
        base_url = "http://127.0.0.1:" + port
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            state = inspect_container(container)["State"]
            if not state["Running"]:
                raise RuntimeError("Container stopped during startup.")
            if state.get("Health", {}).get("Status") == "healthy":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Docker health check did not become healthy within 60 seconds.")
        check(True, "Docker marks the container healthy with a read-only root filesystem")
        status, body, _ = fetch(base_url, "/_health")
        check(status == 200 and json.loads(body) == {"status": "ok"}, "Health endpoint returns 200 and expected JSON")
        status, body, _ = fetch(base_url, "/")
        check(status == 200 and b"GitHub username" in body, "Browser search page is available")
        status, body, headers = fetch(base_url, "/static/style.css")
        check(status == 200 and "text/css" in headers.get("Content-Type", ""), "Browser stylesheet is included")
        status, body, _ = fetch(base_url, "/bad_name")
        check(status == 400 and "error" in json.loads(body), "Invalid username returns a JSON 400")
        if args.live:
            status, body, _ = fetch(base_url, "/octocat")
            data = json.loads(body)
            check(status == 200 and isinstance(data, list)
                  and all(isinstance(item, dict) and item.get("public") is True for item in data),
                  f"Real GitHub request for octocat succeeds (HTTP {status})")
            report["live_github_gist_count"] = len(data)
        report["runtime_stats"] = json.loads(docker("stats", "--no-stream", "--format", "{{json .}}", container))
        docker("stop", "--time", "30", container, timeout=40)
        state = inspect_container(container)["State"]
        report["exit_code"] = state["ExitCode"]
        check(state["ExitCode"] == 0 and not state["OOMKilled"], "SIGTERM stops the server cleanly with exit code 0")
        report["passed"] = True
    except (OSError, RuntimeError, ValueError, URLError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
        print("FAIL:", error, file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        if container:
            try:
                docker("logs", container, capture=False)
            except subprocess.SubprocessError:
                pass
    finally:
        if container:
            try:
                docker("rm", "-f", container)
            except subprocess.SubprocessError:
                pass
        report_path = PROJECT / "container-report.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print("Report:", report_path)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

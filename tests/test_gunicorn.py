"""Run the actual container server program, without needing Docker or GitHub."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen


@unittest.skipUnless(os.name == "posix", "Gunicorn requires a Unix-like system; Docker uses Linux.")
class GunicornTests(unittest.TestCase):
    def test_real_gunicorn_serves_concurrent_requests_and_stops_cleanly(self):
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        with tempfile.TemporaryFile(mode="w+") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "gunicorn", "--config", "gunicorn.conf.py",
                 "--bind", f"127.0.0.1:{port}", "tests.gunicorn_fixture:app"],
                cwd=Path(__file__).resolve().parents[1], stdout=log, stderr=log,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        log.seek(0)
                        self.fail("Gunicorn exited before accepting requests:\n" + log.read())
                    try:
                        with urlopen(base + "/_health", timeout=1) as response:
                            self.assertEqual(json.load(response), {"status": "ok"})
                        break
                    except (OSError, URLError):
                        time.sleep(0.05)
                else:
                    self.fail("Gunicorn did not start within 10 seconds.")

                def fetch_gists(_):
                    with urlopen(base + "/octocat?token=do-not-log", timeout=5) as response:
                        return response.status, json.load(response)

                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(fetch_gists, range(16)))
                self.assertTrue(all(status == 200 and data[0]["id"] == "socket-example"
                                    and data[0]["public"] for status, data in results))
                with urlopen(base + "/?username=octocat", timeout=5) as response:
                    self.assertIn("A controlled HTTP example", response.read().decode())
                with urlopen(base + "/static/style.css", timeout=5) as response:
                    self.assertEqual(response.headers.get_content_type(), "text/css")
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=10), 0)
                log.seek(0)
                text = log.read()
                self.assertNotIn("do-not-log", text)
                self.assertNotIn("Traceback", text)
                self.assertIn("gthread", text)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)

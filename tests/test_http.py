"""A real local HTTP socket test, with a controlled GitHub boundary."""

import json
import threading
import unittest
from urllib.request import urlopen

from werkzeug.serving import make_server

from tests.helpers import github_response, make_app


class HttpServerTests(unittest.TestCase):
    def test_running_server_returns_health_json_and_readable_html(self):
        app, session, _ = make_app()
        expected = [{"id": "local-example", "public": True, "description": "Local HTTP example"}]
        session.get.return_value = github_response(expected)
        server = make_server("127.0.0.1", 0, app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/_health", timeout=3) as response:
                self.assertEqual(json.load(response), {"status": "ok"})
            session.get.assert_not_called()
            with urlopen(base + "/octocat", timeout=3) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get_content_type(), "application/json")
                self.assertEqual(json.load(response), expected)
            with urlopen(base + "/?username=octocat", timeout=3) as response:
                self.assertEqual(response.headers.get_content_type(), "text/html")
                self.assertIn("Local HTTP example", response.read().decode())
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()
        self.assertFalse(thread.is_alive())

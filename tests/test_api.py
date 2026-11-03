"""Check the public HTTP contract, readable page, and safe presentation."""

import unittest

import requests

from app import prepare_gists_for_display
from tests.helpers import github_response, make_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app, self.session, self.factory = make_app()
        self.client = self.app.test_client()

    def test_octocat_returns_a_meaningful_json_list(self):
        expected = [{"id": "example123", "public": True, "description": "A Python example"}]
        self.session.get.return_value = github_response(expected)
        response = self.client.get("/octocat", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(response.get_json(), expected)
        self.assertIn(b'\n  {', response.data)

    def test_health_is_local_and_does_not_call_github(self):
        response = self.client.get("/_health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})
        self.factory.assert_not_called()

    def test_home_and_favicon_do_not_call_github(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("GitHub username", response.get_data(as_text=True))
        self.assertEqual(self.client.get("/favicon.ico").status_code, 204)
        self.factory.assert_not_called()

    def test_browser_page_has_readable_fields_and_a_json_link(self):
        self.session.get.return_value = github_response([{
            "id": "example123", "public": True, "description": "A Python example",
            "files": {"hello.py": {"language": "Python"}},
            "updated_at": "2026-11-02T10:00:00Z",
            "html_url": "https://gist.github.com/octocat/example123",
            "owner": {"organizations_url": "unnecessary internal detail"},
        }])
        response = self.client.get("/", query_string={"username": " octocat "})
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        for value in ("1 public Gist", "A Python example", "hello.py", "Python",
                      "2026-11-02", "https://gist.github.com/octocat/example123", 'href="/octocat"'):
            self.assertIn(value, html)
        self.assertNotIn("unnecessary internal detail", html)

    def test_empty_list_has_a_useful_browser_message(self):
        self.assertIn("No public Gists found.",
                      self.client.get("/?username=octocat").get_data(as_text=True))
        self.assertEqual(self.client.get("/octocat").get_json(), [])

    def test_missing_or_malformed_optional_fields_do_not_break_the_page(self):
        for optional in ({}, {"description": None, "files": None},
                         {"files": ["unexpected"], "updated_at": 123, "html_url": 123},
                         {"files": {"notes.txt": None}, "updated_at": "bad-date"}):
            with self.subTest(optional=optional):
                self.session.get.return_value = github_response([{"id": "a", "public": True, **optional}])
                response = self.client.get("/?username=octocat")
                self.assertEqual(response.status_code, 200)
                self.assertIn("No description provided", response.get_data(as_text=True))

    def test_api_error_mappings_and_browser_error_messages(self):
        for upstream, expected in ((404, 404), (403, 503), (429, 503), (500, 502)):
            with self.subTest(upstream=upstream):
                self.session.get.return_value = github_response({}, status=upstream)
                api = self.client.get("/octocat")
                browser = self.client.get("/?username=octocat")
                self.assertEqual(api.status_code, expected)
                self.assertIn("error", api.get_json())
                self.assertEqual(browser.status_code, expected)
                self.assertIn('role="alert"', browser.get_data(as_text=True))

    def test_invalid_input_is_rejected_by_both_routes(self):
        for url in ("/bad_name", "/?username=bad_name"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 400)
        self.factory.assert_not_called()

    def test_timeout_is_a_safe_504_in_both_formats(self):
        self.session.get.side_effect = requests.Timeout("do not expose this")
        for url in ("/octocat", "/?username=octocat"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 504)
            self.assertNotIn("do not expose this", response.get_data(as_text=True))

    def test_rate_limit_wait_is_forwarded_in_both_formats(self):
        self.session.get.return_value = github_response({}, status=429, headers={"Retry-After": "60"})
        for url in ("/octocat", "/?username=octocat"):
            self.assertEqual(self.client.get(url).headers["Retry-After"], "60")

    def test_html_is_escaped_and_unsafe_links_are_removed(self):
        for url in ("javascript:alert(1)", "https://gist.github.com.attacker.example/a",
                    "https://gist.github.com@attacker.example/a", "https://[bad"):
            with self.subTest(url=url):
                self.session.get.return_value = github_response([{
                    "id": "a", "public": True, "description": "<script>alert(1)</script>",
                    "files": {"<img onerror=alert(1)>": {}}, "html_url": url,
                }])
                html = self.client.get("/?username=octocat").get_data(as_text=True)
                self.assertIn("&lt;script&gt;", html)
                self.assertIn("&lt;img onerror=alert(1)&gt;", html)
                self.assertNotIn('class="open-link"', html)

    def test_normalizing_for_the_page_does_not_change_api_data(self):
        original = [{"id": "a", "public": True, "description": None}]
        rows = prepare_gists_for_display(original)
        self.assertEqual(rows[0]["description"], "No description provided")
        self.assertIsNone(original[0]["description"])

    def test_css_is_served_and_security_headers_allow_it(self):
        response = self.client.get("/static/style.css")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/css")
        self.assertIn("style-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.factory.assert_not_called()

    def test_unknown_paths_and_methods_return_json_with_http_headers_preserved(self):
        response = self.client.get("/not/a/route")
        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.get_json())
        response = self.client.post("/octocat")
        self.assertEqual(response.status_code, 405)
        self.assertIn("GET", response.headers["Allow"])
        self.factory.assert_not_called()

    def test_logs_have_status_and_duration_but_omit_query_strings(self):
        with self.assertLogs("app", level="INFO") as captured:
            self.client.get("/?username=octocat&token=do-not-log")
        log = "\n".join(captured.output)
        self.assertIn("status=200", log)
        self.assertIn("duration_ms=", log)
        self.assertNotIn("do-not-log", log)

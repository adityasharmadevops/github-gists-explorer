"""Exercise pagination, failures, credentials, cleanup, and time limits."""

import unittest
from unittest.mock import Mock

import requests

from github_client import GITHUB_HEADERS, GitHubError, is_valid_username
from settings import Settings
from tests.helpers import github_response, make_client


class GitHubClientTests(unittest.TestCase):
    def test_octocat_uses_the_real_endpoint_and_safe_request_options(self):
        client, session, factory = make_client()
        expected = [{"id": "example123", "public": True}]
        session.get.return_value = github_response(expected)
        self.assertEqual(client.fetch_public_gists("octocat"), expected)
        session.get.assert_called_once_with(
            "https://api.github.com/users/octocat/gists",
            params={"per_page": 100, "page": 1},
            timeout=(3, 5), allow_redirects=False,
        )
        self.assertEqual(session.headers, GITHUB_HEADERS)
        factory.assert_called_once_with()
        session.__exit__.assert_called_once()

    def test_another_username_is_not_hardcoded(self):
        client, session, _ = make_client()
        client.fetch_public_gists("another-user")
        self.assertEqual(session.get.call_args.args[0],
                         "https://api.github.com/users/another-user/gists")

    def test_pages_are_combined_using_one_session(self):
        client, session, factory = make_client()
        first = [{"id": "first", "public": True}]
        second = [{"id": "second", "public": True}]
        session.get.side_effect = [github_response(first, has_next_page=True), github_response(second)]
        self.assertEqual(client.fetch_public_gists("octocat"), first + second)
        self.assertEqual(session.get.call_args_list[1].kwargs["params"]["page"], 2)
        factory.assert_called_once_with()

    def test_a_next_link_cannot_redirect_credentials_to_another_host(self):
        client, session, _ = make_client(Settings(github_token="test-secret"))
        first = github_response([], has_next_page=True)
        first.headers["Link"] = '<https://attacker.example/steal>; rel="next"'
        session.get.side_effect = [first, github_response([])]
        client.fetch_public_gists("octocat")
        self.assertTrue(all(call.args[0].startswith("https://api.github.com/users/")
                            for call in session.get.call_args_list))

    def test_empty_list_is_successful(self):
        client, _, _ = make_client()
        self.assertEqual(client.fetch_public_gists("octocat"), [])

    def test_private_gists_are_filtered_even_when_a_token_is_set(self):
        client, session, _ = make_client(Settings(github_token="test-secret"))
        session.get.return_value = github_response([
            {"id": "public", "public": True}, {"id": "private", "public": False}])
        self.assertEqual(client.fetch_public_gists("octocat"), [{"id": "public", "public": True}])
        self.assertEqual(session.headers["Authorization"], "Bearer test-secret")
        self.assertNotIn("Authorization", GITHUB_HEADERS)

    def test_error_statuses_have_deliberate_mappings(self):
        for upstream, expected in ((404, 404), (403, 503), (429, 503),
                                   (401, 502), (301, 502), (422, 502), (500, 502)):
            with self.subTest(upstream=upstream):
                client, session, _ = make_client()
                session.get.return_value = github_response({}, status=upstream)
                with self.assertRaises(GitHubError) as caught:
                    client.fetch_public_gists("octocat")
                self.assertEqual(caught.exception.status_code, expected)
                session.__exit__.assert_called_once()

    def test_rate_limit_does_not_trigger_automatic_retries(self):
        client, session, _ = make_client()
        session.get.return_value = github_response({}, status=429, headers={"Retry-After": "60"})
        with self.assertRaises(GitHubError) as caught:
            client.fetch_public_gists("octocat")
        self.assertEqual(caught.exception.retry_after, "60")
        self.assertEqual(session.get.call_count, 1)

    def test_retry_after_is_sanitized_without_shortening_the_requested_wait(self):
        for value, expected in (("999999", "999999"), ("-1", None), ("abc", None), ("", None)):
            with self.subTest(value=value):
                client, session, _ = make_client()
                session.get.return_value = github_response({}, status=429, headers={"Retry-After": value})
                with self.assertRaises(GitHubError) as caught:
                    client.fetch_public_gists("octocat")
                self.assertEqual(caught.exception.retry_after, expected)

    def test_transport_failures_are_safe_and_close_the_session(self):
        for failure, expected in ((requests.Timeout("secret details"), 504),
                                  (requests.ConnectionError("secret details"), 502)):
            with self.subTest(failure=type(failure).__name__):
                client, session, _ = make_client()
                session.get.side_effect = failure
                with self.assertRaises(GitHubError) as caught:
                    client.fetch_public_gists("octocat")
                self.assertEqual(caught.exception.status_code, expected)
                self.assertNotIn("secret details", str(caught.exception))
                session.__exit__.assert_called_once()

    def test_invalid_json_returns_a_controlled_error(self):
        client, session, _ = make_client()
        response = github_response([])
        response._content = b"not-json"
        session.get.return_value = response
        with self.assertRaises(GitHubError) as caught:
            client.fetch_public_gists("octocat")
        self.assertEqual(caught.exception.status_code, 502)

    def test_malformed_response_shapes_are_rejected(self):
        for body in ({}, [None], ["string"], [{"id": "no-visibility"}], [{"public": "true"}]):
            with self.subTest(body=body):
                client, session, _ = make_client()
                session.get.return_value = github_response(body)
                with self.assertRaises(GitHubError) as caught:
                    client.fetch_public_gists("octocat")
                self.assertEqual(caught.exception.status_code, 502)

    def test_later_page_failure_never_returns_partial_success(self):
        client, session, _ = make_client()
        session.get.side_effect = [github_response([{"public": True}], has_next_page=True),
                                   github_response({}, status=500)]
        with self.assertRaises(GitHubError) as caught:
            client.fetch_public_gists("octocat")
        self.assertEqual(caught.exception.status_code, 502)

    def test_page_limit_is_an_error_instead_of_silent_truncation(self):
        client, session, _ = make_client(Settings(max_pages=1))
        session.get.return_value = github_response([], has_next_page=True)
        with self.assertRaises(GitHubError) as caught:
            client.fetch_public_gists("octocat")
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(session.get.call_count, 1)

    def test_the_final_allowed_page_can_succeed(self):
        client, _, _ = make_client(Settings(max_pages=1))
        self.assertEqual(client.fetch_public_gists("octocat"), [])

    def test_expired_budget_stops_before_starting_another_call(self):
        client, session, _ = make_client(clock=Mock(side_effect=[0, 21]))
        with self.assertRaises(GitHubError) as caught:
            client.fetch_public_gists("octocat")
        self.assertEqual(caught.exception.status_code, 504)
        session.get.assert_not_called()

    def test_late_success_is_rejected_when_budget_has_expired(self):
        client, session, _ = make_client(clock=Mock(side_effect=[0, 0, 21]))
        with self.assertRaises(GitHubError) as caught:
            client.fetch_public_gists("octocat")
        self.assertEqual(caught.exception.status_code, 504)
        self.assertEqual(session.get.call_count, 1)

    def test_timeout_is_reduced_to_the_remaining_budget(self):
        client, session, _ = make_client(clock=Mock(side_effect=[0, 19, 19.5]))
        client.fetch_public_gists("octocat")
        self.assertEqual(session.get.call_args.kwargs["timeout"], (1, 1))

    def test_timeout_setting_limits_both_connection_and_read_waits(self):
        client, session, _ = make_client(Settings(timeout_seconds=0.5))
        client.fetch_public_gists("octocat")
        self.assertEqual(session.get.call_args.kwargs["timeout"], (0.5, 0.5))

    def test_invalid_username_never_creates_a_github_session(self):
        for name in ("bad_name", "..", "-start", "end-", "two--hyphens", "a" * 40):
            with self.subTest(name=name):
                client, _, factory = make_client()
                with self.assertRaises(GitHubError) as caught:
                    client.fetch_public_gists(name)
                self.assertEqual(caught.exception.status_code, 400)
                factory.assert_not_called()
        for name in ("octocat", "another-user", "a", "a" * 39):
            self.assertTrue(is_valid_username(name))

    def test_token_and_exception_details_do_not_appear_in_logs(self):
        client, session, _ = make_client(Settings(github_token="test-secret"))
        with self.assertLogs("github_client", level="INFO") as captured:
            client.fetch_public_gists("octocat")
        self.assertNotIn("test-secret", "\n".join(captured.output))
        self.assertNotIn("test-secret", repr(client.settings))

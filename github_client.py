"""GitHub communication, independent of Flask and HTML."""

import logging
import re
import time

import requests

logger = logging.getLogger(__name__)
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10",
    "User-Agent": "simple-gists-api",
}


class GitHubError(Exception):
    """A safe message, our HTTP status, and an optional wait before retrying."""

    def __init__(self, message, status_code, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def is_valid_username(username):
    """GitHub usernames contain alphanumeric groups separated by one hyphen."""
    return (
        isinstance(username, str)
        and 1 <= len(username) <= 39
        and re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", username) is not None
    )


class GitHubClient:
    """Fetch public Gists. A session factory and clock make testing predictable."""

    def __init__(self, settings, session_factory=requests.Session, clock=time.monotonic):
        self.settings = settings
        self.session_factory = session_factory
        self.clock = clock

    def fetch_public_gists(self, username):
        if not is_valid_username(username):
            raise GitHubError("Invalid GitHub username.", 400)

        deadline = self.clock() + self.settings.request_budget_seconds
        url = f"https://api.github.com/users/{username}/gists"
        gists = []

        # Each request owns its session: safe with multiple server threads.
        # Connections are reused across pages and closed on every exit.
        with self.session_factory() as session:
            session.headers.update(GITHUB_HEADERS)
            if self.settings.github_token:
                session.headers["Authorization"] = f"Bearer {self.settings.github_token}"

            try:
                for page in range(1, self.settings.max_pages + 1):
                    remaining = self._remaining_seconds(deadline)
                    with session.get(
                        url,
                        params={"per_page": 100, "page": page},
                        timeout=(min(3, self.settings.timeout_seconds, remaining),
                                 min(self.settings.timeout_seconds, remaining)),
                        allow_redirects=False,
                    ) as response:
                        logger.info("github username=%s page=%s status=%s",
                                    username, page, response.status_code)
                        self._check_status(response)
                        page_gists = response.json()
                        if not isinstance(page_gists, list):
                            raise GitHubError("GitHub returned an unexpected response.", 502)
                        for gist in page_gists:
                            if not isinstance(gist, dict) or not isinstance(gist.get("public"), bool):
                                raise GitHubError("GitHub returned an unexpected response.", 502)
                            if gist["public"]:
                                gists.append(gist)
                        has_next_page = "next" in response.links

                    self._remaining_seconds(deadline)
                    if not has_next_page:
                        return gists

            except requests.Timeout as error:
                raise GitHubError("GitHub took too long to respond.", 504) from error
            except (requests.RequestException, ValueError) as error:
                raise GitHubError("Could not read a valid response from GitHub.", 502) from error

        # A partial list must not look like a complete, successful result.
        raise GitHubError("GitHub returned more pages than this service allows.", 502)

    def _remaining_seconds(self, deadline):
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise GitHubError("GitHub request exceeded the time budget.", 504)
        return remaining

    @staticmethod
    def _check_status(response):
        if response.status_code == 404:
            raise GitHubError("GitHub user not found.", 404)
        if response.status_code in (403, 429):
            wait = response.headers.get("Retry-After", "")
            retry_after = str(int(wait)) if re.fullmatch(r"[0-9]{1,6}", wait) else None
            raise GitHubError(
                "GitHub rejected the request or its rate limit was reached.",
                503, retry_after,
            )
        if response.status_code != 200:
            raise GitHubError("GitHub could not complete the request.", 502)

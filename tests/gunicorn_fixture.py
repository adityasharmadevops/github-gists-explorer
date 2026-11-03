"""Test-only server: actual routes and client, with GitHub's reply controlled."""

from tests.helpers import github_response, make_app

app, session, _ = make_app()
session.get.return_value = github_response([{
    "id": "socket-example", "public": True, "description": "A controlled HTTP example",
    "files": {"hello.py": {"language": "Python"}},
    "html_url": "https://gist.github.com/octocat/socket-example",
    "updated_at": "2026-11-02T10:00:00Z",
}])

"""Shared test fixtures: use real Requests response parsing with controlled data."""

import json
from unittest.mock import MagicMock

import requests

from app import create_app
from github_client import GitHubClient
from settings import Settings


def github_response(body, status=200, has_next_page=False, headers=None):
    response = requests.Response()
    response.status_code = status
    response.url = "https://api.github.com/users/octocat/gists"
    response._content = json.dumps(body).encode()
    response._content_consumed = True
    response.encoding = "utf-8"
    if has_next_page:
        response.headers["Link"] = '<https://api.github.com/users/octocat/gists?page=2>; rel="next"'
    if headers:
        response.headers.update(headers)
    return response


def make_client(settings=None, clock=None):
    session = MagicMock()
    session.headers = {}
    session.__enter__.return_value = session
    session.get.return_value = github_response([])
    factory = MagicMock(return_value=session)
    client = GitHubClient(settings or Settings(), factory, clock or (lambda: 0))
    return client, session, factory


def make_app():
    client, session, factory = make_client()
    app = create_app(Settings(), client)
    app.config["TESTING"] = True
    return app, session, factory

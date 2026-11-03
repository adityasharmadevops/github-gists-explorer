"""HTTP routes and presentation. GitHub details live in github_client.py."""

from datetime import datetime
import logging
import sys
import time
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from github_client import GitHubClient, GitHubError
from settings import Settings

logger = logging.getLogger(__name__)


def prepare_gists_for_display(gists):
    """Pick readable fields without modifying the original API data."""
    rows = []
    for gist in gists:
        files = gist.get("files")
        files = files if isinstance(files, dict) else {}
        file_rows = []
        for name, details in files.items():
            details = details if isinstance(details, dict) else {}
            file_rows.append({"name": name, "language": details.get("language") or "Plain text"})

        updated = gist.get("updated_at")
        try:
            updated_date = datetime.fromisoformat(updated.replace("Z", "+00:00")).date().isoformat()
        except (AttributeError, TypeError, ValueError):
            updated_date = "Not available"

        link = gist.get("html_url")
        try:
            parsed = urlsplit(link) if isinstance(link, str) else None
            safe_link = (
                link if parsed and parsed.scheme == "https" and parsed.netloc == "gist.github.com"
                and not any(ord(character) < 32 for character in link) else None
            )
        except ValueError:
            safe_link = None

        rows.append({
            "id": gist.get("id", ""),
            "description": gist.get("description") or "No description provided",
            "files": file_rows,
            "updated_date": updated_date,
            "url": safe_link,
        })
    return rows


def create_app(settings=None, github_client=None):
    """Create independent app instances; tests can supply a controlled client."""
    settings = settings if settings is not None else Settings.from_env()
    client = github_client if github_client is not None else GitHubClient(settings)
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        stream=sys.stdout)
    app = Flask(__name__)
    app.json.compact = False

    @app.before_request
    def start_request_timer():
        g.started_at = time.monotonic()

    @app.after_request
    def finish_request(response):
        elapsed_ms = (time.monotonic() - g.started_at) * 1000
        logger.info("request method=%s path=%r status=%s duration_ms=%.1f",
                    request.method, request.path, response.status_code, elapsed_ms)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'self'; form-action 'self'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(GitHubError)
    def handle_github_error(error):
        logger.warning("github_failure status=%s error=%s", error.status_code, error)
        if request.endpoint == "browse_gists":
            response = app.make_response((render_template(
                "index.html", username=request.args.get("username", "").strip(),
                gists=None, error_message=str(error),
            ), error.status_code))
        else:
            response = jsonify(error=str(error))
            response.status_code = error.status_code
        if error.retry_after is not None:
            response.headers["Retry-After"] = error.retry_after
        return response

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        response = error.get_response()
        response.data = app.json.dumps({"error": error.description})
        response.content_type = "application/json"
        return response

    @app.get("/_health")
    def health():
        """Liveness only: does not call GitHub or claim it is available."""
        return jsonify(status="ok")

    @app.get("/favicon.ico")
    def favicon():
        return "", 204

    @app.get("/")
    def browse_gists():
        username = request.args.get("username", "").strip()
        rows = None
        if username:
            rows = prepare_gists_for_display(client.fetch_public_gists(username))
        return render_template("index.html", username=username, gists=rows, error_message=None)

    @app.get("/<username>")
    def get_gists(username):
        return jsonify(client.fetch_public_gists(username))

    return app


app = create_app()

if __name__ == "__main__":
    # Local practice only. The container starts Gunicorn instead.
    app.run(host="0.0.0.0", port=8080)

# GitHub Gists API — readable Python, tested behavior, lean container

Give the server a GitHub username. It asks GitHub for that person's public Gists
and returns them as JSON. A Gist is a small group of files, often code snippets.
The browser home page presents the same information as a readable table.

Verified on **2 November 2026**: all **41 automated tests** passed, the Docker
build and container checks passed, and a real GitHub request for `octocat`
returned HTTP 200. The container checker reported an image size of **44.2 MiB**
on Rancher Desktop. See [verification results](docs/VERIFICATION.md).

**Start with [the complete code walkthrough](docs/WALKTHROUGH.html).** Open that
file in your browser. It includes the actual source, explanations of every
production function, Docker instructions, tests, Python syntax, and review questions.

## Required behavior

| Request | Response |
| --- | --- |
| `GET /octocat` | JSON list of octocat's public Gists |
| `GET /another-user` | The same behavior for another GitHub username |
| `GET /` | Search form for a person using a browser |
| `GET /?username=octocat` | Readable descriptions, filenames, languages, dates, and GitHub links |
| `GET /_health` | `{"status": "ok"}`; no GitHub request |
| `GET /favicon.ico` | Empty 204 response, avoiding an unnecessary GitHub lookup |

`/<USER>` means replace `<USER>` with a username. The API response remains a JSON
array even when the caller is a browser. For a readable page, visit the home page
at **http://localhost:8080/** and enter `octocat`.

## 1. Run locally on a Mac

Use Python 3.12, which is also the container version. Extract the archive and
open Terminal in the project folder containing `app.py` and `Dockerfile`.

Run one command at a time:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python app.py
```

If you have several Python versions, use `python3.12` instead of `python3` in the
first command. The server keeps the terminal occupied while it is running.

Open **http://localhost:8080/** in your browser. Search for `octocat`.
In another terminal you can also check:

```bash
curl -i http://localhost:8080/_health
curl -i http://localhost:8080/octocat
```

`-i` shows the HTTP status and headers as well as the body. To format JSON in a
terminal, use `curl -s http://localhost:8080/octocat | python3 -m json.tool`.

Press **Ctrl+C** in the server terminal to stop it. On macOS/Linux, you can run
the same server program used by the container:

```bash
python -m gunicorn --config gunicorn.conf.py app:app
```

Gunicorn requires a Unix-like system. On Windows, use `python app.py` for local
practice and Docker for the Gunicorn check. The Gunicorn-specific automated test
is skipped on Windows; the other tests still run.

## 2. Build and run Docker

Start Rancher Desktop or Docker Desktop.
Stop the local Python server first to free port 8080.
From the project folder:

```bash
docker build --pull -t gist-api:local .
docker run --rm --pull=never -p 127.0.0.1:8080:8080 gist-api:local
```

The final `.` tells Docker to use the current folder. A regular image build runs
all automated tests with external networking disabled before copying the tested
application into the final image. If a test fails, the build fails. BuildKit may
reuse a successful test layer when its inputs have not changed.

`-p 127.0.0.1:8080:8080` connects port 8080 on your own computer to the container's
port 8080. The application listens on all interfaces **inside** the container.
`EXPOSE` documents the container port; `-p` publishes it.

Open **http://localhost:8080/** again. This time the app runs inside Docker.
No registry or publishing step is needed.

A version with explicit runtime restrictions is:

```bash
docker run --rm --name gist-api-demo \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 128 --memory 256m --cpus 1 \
  -p 127.0.0.1:8080:8080 gist-api:local
```

The filesystem is read-only except for a small temporary memory filesystem.
Gunicorn uses that temporary folder for worker heartbeat files. Memory, CPU, and
PID values are demonstration limits; choose deployment limits after measuring
real traffic. In a second terminal, use `docker stop --time 30 gist-api-demo` to
allow up to 30 seconds for graceful shutdown. `--rm` removes the stopped container.

## 3. Verify the actual container automatically

Run from the extracted project folder, with your Docker engine running:

```bash
python3 tools/check_container.py
```

This builds the image, verifies its default user and file permissions, checks
that tests/documentation are absent from `/app`, and starts it with the restrictions
above on a temporary localhost port. It waits for Docker's health check, checks
the browser page, CSS, health response and invalid-input response, records local
image size/runtime stats, sends SIGTERM, checks exit code 0, and removes its own
container. It leaves the built image available for you to run.

To also require a successful real GitHub request:

```bash
python3 tools/check_container.py --live
```

The JSON report is `container-report.json`. A nonzero script exit code means a
check failed. The script does not claim a live GitHub success unless `--live`
was requested and that check passed. It forwards `GITHUB_TOKEN` only if already
set in your environment; no token is necessary for public Gists.

For local image inspection and an optional vulnerability scan:

```bash
docker image inspect gist-api:local --format '{{.Size}}'
docker history gist-api:local
docker scout cves gist-api:local
```

The first command reports Docker's image size in bytes. The Scout command is
optional and needs Docker Scout installed. Review scanner findings, update
affected dependencies/base images, rebuild, and retest as part of maintenance.

## Why this image is lean and maintainable

| Choice | Benefit and qualification |
| --- | --- |
| Official Python `slim-bookworm` base | Smaller starting point than the full Python image; keeps familiar Debian behavior. |
| Exact Python tag plus multi-platform index digest | Fixes the selected base contents while allowing Docker to choose the host architecture. Refresh it deliberately for security updates. |
| All direct and transitive Python versions pinned | Avoids unexpectedly resolving a newer library version on every build. Package artifact hashes are not locked. |
| Three stages after a shared base | Dependencies are installed once; tests run separately; only application/runtime files are selected for release. |
| Dependency installation before copying source | Changing a route does not force a dependency download. |
| BuildKit pip cache | Rebuild downloads are cached outside the image layers. |
| Virtual environment without a second pip installation | The base interpreter's pip installs into `/opt/venv`; the copied runtime environment contains application dependencies without another pip copy. The base image's original pip remains in its own Python environment. |
| Binary wheels and no bytecode compilation | Avoids installing a compiler and reduces generated files; a missing compatible wheel causes a clear build failure. |
| Explicit copy list and `.dockerignore` allowlist | Keeps virtual environments, credentials, ZIPs, docs and unrelated files out of the build context. Tests enter only their stage. |
| No extra OS packages | No curl, editor, compiler, or frontend toolchain is added. Python performs the health check. |
| Non-root user; root-owned application files | The process can read application files without being able to edit them. |
| Exec-form startup and SIGTERM | The stop signal reaches Gunicorn directly, which manages workers and shutdown. |
| Read-only-compatible runtime | Supports the restricted run command and the automatic container check. |

Multi-stage separation keeps test files and caches out of the release. The final
container verification reported an image size of **44.2 MiB** on Rancher Desktop.
This is the checker's Docker-reported measurement for that build; image size can
vary by architecture and Docker storage backend. Excluding tests alone saves a
modest amount of space in this small project. The smoke check's resource sample
is separate from a load-test benchmark.

## Code organization and reuse

| File | Responsibility |
| --- | --- |
| `settings.py` | Read environment configuration and reject invalid values |
| `github_client.py` | Validate usernames, call GitHub, combine pages, and produce safe errors |
| `app.py` | HTTP routes, readable display fields, response headers and logs |
| `templates/index.html` | Accessible search form and results table |
| `static/style.css` | Responsive presentation; no JavaScript or external assets |
| `gunicorn.conf.py` | Explicit server defaults |
| `tests/` | Controlled GitHub replies, API checks, real HTTP and Gunicorn checks |
| `tools/check_container.py` | Build and verify the actual Docker image |
| `docs/WALKTHROUGH.html` | Full source and plain-language explanations |

You can reuse the GitHub client without running Flask:

```python
from github_client import GitHubClient
from settings import Settings

client = GitHubClient(Settings.from_env())
gists = client.fetch_public_gists("octocat")
print(len(gists))
```

`create_app(settings, github_client)` also lets tests create independent web
applications with controlled dependencies. This is dependency injection: pass
in the thing a function needs, so tests can control it.

## Configuration

| Environment variable | Default | Meaning |
| --- | --- | --- |
| `GITHUB_TIMEOUT_SECONDS` | `5` | Maximum read wait; also caps the connection wait, which is at most 3 seconds |
| `GITHUB_REQUEST_BUDGET_SECONDS` | `20` | Cooperative time budget across pages; checked before and after each request |
| `GITHUB_MAX_PAGES` | `20` | Maximum pages, each requesting up to 100 Gists |
| `GITHUB_TOKEN` | Unset | Optional GitHub authentication token, hidden from settings repr and application logs |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, or CRITICAL |
| `GUNICORN_CMD_ARGS` | Unset | Optional overrides such as `--workers 1 --threads 2` |

Example: `GITHUB_TIMEOUT_SECONDS=2 python app.py`.
For Docker, pass an already-set token at runtime using `-e GITHUB_TOKEN`.
Do not put it into the Dockerfile, source, ZIP, or a build argument.

The client uses a new Session for each incoming Gist lookup. Its pages can reuse
an HTTPS connection, and its credentials/connections are not shared between
concurrent lookups. Session and response context managers close resources even
when requests fail. Redirects are disabled, and pagination always uses the fixed
GitHub endpoint rather than trusting a next-link destination.

## Responses and operational behavior

| Status | Meaning |
| --- | --- |
| 200 | Complete JSON list, including `[]` for no public Gists |
| 400 | Invalid username |
| 404 | GitHub reports user not found, or route does not exist |
| 405 | Unsupported method; the `Allow` header is preserved |
| 502 | Unexpected upstream status/body or a page limit preventing a complete list |
| 503 | GitHub rejected or rate-limited the request |
| 504 | Connection/read timeout or exhausted cooperative time budget |

API failures have the form `{"error": "safe message"}`. The readable page shows
an error message with the same HTTP status. Numeric GitHub `Retry-After` values
of up to six digits are forwarded for rate limits. HTTP-date hints and
`X-RateLimit-Reset` are not interpreted. There are no automatic retries.

Logs include upstream status, page number, incoming method/path/status and
elapsed milliseconds. Application paths use escaped representation. Application
and configured Gunicorn access logs omit query strings, headers, response bodies,
and raw upstream exception details. Flask's local development server may also
write its own request logs; the configured Gunicorn logger is used in Docker.

The page uses template escaping, validated HTTPS Gist links and a Content Security
Policy. CSS is a local file so that inline styles and scripts can be disallowed.
Health means the application process can respond; it does not assert GitHub is up.

## What tests prove

The suite exercises the actual GitHub client using controlled Requests responses,
and checks the routes through Flask's test client. It also runs a server on a
real localhost socket, and starts Gunicorn with two workers/four threads to check
concurrent requests and graceful shutdown. These tests need no GitHub access.

Tests check returned JSON and content, username forwarding, empty lists,
pagination, private-Gist filtering, malformed upstream data, late-page failures,
page/time budgets, timeout configuration, cleanup, rate-limit hints, safe errors,
configuration, HTML escaping, link safety, styles, and logging behavior.

A test fixture contains sample Gists only for tests. The production application
always calls GitHub. No test is satisfied merely because the process starts.

## Verification and practical limits

See [docs/VERIFICATION.md](docs/VERIFICATION.md) for the results from this revision.
The final multi-stage Docker image passed its build-time tests and the live
container checker on Rancher Desktop. Verification covered non-root execution,
read-only application files and root filesystem, Docker health, HTML/CSS delivery,
invalid-input handling, a real GitHub response, and graceful SIGTERM shutdown.
A browser check confirmed that the running container displayed octocat's Gists
as a readable table. The checker can repeat these checks in another environment.

The Requests read timeout measures inactivity between incoming bytes; it is not
a hard total download deadline. Our budget is checked between operations, so a
slow trickle of bytes, DNS lookup or a single long operation may exceed it before
control returns. Gunicorn's gthread worker timeout is a worker-liveness setting,
not a strict deadline for each request. Internet deployments should define
appropriate proxy/upstream deadlines and response-size limits.

The client collects pages in memory. The page limit bounds the number of calls,
but is not a strict byte limit or a snapshot guarantee. Gists may change between
pages. There is no application cache or database; each search uses GitHub's quota.
Two workers and four threads per worker are a starting point, not a measured
optimum. TLS, ingress protection, load testing, observability dashboards and a
scheduled update/scan process belong to a deployment's requirements.

## A clear explanation for a review

> A caller supplies a GitHub username. Flask sends it to a reusable GitHub client.
> The client validates it, asks GitHub for public Gists, reads the pages, and
> returns ordinary Python data. Flask returns JSON or uses that data to render a
> readable table. Tests control GitHub's replies and also exercise actual HTTP
> and Gunicorn processes. Docker builds dependencies, runs tests, and copies only
> the tested application into a non-root runtime. I also verified the final
> container with a real GitHub request, runtime checks and graceful shutdown.
> The checker reported a 44.2 MiB image on Rancher Desktop.

## Official references

- [GitHub Gists endpoint](https://docs.github.com/en/rest/gists/gists#list-gists-for-a-user)
- [Requests sessions and timeouts](https://requests.readthedocs.io/en/latest/user/advanced/)
- [Flask application factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/)
- [Flask testing](https://flask.palletsprojects.com/en/stable/testing/)
- [Gunicorn settings](https://gunicorn.org/reference/settings/)
- [Docker build practices](https://docs.docker.com/build/building/best-practices/)
- [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Python official image](https://hub.docker.com/_/python) — the exact tag and digest used by this project are recorded in `Dockerfile`.

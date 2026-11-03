# Verification results

Verification completed on **2 November 2026**. These results combine the
41-test automated suite with the successful final Docker build and
`python3 tools/check_container.py --live` run on macOS using Rancher Desktop.
The container was also opened in a browser to check the readable results page.

## Automated tests and dependency checks

| Check | Result | What it establishes |
| --- | --- | --- |
| Automated suite | **41 tests passed** | GitHub client behavior, API responses, browser presentation, errors, settings, security cases, resource cleanup, and time/page limits |
| Docker build-time tests | **Passed** | The final multi-stage build ran the suite with external networking disabled before selecting the tested runtime files |
| Localhost HTTP test | **Passed** | Real socket requests returned health JSON, Gist JSON, and readable HTML with a controlled GitHub boundary |
| Gunicorn process test | **Passed** | The actual server/configuration served 16 concurrent Gist requests, HTML and CSS, sanitized access logs, and stopped on SIGTERM with exit status 0 |
| Dependency compatibility | **Passed** | `pip check` succeeded for the pinned dependencies, including during the final Docker build |
| Runtime environment without its own pip | **Passed** | Application dependencies work in the copied virtual environment without a duplicate pip installation |

The normal automated suite uses controlled GitHub responses so success and
failure cases remain repeatable. The live container check below separately
confirms real GitHub access from the final image.

## Final Docker container checks

The final Docker build succeeded, and every runtime check below printed `PASS`
during the final `--live` run.

| Check | Result |
| --- | --- |
| Final multi-stage Docker image built as `gist-api:local` | **Passed** |
| Image defaults to non-root user `10001:10001` | **Passed** |
| Application files are root-owned and not writable by the service user | **Passed** |
| Tests, documentation, and duplicate pip are excluded from the runtime application environment | **Passed** |
| Container starts with a read-only root filesystem and the checker's runtime restrictions | **Passed** |
| Docker marks the container healthy | **Passed** |
| `GET /_health` returns HTTP 200 and the expected JSON | **Passed** |
| Browser search page and stylesheet are available | **Passed** |
| Invalid username returns a JSON HTTP 400 response | **Passed** |
| Real `GET /octocat` request returns HTTP 200 and a list containing only public Gists | **Passed** |
| SIGTERM stops the server with exit status 0 and no out-of-memory termination | **Passed** |

The checker writes image identity, architecture, image size, a runtime resource
sample, live-request results, and the exit code to `container-report.json`.
That file is generated locally and excluded from version control and the
submission archive. The successful run's terminal output supplied the final
Docker results recorded here.

## Image and browser results

| Item | Verified result |
| --- | --- |
| Image tag | `gist-api:local` |
| Image size | **44.2 MiB**, as reported by the container checker on Rancher Desktop |
| Python base | `python:3.12.14-slim-bookworm`, pinned to a multi-platform image digest |
| Server | Gunicorn 26.2.0, `gthread`, two workers with four threads each |
| Container listener | Port **8080** |
| Browser home page | Search form, results count, readable table, and View JSON link displayed successfully |
| Live example | `octocat` displayed **8 public Gists** during the browser check |
| Additional username | Container logs show a successful GitHub lookup for another username |
| Manual container startup | The image started with `--pull=never` and localhost port mapping |

The Gist count is a point-in-time observation; live GitHub data can change.
Image sizes can vary by architecture and Docker storage backend. The recorded
size describes this verified build, and the resource sample describes a smoke
run rather than sustained-load capacity.

## Reproduce verification

With Rancher Desktop or Docker Desktop running, open Terminal in the project
folder and run:

```bash
python3 tools/check_container.py --live
```

This builds the image, runs the mandatory test stage, checks the final runtime,
requests real public Gists from GitHub, verifies clean shutdown, and writes
`container-report.json`. It removes its temporary check container and leaves the
built image available.

To run the verified application for a demonstration:

```bash
docker run --rm --pull=never -p 127.0.0.1:8080:8080 gist-api:local
```

Open `http://localhost:8080/` for the readable page or
`http://localhost:8080/octocat` for the JSON API.

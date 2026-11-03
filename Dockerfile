# syntax=docker/dockerfile:1
# Pin the multi-platform image index. Review this digest when applying base updates.
ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# Install once; source changes do not invalidate the dependency layer.
FROM base AS dependencies
RUN python -m venv --without-pip /opt/venv
COPY requirements.txt ./
# The download cache stays in the builder, not in the final image.
# Use the base image's pip so the virtual environment needs no second pip copy.
RUN --mount=type=cache,target=/root/.cache/pip \
    /usr/local/bin/python -m pip --python /opt/venv install \
      --no-compile --only-binary=:all: -r requirements.txt \
    && /usr/local/bin/python -m pip --python /opt/venv check

# Every normal image build must pass these network-independent tests.
FROM dependencies AS test
COPY app.py github_client.py settings.py gunicorn.conf.py ./
COPY templates/ ./templates/
COPY static/ ./static/
COPY tests/ ./tests/
RUN --network=none python -m unittest discover -s tests -v

# Copy only dependencies and tested application files into the release image.
FROM base AS runtime
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=dependencies /opt/venv /opt/venv
COPY --from=test /app/app.py /app/github_client.py /app/settings.py /app/gunicorn.conf.py ./
COPY --from=test /app/templates/ ./templates/
COPY --from=test /app/static/ ./static/
# Root owns application files; the service user can read, but cannot edit them.
USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM
# Use Python already in the image rather than installing curl just for this check.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/_health', timeout=2).close()"]
# No shell wrapper: Docker's stop signal reaches the Gunicorn master directly.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]

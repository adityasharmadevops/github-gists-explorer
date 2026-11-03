"""Small-container defaults. GUNICORN_CMD_ARGS can override them at runtime."""

import tempfile

bind = "0.0.0.0:8080"
workers = 2
worker_class = "gthread"
threads = 4
timeout = 30
graceful_timeout = 25
keepalive = 5
worker_tmp_dir = tempfile.gettempdir()
control_socket_disable = True
accesslog = "-"
errorlog = "-"
# Log the path (%U), excluding query strings and headers that may contain secrets.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'

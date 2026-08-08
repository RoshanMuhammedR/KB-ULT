#!/usr/bin/env sh
# Bring the database up to date, then hand off to the container's command.
#
# Both the api and the worker run this image, but only ONE of them may migrate — concurrent
# `alembic upgrade` runs on the same database race. The api owns migrations (RUN_MIGRATIONS=1
# in the compose file); the worker starts with RUN_MIGRATIONS unset and simply waits for the
# api's healthcheck via depends_on.
set -eu

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
	echo "==> alembic upgrade head"
	alembic upgrade head

	# Procrastinate owns its own queue tables and applies them idempotently.
	echo "==> procrastinate schema --apply"
	procrastinate --app=src.infrastructure.queue.app.app schema --apply || {
		# Already applied is not an error worth failing a deploy over; anything else is.
		echo "    (schema already present)"
	}
fi

exec "$@"

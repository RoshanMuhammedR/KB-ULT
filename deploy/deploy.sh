#!/usr/bin/env bash
# Roll onto a new image tag, gated on health. Restores the previous tag on failure.
#   ./deploy.sh sha-1a2b3c4
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"

HEALTH_TIMEOUT=240
# The api is the meaningful gate: its healthcheck only passes after migrations have run.
SERVICE="${HEALTH_SERVICE:-api}"

NEW_TAG="${1:-}"
[ -n "$NEW_TAG" ] || { echo "usage: $(basename "$0") <image-tag>" >&2; exit 2; }
[ -f .env ] || { echo "error: no .env in $STACK_DIR" >&2; exit 2; }

PREV_TAG="$(sed -n -E 's/^IMAGE_TAG=(.*)$/\1/p' .env | tail -1)"
PREV_TAG="${PREV_TAG:-latest}"

set_tag() {
	if grep -qE '^IMAGE_TAG=' .env; then
		sed -i -E "s|^IMAGE_TAG=.*|IMAGE_TAG=$1|" .env
	else
		printf 'IMAGE_TAG=%s\n' "$1" >>.env
	fi
}

wait_healthy() {
	local waited=0 cid status
	while [ "$waited" -lt "$HEALTH_TIMEOUT" ]; do
		cid="$(docker compose ps -q "$SERVICE" || true)"
		if [ -n "$cid" ]; then
			status="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)"
			[ "$status" = healthy ] && return 0
			# A service with no HEALTHCHECK reports <no value> — fall back to "running".
			if [ "$status" = "<no value>" ]; then
				[ "$(docker inspect -f '{{.State.Status}}' "$cid")" = running ] && return 0
			fi
		fi
		sleep 5
		waited=$((waited + 5))
		printf '  ... waiting for %s (%ss/%ss)\n' "$SERVICE" "$waited" "$HEALTH_TIMEOUT"
	done
	return 1
}

# The api healthcheck alone is not proof the deploy is good: it passes while caddy (the only
# publicly reachable service) or the worker is crash-looping. So we also drive the real
# published port and refuse anything stuck restarting.
verify_stack() {
	local port restarting code
	port="$(sed -n -E 's/^APP_PORT=(.*)$/\1/p' .env | tail -1)"
	port="${port:-80}"

	restarting="$(docker compose ps --format '{{.Service}} {{.Status}}' | grep -i restarting || true)"
	if [ -n "$restarting" ]; then
		echo "!!! containers stuck restarting:" >&2
		printf '%s\n' "$restarting" >&2
		return 1
	fi

	# Through caddy, exactly as AIC's proxy will arrive.
	for path in /api/health /app/login /; do
		code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H "Host: ${APP_BASE_URL#https://}" "http://127.0.0.1:${port}${path}" || echo 000)"
		echo "    ${path} -> ${code}"
		case "$code" in
		2* | 3*) ;;
		*)
			echo "!!! ${path} returned ${code} through the published port" >&2
			return 1
			;;
		esac
	done
	return 0
}

echo "==> deploying $NEW_TAG (current: $PREV_TAG)"
set_tag "$NEW_TAG"
docker compose pull
docker compose up -d --remove-orphans

# APP_BASE_URL is only needed for the Host header in verify_stack.
set -a
# shellcheck disable=SC1091
. ./.env
set +a

if wait_healthy; then
	echo "==> api healthy — verifying the whole stack through :${APP_PORT}"
	# Give caddy and the worker a moment to settle before judging them.
	sleep 5
	if verify_stack; then
		echo "==> deploy verified on $NEW_TAG"
		docker image prune -f >/dev/null || true
		docker compose ps
		exit 0
	fi
	echo "!!! stack verification failed" >&2
fi

echo "!!! deploy of $NEW_TAG failed — rolling back to $PREV_TAG" >&2
# Logs from every service, not just the health-gated one: the failure is often in caddy or
# the worker, which is precisely what the api healthcheck cannot see.
docker compose logs --tail=40 >&2 || true
set_tag "$PREV_TAG"
docker compose up -d --remove-orphans >&2 || true
exit 1

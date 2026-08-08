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

echo "==> deploying $NEW_TAG (current: $PREV_TAG)"
set_tag "$NEW_TAG"
docker compose pull
docker compose up -d --remove-orphans

if wait_healthy; then
	echo "==> healthy on $NEW_TAG"
	docker image prune -f >/dev/null || true
	docker compose ps
	exit 0
fi

echo "!!! $SERVICE unhealthy after ${HEALTH_TIMEOUT}s — rolling back to $PREV_TAG" >&2
docker compose logs --tail=80 "$SERVICE" >&2 || true
set_tag "$PREV_TAG"
docker compose up -d --remove-orphans >&2 || true
exit 1

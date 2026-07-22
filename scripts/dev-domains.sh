#!/usr/bin/env sh
# Map local dev domains to 127.0.0.1 so the Saga two-app domain-handoff flow is testable
# on localhost. The marketing site runs at the first domain, and each additional domain is a
# tenant workspace you can register/log into on the product app.
#
#   Marketing (website) : http://saga.test:${WEBSITE_PORT:-3001}
#   Product (per tenant): http://<domain>:${WEB_PORT:-3000}   e.g. http://acme.test:3000
#
# Usage:
#   pnpm run domains:map           # add the managed block to /etc/hosts (needs sudo)
#   pnpm run domains:unmap         # remove the managed block
#
# Edit DOMAINS below to add your own tenant domains, then re-run. CORS on the API already
# allows any *.test host (see cors_allowed_origin_regex), so no backend edit is needed.
set -eu

# --- Edit this list ---------------------------------------------------------
DOMAINS="saga.test acme.test admin.test roshan.test"
# ---------------------------------------------------------------------------

HOSTS_FILE="/etc/hosts"
BEGIN="# >>> saga dev domains >>>"
END="# <<< saga dev domains <<<"
WEBSITE_PORT="${WEBSITE_PORT:-3001}"
WEB_PORT="${WEB_PORT:-3000}"

remove_block() {
  # Strip any existing managed block (idempotent). Uses a temp file so we can sudo-copy it back.
  if grep -qF "$BEGIN" "$HOSTS_FILE" 2>/dev/null; then
    tmp="$(mktemp)"
    sed "/^${BEGIN}$/,/^${END}$/d" "$HOSTS_FILE" > "$tmp"
    # Drop any trailing blank lines the block left behind, then restore one newline.
    sudo cp "$tmp" "$HOSTS_FILE"
    rm -f "$tmp"
  fi
}

if [ "${1:-}" = "--remove" ] || [ "${1:-}" = "-r" ]; then
  echo "Removing Saga dev domains from ${HOSTS_FILE} (sudo)…"
  remove_block
  echo "Done. Local domain mappings removed."
  exit 0
fi

echo "Mapping Saga dev domains to 127.0.0.1 in ${HOSTS_FILE} (sudo)…"
remove_block

block="${BEGIN}\n"
for d in $DOMAINS; do
  block="${block}127.0.0.1 ${d}\n"
  block="${block}::1 ${d}\n"
done
block="${block}${END}"

# Append the managed block.
printf "%b\n" "$block" | sudo tee -a "$HOSTS_FILE" > /dev/null

echo ""
echo "Mapped:"
first=""
for d in $DOMAINS; do
  if [ -z "$first" ]; then
    first="$d"
    echo "  • ${d}  → marketing site : http://${d}:${WEBSITE_PORT}"
  else
    echo "  • ${d}  → product app    : http://${d}:${WEB_PORT}"
  fi
done
echo ""
echo "Start everything with:  pnpm run dev"
echo "Then open:              http://${first}:${WEBSITE_PORT}"

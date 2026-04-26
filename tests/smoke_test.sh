#!/usr/bin/env bash
# tests/smoke_test.sh — End-to-end smoke test for Farm Manager.
#
# Verifies: server starts, login works with CSRF, every protected page loads,
# CSRF rejects tokenless POSTs, viewer role cannot mutate, inventory survives
# rejected attacks. Read-only against the DB — does not modify any data.
#
# Usage:
#   chmod +x tests/smoke_test.sh    (one time)
#   ./tests/smoke_test.sh
#
# Override credentials via env if your seed data is different:
#   ADMIN_EMAIL=alice@unl.edu ADMIN_PASS=hunter2 ./tests/smoke_test.sh

cd "$(dirname "$0")/.."

ADMIN_EMAIL="${ADMIN_EMAIL:-ijandu@unl.edu}"
ADMIN_PASS="${ADMIN_PASS:-admin123}"
VIEWER_EMAIL="${VIEWER_EMAIL:-pnair@unl.edu}"
VIEWER_PASS="${VIEWER_PASS:-pnair2024}"

BASE_URL="http://127.0.0.1:5001"
ADMIN_COOKIE=$(mktemp)
VIEWER_COOKIE=$(mktemp)
PASS=0
FAIL=0
SERVER_PID=""

cleanup() {
  rm -f "$ADMIN_COOKIE" "$VIEWER_COOKIE"
  [ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null
}
trap cleanup EXIT

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }
blue()  { printf "\033[34m%s\033[0m\n" "$1"; }

check() {
  local name="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    green "  PASS: $name (got $actual)"
    PASS=$((PASS+1))
  else
    red "  FAIL: $name (expected $expected, got $actual)"
    FAIL=$((FAIL+1))
  fi
}

extract_token() {
  echo "$1" | grep -oE 'name="csrf_token" value="[^"]+"' | head -1 | cut -d'"' -f4
}

# ── 1. Start the Flask server ──────────────────────────────────────────────
blue "→ Starting Flask server..."
python server.py >/tmp/farm_smoke.log 2>&1 &
SERVER_PID=$!
sleep 2

if ! curl -s -o /dev/null "$BASE_URL/login"; then
  red "  FAIL: server did not start. Last 20 lines of /tmp/farm_smoke.log:"
  tail -20 /tmp/farm_smoke.log
  exit 1
fi
green "  ✓ Server started (PID $SERVER_PID)"

# ── 2. Login flow with CSRF ────────────────────────────────────────────────
echo
blue "→ Login flow (admin)..."
LOGIN_PAGE=$(curl -s -c "$ADMIN_COOKIE" "$BASE_URL/login")
TOKEN=$(extract_token "$LOGIN_PAGE")
if [ -z "$TOKEN" ]; then
  red "  FAIL: no csrf_token in /login HTML — Step 6 may not be applied"
  exit 1
fi
green "  ✓ CSRF token in /login: ${TOKEN:0:24}..."

STATUS=$(curl -s -b "$ADMIN_COOKIE" -c "$ADMIN_COOKIE" -o /dev/null -w '%{http_code}' \
  -d "identifier=$ADMIN_EMAIL&password=$ADMIN_PASS&csrf_token=$TOKEN" \
  "$BASE_URL/login")
check "admin login redirects" "302" "$STATUS"

# ── 3. Page load checks (as admin) ─────────────────────────────────────────
echo
blue "→ Page loads (as admin)..."
for path in / /inventory /treatments /log /suggestions; do
  STATUS=$(curl -s -b "$ADMIN_COOKIE" -o /dev/null -w '%{http_code}' "$BASE_URL$path")
  check "GET $path" "200" "$STATUS"
done

# ── 4. CSRF protection — admin POST without a token must 400 ──────────────
echo
blue "→ CSRF protection..."
STATUS=$(curl -s -b "$ADMIN_COOKIE" -o /dev/null -w '%{http_code}' \
  -X POST "$BASE_URL/inventory/1/delete")
check "POST without csrf_token rejected" "400" "$STATUS"

# ── 5. Role enforcement — viewer with valid CSRF should still be blocked ──
echo
blue "→ Role enforcement (as viewer)..."
LOGIN_PAGE=$(curl -s -c "$VIEWER_COOKIE" "$BASE_URL/login")
TOKEN=$(extract_token "$LOGIN_PAGE")
STATUS=$(curl -s -b "$VIEWER_COOKIE" -c "$VIEWER_COOKIE" -o /dev/null -w '%{http_code}' \
  -d "identifier=$VIEWER_EMAIL&password=$VIEWER_PASS&csrf_token=$TOKEN" \
  "$BASE_URL/login")
check "viewer login redirects" "302" "$STATUS"

# Fresh token tied to the post-login session
DASHBOARD=$(curl -s -b "$VIEWER_COOKIE" "$BASE_URL/")
VIEWER_TOKEN=$(extract_token "$DASHBOARD")
if [ -z "$VIEWER_TOKEN" ]; then
  red "  FAIL: viewer dashboard has no csrf_token (logout form should provide one)"
  exit 1
fi

STATUS=$(curl -s -b "$VIEWER_COOKIE" -o /dev/null -w '%{http_code}' \
  -d "csrf_token=$VIEWER_TOKEN" \
  -X POST "$BASE_URL/inventory/1/delete")
check "viewer with CSRF still cannot delete" "302" "$STATUS"

# ── 6. Data integrity — item 1 must still exist after both attacks ────────
echo
blue "→ Inventory integrity..."
COUNT=$(sqlite3 farm_manager.db "SELECT COUNT(*) FROM inventory_items WHERE id=1;")
check "inventory item 1 still present" "1" "$COUNT"

# ── Summary ───────────────────────────────────────────────────────────────
echo
echo "──────────────────────────────"
printf "  Passed: %d\n" "$PASS"
printf "  Failed: %d\n" "$FAIL"
echo "──────────────────────────────"
if [ "$FAIL" -eq 0 ]; then
  green "All smoke checks passed."
  exit 0
else
  red "Some checks failed. See /tmp/farm_smoke.log for server output."
  exit 1
fi

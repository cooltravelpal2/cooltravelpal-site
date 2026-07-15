#!/bin/bash
# Route-protection check for cooltravelpal.com.
#
# Local mode (default):   ./tests/check_routes.sh
#   Verifies each protected route resolves to a file in the repo
#   (GitHub Pages serves <route>/index.html for directory routes).
#
# Live mode:              ./tests/check_routes.sh --live
#   Curls https://cooltravelpal.com<route> and requires HTTP 200
#   without a redirect to an unrelated page. Run after deploying.
set -u
cd "$(dirname "$0")/.."

ROUTES_FILE="tests/protected-routes.txt"
MODE="${1:-local}"
FAIL=0

while IFS= read -r route; do
  [[ -z "$route" || "$route" == \#* ]] && continue

  if [[ "$MODE" == "--live" ]]; then
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://cooltravelpal.com${route}")
    if [[ "$code" == "200" ]]; then
      echo "OK   200  $route"
    else
      echo "FAIL $code $route"
      FAIL=1
    fi
  else
    if [[ "$route" == */ ]]; then
      f=".${route}index.html"
    else
      f=".${route}"
    fi
    if [[ -s "$f" ]]; then
      echo "OK   $route -> $f"
    else
      echo "FAIL $route (missing or empty: $f)"
      FAIL=1
    fi
  fi
done < "$ROUTES_FILE"

if [[ $FAIL -eq 1 ]]; then
  echo "ROUTE PROTECTION FAILURE — do not deploy."
  exit 1
fi
echo "All protected routes present."

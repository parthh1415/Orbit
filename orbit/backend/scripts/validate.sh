#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$(dirname "$BACKEND_DIR")/frontend"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC} $1"; }
fail() { echo -e "${RED}FAIL${NC} $1"; exit 1; }

echo "=== ORBIT Validation ==="
echo ""

echo "--- Backend: ruff check ---"
cd "$BACKEND_DIR"
ruff check app/ tests/ && pass "ruff check" || fail "ruff check"

echo "--- Backend: ruff format ---"
ruff format --check app/ tests/ && pass "ruff format" || fail "ruff format"

echo "--- Backend: mypy ---"
mypy app/ && pass "mypy" || fail "mypy"

echo "--- Backend: pytest ---"
pytest --tb=short -q && pass "pytest" || fail "pytest"

echo ""
echo "--- Frontend: typecheck ---"
cd "$FRONTEND_DIR"
npx tsc --noEmit && pass "tsc" || fail "tsc"

echo "--- Frontend: eslint ---"
npx eslint 'src/**/*.{ts,tsx}' && pass "eslint" || fail "eslint"

echo "--- Frontend: prettier ---"
npx prettier --check 'src/**/*.{ts,tsx,css}' && pass "prettier" || fail "prettier"

echo "--- Frontend: vitest ---"
npx vitest run && pass "vitest" || fail "vitest"

echo ""
echo -e "${GREEN}=== All checks passed ===${NC}"

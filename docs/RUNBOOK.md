# Runbook

Version: 0.1  
Date: March 1, 2026

## 1. Purpose

Operational quick-start for local bring-up, CI-parity validation, and first-response triage.

## 2. Prerequisites

- Python 3.12+
- Node.js 20+
- npm 10+
- `make`

## 3. Local Bring-Up

Install web dependencies:

```bash
npm --prefix apps/dashboard-web ci
```

Start API services in separate shells:

```bash
uvicorn main:app --app-dir apps/observability-api/src --reload --port 8000
uvicorn main:app --app-dir apps/dashboard-api/src --reload --port 8001
```

## 4. CI-Parity Validation

Run the same top-level gate used by CI:

```bash
make test
```

This executes:

- `make test-python` (`pytest -q` + `python3 -m compileall -q apps`)
- `make test-web` (`typecheck` + e2e test suite)

## 5. Failure Triage

### Python import path failures

Symptoms:

- `ModuleNotFoundError` when tests/scripts import app modules.

Checks:

- Run commands from repo root.
- Verify `pytest.ini` is present and root path is used.
- For direct script execution, prepend the correct source path or use module execution.

Examples:

```bash
python3 -m pytest -q
python3 -m compileall -q apps
```

### Playwright/browser dependency failures

Symptoms:

- e2e failures mentioning missing Chromium executable.

Fix:

```bash
npm --prefix apps/dashboard-web exec playwright install chromium
```

Re-run:

```bash
make test
```

### Web typecheck regressions

Symptoms:

- `npm --prefix apps/dashboard-web run typecheck` fails.

Checks:

- Keep test typings aligned with `tests/e2e/playwright-shim.d.ts`.
- Avoid adding Node module imports without matching local shim declarations.

## 6. Release Checks (Prototype)

Before cutting a release:

- `make test` passes locally.
- `CI` workflow is green on `master`.
- `master` branch protection remains enabled (required checks + required PR approval).

# AGENTS.md

## Purpose

`portfolio-dashboard` is the user-facing application. It combines a FastAPI backend with a bundled
React frontend, reads the external portfolio data workspace, and starts loader refreshes through
installed CLI process boundaries. A checkout of the loader repositories is not required.

## Dependency And Runtime Map

| Package/workspace | How the dashboard uses it |
| --- | --- |
| `portfolio-core` | Settings, data-root selection, schema validation, metadata, paths, and forex lookup. |
| `portfolio-market-data` | Installed runtime dependency. Its deliberate `dashboard_data` read contract is imported; refresh jobs invoke its CLI. |
| `portfolio-crypto-data` | Its Nexo and on-chain read contracts are imported; refresh jobs invoke its CLI. |
| `portfolio-data` | External runtime workspace read by API services and mutated only through explicit refresh jobs. It is not source code and is not bundled in the wheel. |

No first-party package depends on the dashboard. It is the top-level application and composition
root.

## Application Map

- `portfolio_dashboard.cli`: configures the data root and serves on `127.0.0.1` only.
- `portfolio_dashboard.main`: explicit `create_app(context=...)` factory, FastAPI routes,
  localhost guards, and static frontend mounting.
- `portfolio_dashboard.services`: dependency read models and compact JSON payload construction.
- `portfolio_dashboard.arbitrum`: strict reader for the consumed Arbitrum dashboard artifacts.
- `portfolio_dashboard.real_estate`: one-pass real-estate loading and dashboard calculations.
- `portfolio_dashboard.refresh_jobs`: one-at-a-time subprocess orchestration for prices,
  transactions, crypto, and combined refreshes.
- `frontend/`: editable TypeScript/React source.
- `static/`: generated production assets bundled in the wheel.
- `scripts/test-all.ps1`: coordinated developer checks for every sibling package and the optional
  tag-backed data environment.

## Refactoring Policy

- Favor a coherent current UI/API over backward compatibility with the old Dash app or monorepo
  namespaces.
- Change Python and TypeScript interfaces freely when both sides are updated in the same refactor.
- Do not add duplicate routes, legacy JSON keys, deprecated component props, adapter modules, or
  old package namespaces unless the user explicitly requests a transition period.
- Remove replaced code rather than leaving parallel implementations.
- Keep data loading and mutation in the loader packages. The dashboard coordinates their CLIs and
  consumes deliberate read contracts; it must not fork their business logic.
- Keep reusable path, schema, metadata, and price rules in `portfolio-core`.
- Prefer a schema/version bump and coordinated reader update over permissive parsing of multiple
  historical layouts.

The frontend/backend API is an internal application contract. Breaking it is encouraged when it
simplifies the design, provided routes, TypeScript types, tests, and the bundled build are updated
together.

## Stable Operational Invariants

- Bind only to `127.0.0.1`; do not expose the private dashboard on all interfaces.
- Mutating stop and refresh endpoints must remain loopback-only.
- Only one refresh job may mutate the data workspace at a time.
- Subprocess commands must be argument lists, never shell-constructed strings.
- The installed wheel must serve `static/index.html` without Node.js or a source checkout.
- `frontend/node_modules` and frontend source must not enter the wheel.
- API services should tolerate absent optional private datasets by returning useful empty states,
  but should not hide genuine contract violations.

## Frontend Workflow

Do not edit hashed files in `static/assets` manually. Change `frontend/src`, then rebuild:

```powershell
cd src\portfolio_dashboard\frontend
npm.cmd ci
npm.cmd audit --audit-level=low
npm.cmd run build
```

Commit the updated `package-lock.json` and generated `static/` assets. Keep the production bundle
reproducible and verify that `npm audit` reports no known vulnerabilities.

## Release Coordination

- Core, market, and crypto dependencies are pinned to Git tags in `pyproject.toml` and `uv.lock`.
- Upgrade and release dependencies first, then update all three source tags here.
- Rebuild the frontend, run the backend suite, build the wheel, and test an install without sibling
  repositories.
- Never move a published tag; publish a new dashboard version.

## Development

`[project].dependencies` must retain immutable Git tags so the wheel installs without sibling
checkouts. `[tool.uv.sources]` deliberately overrides all three first-party dependencies with
editable sibling paths only when synchronizing this repository. Keep both halves of that setup.

Use `scripts/test-all.ps1` for the coordinated local package suite. Pass `-Frontend` for npm audit
and the production bundle, and `-DataWorkspace <path>` to validate the separate tag-backed
end-user environment.

```powershell
uv sync
uv run ruff check src tests
uv run python -m pytest
uv build
uv run portfolio-dashboard configure --data-dir C:\path\to\portfolio-data
uv run portfolio-dashboard serve --no-open
```

Do not start real refresh jobs during tests or routine refactoring. Mock the job runner and use
temporary workspaces. The actual virtual environment belongs in uv's centralized cache.

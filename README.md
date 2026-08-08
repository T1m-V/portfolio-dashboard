# Portfolio dashboard

FastAPI backend and bundled React frontend for the portfolio data workspace. The wheel depends on
the core, market-data, and crypto-data packages, so the source repositories do not need to be
checked out after installation.

## End-user setup

Install the released dashboard and configure a data workspace. The uv tool environment installs
the tagged core and loader packages, never local source paths:

```powershell
uv tool install "portfolio-dashboard @ git+https://github.com/T1m-V/portfolio-dashboard.git@v0.2.0"
portfolio-dashboard configure --data-dir "C:\path\to\portfolio-data"
portfolio-dashboard serve
```

The server binds to `127.0.0.1` only and opens at <http://127.0.0.1:8000>. Price, Getquin, crypto,
and combined refresh jobs can be started from the sidebar. Job output and status remain available
through the local API while the process is running.

No source checkout is needed after installation. To upgrade later, repeat the install command with
the newer release tag.

## Developer setup

Keep all four source repositories as siblings:

```text
C:\Users\timvo\source\portfolio\
|-- portfolio-core\
|-- portfolio-market-data\
|-- portfolio-crypto-data\
`-- portfolio-dashboard\
```

The dashboard's `[tool.uv.sources]` maps all first-party dependencies to those sibling directories
in editable mode. A normal sync therefore imports your working-tree code immediately:

```powershell
cd C:\Users\timvo\source\portfolio\portfolio-dashboard
uv sync --frozen
uv run python -c "from pathlib import Path; import portfolio_core, portfolio_crypto_data, portfolio_market_data; print(Path(portfolio_core.__file__).resolve()); print(Path(portfolio_crypto_data.__file__).resolve()); print(Path(portfolio_market_data.__file__).resolve())"
uv run portfolio-dashboard serve --data-dir "C:\path\to\portfolio-data"
```

Run every Python package's sync, lint, tests, and wheel build from one command:

```powershell
.\scripts\test-all.ps1
```

Include the reproducible frontend install, audit, and production build, and optionally validate the
tag-backed end-user data environment:

```powershell
.\scripts\test-all.ps1 -Frontend -DataWorkspace "C:\Users\timvo\OneDrive\Documenten\Projects\portfolio-data"
```

The actual environments live in uv's centralized cache under `%LOCALAPPDATA%\uv`; `.venv` entries
inside the checkouts are lightweight junctions. The editable mappings affect only `uv sync` in a
source checkout. They are excluded from wheel metadata, whose dependencies remain immutable Git
tags.

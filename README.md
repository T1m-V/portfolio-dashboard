# Portfolio dashboard

FastAPI backend and bundled React frontend for the portfolio data workspace. The wheel depends on
the core, market-data, and crypto-data packages, so the source repositories do not need to be
checked out after installation.

```powershell
uv sync
uv run portfolio-dashboard configure --data-dir "C:\path\to\portfolio-data"
uv run portfolio-dashboard serve
```

The server binds to `127.0.0.1` only and opens at <http://127.0.0.1:8000>. Price, Getquin, crypto,
and combined refresh jobs can be started from the sidebar. Job output and status remain available
through the local API while the process is running.

uv stores this project's environment in its local centralized cache rather than beside the repo.

For an installation that does not require any source checkout:

```powershell
uv tool install "portfolio-dashboard @ git+https://github.com/T1m-V/portfolio-dashboard.git@v0.2.0"
portfolio-dashboard configure --data-dir "C:\path\to\portfolio-data"
portfolio-dashboard serve
```

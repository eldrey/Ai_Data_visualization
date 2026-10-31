# AI Data Visualization

Build dashboards by describing charts in plain language. An LLM (Claude, OpenAI or Gemini) writes the chart code from your request, and the app runs it against your own data sources: PostgreSQL, Neon, or local CSV/XLSX files.

- Python + Streamlit frontend, packaged as a Docker container
- **Read-only** access to data sources
- No local database: configuration lives in a YAML file and charts are saved as Python scripts
- No authentication (meant for local or trusted-network use)

## Quick start

Requirements: Docker with Compose and `make`.

```bash
make up        # build and start → http://localhost:8501
make demo      # same, plus a sample PostgreSQL database with sales data
make down      # stop everything
```

`make up` creates `.env` from `.env.example` the first time. Put your LLM API keys there, then restart with `make up`.

When using `make demo`, add this data source in the UI:

| Field    | Value           |
| -------- | --------------- |
| Type     | PostgreSQL      |
| Host     | `postgres-demo` |
| Port     | `5432`          |
| Database | `demo`          |
| User     | `leitor`        |
| Password | `leitor`        |

### All make targets

| Target         | Description                                         |
| -------------- | --------------------------------------------------- |
| `make up`      | Build and start the app in Docker                   |
| `make demo`    | Start the app plus the demo PostgreSQL database     |
| `make down`    | Stop all containers                                 |
| `make logs`    | Follow the app logs                                 |
| `make build`   | Build the Docker image only                         |
| `make install` | Install dependencies locally with uv                |
| `make dev`     | Run the app locally, without Docker                 |
| `make test`    | Run unit tests with coverage (fails below 60%)      |
| `make clean`   | Remove caches and coverage files                    |

## Using the app

1. **Data sources**: add PostgreSQL or Neon connections, or point to a CSV/XLSX file or folder. Use *Test connection* to check it.
2. **Explorer**: browse schemas, tables and columns, preview rows, and run `SELECT` queries.
3. **LLM**: choose the provider and model and enter the API key, then use *Test* to check it.
4. **Generate chart**: pick a source and tables, give the chart a title and describe it. The LLM returns a script that you can review, edit and preview before saving it to a panel.
5. **Dashboard**: organize charts into named **panels** (e.g. *Sales*, *Operations*):
   - switch panels from the selector at the top. The current panel is kept in the URL (`?painel=<name>`), so it can be bookmarked;
   - create, rename or delete panels under *Gerenciar painéis*. There is always at least one panel;
   - choose each panel's charts and column count. The same chart can appear on several panels;
   - **🔄 Atualizar** re-runs the queries. Results are otherwise cached, so interacting with the page does not query the databases again;
   - each chart can be **removed** from the current panel (the script is kept) or **deleted** permanently (the file is removed and the chart disappears from every panel).

## Configuration

### `config/settings.yaml`

Created and updated by the UI. It stores data sources, the LLM settings and the panels (name, charts and columns of each). Files written by older versions (a single `dashboard:` entry) are migrated automatically to a panel named *Principal*. See [config/settings.example.yaml](config/settings.example.yaml).

To keep secrets out of this file, write any password or API key as `${ENV_VAR}`. It is then read from the environment (`.env`):

```yaml
llm:
  provider: anthropic          # anthropic | openai | gemini
  model: claude-opus-5-5
  api_key: ${ANTHROPIC_API_KEY}
```

### Environment variables

| Variable                 | Purpose                                                          |
| ------------------------ | ---------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`      | Claude API key                                                   |
| `OPENAI_API_KEY`         | OpenAI API key                                                   |
| `GEMINI_API_KEY`         | Google Gemini API key                                            |
| `APP_CONFIG_PATH`        | Settings file path (default `config/settings.yaml`)              |
| `DASHBOARD_SCRIPTS_DIR`  | Folder for chart scripts (default `src/dashboards_scripts`)      |

### Docker volumes

| Host path                 | Container path                 | Content                                       |
| ------------------------- | ------------------------------ | --------------------------------------------- |
| `./config`                | `/app/config`                  | `settings.yaml`                               |
| `./src/dashboards_scripts`| `/app/src/dashboards_scripts`  | Saved chart scripts                           |
| `./data`                  | `/app/data`                    | Local CSV/XLSX files (use `/app/data` as path)|

To reach a PostgreSQL server running on the host machine, use `host.docker.internal` as the host.

## Architecture

```text
┌──────────────────────────── Streamlit UI (src/pages) ─────────────────────────────┐
│  Dashboard   Generate chart   Explorer   Data sources   LLM settings             │
└───────┬──────────────┬─────────────┬────────────┬──────────────┬─────────────────┘
        │              │             │            │              │
        ▼              ▼             ▼            ▼              ▼
  script_runner  chart_generator  DataSource   config/settings  LLMClient
        │         │         │        │          (YAML file)   (Claude/OpenAI/Gemini)
        │         │         └──► code_validator + sql_guard
        │         ▼
        │    script_store ──► src/dashboards_scripts/*.py
        ▼
  subprocess (runner_entry.py): build_chart(df) ──► Plotly figure (JSON)
```

### Project layout

```text
src/
├── app.py                      # Streamlit entry point (navigation)
├── pages/                      # UI only; logic lives in services
├── config/settings.py          # Pydantic models, YAML load/save, ${ENV} resolution
├── services/
│   ├── db_connections/         # DataSource interface, PostgresSource, FileSource, factory
│   ├── llm_connections/        # LLMClient interface, Anthropic/OpenAI/Gemini clients, factory
│   ├── sql_guard.py            # Read-only SQL validation + default LIMIT
│   ├── code_validator.py       # AST validation of generated scripts
│   ├── chart_generator.py      # Prompt building, LLM call, validation, one retry
│   ├── script_store.py         # Save/list/load/delete chart scripts
│   └── script_runner.py        # Runs query + build_chart in an isolated subprocess
├── utils/                      # Code extraction, subprocess entry point, UI state helpers
└── dashboards_scripts/         # Saved charts (Docker volume)
tests/                          # pytest suite mirroring src/
```

### Data sources

All sources implement the same `DataSource` interface (`list_schemas`, `list_tables`, `get_columns`, `preview`, `run_query`):

- **PostgreSQL / Neon**: SQLAlchemy 2 + psycopg 3. Neon is treated as PostgreSQL with `sslmode=require` by default.
- **CSV / XLSX**: files are loaded into an **in-memory** DuckDB, which is never written to disk. A CSV file becomes one table. Each sheet of a single XLSX file becomes its own table, and in a folder of XLSX files tables are named `<file>_<sheet>`. This lets file sources use the same SQL contract as databases.

### Chart scripts

Every chart is a standalone Python file in `src/dashboards_scripts/<slug>.py`:

```python
import pandas as pd
import plotly.express as px

METADATA = {"title": "Sales by month", "source": "demo", "prompt": "...", "created_at": "..."}

SQL = "SELECT date_trunc('month', data) AS month, SUM(valor) AS total FROM vendas GROUP BY 1 ORDER BY 1"

def build_chart(df: pd.DataFrame):
    return px.bar(df, x="month", y="total", title="Sales by month")
```

To render a chart, the app looks up the source named in `METADATA` and runs `SQL` on it (read-only). It then passes the resulting DataFrame to `build_chart` in a subprocess and displays the Plotly figure that comes back.

### Chart generation flow

1. The system prompt describes the script contract, the allowed imports and the SQL dialect (`postgres` or `duckdb`).
2. The user prompt includes the selected tables' columns and types, 5 sample rows per table, and the request.
3. The response goes through these steps: code is extracted from it, `METADATA` is injected, the AST is validated, and `sql_guard` checks the SQL. If any check fails, the errors are sent back to the LLM for **one** retry.
4. You review and edit the code (it is re-validated on every change), preview it, and save it.

### LLM providers

| Provider  | SDK             | Default model     | Notes                                                       |
| --------- | --------------- | ----------------- | ----------------------------------------------------------- |
| Anthropic | `anthropic`     | `claude-opus-5-5` | Server-side refusal fallback enabled; temperature not sent  |
| OpenAI    | `openai`        | `gpt-5`           | Responses API                                               |
| Gemini    | `google-genai`  | `gemini-2.5-pro`  | Uses the configured temperature                             |

The model name can be changed in the UI.

## Security model

The app never writes to data sources, and LLM-generated code is treated as untrusted:

| Layer                 | Protection                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------ |
| SQL validation        | `sqlglot` accepts exactly one `SELECT` / `WITH … SELECT`. DML, DDL, `SELECT INTO` and multiple statements are rejected. A default `LIMIT` is applied. |
| PostgreSQL            | Every query runs inside a `SET TRANSACTION READ ONLY` transaction that is always rolled back                  |
| DuckDB (files)        | `enable_external_access = false` and locked configuration, so queries cannot read arbitrary files or URLs     |
| Code validation (AST) | Imports limited to `pandas`, `numpy`, `plotly`, `math`, `datetime`, `statistics`. `open`, `exec`, `eval`, `getattr`, `__import__`, dunder access and `global` are blocked |
| Execution sandbox     | `python -I` subprocess with timeout (30 s), memory (2 GB) and CPU limits, and an empty environment, so API keys are not visible to the script |

Also connect with a database user that has `SELECT`-only privileges. See [docker/demo-init.sql](docker/demo-init.sql) for an example.

## Development

The project uses [uv](https://docs.astral.sh/uv/) for dependency management (Python 3.12).

```bash
make install                 # uv sync
make dev                     # uv run streamlit run src/app.py (loads .env automatically)
make test                    # uv run pytest (coverage report, fails below 60%)
uv add <package>             # add a runtime dependency
uv add --dev <package>       # add a dev dependency
```

The suite covers settings, SQL guard, AST validation, data sources (DuckDB, and SQLite standing in for SQLAlchemy), mocked LLM clients, chart generation with a fake LLM, the script store and runner, and smoke tests for every page using Streamlit's `AppTest`.

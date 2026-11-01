# DashMCP PBI

[![dash_mcp MCP server](https://glama.ai/mcp/servers/a-negi/dash_mcp/badges/card.svg)](https://glama.ai/mcp/servers/a-negi/dash_mcp)
[![dash_mcp MCP server](https://glama.ai/mcp/servers/a-negi/dash_mcp/badges/score.svg)](https://glama.ai/mcp/servers/a-negi/dash_mcp)
[![smithery badge](https://smithery.ai/badge/a-negi/dash_mcp)](https://smithery.ai/server/a-negi/dash_mcp)

Generate Power BI (`.pbit`) dashboards from CSV files or live SQL databases — locally, on your own machine, in seconds.

DashMCP profiles your data, designs a sensible dashboard layout (KPI cards + charts + filters), compiles it to a Power BI template, and writes the result to disk. Open the `.pbit` in Power BI Desktop and you have a working report.

---

## Highlights

- **CSV upload** — drop a single `.csv`, get a `.pbit`. No Power BI required to generate it.
- **Live SQL sources** — SQL Server, PostgreSQL, Oracle. The generated `.pbit` queries the database on open; credentials are never embedded.
- **Plain-English prompts** — describe what you want (*"bar chart company by revenue, line of growth over year"*). Powered by Groq (Llama 3.3 70B) — bring your own API key. Without a key, DashMCP still produces a sensible default dashboard from a CSV profile; the prompt is ignored.
- **Layout from a reference image** — drop in a screenshot of a dashboard you like. DashMCP reads the structure (card count, chart types, filter panel) and applies it to the generated layout, then adopts the color palette as the report theme.
- **Multiple chart types** — bar, column, line, area, pie, donut, scatter, table. KPI cards. Slicers.
- **Browser UI** — runs on `http://127.0.0.1:8000/`. Local-only by default.
- **MCP server** — exposes the same tools to Claude Desktop over stdio for "/" prompts inside Claude.

---

## Quick start

```powershell
# 1. Clone
git clone https://github.com/a-negi/dash_mcp.git
cd dash_mcp

# 2. Install Python deps (creates .venv)
.\setup_local.ps1

# 3. Install pbi-tools.core somewhere on PATH or at C:\pbi-tools\
#    Download: https://github.com/pbi-tools/pbi-tools/releases

# 4. Start the local server
.\run_api.ps1
```

Open <http://127.0.0.1:8000/> in your browser.

If you'd rather use DashMCP inside Claude Desktop, see [LOCAL_SETUP.md](LOCAL_SETUP.md) for the stdio MCP setup.

---

## The browser UI

| Field | What it does |
|-------|--------------|
| **Data source** | Pick `CSV file` or one of the SQL connectors. |
| **CSV file** | Single CSV with a header row. Columns are profiled automatically (measures, dimensions, dates, geographic fields). |
| **SQL fields** | `Server`, `Database`, `Schema`, `Table` (or a free-form `SELECT` query). Username/password used **only** for profiling — never embedded in the `.pbit`. |
| **Prompt** | Plain-English description of what you want to see. Requires an LLM key (see "AI assistance" below). Without a key the prompt is ignored and you get the deterministic default dashboard. |
| **Style reference image** | Optional PNG/JPG. DashMCP reads the dashboard structure (number of KPI cards, chart types, filter panel presence) using Groq Vision and mirrors that layout in the generated report. Colors are also extracted and applied as the report theme. |
| **AI assistance** | Required for prompts to take effect. Pick Groq/OpenAI and paste an API key, or pick local Qwen through Ollama. Only column **names** (not data rows) are sent to the model. |

The downloaded `.pbit` opens in Power BI Desktop, prompts for any data-source credentials, and renders the dashboard.

---

## How prompts work

DashMCP always runs the deterministic dashboard builder (KPI cards, headline bar/line chart, donut for low-cardinality dims, second "Breakdowns" page when the dataset is rich). On top of that, if you supply an LLM key, your prompt is interpreted and additional visuals are appended.

What the LLM sees:
- Your prompt
- Column names + roles (`measure` / `dimension`)
- Column semantic types (`temporal`, `geographic`, `categorical`, etc.)
- Visuals the deterministic builder already produced (so it doesn't duplicate them)

What it does NOT see: any of your data rows.

The model returns a JSON list of chart specs (type, x-axis column, y-axis column, title); DashMCP validates each spec against the column profile and adds the ones that pass.

The response header `X-DashMCP-Parser` tells you which path ran for any given generate (`llm:groq`, `llm:openai`, `llm:qwen`, `llm:<provider>-empty`, `no-key`, or `deterministic-only`). The UI shows this under each "Report ready" message.

---

## SQL data sources

DashMCP ships with **lazy** driver imports — the base install works for CSV-only use. Install drivers only for the databases you need:

```powershell
# SQL Server (also needs the Microsoft ODBC Driver 17 or 18, installed system-wide)
.\.venv\Scripts\python.exe -m pip install pyodbc

# PostgreSQL
.\.venv\Scripts\python.exe -m pip install psycopg2-binary

# Oracle (thin mode - no Oracle client install required)
.\.venv\Scripts\python.exe -m pip install oracledb
```

In the UI, pick the source kind from the **Data source** dropdown. DashMCP:

1. Connects with the credentials you supply.
2. Pulls `SELECT TOP 1000` (or `LIMIT 1000`) to profile column types, cardinality, and roles.
3. Generates a Power Query M expression that Power BI Desktop will use to fetch the **full** dataset live.
4. Compiles everything into a `.pbit`.

The credentials never make it into the `.pbit` file — Power BI Desktop will prompt for sign-in on first open. This is the standard Power BI Template behavior.

### Example: SQL Server

| Field | Example |
|-------|---------|
| Server | `db-prod.corp.com,1433` or `localhost\SQLEXPRESS` |
| Database | `AdventureWorks2022` |
| Schema | `Sales` (defaults to `dbo`) |
| Table | `Customer` |
| Username/Password | Leave blank for Windows auth, fill for SQL auth. |

### Example: free-form query

Paste a `SELECT` (with joins, filters, anything) into the **Or: SELECT query** box. DashMCP will profile the first 1000 rows of the result and target the same query in the generated M.

---

## AI assistance

| Provider | Model used | Where to get a key |
|----------|------------|---------------------|
| Groq | `llama-3.3-70b-versatile` | <https://console.groq.com/keys> |
| OpenAI | `gpt-4o-mini` | <https://platform.openai.com/api-keys> |
| Local Qwen | Auto-detected Ollama Qwen model, or `QWEN_MODEL` / `OLLAMA_MODEL` | No API key required |

What gets sent to the model:
- Your prompt
- The list of column names + their inferred roles
- The list of visuals already generated by the deterministic builder
- **Nothing else.** Your data rows never leave your machine.

The key is cached in the browser tab's `sessionStorage` so you don't have to re-paste it on every generate. It's wiped when the tab closes.

For local Qwen, choose **Local Qwen 2.5 (Ollama)** in the provider dropdown. The Windows installer bundles a CPU-only Ollama runtime and will start it when DashMCP launches; `qwen2.5:3b` is pulled on first use if it is missing, so the first Qwen generation can take a few minutes and needs internet access. DashMCP calls `http://127.0.0.1:11434` by default; override with `QWEN_OLLAMA_URL` or `OLLAMA_HOST` if your Ollama server runs elsewhere.

If you skip the key, DashMCP falls back to the deterministic dashboard builder only. Your prompt has no effect in that case — the dashboard is built purely from the column profile.

---

## Style reference image

Drop any PNG/JPG (a screenshot of a dashboard you like, a brand mockup, a Tableau page). DashMCP runs two extractions in parallel:

**Layout extraction (Groq Vision, requires Groq key)**
Reads the structural layout of the reference dashboard:
- How many KPI/metric cards are visible → used as the KPI card count in the generated report
- Which chart types are present (bar, column, line, area, donut, etc.) → influences chart type selection
- Whether a right-side filter/slicer panel exists → adds or omits a slicer panel
- Whether the KPI cards are in a left-column rail or a top-row grid → picks the matching layout template

**Palette extraction (Groq Vision, or local Pillow fallback)**
Extracts the color scheme:
- Primary, secondary, and accent colors
- Page canvas background
- Chart series palette (8-color rotation)

The layout extraction requires a `GROQ_API_KEY`. If no key is available, DashMCP still samples colors locally with Pillow and the layout falls back to the data-driven default.

---

## API endpoints

All endpoints are local-only (`127.0.0.1:8000`).

| Method + path | Purpose |
|---------------|---------|
| `GET /health` | Liveness probe. |
| `GET /` | The browser UI. |
| `POST /generate-from-csv` | Multipart: `csv_file`, `prompt`, `image_file?`, `llm_provider?`, `llm_api_key?`. Returns the `.pbit` file. |
| `POST /generate-from-source` | Multipart: `kind`, `server`, `database`, `schema`, `table` or `query`, `username`, `password`, `prompt`, `image_file?`, `llm_provider?`, `llm_api_key?`. Returns the `.pbit`. |
| `POST /generate` | LLM-only path (requires `GROQ_API_KEY` env var). For Claude Desktop. |
| `/mcp/*` | The MCP server, exposed over HTTP. Used by Claude Desktop and other MCP-aware clients. |

For Claude Desktop integration over stdio, point the launcher at `run_mcp_stdio.ps1` — see [LOCAL_SETUP.md](LOCAL_SETUP.md).

---

## Windows installer (single .exe for end users)

A double-clickable installer is available for users who don't want to run `setup_local.ps1`. It bundles Python, all dependencies, the FastAPI app, and `pbi-tools.core` into one `.exe`. See [installer/README.md](installer/README.md) for the build process. End-user install flow:

1. Download `DashMCP-PBI-Setup-1.0.3.exe` (or the latest version).
2. Run it (admin required — installs into `Program Files`).
3. Start Menu → **DashMCP PBI**. The server starts and your browser opens automatically.
4. User data (generated reports, sources, sessions) lives at `%LOCALAPPDATA%\DashMCP\` and survives reinstall/uninstall.

---

## Power BI Desktop External Tool button

Optional. Adds a **DashMCP PBI** button to the External Tools ribbon in Power BI Desktop. See [EXTERNAL_TOOL_SETUP.md](EXTERNAL_TOOL_SETUP.md).

> Some tenants block External Tools registration via Fabric tenant policy. If the ribbon button doesn't appear after registering, the browser UI still works — just open <http://127.0.0.1:8000/> directly.

---

## Architecture (one screen)

```
                ┌──────────────┐
   CSV / SQL → ┤ data_profiler / data_sources ┤ → DatasetProfile
                └──────────────┘
                        │
                        ▼
                  build_intent_from_profile      (deterministic)
                        │
                        │  + prompt parser (regex OR LLM)
                        │  + image layout hint extractor  (Claude Vision)
                        │  + image palette extractor      (Claude Vision / Pillow)
                        ▼
                  ReportIntent (Pydantic)
                        │
                        ▼
                  build_bim_from_profile  →  semantic model (BIM JSON)
                  build_m_for_source      →  Power Query M
                  build_layout_from_intent →  report layout (visuals + theme)
                        │

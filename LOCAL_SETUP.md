# Local Setup for Claude Desktop

This project is intended to run locally as a Claude Desktop MCP server. Local
setup is preferred because Power BI report generation needs local CSV access and
saves `.pbit` files for Power BI Desktop.

## 1. Install Prerequisites

Install:

- Python 3.11+
- Power BI Desktop
- pbi-tools.core

`pbi-tools.core` must be available in one of these ways:

- On `PATH` as `pbi-tools.core.exe` / `pbi-tools.core`
- On `PATH` as `pbi-tools`
- At `C:\pbi-tools\pbi-tools.core.exe`

Download pbi-tools from the project releases and use the Windows x64 core build.

## 2. Clone and Install

If you received the ZIP package:

```powershell
# Extract dash_mcp-pbi-local.zip first, then:
cd dash_mcp-pbi-local
.\setup_local.ps1
```

If installing from Git:

```powershell
git clone https://github.com/a-negi/dash_mcp.git
cd dash_mcp
.\setup_local.ps1
```

This creates:

- `.venv/`
- `generated_reports/`
- `generated_sources/`
- `.sessions/`

## 3. Configure Claude Desktop

Open your Claude Desktop config file:

```text
%APPDATA%\Claude\claude_desktop_config.json
```

Add this MCP server entry. Update the path if you cloned elsewhere:

```json
{
  "mcpServers": {
    "dash_mcp-pbi": {
      "command": "powershell.exe",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "C:\\Users\\z0051snb\\Desktop\\pbix\\dash_mcp-pbi\\run_mcp_stdio.ps1"
      ],
      "env": {
        "GROQ_API_KEY": "optional-only-needed-for-llm-features"
      }
    }
  }
}
```

Restart Claude Desktop after editing the config.

## 4. Groq Key Rules

For CSV-to-dashboard generation, a Groq key is not required.

No key needed for:

- `create_dashboard`
- `create_from_csv_file_path`
- `create_from_csv_text`
- `create_from_csv`
- `export_pbit_file`
- `get_report_state`

Key needed for Groq-powered features:

- `create_report`
- `add_visual`
- `edit_styling`
- `apply_image_theme`
- `add_filter`

Because the MCP runs locally under Claude Desktop, you can put the key in the
MCP server `env` block above or set it as a normal Windows environment variable.

## 5. Example Prompts in Claude

```text
Use DashMCP PBI to create a dashboard from:
C:\Users\me\Downloads\sales.csv
Title it "Sales Performance Dashboard".
```

```text
Create a Power BI dashboard from this CSV text and save it locally:
<paste CSV here>
```

```text
Export the current report as a local PBIT file.
```

Generated reports are saved in:

```text
generated_reports/
```

Report filenames are intentionally shortened for Power BI Desktop/Windows
compatibility. Long prompts are treated as styling instructions, not as literal
file names.

## 6. Optional Local API

You can also run a local HTTP server:

```powershell
.\run_api.ps1
```

Endpoints:

- `GET http://127.0.0.1:8000/health`
- `POST http://127.0.0.1:8000/generate-from-csv`
- `GET http://127.0.0.1:8000/session/{session_id}/export`
- MCP HTTP mount: `http://127.0.0.1:8000/mcp`

## 7. Troubleshooting

If Power BI rendering fails, regenerate with the latest code. The generator now
strips problematic hand-authored sort metadata that caused Desktop renderer
errors in newer Power BI builds.

If Claude cannot start the MCP server:

- Run `.\setup_local.ps1` again.
- Confirm `.venv\Scripts\python.exe` exists.
- Confirm `run_mcp_stdio.ps1` path in Claude config is correct.
- Confirm `pbi-tools.core.exe` is on `PATH` or at `C:\pbi-tools\pbi-tools.core.exe`.

If a local CSV path fails:

- Use an absolute Windows path.
- Make sure the file is `.csv`.
- Make sure Claude Desktop has permission to read that folder.

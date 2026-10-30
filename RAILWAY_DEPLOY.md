# Deploy DashMCP PBI MCP on Railway

## Service

Railway will detect the `Dockerfile`. The container starts FastAPI and mounts
the MCP server at:

```text
https://<your-service>.up.railway.app/mcp
```

Healthcheck:

```text
/health
```

## Required Variables

Set these in Railway service variables:

```text
GROQ_API_KEY=<your Groq API key>
PUBLIC_BASE_URL=https://<your-service>.up.railway.app
```

Optional:

```text
OUTPUT_DIR=/tmp/dash_mcp_reports
SESSION_DIR=/tmp/dash_mcp_sessions
```

## Remote Usage Notes

- Remote MCP cannot read files from your laptop path, so avoid
  `create_from_csv_file_path` on Railway.
- Use `create_from_csv`, `create_from_csv_text`, or the HTTP
  `POST /generate-from-csv` endpoint.
- Use `export_pbit_url` to get a downloadable `.pbit` link from Railway.
- Generated files and sessions are ephemeral unless you attach a Railway volume
  and point `OUTPUT_DIR` / `SESSION_DIR` to it.

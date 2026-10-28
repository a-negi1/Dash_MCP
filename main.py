import base64
import re
from pathlib import Path
from fastapi import FastAPI, UploadFile, Form, File
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from orchestrator import (pipeline_create, pipeline_add_visual,
                           pipeline_apply_theme, pipeline_edit_style,
                           pipeline_add_filter, pipeline_export,
                           pipeline_from_csv)
from session_manager import require_session
from mcp_server import mcp, OUTPUT_DIR


def _safe_filename(name: str, max_len: int = 48) -> str:
    safe = re.sub(r"[^A-Za-z0-9_. -]", "_", name).strip(" .-_")
    safe = re.sub(r"\s+", "-", safe)
    safe = safe[:max_len].strip(" .-_")
    return safe or "report"

_mcp_asgi = mcp.http_app(path="/", transport="streamable-http")

app = FastAPI(
    title="DashMCP PBI",
    description="Power BI .pbix generator with image theming, NL editing, and MCP support",
    version="1.0.0",
    lifespan=_mcp_asgi.lifespan,
)

@app.get("/health")
def health():
    return {"status": "ok", "service": "DashMCP PBI"}


@app.get("/.well-known/mcp/server-card.json")
def server_card():
    return JSONResponse({
        "serverInfo": {
            "name": "DashMCP PBI",
            "version": "1.0.0",
            "description": (
                "Generate Power BI .pbit reports from CSV datasets, "
                "natural-language instructions, and reference-image styling. "
                "Works with local files via Claude Desktop MCP."
            )
        },
        "authentication": {
            "type": "none"
        },
        "tools": [
            {"name": "create_dashboard", "description": "Create a Power BI dashboard from a local CSV file path"},
            {"name": "create_from_csv_text", "description": "Create a Power BI dashboard from raw CSV text"},
            {"name": "create_from_csv", "description": "Create a Power BI dashboard from a base64-encoded CSV"},
            {"name": "create_report", "description": "Create a report from a natural language description (requires Groq API key)"},
            {"name": "add_visual", "description": "Add a visual to an existing report session"},
            {"name": "apply_image_theme", "description": "Extract color palette from an image and apply as report theme"},
            {"name": "edit_styling", "description": "Edit report styling via natural language"},
            {"name": "add_filter", "description": "Add a slicer or filter to the report"},
            {"name": "export_pbix", "description": "Export the report as base64-encoded .pbit"},
            {"name": "export_pbit_file", "description": "Save the .pbit file locally and return its path"},
            {"name": "export_pbit_url", "description": "Save the .pbit and return a public download URL"},
            {"name": "get_report_state", "description": "Return the current report structure for inspection"}
        ]
    })


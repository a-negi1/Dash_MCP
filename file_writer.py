import json, os, io, struct, zipfile, shutil
from pathlib import Path
from models import ProjectState

def write_project(state: ProjectState) -> str:
    """Write all project files to state.project_dir. Returns project_dir."""
    base = Path(state.project_dir)
    base.mkdir(parents=True, exist_ok=True)

    _write_pbixproj(base, state.m_code or {})
    _write_version(base)
    _write_report_metadata(base)
    _write_report_settings(base)
    _write_diagram_layout(base)
    _write_bim(base, state.bim or {})
    _write_m(base, state.m_code or {})
    _write_layout(base, state.layout or {})
    if state.theme:
        _write_theme(base, state.theme, state.intent.report_title if state.intent else "Report")
    return str(base)


def _write_pbixproj(base: Path, m_code: dict):
    manifest = {
        "version": "0.10",
        "settings": {
            "model": {"serializationMode": "Raw"},
            "pbiSessions": []
        },
        "queries": {name: "Section1" for name in m_code.keys()}
    }
    (base / ".pbixproj.json").write_text(json.dumps(manifest, indent=2))


def _write_version(base: Path):
    (base / "Version.txt").write_text("1.25")


def _write_report_metadata(base: Path):
    (base / "ReportMetadata.json").write_text(json.dumps({
        "Version": 5,
        "AutoCreatedRelationships": [],
        "FileDescription": "",
        "CreatedFrom": "Cloud",
        "CreatedFromRelease": "2024.11"
    }, indent=2))


def _write_report_settings(base: Path):
    (base / "ReportSettings.json").write_text(json.dumps({
        "Version": 1,
        "ReportSettings": {},
        "QueriesSettings": {
            "TypeDetectionEnabled": True,
            "RelationshipImportEnabled": True,
            "RunBackgroundAnalysis": True,
            "Version": "2.130.0.0"
        }
    }, indent=2))



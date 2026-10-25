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


def _write_diagram_layout(base: Path):
    (base / "DiagramLayout.json").write_text(json.dumps({
        "version": "1.1.0",
        "diagrams": [{"ordinal": 0, "scrollPosition": {"x": 0, "y": 0}, "nodes": [], "zoomValue": 100}]
    }, indent=2))


def _write_bim(base: Path, bim: dict):
    model_dir = base / "Model"
    model_dir.mkdir(exist_ok=True)
    (model_dir / "database.json").write_text(
        json.dumps(bim, indent=2, ensure_ascii=False))


def _write_m(base: Path, m_code: dict):
    mashup_dir = base / "Mashup" / "Package" / "Formulas"
    mashup_dir.mkdir(parents=True, exist_ok=True)
    lines = ["section Section1;\n"]
    for name, expr in m_code.items():
        lines.append(f'shared #"{name}" = {expr};\n')
    (mashup_dir / "Section1.m").write_text("\n".join(lines))


def _write_layout(base: Path, layout: dict):
    report_dir = base / "Report"
    sections_dir = report_dir / "sections"
    sections_dir.mkdir(parents=True, exist_ok=True)

    pages = layout.get("pages", [])

    (report_dir / "config.json").write_text(json.dumps({
        "version": "5.59",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "version": "5.59", "type": 2}
        },
        "activeSectionIndex": 0,
        "defaultDrillFilterOtherVisuals": True,
        "slowDataSourceSettings": {
            "isCrossHighlightingDisabled": False,
            "isSlicerSelectionsButtonEnabled": False,
            "isFilterSelectionsButtonEnabled": False,
            "isFieldWellButtonEnabled": False,
            "isApplyAllButtonEnabled": False
        },
        "linguisticSchemaSyncVersion": 2,
        "settings": {}
    }, indent=2))

    (report_dir / "report.json").write_text(json.dumps({
        "id": "00000000-0000-0000-0000-000000000000",
        "pods": [],
        "resourcePackages": [],
        "sections": [p["name"] for p in pages],
        "theme": {"name": "CY24SU10", "version": "5.59"},
        "config": "{}", "filters": "[]"
    }, indent=2))

    for page in pages:
        page = _fix_serialization(page)
        (sections_dir / f"{page['name']}.json").write_text(
            json.dumps(page, indent=2, ensure_ascii=False))


def _write_theme(base: Path, theme: dict, title: str):
    """Write PBI theme to StaticResources so it's applied to the report."""
    res_dir = base / "Report" / "StaticResources" / "RegisteredResources"
    res_dir.mkdir(parents=True, exist_ok=True)
    theme_name = f"{title.replace(' ', '_')}_Theme"
    (res_dir / f"{theme_name}.json").write_text(
        json.dumps(theme, indent=2))


def _fix_serialization(page: dict) -> dict:
    """CRITICAL: config/filters/query/dataTransforms must be strings not objects."""
    STRING_FIELDS = {"config", "filters", "query", "dataTransforms"}
    for vc in page.get("visualContainers", []):
        _remove_generated_sort_metadata(vc)
        for field in STRING_FIELDS:
            val = vc.get(field)
            if isinstance(val, (dict, list)):
                vc[field] = json.dumps(val, ensure_ascii=False,
                                       separators=(",", ":"))
            elif not val:
                vc[field] = "[]" if field == "filters" else "{}"
    return page


def _remove_generated_sort_metadata(vc: dict) -> None:
    """Avoid Desktop 2026 renderer crashes from generated sort expressions."""

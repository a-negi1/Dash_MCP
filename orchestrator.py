import subprocess, tempfile, os
import re
from pathlib import Path
from models import ProjectState, ReportIntent, ColorPalette
from session_manager import new_session, save_session, require_session
from image_analyzer import extract_palette_from_image
from theme_generator import palette_to_pbi_theme, default_theme
from claude_calls import (extract_intent, generate_bim, generate_m_queries,
                          generate_layout, apply_style_edit)
from visual_editor import add_visual_to_session, add_slicer_filter
from file_writer import write_project, inject_data_mashup, inject_report_layout
from validators import validate_all
from data_profiler import profile_csv
from auto_intent import (build_intent_from_profile, build_bim_from_profile,
                         build_m_from_profile, build_layout_from_intent)

async def pipeline_create(prompt: str, schema_hint: str = "",
                           image_base64: str = None,
                           media_type: str = "image/png") -> ProjectState:
    state = new_session()

    if image_base64:
        raw_palette = extract_palette_from_image(image_base64, media_type)
        state.palette = ColorPalette(**raw_palette)
        state.theme = palette_to_pbi_theme(state.palette)
    else:
        state.theme = default_theme()

    intent_dict = extract_intent(prompt, schema_hint)
    state.intent = ReportIntent(**intent_dict)
    bim_raw = generate_bim(state.intent.model_dump())
    state.bim = bim_raw
    state.m_code = generate_m_queries(state.intent.model_dump(), schema_hint)
    inline_m_partition_sources(state.bim, state.m_code)
    state.layout = generate_layout(state.intent.model_dump())

    validate_all(state)
    state.project_dir = tempfile.mkdtemp(prefix=f"pbi_{state.session_id}_")
    write_project(state)
    state.pbix_path = compile_and_inject(state.project_dir, state.m_code or {}, state.layout or {})

    state.history.append(f"create: {prompt}")
    save_session(state)
    return state


async def pipeline_add_visual(session_id: str, description: str,
                              page_name: str = "Overview") -> ProjectState:
    state = require_session(session_id)
    state = add_visual_to_session(state, description, page_name)
    inline_m_partition_sources(state.bim, state.m_code or {})
    write_project(state)
    state.pbix_path = compile_and_inject(state.project_dir, state.m_code or {}, state.layout or {})
    save_session(state)
    return state


async def pipeline_apply_theme(session_id: str, image_base64: str,
                               media_type: str = "image/png") -> ProjectState:
    state = require_session(session_id)
    raw_palette = extract_palette_from_image(image_base64, media_type)
    state.palette = ColorPalette(**raw_palette)
    state.theme = palette_to_pbi_theme(
        state.palette,
        state.intent.report_title if state.intent else "Report"
    )
    state.history.append("apply_theme: image uploaded")
    inline_m_partition_sources(state.bim, state.m_code or {})
    write_project(state)
    state.pbix_path = compile_and_inject(state.project_dir, state.m_code or {}, state.layout or {})
    save_session(state)
    return state


async def pipeline_edit_style(session_id: str, instruction: str) -> ProjectState:
    state = require_session(session_id)
    state.theme = apply_style_edit(state.theme or default_theme(), instruction)
    state.history.append(f"edit_style: {instruction}")
    inline_m_partition_sources(state.bim, state.m_code or {})
    write_project(state)
    state.pbix_path = compile_and_inject(state.project_dir, state.m_code or {}, state.layout or {})
    save_session(state)
    return state


async def pipeline_add_filter(session_id: str, filter_description: str,
                              page_name: str = None) -> ProjectState:
    state = require_session(session_id)
    state = add_slicer_filter(state, filter_description, page_name)
    inline_m_partition_sources(state.bim, state.m_code or {})
    write_project(state)
    state.pbix_path = compile_and_inject(state.project_dir, state.m_code or {}, state.layout or {})
    save_session(state)
    return state


async def pipeline_from_csv(csv_bytes: bytes, filename: str = "data.csv",
                            prompt: str = "",
                            image_base64: str = None,
                            media_type: str = "image/png") -> ProjectState:
    state = new_session()
    csv_path = persist_csv_source(csv_bytes, filename, state.session_id)
    state.csv_filename = str(csv_path)

    if image_base64:
        raw_palette = extract_palette_from_image(image_base64, media_type)
        state.palette = ColorPalette(**raw_palette)
        state.theme = palette_to_pbi_theme(state.palette)
    else:
        state.theme = default_theme()

    profile = profile_csv(csv_bytes, filename)
    state.dataset_profile = profile

    intent = build_intent_from_profile(profile, filename)
    if prompt:
        intent.report_title = _report_title_from_prompt(
            prompt,
            intent.report_title,
        )
    state.intent = intent

    table_name = intent.tables[0].name
    state.m_code = build_m_from_profile(profile, table_name, str(csv_path))
    state.bim = build_bim_from_profile(profile, table_name)
    inline_m_partition_sources(state.bim, state.m_code)
    state.layout = build_layout_from_intent(intent)

    validate_all(state)
    state.project_dir = tempfile.mkdtemp(prefix=f"pbi_{state.session_id}_")
    write_project(state)
    state.pbix_path = compile_and_inject(state.project_dir, state.m_code, state.layout or {})

    state.history.append(f"create_from_csv: {filename}")
    save_session(state)
    return state


async def pipeline_export(session_id: str) -> tuple[ProjectState, str]:
    state = require_session(session_id)
    inline_m_partition_sources(state.bim, state.m_code or {})
    write_project(state)
    pbix_path = compile_and_inject(state.project_dir, state.m_code or {}, state.layout or {})
    state.pbix_path = pbix_path
    save_session(state)
    return state, pbix_path


def compile_project(project_dir: str) -> str:
    out_path = os.path.join(project_dir, "output.pbit")
    exe = _find_pbi_tools()
    result = subprocess.run(
        [exe, "compile", project_dir, out_path, "PBIT", "True"],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"pbi-tools compile failed (exit {result.returncode})\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    if not os.path.exists(out_path):
        raise RuntimeError(
            f"pbi-tools compile ran but no output file at {out_path}\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return out_path


def compile_and_inject(project_dir: str, m_code: dict, layout: dict | None = None) -> str:
    pbit_path = compile_project(project_dir)
    inject_data_mashup(pbit_path, m_code)
    if layout:
        inject_report_layout(pbit_path, layout)
    return pbit_path


def persist_csv_source(csv_bytes: bytes, filename: str, session_id: str) -> Path:
    safe_filename = re.sub(r"[^A-Za-z0-9_. -]", "_", Path(filename).name)
    if not safe_filename or safe_filename in {".", ".."}:
        safe_filename = "data.csv"
    source_dir = Path(__file__).resolve().parent / "generated_sources" / session_id
    source_dir.mkdir(parents=True, exist_ok=True)
    csv_path = source_dir / safe_filename
    csv_path.write_bytes(csv_bytes)
    return csv_path.resolve()


def _report_title_from_prompt(prompt: str, fallback: str) -> str:
    clean = " ".join(prompt.split()).strip()
    if not clean:
        return fallback
    if len(clean) > 70 or clean.count(" ") > 10:
        return fallback
    safe = re.sub(r"[^A-Za-z0-9&,.() -]", "", clean).strip(" .-_")
    return safe.title() if safe else fallback


def inline_m_partition_sources(bim: dict | None, m_code: dict) -> None:
    if not bim or not m_code:
        return
    for table in bim.get("model", {}).get("tables", []):
        table_name = table.get("name")
        for partition in table.get("partitions", []):
            source = partition.get("source", {})
            expr = source.get("expression", "")
            expr_text = "\n".join(expr) if isinstance(expr, list) else str(expr)
            query_name = expr_text.strip().strip('"')
            if query_name in m_code:
                source["expression"] = m_code[query_name]
            elif table_name in m_code and not expr_text.strip().lower().startswith("let"):
                source["expression"] = m_code[table_name]


def _find_pbi_tools() -> str:
    import shutil
    for candidate in ["pbi-tools.core.exe", "pbi-tools.core", "pbi-tools"]:
        path = shutil.which(candidate)
        if path:
            return path
    dotnet_tools = Path.home() / ".dotnet" / "tools"
    for candidate in ["pbi-tools.core.exe", "pbi-tools.exe", "pbi-tools"]:
        path = dotnet_tools / candidate
        if path.exists():
            return str(path)
    default = r"C:\pbi-tools\pbi-tools.core.exe"
    if os.path.exists(default):
        return default
    raise FileNotFoundError(
        "pbi-tools not found. Download from https://github.com/pbi-tools/pbi-tools/releases "
        "and ensure it is on PATH or installed at C:\\pbi-tools\\"
    )

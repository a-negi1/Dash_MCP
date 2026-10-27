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

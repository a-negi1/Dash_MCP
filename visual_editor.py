import json
from models import ProjectState
from claude_calls import apply_visual_edit

def add_visual_to_session(state: ProjectState, description: str,
                           page_name: str = "Overview") -> ProjectState:
    if not state.layout:
        raise ValueError("No layout in session — create a report first")

    pages = state.layout.get("pages", [])
    target = next((p for p in pages if p["name"] == page_name), None)

    if not target:
        target = {
            "name": page_name,
            "displayName": page_name,
            "width": 1280, "height": 720,
            "visualContainers": []
        }
        pages.append(target)

    updated_page = apply_visual_edit(target, f"Add: {description}")

    state.layout["pages"] = [
        updated_page if p["name"] == page_name else p
        for p in pages
    ]
    state.history.append(f"add_visual: {description} on {page_name}")
    return state


def edit_visual_in_session(state: ProjectState, instruction: str,
                            page_name: str = None) -> ProjectState:
    if not state.layout:
        raise ValueError("No layout in session")

    pages = state.layout.get("pages", [])
    target_pages = (
        [p for p in pages if p["name"] == page_name]
        if page_name else pages
    )

    for page in target_pages:
        updated = apply_visual_edit(page, instruction)
        state.layout["pages"] = [
            updated if p["name"] == page["name"] else p
            for p in state.layout["pages"]
        ]

    state.history.append(f"edit_visual: {instruction}")
    return state


def remove_visual_from_session(state: ProjectState, instruction: str,
                                page_name: str = None) -> ProjectState:
    return edit_visual_in_session(
        state, f"Remove the visual matching: {instruction}", page_name
    )


def add_slicer_filter(state: ProjectState, filter_description: str,
                      page_name: str = None) -> ProjectState:
    return edit_visual_in_session(
        state, f"Add a slicer for: {filter_description}", page_name
    )

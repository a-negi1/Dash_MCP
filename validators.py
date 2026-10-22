def validate_all(state):
    validate_compat_level(state.bim or {})
    validate_partition_sources(state.bim or {}, state.m_code or {})

def validate_compat_level(bim: dict):
    level = bim.get("compatibilityLevel")
    if level != 1550:
        raise ValueError(f"BIM compatibilityLevel must be 1550, got {level!r}")

def validate_partition_sources(bim: dict, m_code: dict):
    invalid = []
    for table in bim.get("model", {}).get("tables", []):
        for partition in table.get("partitions", []):
            expr = partition.get("source", {}).get("expression", "")
            expr_text = "\n".join(expr) if isinstance(expr, list) else str(expr)
            stripped = expr_text.strip().strip('"')
            if stripped in m_code:
                continue
            if stripped.lower().startswith("let") and "\nin" in stripped.lower():
                continue
            invalid.append(stripped)
    if invalid:
        raise ValueError(
            f"BIM partition sources must be M expressions or known query names: {invalid}\n"
            f"Available queries: {set(m_code.keys())}"
        )

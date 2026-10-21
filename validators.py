def validate_compat_level(bim: dict):
    level = bim.get("compatibilityLevel")
    if level != 1550:
        raise ValueError(f"BIM compatibilityLevel must be 1550, got {level!r}")


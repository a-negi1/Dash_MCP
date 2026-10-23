from models import ColorPalette

def palette_to_pbi_theme(palette: ColorPalette, report_title: str = "Report") -> dict:
    """
    Generates a Power BI theme JSON from an extracted palette.
    This theme JSON is written to:
      Report/StaticResources/RegisteredResources/<ThemeName>.json
    and referenced in report.json.
    """
    colors = palette.data_colors
    if not colors:
        colors = [
            palette.primary,
            palette.secondary,
            palette.accent,
            "#28C76F", "#EA5455", "#FF9F43", "#1E9AF5", "#9B59B6"
        ]

    return {
        "name": f"{report_title} Theme",
        "dataColors": colors[:8],
        "background": palette.background,
        "foreground": palette.text,
        "tableAccent": palette.primary,
        "maximum": colors[0] if colors else palette.primary,
        "center": colors[1] if len(colors) > 1 else palette.secondary,
        "minimum": colors[2] if len(colors) > 2 else palette.accent,
        "null": "#888780",
        "bad": "#EA5455",
        "neutral": "#FF9F43",
        "good": "#28C76F",
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{
                        "color": {"solid": {"color": palette.background}},
                        "transparency": 0
                    }],
                    "outspacePane": [{
                        "backgroundColor": {
                            "solid": {"color": palette.background}
                        }
                    }]
                }
            }
        }
    }


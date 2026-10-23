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

def default_theme() -> dict:
    """Fallback theme when no image provided."""
    return {
        "name": "DashMCP Template Dashboard",
        "dataColors": [
            "#0F6FB5", "#36B4E5", "#5B2FA6",
            "#0EA5A4", "#FF7676", "#60C878",
            "#B0008B", "#8AA1B4"
        ],
        "background": "#EAF4FC",
        "foreground": "#111827",
        "tableAccent": "#0F6FB5",
        "textClasses": {
            "title": {
                "fontFace": "Segoe UI Semibold",
                "fontSize": 12,
                "fontColor": "#111827"
            },
            "label": {
                "fontFace": "Segoe UI",
                "fontSize": 10,
                "fontColor": "#4B5563"
            },
            "callout": {
                "fontFace": "Segoe UI Semibold",
                "fontSize": 28,
                "fontColor": "#111827"
            }
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{
                        "color": {"solid": {"color": "#FFFFFF"}},
                        "transparency": 0
                    }],
                    "border": [{
                        "show": True,
                        "color": {"solid": {"color": "#CFE3F2"}},
                        "radius": 8
                    }],
                    "visualHeader": [{
                        "show": False
                    }],
                    "title": [{
                        "show": True,
                        "fontColor": {"solid": {"color": "#111827"}},
                        "textSize": 11
                    }]
                }
            },
            "card": {
                "*": {
                    "labels": [{
                        "color": {"solid": {"color": "#0F6FB5"}},
                        "fontSize": 26
                    }],
                    "categoryLabels": [{
                        "color": {"solid": {"color": "#6B7280"}},
                        "fontSize": 10
                    }]
                }
            },
            "barChart": {
                "*": {
                    "dataPoint": [{
                        "defaultColor": {"solid": {"color": "#0F6FB5"}}
                    }],
                    "categoryAxis": [{
                        "labelColor": {"solid": {"color": "#4B5563"}}
                    }],
                    "valueAxis": [{
                        "labelColor": {"solid": {"color": "#6B7280"}}
                    }]
                }
            },
            "lineChart": {
                "*": {
                    "dataPoint": [{
                        "defaultColor": {"solid": {"color": "#0EA5A4"}}
                    }]
                }
            }
        }
    }

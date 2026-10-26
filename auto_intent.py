"""
Rule-based dashboard generation from DatasetProfile.
Produces ReportIntent, BIM JSON, M code dict, and layout dict
without any Claude API calls.
"""
import json, re, uuid
from pathlib import Path
from models import (
    DatasetProfile, ColumnProfile, ReportIntent, TableIntent, Column,
    MeasureIntent, RelationshipIntent, PageIntent, VisualIntent,
)

_PBI_TYPE = {
    "string": "string",
    "int64": "int64",
    "decimal": "decimal",
    "dateTime": "dateTime",
    "boolean": "boolean",
}

_M_TYPE = {
    "string": "type text",
    "int64": "type number",
    "decimal": "type number",
    "dateTime": "type datetime",
    "boolean": "type logical",
}

def _safe_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    return safe or "Data"


def _col_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _is_system_column(name: str) -> bool:
    if name.strip().startswith("_"):
        return True
    key = _col_key(name)
    return key in {
        "id", "url", "page_url", "pageurl", "source", "input", "num",
        "widget_name", "widgetname", "result_number", "resultnumber",
    }


def _is_metric_candidate(col: ColumnProfile) -> bool:
    key = _col_key(col.name)
    if _is_system_column(col.name):
        return False
    if key in {"rank", "founded", "founded_year", "year_founded"}:
        return False
    return col.role == "measure"


def _entity_column(profile: DatasetProfile) -> ColumnProfile | None:
    preferred = ("company", "customer", "client", "employee", "product", "name")
    for wanted in preferred:
        found = next((c for c in profile.columns if _col_key(c.name) == wanted), None)
        if found:
            return found
    return None

def _format_string(col: ColumnProfile) -> str:
    name_lower = col.name.lower()
    if col.semantic_type == "rate":
        return "0.00%"
    if col.semantic_type == "currency" or any(k in name_lower for k in ("revenue", "sales", "profit", "cost", "price", "amount", "income", "expense", "budget", "wage", "salary")):
        return "$#,0"
    if col.data_type == "decimal":
        return "#,0.00"
    return "#,0"

def _dax_expr(col: ColumnProfile, table_name: str) -> str:
    agg = col.aggregation
    col_ref = f"'{table_name}'[{col.name}]"
    if agg == "AVG":
        return f"AVERAGE({col_ref})"
    if agg == "COUNT":
        return f"COUNT({col_ref})"
    if agg == "COUNTD":
        return f"DISTINCTCOUNT({col_ref})"
    if agg == "MIN":
        return f"MIN({col_ref})"
    if agg == "MAX":
        return f"MAX({col_ref})"
    return f"SUM({col_ref})"

def _measure_name(col_name: str) -> str:
    name = col_name.strip()
    if re.search(r"\b(total|sum|avg|average|count|max|min)\b", name, re.I):
        return name
    return f"Total {name}"


def _measure_source_col(measure: MeasureIntent) -> str:
    match = re.search(r"'?([^'\[]+)'?\[([^\]]+)\]", measure.dax)
    return match.group(2) if match else measure.name.removeprefix("Total ").strip()


def _is_currency_measure(measure: MeasureIntent) -> bool:
    text = f"{measure.name} {measure.dax} {measure.format}".lower()
    return "$" in measure.format or any(
        word in text for word in ("revenue", "sales", "profit", "cost", "amount", "income", "expense", "budget")
    )


def _is_count_measure(measure: MeasureIntent) -> bool:
    text = measure.name.lower()
    return any(word in text for word in ("unit", "qty", "quantity", "order", "count", "transaction", "visit"))


def _is_average_metric(col: ColumnProfile) -> bool:
    key = _col_key(col.name)
    return col.aggregation == "AVG" or any(word in key for word in ("growth", "rate", "pct", "percent", "margin", "ratio", "score"))


def _m_string(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def build_intent_from_profile(profile: DatasetProfile, filename: str) -> ReportIntent:
    table_name = _safe_name(Path(filename).stem)
    report_title = f"{table_name.replace('_', ' ').title()} Dashboard"

    columns = [
        Column(name=col.name, type=_PBI_TYPE.get(col.data_type, "string"))
        for col in profile.columns
    ]
    table = TableIntent(name=table_name, columns=columns)

    metric_cols = [c for c in profile.columns if _is_metric_candidate(c)]
    entity_col = _entity_column(profile)
    measures = []
    if entity_col:
        measures.append(MeasureIntent(
            name=f"{entity_col.name.title()} Count",
            table=table_name,
            dax=f"DISTINCTCOUNT('{table_name}'[{entity_col.name}])",
            format="#,0",
        ))

    for col in metric_cols[:6]:
        measure_name = (
            f"Avg {col.name}"
            if _is_average_metric(col)
            else _measure_name(col.name)
        )
        measures.append(MeasureIntent(
            name=measure_name,
            table=table_name,
            dax=_dax_expr(col, table_name),
            format=_format_string(col),
        ))

    currency_measure = next((m for m in measures if _is_currency_measure(m)), None)
    count_measure = next((m for m in measures if _is_count_measure(m)), None)
    if currency_measure and count_measure:
        numerator = _measure_source_col(currency_measure)
        denominator = _measure_source_col(count_measure)
        measures.append(MeasureIntent(
            name=f"Avg {numerator} per {denominator}",
            table=table_name,
            dax=f"DIVIDE(SUM('{table_name}'[{numerator}]), SUM('{table_name}'[{denominator}]))",
            format=currency_measure.format,
        ))

    cat_dims = [c for c in profile.columns
                if not _is_system_column(c.name)
                and c.role == "dimension"
                and c.semantic_type in ("categorical", "geographic")]
    temp_dims = [c for c in profile.columns if c.semantic_type == "temporal"]

    ranking_candidates = sorted(
        cat_dims,
        key=lambda c: (
            0 if c.semantic_type == "categorical" and c.data_type == "string" else
            1 if c.semantic_type == "geographic" else
            2,
            c.cardinality,
        ),
    )
    ranking_dim = next(
        (c for c in ranking_candidates if 3 <= c.cardinality <= 25), None
    ) or (ranking_candidates[0] if ranking_candidates else None)

    secondary_dim = next(
        (c for c in cat_dims
         if ranking_dim and c.name != ranking_dim.name
         and 2 <= c.cardinality <= 25),
        None,
    )

    slicer_dim = next(
        (c for c in sorted(cat_dims, key=lambda c: c.cardinality)
         if 5 <= c.cardinality <= 30
         and (not ranking_dim or c.name != ranking_dim.name)), None
    ) or (cat_dims[-1] if len(cat_dims) > 1 else (cat_dims[0] if cat_dims else None))

    primary_measure = (
        next((m for m in measures if "count" in m.name.lower()), None)
        or measures[0] if measures else None
    )

    visuals: list[VisualIntent] = []

    for m in measures[:3]:
        visuals.append(VisualIntent(type="card", title=m.name, value=m.name))

    if ranking_dim and primary_measure:
        visuals.append(VisualIntent(
            type="barChart",
            title=f"{primary_measure.name} by {ranking_dim.name}",
            x_axis=f"{table_name}[{ranking_dim.name}]",
            y_axis=primary_measure.name,
        ))

    if temp_dims and primary_measure:
        visuals.append(VisualIntent(
            type="lineChart",
            title=f"{primary_measure.name} Over Time",
            x_axis=f"{table_name}[{temp_dims[0].name}]",
            y_axis=primary_measure.name,
        ))

    if secondary_dim and primary_measure:
        visuals.append(VisualIntent(
            type="barChart",
            title=f"{primary_measure.name} by {secondary_dim.name}",
            x_axis=f"{table_name}[{secondary_dim.name}]",
            y_axis=primary_measure.name,
        ))

    if slicer_dim:
        visuals.append(VisualIntent(
            type="slicer",
            title=f"Filter by {slicer_dim.name}",
            field=f"{table_name}[{slicer_dim.name}]",
        ))

    page = PageIntent(name="Overview", display_name="Overview", visuals=visuals)

    return ReportIntent(
        report_title=report_title,
        tables=[table],
        measures=measures,
        relationships=[],  # single-table model; no relationships needed
        pages=[page],
    )

def build_bim_from_profile(profile: DatasetProfile, table_name: str) -> dict:
    columns = []
    for col in profile.columns:
        entry = {
            "name": col.name,
            "dataType": _PBI_TYPE.get(col.data_type, "string"),
            "sourceColumn": col.name,
        }
        if col.data_type in ("int64", "decimal"):
            entry["summarizeBy"] = "sum" if col.aggregation == "SUM" else "average" if col.aggregation == "AVG" else "count"
        else:
            entry["summarizeBy"] = "none"
        columns.append(entry)

    measure_cols = [c for c in profile.columns if _is_metric_candidate(c)]
    measures = [
        {
            "name": f"Avg {col.name}" if _is_average_metric(col) else _measure_name(col.name),
            "expression": _dax_expr(col, table_name),
            "formatString": _format_string(col),
        }
        for col in measure_cols[:6]
    ]
    entity_col = _entity_column(profile)
    if entity_col:
        measures.insert(0, {
            "name": f"{entity_col.name.title()} Count",
            "expression": f"DISTINCTCOUNT('{table_name}'[{entity_col.name}])",
            "formatString": "#,0",
        })
    currency_col = next((c for c in measure_cols if _format_string(c).startswith("$")), None)
    count_col = next((
        c for c in measure_cols
        if any(word in c.name.lower() for word in ("unit", "qty", "quantity", "order", "count", "transaction", "visit"))
    ), None)
    if currency_col and count_col:
        measures.append({
            "name": f"Avg {currency_col.name} per {count_col.name}",
            "expression": (
                f"DIVIDE(SUM('{table_name}'[{currency_col.name}]), "
                f"SUM('{table_name}'[{count_col.name}]))"
            ),
            "formatString": _format_string(currency_col),
        })
    elif currency_col and entity_col:
        measures.append({
            "name": f"Avg {currency_col.name} per {entity_col.name}",
            "expression": (
                f"DIVIDE(SUM('{table_name}'[{currency_col.name}]), "
                f"DISTINCTCOUNT('{table_name}'[{entity_col.name}]))"
            ),
            "formatString": _format_string(currency_col),
        })

    return {
        "name": "SemanticModel",
        "compatibilityLevel": 1550,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "tables": [
                {
                    "name": table_name,
                    "columns": columns,
                    "measures": measures,
                    "partitions": [
                        {
                            "name": table_name,
                            "mode": "import",
                            "source": {
                                "type": "m",
                                "expression": table_name,
                            },
                        }
                    ],
                }
            ],
            "relationships": [],
            "annotations": [{"name": "PBIDesktopVersion", "value": "2.130.0.0"}],
        },
    }


def build_m_from_profile(profile: DatasetProfile, table_name: str, csv_filename: str) -> dict:
    type_pairs = ", ".join(
        f'{{"{col.name}", {_M_TYPE.get(col.data_type, "type text")}}}'
        for col in profile.columns
    )
    expr = (
        'let\n'
        f'    Source = Csv.Document(File.Contents({_m_string(csv_filename)})'
        ',[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
        '    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),\n'
        f'    #"Changed Types" = Table.TransformColumnTypes(#"Promoted Headers",'
        f'{{{type_pairs}}})\n'
        'in\n'
        '    #"Changed Types"'
    )
    return {table_name: expr}


def _literal(value: str) -> dict:
    return {"expr": {"Literal": {"Value": "'" + value.replace("'", "''") + "'"}}}


def _literal_bool(value: bool) -> dict:
    return {"expr": {"Literal": {"Value": "true" if value else "false"}}}


def _literal_num(value: int | float, suffix: str = "D") -> dict:
    return {"expr": {"Literal": {"Value": f"{value}{suffix}"}}}


def _color_expr(color: str) -> dict:
    return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}}


def _source_ref(table_name: str) -> dict:
    return {"SourceRef": {"Source": table_name}}


def _column_select(table_name: str, column_name: str) -> dict:
    return {
        "Column": {
            "Expression": _source_ref(table_name),
            "Property": column_name,
        },
        "Name": f"{table_name}.{column_name}",
        "NativeReferenceName": column_name,
    }


def _sum_ref(table_name: str, column_name: str) -> str:
    return f"Sum({table_name}.{column_name})"


def _measure_ref(table_name: str, measure_name: str) -> str:
    return f"{table_name}.{measure_name}"


def _measure_select(table_name: str, measure_name: str) -> dict:
    return {
        "Measure": {
            "Expression": _source_ref(table_name),
            "Property": measure_name,
        },
        "Name": _measure_ref(table_name, measure_name),
        "NativeReferenceName": measure_name,
    }


def _aggregation_select(table_name: str, column_name: str,
                        aggregation: str = "SUM") -> dict:
    function = 1 if aggregation == "AVG" else 2 if aggregation == "MIN" else 3 if aggregation == "MAX" else 0
    label = "Average" if aggregation == "AVG" else "Minimum" if aggregation == "MIN" else "Maximum" if aggregation == "MAX" else "Sum"
    return {
        "Aggregation": {
            "Expression": {
                "Column": {
                    "Expression": _source_ref(table_name),
                    "Property": column_name,
                }
            },
            "Function": function,
        },
        "Name": _sum_ref(table_name, column_name),
        "NativeReferenceName": f"{label} of {column_name}",
    }


def _measure_column(intent: ReportIntent, measure_name: str) -> tuple[str, str]:
    for measure in intent.measures:
        if measure.name == measure_name:
            match = re.search(r"'?([^'\[]+)'?\[([^\]]+)\]", measure.dax)
            if match:
                return match.group(1), match.group(2)
    table = intent.tables[0].name
    return table, measure_name.removeprefix("Total ").strip()


def _field_parts(field_ref: str, default_table: str) -> tuple[str, str]:
    match = re.match(r"([^\[]+)\[([^\]]+)\]", field_ref or "")
    if match:
        return match.group(1), match.group(2)
    if "." in field_ref:
        table, col = field_ref.split(".", 1)
        return table, col
    return default_table, field_ref


def _visual_config(table_name: str, visual_type: str, title: str,
                   x: int, y: int, w: int, h: int,
                   category_col: str = "", value_col: str = "",
                   value_measure: str = "",
                   value_aggregation: str = "SUM",
                   role_overrides: dict = None) -> dict:
    visual_id = str(uuid.uuid4())
    projections = {}
    selects = []

    if category_col:
        category_ref = f"{table_name}.{category_col}"
        projections["Category"] = [{"queryRef": category_ref, "active": True}]
        selects.append(_column_select(table_name, category_col))

    if value_measure:
        value_ref = _measure_ref(table_name, value_measure)
        value_roles = role_overrides.get("value", ["Y"]) if role_overrides else ["Y"]
        for role in value_roles:
            projections[role] = [{"queryRef": value_ref}]
        selects.append(_measure_select(table_name, value_measure))
    elif value_col:
        value_ref = _sum_ref(table_name, value_col)
        value_roles = role_overrides.get("value", ["Y"]) if role_overrides else ["Y"]
        for role in value_roles:
            projections[role] = [{"queryRef": value_ref}]
        selects.append(_aggregation_select(table_name, value_col, value_aggregation))

    cfg = {
        "name": visual_id,
        "layouts": [{
            "id": 0,
            "position": {
                "x": float(x), "y": float(y), "z": 0,
                "width": float(w), "height": float(h),
                "tabOrder": 0,
            },
        }],
        "singleVisual": {
            "visualType": visual_type,
            "projections": projections,
            "prototypeQuery": {
                "Version": 2,
                "From": [{"Name": table_name, "Entity": table_name, "Type": 0}],
                "Select": selects,
            },
            "drillFilterOtherVisuals": True,
            "objects": {
                "background": [{
                    "properties": {
                        "show": _literal_bool(True),
                        "color": {"solid": {"color": {"expr": {"Literal": {"Value": "'#FFFFFF'"}}}}},
                        "transparency": _literal_num(0),
                    }
                }],
                "border": [{
                    "properties": {
                        "show": _literal_bool(True),
                        "color": _color_expr("#CFE3F2"),
                    }
                }],
                "visualHeader": [{
                    "properties": {"show": _literal_bool(False)}
                }],
                "legend": [{
                    "properties": {"show": _literal_bool(False)}
                }],
                "categoryAxis": [{
                    "properties": {
                        "show": _literal_bool(True),
                        "labelColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#605E5C'"}}}}},
                    }
                }],
                "valueAxis": [{
                    "properties": {
                        "show": _literal_bool(True),
                        "labelColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#605E5C'"}}}}},
                        "gridlineColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#EDEBE9'"}}}}},
                    }
                }],
                "dataPoint": [{
                    "properties": {
                        "defaultColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#2D5BFF'"}}}}},
                    }
                }],
            },
            "vcObjects": {
                "title": [{
                    "properties": {
                        "show": _literal_bool(True),
                        "text": _literal(title.upper()),
                        "fontColor": {"solid": {"color": {"expr": {"Literal": {"Value": "'#252423'"}}}}},
                        "fontSize": _literal_num(12),
                    }
                }]
            },
        },
    }
    return cfg


def _vc(x, y, w, h, visual_type, title, config_extra: dict = None) -> dict:
    cfg = config_extra or {"singleVisual": {"visualType": visual_type, "title": title}}
    return {
        "x": x, "y": y, "width": w, "height": h,
        "config": json.dumps(cfg, separators=(",", ":")),
        "filters": "[]",
        "query": "{}",
        "dataTransforms": "{}",
    }


def _textbox_config(text: str, font_size: int = 20, color: str = "#252423",
                    bold: bool = True) -> dict:
    return {
        "name": str(uuid.uuid4()),
        "singleVisual": {
            "visualType": "textbox",
            "objects": {
                "general": [{
                    "properties": {
                        "paragraphs": [{
                            "textRuns": [{
                                "value": text,
                                "textStyle": {
                                    "fontSize": f"{font_size}pt",
                                    "fontFamily": "Segoe UI",
                                    "fontWeight": "bold" if bold else "normal",
                                    "color": color,
                                },
                            }],
                        }]
                    }
                }]
            },
        },
    }


def _textbox_vc(x: int, y: int, w: int, h: int, text: str,
                font_size: int = 20, color: str = "#252423",
                bold: bool = True) -> dict:
    return _vc(
        x, y, w, h, "textbox", text,
        _textbox_config(text, font_size=font_size, color=color, bold=bold),
    )


def _page_config(background: str = "#EAF4FC") -> str:
    return json.dumps({
        "objects": {
            "background": [{
                "properties": {
                    "color": _color_expr(background),
                    "transparency": _literal_num(0),
                }
            }]
        }
    }, separators=(",", ":"))


def _append_card(containers: list, intent: ReportIntent, card: VisualIntent,
                 x: int, y: int, w: int, h: int) -> None:
    value_table, value_col = _measure_column(intent, card.value)
    containers.append(_vc(
        x=x, y=y, w=w, h=h,
        visual_type="card", title=card.title,
        config_extra=_visual_config(
            value_table, "card", card.title,
            x, y, w, h,
            value_col=value_col,
            value_measure=card.value,
            role_overrides={"value": ["Values"]},
        ) if card.value else None,
    ))


def _append_chart(containers: list, intent: ReportIntent, visual: VisualIntent,
                  table_name: str, x: int, y: int, w: int, h: int) -> None:
    if visual.type == "slicer":
        field_table, field_col = _field_parts(visual.field, table_name)
        cfg = _visual_config(field_table, "slicer", visual.title,
                             x, y, w, h, category_col=field_col)
        cfg["singleVisual"]["projections"] = {
            "Values": [{"queryRef": f"{field_table}.{field_col}", "active": True}]
        }
        containers.append(_vc(x, y, w, h, "slicer", visual.title,
                              cfg if visual.field else None))
        return

    cat_table, cat_col = _field_parts(visual.x_axis, table_name)
    value_table, value_col = _measure_column(intent, visual.y_axis)
    visual_type = visual.type if visual.type in {
        "barChart", "columnChart", "lineChart", "pieChart", "tableEx"
    } else "barChart"
    containers.append(_vc(
        x, y, w, h, visual_type, visual.title,
        _visual_config(
            value_table or cat_table, visual_type, visual.title,
            x, y, w, h, cat_col, value_col,
            value_measure=visual.y_axis,
            role_overrides={"value": ["Y", "Values"]} if visual_type == "pieChart" else None,
        ) if visual.x_axis else None,
    ))


def build_layout_from_intent(intent: ReportIntent) -> dict:
    pages = []
    table_name = intent.tables[0].name if intent.tables else "Table"
    for page in intent.pages:
        visuals = page.visuals
        containers = []
        card_w, card_h = 240, 100
        gap = 16
        top_y = 20

        cards = [v for v in visuals if v.type == "card"]
        for i, card in enumerate(cards[:4]):
            value_table, value_col = _measure_column(intent, card.value)
            containers.append(_vc(
                x=20 + i * (card_w + gap),
                y=top_y,
                w=card_w,
                h=card_h,
                visual_type="card",
                title=card.title,
                config_extra=_visual_config(
                    value_table, "card", card.title,
                    20 + i * (card_w + gap), top_y, card_w, card_h,
                    value_col=value_col,
                    role_overrides={"value": ["Values"]},
                ) if card.value else None,
            ))

        chart_y = top_y + card_h + gap  # 136
        chart_h = 260
        slicer_y = chart_y + chart_h + gap  # 412
        slicer_h = 60

        bar_added = False
        line_added = False

        for v in visuals:
            if v.type == "barChart" and not bar_added:
                cat_table, cat_col = _field_parts(v.x_axis, table_name)
                value_table, value_col = _measure_column(intent, v.y_axis)
                containers.append(_vc(20, chart_y, 580, chart_h, "barChart", v.title,
                    _visual_config(value_table or cat_table, "barChart", v.title,
                                   20, chart_y, 580, chart_h, cat_col, value_col)
                    if v.x_axis else None))
                bar_added = True
            elif v.type == "lineChart" and not line_added:
                cat_table, cat_col = _field_parts(v.x_axis, table_name)
                value_table, value_col = _measure_column(intent, v.y_axis)
                containers.append(_vc(620, chart_y, 620, chart_h, "lineChart", v.title,
                    _visual_config(value_table or cat_table, "lineChart", v.title,
                                   620, chart_y, 620, chart_h, cat_col, value_col)
                    if v.x_axis else None))
                line_added = True

        pie_added = False
        slicer_added = False
        for v in visuals:
            if v.type == "pieChart" and not pie_added:
                cat_table, cat_col = _field_parts(v.x_axis, table_name)
                value_table, value_col = _measure_column(intent, v.y_axis)
                containers.append(_vc(20, slicer_y, 280, 200, "pieChart", v.title,
                    _visual_config(value_table or cat_table, "pieChart", v.title,
                                   20, slicer_y, 280, 200, cat_col, value_col,
                                   role_overrides={"value": ["Y", "Values"]})
                    if v.x_axis else None))
                pie_added = True
            elif v.type == "slicer" and not slicer_added:
                field_table, field_col = _field_parts(v.field, table_name)
                cfg = _visual_config(field_table, "slicer", v.title,
                                     320, slicer_y, 200, slicer_h,
                                     category_col=field_col)
                cfg["singleVisual"]["projections"] = {
                    "Values": [{"queryRef": f"{field_table}.{field_col}", "active": True}]
                }
                containers.append(_vc(320, slicer_y, 200, slicer_h, "slicer", v.title,
                    cfg if v.field else None))
                slicer_added = True

        pages.append({
            "name": page.name,
            "displayName": page.display_name,
            "width": 1280,
            "height": 720,
            "visualContainers": containers,
        })

    return {"pages": pages}


def build_layout_from_intent(intent: ReportIntent) -> dict:
    """Build a clean template-based dashboard layout.

    Visuals are assigned to fixed template slots instead of being tiled freely.
    This keeps the page readable and mirrors the supplied reference dashboards:
    a light canvas, white panels, KPI rail/grid, main chart area, and a reserved
    right-side filter panel.
    """
    pages = []
    table_name = intent.tables[0].name if intent.tables else "Table"
    for page in intent.pages:
        visuals = page.visuals
        containers = []
        gap = 14
        margin = 14
        canvas_w, canvas_h = 1280, 720
        header_h = 62
        footer_h = 22

        containers.append(_textbox_vc(
            margin + 54, 12, 640, 42, intent.report_title,
            font_size=20, color="#252423", bold=True,
        ))
        containers.append(_textbox_vc(
            margin, 14, 44, 36, "RF",
            font_size=14, color="#0EA5E9", bold=True,
        ))
        containers.append(_textbox_vc(
            938, 18, 320, 30, page.display_name,
            font_size=12, color="#0F5EA8", bold=True,
        ))

        cards = [v for v in visuals if v.type == "card"]
        slicers = [v for v in visuals if v.type == "slicer"]
        charts = [
            v for v in visuals
            if v.type in {"barChart", "columnChart", "lineChart", "pieChart", "tableEx"}
        ]

        if len(cards) <= 4:
            left_w = 210
            right_w = 210
            main_x = margin + left_w + gap
            has_filter_panel = bool(slicers)
            right_x = canvas_w - margin - right_w if has_filter_panel else canvas_w - margin
            main_w = right_x - gap - main_x if has_filter_panel else right_x - main_x
            content_y = header_h + gap
            content_h = canvas_h - content_y - footer_h - gap

            kpi_count = min(max(len(cards), 1), 4)
            kpi_h = int((content_h - gap * (kpi_count - 1)) / kpi_count)
            for i, card in enumerate(cards[:4]):
                _append_card(
                    containers, intent, card,
                    margin, content_y + i * (kpi_h + gap), left_w, kpi_h,
                )

            chart_count = min(len(charts), 4)
            col_w = int((main_w - gap) / 2)
            row_h = int((content_h - gap) / 2)
            if chart_count == 1:
                slots = [(main_x, content_y, main_w, content_h)]
            elif chart_count == 2:
                slots = [
                    (main_x, content_y, col_w, content_h),
                    (main_x + col_w + gap, content_y, col_w, content_h),
                ]
            elif chart_count == 3:
                slots = [
                    (main_x, content_y, col_w, row_h),
                    (main_x + col_w + gap, content_y, col_w, row_h),
                    (main_x, content_y + row_h + gap, main_w, row_h),
                ]
            else:
                slots = [
                    (main_x, content_y, col_w, row_h),
                    (main_x + col_w + gap, content_y, col_w, row_h),
                    (main_x, content_y + row_h + gap, col_w, row_h),
                    (main_x + col_w + gap, content_y + row_h + gap, col_w, row_h),
                ]
            for visual, slot in zip(charts[:4], slots):
                _append_chart(containers, intent, visual, table_name, *slot)

            if has_filter_panel:
                containers.append(_textbox_vc(
                    right_x + 16, content_y + 16, right_w - 32, 30, "FILTERS",
                    font_size=11, color="#252423", bold=True,
                ))
                available_filter_h = content_h - 58
                slicer_count = min(len(slicers), 3)
                slicer_h = max(104, int((available_filter_h - gap * max(slicer_count - 1, 0)) / max(slicer_count, 1)))
                for i, slicer in enumerate(slicers[:3]):
                    _append_chart(
                        containers, intent, slicer, table_name,
                        right_x + 16,
                        content_y + 58 + i * (slicer_h + gap),
                        right_w - 32,
                        slicer_h,
                    )

        else:
            right_w = 210
            right_x = canvas_w - margin - right_w
            main_w = right_x - gap - margin
            kpi_y = header_h + gap
            kpi_h = 68
            kpi_cols = 4
            kpi_w = int((main_w - gap * (kpi_cols - 1)) / kpi_cols)
            for i, card in enumerate(cards[:8]):
                row = i // kpi_cols
                col = i % kpi_cols
                _append_card(
                    containers, intent, card,
                    margin + col * (kpi_w + gap),
                    kpi_y + row * (kpi_h + gap),
                    kpi_w, kpi_h,
                )

            chart_y = kpi_y + (2 * kpi_h) + gap * 2
            chart_h = 210
            chart_w = int((main_w - gap * 2) / 3)
            for visual, i in zip(charts[:3], range(3)):
                _append_chart(
                    containers, intent, visual, table_name,
                    margin + i * (chart_w + gap), chart_y, chart_w, chart_h,
                )
            if len(charts) > 3:
                _append_chart(
                    containers, intent, charts[3], table_name,
                    margin, chart_y + chart_h + gap, main_w, 190,
                )

            containers.append(_textbox_vc(
                right_x + 16, kpi_y + 16, right_w - 32, 30, "FILTERS",
                font_size=11, color="#252423", bold=True,
            ))
            for i, slicer in enumerate(slicers[:4]):
                _append_chart(
                    containers, intent, slicer, table_name,
                    right_x + 16, kpi_y + 58 + i * 112, right_w - 32, 92,
                )

        pages.append({
            "name": page.name,
            "displayName": page.display_name,
            "width": canvas_w,
            "height": canvas_h,
            "config": _page_config("#EAF4FC"),
            "visualContainers": containers,
        })

    return {"pages": pages}

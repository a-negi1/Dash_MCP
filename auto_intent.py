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

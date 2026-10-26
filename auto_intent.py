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


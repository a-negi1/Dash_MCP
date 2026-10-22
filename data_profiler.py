import csv, io, re
from datetime import datetime
from models import ColumnProfile, DatasetProfile

MEASURE_KEYWORDS = {
    "sales", "profit", "revenue", "cost", "price", "amount", "total",
    "quantity", "qty", "discount", "margin", "rate", "ratio", "count",
    "sum", "average", "avg", "budget", "spend", "income", "expense",
    "fee", "tax", "weight", "height", "width", "length", "area",
    "volume", "score", "rating", "percentage", "pct", "value", "num",
    "number", "payment", "wage", "salary", "gdp", "units", "orders",
    "transactions", "visits", "sessions", "clicks", "impressions",
}

DIMENSION_KEYWORDS = {
    "id", "key", "code", "name", "type", "category", "class", "group",
    "segment", "region", "country", "state", "city", "status", "flag",
    "label", "tag", "mode", "level", "tier", "channel", "source",
    "department", "division",
}

GEO_KEYWORDS = {
    "country", "state", "province", "city", "zip", "zipcode", "postal",
    "region", "county", "district", "territory", "latitude", "longitude",
    "lat", "lng", "lon", "geo", "address", "location",
}

TEMPORAL_KEYWORDS = {
    "date", "time", "datetime", "timestamp", "year", "month", "quarter",
    "week", "day", "hour", "minute", "period", "fiscal",
}

RATE_KEYWORDS = {
    "rate", "margin", "ratio", "pct", "percentage", "share", "yield",
    "efficiency", "utilization", "conversion", "bounce", "churn",
    "retention", "satisfaction", "score", "rating",
}

COUNT_KEYWORDS = {
    "count", "qty", "quantity", "units", "orders", "transactions",
    "visits", "sessions", "clicks", "impressions", "num", "number",
}

DOMAIN_SIGNATURES = {
    "retail":     ["sales", "profit", "order", "customer", "product", "category", "discount"],
    "finance":    ["revenue", "budget", "fiscal", "quarter", "account", "invoice", "payment"],
    "marketing":  ["click", "impression", "campaign", "conversion", "bounce", "session", "engagement"],
    "operations": ["sensor", "uptime", "latency", "cpu", "memory", "throughput", "error"],
    "hr":         ["employee", "salary", "department", "hire", "headcount", "tenure"],
    "healthcare": ["patient", "diagnosis", "treatment", "hospital", "readmission"],
    "logistics":  ["shipment", "delivery", "warehouse", "route", "fleet", "tracking"],
}

DATE_FORMATS = [
    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%m-%d-%Y",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y",
    "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%Y%m%d",
]


def _col_key(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def _infer_type(values: list[str]) -> str:
    non_null = [v.strip() for v in values if v.strip() not in ("", "null", "NULL", "None", "NA", "N/A")]
    if not non_null:
        return "string"
    sample = non_null[:200]
    n = len(sample)
    threshold = 0.8

    def passes(fn):
        ok = 0
        for v in sample:
            try:
                fn(v)
                ok += 1
            except Exception:
                pass
        return ok / n >= threshold

    bool_vals = {"true", "false", "yes", "no", "1", "0", "t", "f", "y", "n"}
    if passes(lambda v: (_ for _ in ()).throw(ValueError()) if v.lower() not in bool_vals else True):
        return "boolean"

    def try_numeric(v):
        cleaned = re.sub(r"[\$,\s]", "", v).replace("(", "-").replace(")", "")
        if cleaned.endswith("%"):
            cleaned = cleaned[:-1]
        float(cleaned)

    if passes(try_numeric):
        int_ok = sum(1 for v in sample
                     if v.strip().lstrip("-").isdigit()) / n >= threshold
        return "int64" if int_ok else "decimal"

    def try_date(v):
        for fmt in DATE_FORMATS:
            try:
                datetime.strptime(v.strip(), fmt)
                return
            except ValueError:
                pass
        raise ValueError

    if passes(try_date):
        return "dateTime"

    return "string"


def _infer_aggregation(col_name_lower: str, data_type: str) -> str:
    if any(k in col_name_lower for k in RATE_KEYWORDS):
        return "AVG"
    if any(k in col_name_lower for k in COUNT_KEYWORDS):
        return "SUM"
    return "SUM"


def _classify(name: str, data_type: str, cardinality: int, row_count: int,
              sample_values: list) -> tuple[str, str, str]:
    """Returns (role, semantic_type, aggregation)."""
    key = _col_key(name)
    tokens = set(re.split(r"[_\s\-]+", key))

    is_numeric = data_type in ("int64", "decimal")
    is_temporal = data_type == "dateTime"
    is_geo = bool(tokens & GEO_KEYWORDS)
    is_temporal_kw = bool(tokens & TEMPORAL_KEYWORDS)
    is_measure_kw = bool(tokens & MEASURE_KEYWORDS)
    is_dimension_kw = bool(tokens & DIMENSION_KEYWORDS)

    if is_temporal or is_temporal_kw:
        return "dimension", "temporal", "MIN"

    if is_geo:
        return "dimension", "geographic", "COUNT"

    if is_numeric:
        if is_measure_kw:
            agg = _infer_aggregation(key, data_type)
            sem = "rate" if agg == "AVG" else "currency" if any(k in key for k in ("revenue", "sales", "profit", "cost", "price", "amount", "income", "expense", "budget")) else "numeric"
            return "measure", sem, agg
        if is_dimension_kw or (cardinality <= 20 and row_count >= 100):
            return "dimension", "categorical", "COUNT"
        if cardinality <= 5 or (row_count > 0 and cardinality / row_count < 0.05 and cardinality <= 30):
            return "dimension", "categorical", "COUNT"
        agg = _infer_aggregation(key, data_type)
        sem = "rate" if agg == "AVG" else "currency" if any(k in key for k in ("revenue", "sales", "profit", "cost", "price", "amount", "income", "expense", "budget")) else "numeric"
        return "measure", sem, agg

    if is_measure_kw:
        def _looks_numeric(vals):
            ok = sum(1 for v in vals if re.fullmatch(r"[-+]?\d*\.?\d+%?", v.strip().replace(",", "")))
            return ok / max(len(vals), 1) > 0.6
        if _looks_numeric([str(v) for v in sample_values]):
            return "measure", "numeric", "SUM"

    return "dimension", "categorical", "COUNT"


def _detect_domain(col_names: list[str]) -> str:
    joined = " ".join(col_names).lower()
    best, best_score = "general", 0
    for domain, kws in DOMAIN_SIGNATURES.items():
        score = sum(1 for k in kws if k in joined)
        if score >= 2 and score > best_score:
            best, best_score = domain, score
    return best



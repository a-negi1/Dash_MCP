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



from pydantic import BaseModel, Field
from typing import Optional, Any
import uuid, time

class Column(BaseModel):
    name: str
    type: str  # string | int64 | decimal | dateTime | boolean

class TableIntent(BaseModel):
    name: str
    columns: list[Column]

class MeasureIntent(BaseModel):
    name: str
    table: str
    dax: str
    format: str = "#,0.00"

class RelationshipIntent(BaseModel):
    from_table: str
    from_col: str
    to_table: str
    to_col: str

class VisualIntent(BaseModel):
    type: str        # columnChart | lineChart | card | slicer | tableEx | barChart | pieChart
    title: str = ""
    x_axis: str = ""
    y_axis: str = ""
    field: str = ""  # for slicers
    value: str = ""  # for cards

class PageIntent(BaseModel):
    name: str
    display_name: str
    visuals: list[VisualIntent]

class ReportIntent(BaseModel):
    report_title: str
    tables: list[TableIntent]
    measures: list[MeasureIntent]
    relationships: list[RelationshipIntent]
    pages: list[PageIntent]

class ColorPalette(BaseModel):
    primary: str        # hex e.g. "#2D5BFF"
    secondary: str
    accent: str
    background: str = "#FFFFFF"
    text: str = "#252423"
    data_colors: list[str] = []   # up to 8 hex values for chart series

class ColumnProfile(BaseModel):
    name: str
    role: str
    semantic_type: str
    data_type: str
    cardinality: int
    null_pct: float
    aggregation: str
    sample_values: list[Any] = []

class DatasetProfile(BaseModel):
    row_count: int
    columns: list[ColumnProfile]
    dimensions: list[str]
    measures: list[str]
    temporal_columns: list[str]
    geographic_columns: list[str]
    domain_hint: str
    has_strong_temporal: bool
    has_strong_geographic: bool
    has_part_to_whole: bool
    kpi_count: int

class ProjectState(BaseModel):

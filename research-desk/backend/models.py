"""Typed inputs and model outputs; unknown fields are rejected."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

Mode = Literal["baseline", "history", "lessons"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Selection(Strict):
    status: Literal["answer", "review"]
    operand_ids: list[str] = Field(max_length=2)
    explanation: str = Field(min_length=1, max_length=4000)
    qualification: str = Field(max_length=2000)


class Audit(Strict):
    supported: bool
    issues: list[str] = Field(max_length=8)
    explanation: str = Field(max_length=2000)


class LabelBinding(Strict):
    kind: Literal["source_label_binding"]
    first_label: str = Field(min_length=1, max_length=150)
    second_label: str = Field(min_length=1, max_length=150)
    period_kind: Literal["annual", "quarterly"]
    revenue_basis: Literal["sales", "total_revenue"]


class Procedure(Strict):
    procedure: str = Field(min_length=20, max_length=1800)
    conditions: list[str] = Field(min_length=1, max_length=6)
    exclusions: str = Field(min_length=10, max_length=1200)
    rationale: str = Field(min_length=10, max_length=1200)
    binding: LabelBinding | None = Field(
        default=None,
        description="For a corrected source-ID/operand-order error, bind the first and second operand to exact source row labels, reporting-period kind and requested revenue basis. No IDs, figures, dates, code or answers. Otherwise null.",
    )


class Analyze(Strict):
    case_id: str
    mode: Mode = "lessons"


class Correction(Strict):
    attempt_id: str
    text: str = Field(min_length=10, max_length=4000)
    checked: bool
    parent_id: str | None = None


class Identifier(Strict):
    id: str


class Decision(Identifier):
    status: Literal["accepted", "disabled", "rejected"]
    reviewed: bool = False


class Review(Identifier):
    status: Literal["reviewed", "needs_correction"]


class Freeze(Strict):
    reviewed: bool


class Evaluate(Strict):
    split: Literal["validation", "final"] = "validation"
    freeze_id: str | None = None


class Step(Strict):
    company: str
    task: Literal["operating_margin", "revenue_growth"]
    period: int = Field(ge=1990, le=2100)
    prior_period: int = Field(ge=1990, le=2100)
    revenue_basis: Literal["sales", "total_revenue"]


class Plan(Strict):
    summary: str
    steps: list[Step] = Field(max_length=6)
    clarification: str = ""


class Assignment(Strict):
    question: str = Field(min_length=12, max_length=1800)
    companies: list[str] = Field(min_length=1, max_length=2)
    mode: Mode = "lessons"
    source_id: str | None = Field(default=None, min_length=1, max_length=200)


class Cell(Strict):
    id: str = Field(min_length=1, max_length=140)
    company: str = Field(min_length=1, max_length=100)
    period: int = Field(ge=1990, le=2100)
    label: str = Field(min_length=1, max_length=150)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=50)
    source: HttpUrl
    location: str = Field(min_length=1, max_length=250)


class Import(Strict):
    name: str = Field(min_length=3, max_length=150)
    company: Literal["Target", "Costco"]
    source_url: HttpUrl
    format: Literal["pdf", "html", "text"]
    content: str = Field(min_length=10, max_length=12000000)


class Curate(Strict):
    document_id: str
    company: Literal["Target", "Costco"]
    convention: str = Field(min_length=3, max_length=150)
    notes: str = Field(min_length=5, max_length=10000)
    cells: list[Cell] = Field(min_length=2, max_length=100)
    checked: bool

    @field_validator("cells")
    @classmethod
    def unique_cells(cls, cells):
        if len({c.id for c in cells}) != len(cells):
            raise ValueError("Source-cell IDs must be unique")
        return cells


class Search(Strict):
    query: str = Field(min_length=3, max_length=500)
    company: Literal["Target", "Costco"] | None = None

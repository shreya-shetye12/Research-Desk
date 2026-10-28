"""A bounded learned action: look up two original labels, never execute code.

The teacher supplies labels and scope from checked feedback. The runtime resolves
new report IDs from that saved rule. There are no reference answers or company
specific mappings in this executor. Missing/ambiguous matches require review.
"""

import re
import unicodedata
from .models import LabelBinding


def normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def cell_kind(cell):
    location = normalize(cell.get("location", ""))
    kinds = set()
    if re.search(r"\bannual\b|\bfull[- ]year\b", location):
        kinds.add("annual")
    if re.search(r"\bquarter(?:ly)?\b|\bq[1-4]\b", location):
        kinds.add("quarterly")
    for weeks in re.findall(r"\b(\d{1,2})\s*weeks?\b", location):
        if int(weeks) in {52, 53}:
            kinds.add("annual")
        elif int(weeks) in {12, 13, 14, 16, 17}:
            kinds.add("quarterly")
    return next(iter(kinds)) if len(kinds) == 1 else None


def requested_kind(case):
    text = normalize(case.get("request_context") or case["question"])
    # Ignore a report title before the actual calculation request.
    text = re.split(r"\b(?:calculate|compute|determine|find)\b", text)[-1]
    text = re.split(r"\bfrom\b", text, maxsplit=1)[0]
    annual = bool(re.search(r"\bfull[- ]year\b|\bannual\b", text))
    quarterly = bool(
        re.search(
            r"\b(?:first|second|third|fourth)[- ]quarter\b|\bq[1-4]\b|\bquarterly\b|\b(?:12|13|14|16|17)[- ]weeks?\b",
            text,
        )
    )
    if annual or quarterly:
        return None if annual and quarterly else "annual" if annual else "quarterly"
    kinds = {
        cell_kind(c)
        for c in case["cells"]
        if c["company"] == case["company"] and c["period"] == case["period"]
    }
    return next(iter(kinds)) if len(kinds) == 1 and None not in kinds else None


def scope_matches(binding, case):
    try:
        binding = LabelBinding.model_validate(binding).model_dump()
    except ValueError:
        return False
    return binding["revenue_basis"] == case["revenue_basis"] and binding[
        "period_kind"
    ] == requested_kind(case)


def resolve(binding, case):
    binding = LabelBinding.model_validate(binding).model_dump()
    if not scope_matches(binding, case):
        raise ValueError(
            "The learned binding does not match the requested basis and reporting period"
        )
    periods = [
        case["period"],
        (
            case.get("prior_period")
            if case["task"] == "revenue_growth"
            else case["period"]
        ),
    ]
    selected = []
    for label, period in zip(
        [binding["first_label"], binding["second_label"]], periods
    ):
        matches = [
            c
            for c in case["cells"]
            if (
                c["company"] == case["company"]
                and c["period"] == period
                and normalize(c["label"]) == normalize(label)
                and cell_kind(c) == binding["period_kind"]
            )
        ]
        if len(matches) != 1:
            raise ValueError(
                f"The learned label '{label}' has {len(matches)} matching source rows; review the source"
            )
        selected.append(matches[0])
    if selected[0]["id"] == selected[1]["id"]:
        raise ValueError(
            "The learned operands must resolve to two distinct source cells"
        )
    if selected[0]["unit"] != selected[1]["unit"]:
        raise ValueError("The learned operands use different units")
    return [c["id"] for c in selected]


def apply(case, selection, memory):
    actions = [p for p in memory if p.get("binding")]
    if not actions:
        return selection
    traces, choices = [], []
    original = dict(selection)
    try:
        for p in actions:
            ids = resolve(p["binding"], case)
            choices.append(ids)
            traces.append(
                {
                    "procedure_id": p["id"],
                    "version": p["version"],
                    "binding": p["binding"],
                    "resolved_operand_ids": ids,
                }
            )
        if any(ids != choices[0] for ids in choices[1:]):
            raise ValueError("Accepted procedures disagree on source operand roles")
    except ValueError as error:
        return {
            **selection,
            "status": "review",
            "operand_ids": [],
            "qualification": str(error),
            "procedure_execution": {
                "status": "review",
                "original_selection": original,
                "actions": traces,
                "issue": str(error),
            },
        }
    first = actions[0]["binding"]
    return {
        **selection,
        "status": "answer",
        "operand_ids": choices[0],
        "explanation": f"Applied the saved source-label procedure: copied the exact IDs for {first['first_label']} first and {first['second_label']} second from the requested {first['period_kind']} source columns. Original model selection and the binding trace are retained for review.",
        "procedure_execution": {
            "status": "applied",
            "original_selection": original,
            "actions": traces,
        },
    }

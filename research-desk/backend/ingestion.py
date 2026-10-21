"""Bounded report sections. Extraction is never approval of financial evidence."""

import base64
import hashlib
import io
import re
from decimal import Decimal
from html.parser import HTMLParser
import pdfplumber
from . import corpus, store


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        elif tag in {"tr", "p", "div", "h1", "h2", "h3", "table"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def ingest(request):
    raw = (
        base64.b64decode(request.content, validate=True)
        if request.format == "pdf"
        else request.content.encode()
    )
    if len(raw) > 8_000_000:
        raise ValueError("Use a report section under 8 MB")
    tables = []
    if request.format == "pdf":
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            if len(pdf.pages) > 80:
                raise ValueError("Select up to 80 PDF pages")
            parts = []
            for i, page in enumerate(pdf.pages):
                parts.append(f"PAGE {i+1}\n" + (page.extract_text() or ""))
                tables.extend({"page": i + 1, "rows": t} for t in page.extract_tables())
            text = "\n\n".join(parts)
    elif request.format == "html":
        parser = HTMLText()
        parser.feed(raw.decode(errors="replace"))
        text = "".join(parser.parts)
    else:
        text = raw.decode(errors="replace")
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 30:
        raise ValueError(
            "No usable text found. Scanned PDFs need OCR outside this importer."
        )
    if len(text) > 180000:
        raise ValueError(
            "Extract a smaller section; source text exceeds 180,000 characters"
        )
    sha = hashlib.sha256(raw).hexdigest()
    identifier = (
        "document_"
        + corpus.digest(
            {"sha": sha, "company": request.company, "source": str(request.source_url)}
        )[:18]
    )
    item = store.create_once(
        "document",
        {
            "name": request.name,
            "company": request.company,
            "source": str(request.source_url),
            "sha256": sha,
            "content": text,
            "tables": tables,
            "status": "needs_curation",
        },
        identifier,
    )
    store.log("Report extracted", request.name + " · unavailable until source curation")
    return {"document_id": item["id"]}


def curate(request):
    if not request.checked:
        raise ValueError(
            "Check every figure and definition against the original source before use"
        )
    doc = store.get("document", request.document_id)
    if doc["company"] != request.company:
        raise ValueError("Company must match the imported document")
    protected = {
        (c["company"], c["period"], c["value"], c["unit"])
        for case in corpus.cases()
        if case["split"] in {"validation", "final"}
        for c in case["cells"]
    }
    for cell in request.cells:
        if cell.company != request.company or str(cell.source) != doc["source"]:
            raise ValueError("Cell company and source must match the imported report")
        if (cell.company, cell.period, cell.value, cell.unit) in protected:
            raise ValueError(
                "Imported figures overlap reserved evaluation evidence; keep them outside teaching"
            )
        numbers = re.findall(
            r"(?<![\w.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?![\w])",
            doc["content"].replace(",", "").replace("−", "-"),
        )
        if Decimal(str(cell.value)) not in {Decimal(n) for n in numbers}:
            raise ValueError(f"Source figure not found in extracted text: {cell.label}")
    if (
        request.convention.startswith("target_")
        and request.company != "Target"
        or request.convention.startswith("costco_")
        and request.company != "Costco"
    ):
        raise ValueError("The chosen report convention belongs to another company")
    convention = (
        request.convention
        if request.convention
        in {
            "target_separate_sales_total_revenue",
            "target_2024_new",
            "costco_net_sales_plus_fees",
        }
        else "new_convention:" + request.document_id
    )
    pid = "pack_" + request.document_id
    pack = {
        "company": request.company,
        "report": convention,
        "group": request.document_id,
        "split": "learning",
        "notes": request.notes,
        "cells": [c.model_dump(mode="json") for c in request.cells],
        "source_review": "human attested",
        "document_id": doc["id"],
    }
    with store.connect() as db:
        store.put("pack", pack, pid, db)
        store.put("document", dict(doc, status="curated"), doc["id"], db)
    store.log("Source evidence curated", doc["name"] + " · human checked")
    return {"pack_id": pid}

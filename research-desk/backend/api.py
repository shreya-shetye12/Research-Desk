"""Single-user loopback API. No reference files or personal files are static assets."""

import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import corpus, engine, evaluation, jobs, learning, model, models, store
from . import ingestion
import os
from .store import ROOT

TOKEN = secrets.token_urlsafe(24)


@asynccontextmanager
async def lifespan(app):
    store.initialize()
    jobs.recover()
    yield


app = FastAPI(
    title="SHIFT + APPRENTICE — Hackathon edition",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
)


@app.middleware("http")
async def boundary(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("x-workspace-token") != TOKEN:
            return JSONResponse(
                {"error": "Refresh the workspace and try again."}, status_code=403
            )
        if request.headers.get("origin") not in {
            None,
            str(request.base_url).rstrip("/"),
        }:
            return JSONResponse({"error": "Local origin required"}, status_code=403)
        limit = 13_000_000 if request.url.path == "/api/import" else 100_000
        if len(await request.body()) > limit:
            return JSONResponse({"error": "Request too large"}, status_code=413)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'"
    )
    return response


@app.exception_handler(ValueError)
async def invalid(request, error):
    return JSONResponse({"error": str(error)}, status_code=400)


@app.get("/health")
def health():
    return {"status": "ok", "edition": "hackathon"}


@app.get("/api/state")
def state():
    reviews = {r["attempt_id"]: r["status"] for r in store.rows("review")}
    attempts = store.rows("attempt")
    for attempt in attempts:
        attempt["review"] = reviews.get(attempt["id"], "unreviewed")
    procedures = store.rows("procedure")
    for p in procedures:
        if p.get("validation"):
            p["validation"] = {k: v for k, v in p["validation"].items() if k != "rows"}
    evals = []
    for e in store.rows("evaluation"):
        evals.append({k: v for k, v in e.items() if k != "rows"})
    return {
        "token": TOKEN,
        "model": model.health(),
        "cases": corpus.cases("learning"),
        "attempts": attempts,
        "procedures": procedures,
        "jobs": store.rows("job")[:20],
        "integrity": corpus.integrity(),
        "evaluations": evals,
        "freezes": [
            {"id": f["id"], "created": f["created"]} for f in store.rows("freeze")
        ],
        "events": store.rows("event")[:40],
        "changes": corpus.changes(),
        "packs": corpus.packs(),
        "catalog": corpus.catalog(),
        "documents": [
            {k: v for k, v in d.items() if k not in {"content", "tables"}}
            for d in store.rows("document")
        ],
        "tracking_enabled": os.environ.get("SHIFT_TRACKING", "1") != "0",
    }


@app.post("/api/analyze", status_code=202)
def analyze(request: models.Analyze):
    case = corpus.brief(request.case_id)
    return jobs.analysis(
        {
            "case": case,
            "question": case["question"],
            "companies": [case["company"]],
            "mode": request.mode,
        }
    )


@app.post("/api/assignments", status_code=202)
def assignment(request: models.Assignment):
    packs = corpus.packs()
    companies = {p["company"] for p in packs}
    if not set(request.companies).issubset(companies):
        raise ValueError("Choose companies with available source evidence")
    if request.source_id:
        source = next((p for p in packs if p["id"] == request.source_id), None)
        if source is None:
            raise ValueError("The selected report is no longer available")
        if set(request.companies) != {source["company"]}:
            raise ValueError("Select only the company belonging to the chosen report")
    return jobs.analysis(request.model_dump())


@app.post("/api/retry", status_code=202)
def retry(request: models.Identifier):
    return jobs.retry(request.id)


@app.post("/api/import", status_code=202)
def import_report(request: models.Import):
    return jobs.submit("Extract report section", lambda emit: ingestion.ingest(request))


@app.get("/api/documents/{identifier}")
def document(identifier: str):
    return store.get("document", identifier)


@app.post("/api/curate")
def curate(request: models.Curate):
    if jobs.BUSY.locked():
        raise ValueError("Finish the running task before changing source evidence")
    return ingestion.curate(request)


@app.post("/api/search", status_code=202)
def search(request: models.Search):
    from .retrieval import retrieve

    def operation(emit):
        emit("retrieve", "Searching checked report evidence")
        sources, details = retrieve(
            request.query,
            [
                p
                for p in corpus.packs()
                if not request.company or p["company"] == request.company
            ],
            semantic=os.environ.get("SHIFT_SEMANTIC", "1") != "0",
        )
        return {"sources": sources, "retrieval": details}

    return jobs.submit("Search source evidence", operation)


@app.post("/api/corrections", status_code=202)
def correction(request: models.Correction):
    if not request.checked:
        raise ValueError("Check the correction against the original source first.")
    return jobs.submit(
        "Propose a procedure",
        lambda emit: learning.propose(
            request.attempt_id, request.text, request.checked, request.parent_id
        ),
    )


@app.post("/api/validate", status_code=202)
def validate(request: models.Identifier):
    return jobs.submit(
        "Validate candidate", lambda emit: learning.validate(request.id, emit)
    )


@app.post("/api/refine", status_code=202)
def refine(request: models.Identifier):
    return jobs.submit("Refine procedure", lambda emit: learning.refine(request.id))


@app.post("/api/procedures")
def decide(request: models.Decision):
    return learning.decide(request.id, request.status, request.reviewed)


@app.post("/api/reviews")
def review(request: models.Review):
    return jobs.review_attempt(request.id, request.status)


@app.get("/api/reviews")
def reviews():
    return store.rows("review")


@app.post("/api/freeze")
def freeze(request: models.Freeze):
    if jobs.BUSY.locked():
        raise ValueError("Finish the running task before freezing the experiment.")
    return evaluation.freeze(request.reviewed)


@app.post("/api/evaluate", status_code=202)
def replay(request: models.Evaluate):
    return jobs.submit(
        "Replay " + request.split,
        lambda emit: evaluation.replay(request.split, request.freeze_id, emit),
    )


@app.get("/api/evaluations/{identifier}")
def experiment(identifier: str):
    return store.get("evaluation", identifier)


@app.get("/api/procedures/{identifier}")
def procedure(identifier: str):
    p = store.get("procedure", identifier)
    return {**p, "checked_correction": store.get("correction", p["correction_id"])}


@app.get("/api/memo/{identifier}")
def memo(identifier: str):
    a = store.get("attempt", identifier)
    c, r = a["case"], a["result"]
    review = next(
        (v["status"] for v in store.rows("review") if v["attempt_id"] == identifier),
        "unreviewed",
    )
    lines = [
        "# SHIFT + APPRENTICE",
        c["question"],
        "",
        f"Status: {r['status']} · Human review: {review}",
        (
            f"Result: {r['result']}%"
            if r["result"] is not None
            else "Result requires review"
        ),
        r["formula"] or "",
        r["explanation"],
        r["qualification"],
        "",
        "## Source evidence",
    ]
    lines += [
        f"- {s['label']} · FY{s['period']} · {s['value']} {s['unit']} · [{s['location']}]({s['source']})"
        for s in c["cells"]
    ]
    lines += [
        "",
        c["notes"],
        "",
        "Model-assisted review and arithmetic checks do not establish accounting correctness.",
    ]
    return PlainTextResponse(
        "\n\n".join(lines),
        headers={
            "Content-Disposition": f'attachment; filename="shift-{identifier}.md"'
        },
    )


@app.get("/")
def index():
    return FileResponse(ROOT / "web/index.html")


@app.get("/{asset}")
def asset(asset: str):
    from fastapi import HTTPException

    if asset not in {"app.js", "features.js", "style.css", "favicon.svg"}:
        raise HTTPException(404)
    return FileResponse(ROOT / "web" / asset)

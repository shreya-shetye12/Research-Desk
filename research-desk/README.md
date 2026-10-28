# Research Desk

**Financial AI that turns analyst corrections into tested, reusable procedures.**

## Project summary

**Problem:** Financial reports change labels and mix annual and quarterly figures. An assistant can calculate correctly using the wrong inputs, leaving analysts to identify and repeatedly correct the same selection mistakes.

**Solution:** Research desk exposes the inputs behind an answer, captures an analyst's checked correction, and validates a reusable procedure before activation. It supports **Target and Costco operating margins and reported revenue growth**, on sales or total-revenue bases.

**Who it helps:** Analysts reviewing recurring financial reports. The intended benefit is fewer repeated corrections as approved procedures accumulate; review-time and cost savings remain unmeasured.

## How it works

**Report → source curation → plan → retrieve evidence → select figures → audit and calculate → human review → memo.**

When a reviewed answer is wrong:

**Checked correction → inactive procedure draft → separate validation → human approval → scoped reuse.**

One Qwen3 model performs separate **planner, analyst, auditor and teacher** calls: creating tasks, selecting figures, checking selections and drafting lessons. These are coordinated roles, not independently trained agents. Python executes the formulas.

Learning changes **procedural memory, not model weights**. Typed rules save ordered source labels, scoped by company, report convention, task, period type and revenue basis. Python resolves current IDs; ambiguous or conflicting matches require review.

## Features

| Area | What is implemented |
| --- | --- |
| Research | Prepared examples; assignments up to six steps; company/report selection; margins, growth, source figures, formulas, citations and fiscal-period notes. |
| Ingestion | PDF/HTML/text extraction, PDF table preview and source hashes. Checked curation preserves labels, units, years, definitions and locations before use. |
| Search | Hybrid keyword/vector retrieval with reciprocal-rank fusion, evidence allowlists and recorded BM25 fallback. |
| Memory | Baseline, correction-history and validated-procedure modes; correction traces, drafts, refinement, versions, rejection, disabling and approved supersession. |
| Validation | Paired comparisons. Acceptance requires an applicable gain, all applicable cases passing, boundary coverage, zero observed regressions, current fingerprints and human approval. |
| Workflow | Graph checkpoints, visible stages, human-review pauses, saved decisions and failed/interrupted research recovery. |
| Experiments | Three-mode replay, model/settings/data fingerprints, MLflow traces/metrics, evaluator-only references, reviewed final freezes and exposure tracking. |
| Dashboard | Validation summary, review queue, analysis/source registers, report-change signals, activity and Markdown memo export. |

## Stack and why

| Technology | Role and reason |
| --- | --- |
| Python 3.12, FastAPI, Pydantic | Backend APIs, typed requests and schema-validated model outputs. |
| Ollama + Qwen3 8B | Local role calls without a hosted inference key; one model keeps the runtime manageable. Cost savings remain unmeasured. |
| LangGraph + SQLite | Stateful orchestration, review and recovery; persistent checkpoints, records and procedure versions. |
| LlamaIndex, BM25, Chroma, Nomic Embed Text | Retrieval interface, exact-term ranking, persistent vectors and local semantic embeddings. |
| pdfplumber + HTML/text parsing | Bounded extraction; human curation separates extracted text from checked evidence. |
| Restricted calculator + typed rule executor | Deterministic formulas and current-ID resolution without generated-code execution. |
| MLflow | Inspectable local traces, evaluation parameters and metrics. |
| HTML, CSS, JavaScript | Responsive dark UI; no Node.js or frontend build step. |
| pytest | Offline workflow and boundary checks using mocked inference and isolated state. |

## Run locally

Requires **Python 3.12+**, **Ollama** and memory for local models. Initial downloads need internet; no training is required.

Using Conda:

```sh
conda create -n shift python=3.12 pip
conda activate shift
python -m pip install -r requirements.txt -c requirements.lock.txt
python -m pip check
```

Alternatively, `./scripts/setup.sh` creates `.venv`; select Python with `SHIFT_PYTHON=python3.12 ./scripts/setup.sh` if needed.

Start Ollama if it is not already running (keep this terminal open):

```sh
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 ollama serve
```

In your project terminal, download the models once:

```sh
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

Start the app from the project folder:

```sh
./scripts/run.sh
```

Open **http://127.0.0.1:8503/**. If occupied, run `PORT=8506 ./scripts/run.sh` and open **http://127.0.0.1:8506/**. The launcher prefers the active Conda environment, then `.venv`. Startup does not download models.

Open **Research** for examples, **Sources** for imports, **Memory** for lessons and **Inspect** for experiments. A fresh checkout has no personal uploads, accepted procedures or runtime history.

## Using the app

1. In **Research**, choose a prepared example or select a company and report for an assignment. Start with **Without memory** to inspect the baseline.
2. For your own report, use **Sources** to import it, check the extracted figures against the original, and make the evidence available before analysis.
3. Run the analysis and inspect its figures, period, units, formula and source locations. An arithmetic check does not establish that the selected figures are correct.
4. If an answer is wrong, use **Correct & teach** to provide a source-checked correction and draft a reusable procedure.
5. In **Memory**, validate the inactive candidate, inspect its gains and boundary cases, and review acceptance if it passes the gate.
6. Rerun a matching question with **Validated procedures**. Inspect the applied procedure and source selections to confirm actual reuse. Questions outside its scope should not use it.

For the Costco FY2024 full-year total-revenue example, the reference calculation is `9285 / 254453 * 100`, approximately **3.65%**. The report also contains quarterly figures, so selecting the annual column matters. A fresh model run may already be correct; a successful baseline is not evidence of learning.

## Reliability and human oversight

Structured-output validation, evidence allowlists, source auditing and scoped rule execution constrain agent behavior. Stage traces preserve original selections and applied procedures for inspection. Unsupported or ambiguous evidence requires review. Candidate procedures remain inactive until paired validation and human approval; configuration fingerprints prevent stale validation from authorizing acceptance. Procedures can be rejected, disabled or superseded. The auditor can still miss errors, so arithmetic checks and model agreement do not replace human review.

The dashboard organizes research, sources, procedural memory and evaluation around the analyst's review task. Source figures, formulas, candidate status and validation comparisons remain visible so users can inspect how an answer was produced.

## Recorded results

**71 authored questions** cover six source groups: 16 learning, 50 development validation and 5 reserved final. The development suite contains 30 distinct calculations and 20 labeled row-order/opaque-ID variants over three validation source groups. See [the expanded evaluation guide](docs/EVALUATION_50.md) and [the fresh measured report](results/RESULTS.md). Prepared JSON excerpts link to corporate reports; they are not downloaded FinanceQA examples or bundled PDFs. Imports are separate. Full corpus review is required before final freezing.

**Fresh 50-case run: 34/50 (68%) baseline → 38/50 (76%) with an explicitly unapproved evaluation-only reference rule; +8 percentage points.** The original application name and approval workflow are unchanged. All 82 software tests passed. Full results, per-case CSV and actual MLflow traces are in [results/](results/RESULTS.md).

**Historical result recorded in the supplied README: 9/12 → 11/12; 2 gains, 0 regressions.** This is not the new 50-case result. Both gains are annual-margin questions from one separate Costco release; one sales-basis boundary still fails. In isolated UI QA, an approved rule corrected FY2024 Costco’s reversed-operand result from **2740.47% to 3.65%**; Target growth used zero Costco procedures.

The new 50-case runner uses an explicit reference rule derived from this checkout’s learning evidence, because the supplied source ZIP has no saved accepted procedure. It never activates that rule in the application or claims new human approval. The fresh report includes its actual results and model fingerprints. This measures the combined rule/execution system, not text-only memory. It is development evidence, not an independent benchmark. An equivalent nonlearning typed-rule baseline remains untested. No real reserved-final replay has occurred.

## Project structure and key files

| File | What to review |
| --- | --- |
| [backend/workflow.py](backend/workflow.py) and [backend/engine.py](backend/engine.py) | Stateful orchestration and model-driven analysis. |
| [backend/learning.py](backend/learning.py) | Correction-to-procedure workflow, validation gates and approval. |
| [backend/bindings.py](backend/bindings.py) | Scoped source-label matching and ordered operand resolution. |
| [backend/retrieval.py](backend/retrieval.py) and [backend/ingestion.py](backend/ingestion.py) | Hybrid evidence retrieval and report extraction. |
| [backend/evaluation.py](backend/evaluation.py) and [data/cases.json](data/cases.json) | Evaluation controls and authored source-linked cases. |
| [web/index.html](web/index.html), [web/style.css](web/style.css) and [web/app.js](web/app.js) | Dashboard design and interactions. |
| [tests/test_workflow.py](tests/test_workflow.py) and [tests/test_bindings.py](tests/test_bindings.py) | Offline workflow, acceptance and rule-boundary checks. |

## Checks

```sh
python -m pip install -r requirements-dev.txt -c requirements.lock.txt
python -m pytest tests -q
python scripts/evaluate.py check
```




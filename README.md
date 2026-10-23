# CT-200 Manual Intelligence API

A Python/FastAPI prototype for the Tri9T AI assignment. It parses the supplied CT-200 PDF manuals into versioned section nodes, exposes browse/search/change APIs, stores version-pinned selections, generates QA ideas with a deterministic fallback (optional OpenAI-compatible generation), and checks generated cases for staleness.

## Implemented
- PDF text extraction using PyMuPDF; numbered heading hierarchy; body text, parent/child references, page spans, SHA-256 content hashes.
- Separate v1 and v2 records. Logical IDs are derived from parent logical ID + section number + normalized heading; version-specific IDs preserve snapshots.
- Browse: `/sections`, `/nodes/{node_id}`, `/search`, `/changes/{logical_id}`.
- Version-pinned selections: `POST /selections`, `GET /selections/{selection_id}`.
- QA generation: `POST /generate`; output is validated for 3–5 structured cases. If LLM key is missing, request fails, or output is malformed, deterministic rules-based fallback is used.
- Retrieval/staleness: `GET /generations/{generation_id}`, `GET /generations?selection_id=...` and optional `node_id`.
- At least 3 irregularity-focused tests.

## Run locally
Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs. On first startup, the included v1 and v2 PDFs are parsed and stored in `ct200.db`.

## Quick demo
1. `GET /sections?version=1` and `GET /sections?version=2`.
2. `GET /search?q=battery&version=1` then v2.
3. Copy a node ID from the response and use `GET /nodes/{node_id}`.
4. To create a selection, send `POST /selections` with `{"name":"Battery QA","version":2,"node_ids":["<version-2-node-id>"]}`.
5. Send `POST /generate` with `{"selection_id":"<returned-id>"}`.
6. Retrieve `GET /generations/{generation_id}` to inspect staleness. For optional LLM generation install `openai`, set `OPENAI_API_KEY`, then use `{"selection_id":"...","provider":"openai"}`.
7. Run tests: `pytest -q`.

## Important scope/limitations
- This version uses text extraction, not a full OCR engine. Pages without selectable text are reported in `empty_text_pages`; scanned pages need OCR added (e.g. Tesseract or a document OCR service).
- Numbered headings are inferred from text, so layout edge cases and table reconstruction need visual QA. Table rows currently remain as body text rather than structured cells.
- The source manuals contain irregular numbering (e.g. 2.1.1.1 without 2.1.1 and 3.4 before 3.3). The parser preserves order and does not invent missing sections. The parent is the nearest preceding shallower numbered section; this is a stated heuristic, not a claim of perfect semantic hierarchy.
- Stable logical IDs use path/number/title. Renumbering or moving a section can change identity; ambiguous duplicate headings should be reviewed. Version-specific IDs retain historical snapshots.
- Staleness is hash-based: any body-text change marks a generation stale, even if the change is editorial rather than safety-critical. It does not yet classify semantic risk.
- LLM output is accepted only if it is valid JSON containing 3–5 objects with required keys. Otherwise the deterministic fallback is used. Duplicate generation requests create separate generation records.

## API endpoints
| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/versions` | Available versions |
| POST | `/ingest/{version}` | Upload and ingest a PDF |
| GET | `/sections?version=1` | Top-level sections |
| GET | `/nodes/{node_id}` | Node with children and hash |
| GET | `/search?q=battery&version=2` | Search headings/body |
| GET | `/changes/{logical_id}` | Compare node versions |
| POST | `/selections` | Save version-pinned selection |
| GET | `/selections/{selection_id}` | Retrieve immutable selection snapshot |
| POST | `/generate` | Generate QA ideas |
| GET | `/generations/{generation_id}` | Retrieve cases and staleness |
| GET | `/generations?selection_id=...` | List generations |

## Engineering notes
See `docs/APPROACH.md` and `docs/DECISION_LOG.md`.

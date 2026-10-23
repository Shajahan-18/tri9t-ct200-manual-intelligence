# Decision Log

## D1 — PyMuPDF before OCR
**Decision:** Use PyMuPDF text extraction for text-native supplied manuals and report pages with no extractable text.
**Reason:** Preserves selectable text and avoids OCR errors on content that already has a text layer.
**Trade-off:** Scanned pages need an OCR adapter; not claimed as implemented.

## D2 — Explicit numbering plus stack hierarchy
**Decision:** Infer levels from section-number depth and attach a node to the nearest preceding shallower level.
**Reason:** The source uses numbered headings and contains missing/out-of-order numbers.
**Trade-off:** Does not fabricate absent parents; semantic parent inference may need manual review.

## D3 — Path-based logical ID, version-specific node ID
**Decision:** Logical ID uses parent logical ID, section number, and normalized heading; physical node ID includes version.
**Reason:** Body edits should not create a brand-new logical node; version-specific IDs preserve exact historical nodes.
**Trade-off:** Renumbering/moving headings can break identity.

## D4 — SHA-256 body hashes for staleness
**Decision:** Exact body-text hash comparison.
**Reason:** Deterministic, fast, and explainable.
**Trade-off:** Any textual change marks stale; no semantic risk weighting.

## D5 — Validated LLM output with fallback
**Decision:** Accept only valid JSON array of 3–5 test case objects with required keys; otherwise use deterministic rules fallback.
**Reason:** API reliability should not depend on model output being well formed.
**Trade-off:** Fallback ideas are generic and should be reviewed by a human.

## D6 — Duplicate generation policy
**Decision:** Every generation request creates a new generation record.
**Reason:** Retains run history and makes repeat attempts auditable.

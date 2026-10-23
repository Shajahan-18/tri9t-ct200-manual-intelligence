# Approach Document — CT-200 Manual Intelligence API

## 1. Objective
Build a backend that converts the two supplied CT-200 manuals into a browsable, versioned hierarchy, then generates QA test ideas tied to immutable source text and reports when that source changes.

## 2. Parsing approach
The supplied PDFs expose selectable text, so PyMuPDF is used first to extract text lines, page numbers, and font sizes. This avoids unnecessary OCR noise for text-native pages. The parser detects numbered headings using their printed section numbers and uses numbering depth to infer level. It stores heading, body, level, parent ID, child IDs, page range, version-specific ID, logical ID, and SHA-256 content hash. Empty-text pages are surfaced as a warning for OCR rather than silently treated as parsed.

## 3. Hierarchy strategy and edge cases
- `2.1.1.1 Battery Life Under Typical Use` appears without an explicit `2.1.1` heading. The parser preserves level 4 and does not fabricate the missing node.
- `3.4 Auto Shutoff` appears before `3.3 Result Display and Classification`. Source order is preserved; numbering is not sorted into a false order.
- Classification lists and error-code tables are kept as source body text. This retains their content, but does not yet represent table cells as structured data.
- Similar or repeated heading text can occur in multiple branches. Logical identity includes parent logical ID, section number, and normalized heading so same titles in different branches are not merged by title alone.
- Hyphenation/ligature artifacts are normalized conservatively (`ﬁ`/`ﬂ`, soft hyphen). Original source PDFs remain included and should be used for visual comparison.

## 4. Version matching
A logical ID is computed from the parent logical ID + section number + normalized heading. A version-specific node ID adds the version prefix. This preserves the same logical identity when body text changes but the section path/number/title remain stable. SHA-256 hashes of body text detect exact changes. Limitations: section renumbering/moves can create new logical IDs; duplicate same-number/same-title sections may need a disambiguator; semantic equivalence is not inferred from hashes.

## 5. API and persistence
SQLite stores versions, nodes, selections, and generations. Version 1 and version 2 are separate snapshots. Selections validate that all requested node IDs belong to the selected version and store full text + hashes at creation time. Generated cases store the selection ID and source hashes, so old selections remain resolvable after a later ingestion.

## 6. QA generation and failure handling
If configured, an OpenAI-compatible client is asked for a JSON array of 3–5 test-case objects. Output is validated for JSON shape and required fields. Exceptions, absent keys, malformed JSON, or invalid shape trigger deterministic rules-based generation; the API still returns 3–5 structured ideas and labels the provider as fallback. The fallback is intentionally transparent and is not represented as LLM output. Repeating the same request creates a new generation record, preserving run history rather than overwriting it.

## 7. Staleness / impact detection
At retrieval time, each source node's original hash is compared to the latest version's hash for the same logical ID. Any mismatch marks the generation stale. This is deliberately conservative and easy to explain. It does not distinguish a punctuation edit from a clinically important threshold change; a future enhancement could classify numeric/safety-critical changes and show a semantic diff.

## 8. Validation
The test suite checks v1/v2 battery changes, preservation of the missing intermediate heading, out-of-order 3.4/3.3 headings, and deterministic hashing. Additional validation should compare extracted hierarchy and tables against page images and add fixtures for duplicate headings, scanned pages, multi-column layouts, and table cells.

## 9. Improvements if more time is available
1. Add OCR fallback for pages with no text layer.
2. Use bounding boxes and font hierarchy for unnumbered headings and table extraction.
3. Add explicit duplicate-heading disambiguation and fuzzy matching across renumbering.
4. Add integration tests for version-pinned selections, API responses, malformed LLM output, and stale generation retrieval.
5. Add structured table extraction and a numeric-change risk flag.

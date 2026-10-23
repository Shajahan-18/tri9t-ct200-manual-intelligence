"""PDF text extraction and hierarchy reconstruction for the supplied CT-200 manuals.

This is a layout-aware text parser for digitally-readable PDFs. OCR is not silently
pretended: if a page has no extractable text, the parser reports it for OCR review.
"""
from __future__ import annotations
import hashlib, re
from pathlib import Path
from typing import Any
import fitz

NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\s+(.+?)\s*$")
TITLE = "CardioTrack CT-200 Home Blood Pressure Monitor — Technical & User Manual"

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def clean(s: str) -> str:
    s = s.replace("\u00ad", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()

def extract_lines(pdf_path: str | Path) -> tuple[list[dict[str, Any]], list[int]]:
    doc = fitz.open(pdf_path)
    lines, empty_pages = [], []
    for pno, page in enumerate(doc, 1):
        blocks = page.get_text("dict").get("blocks", [])
        page_lines = []
        for block in blocks:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = clean("".join(s.get("text", "") for s in spans))
                if not text:
                    continue
                size = max((s.get("size", 0) for s in spans), default=0)
                page_lines.append({"text": text, "page": pno, "font_size": size})
        if not page_lines:
            empty_pages.append(pno)
        lines.extend(page_lines)
    return lines, empty_pages

def parse_pdf(pdf_path: str | Path, version: int = 1) -> dict[str, Any]:
    lines, empty_pages = extract_lines(pdf_path)
    nodes: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    title_seen = False
    for item in lines:
        text = item["text"]
        if not title_seen and ("CardioTrack CT-200" in text or "Technical & User Manual" in text):
            title_seen = True
            continue
        m = NUMBERED_HEADING.match(text)
        # Numbered headings are recognized from the manual's explicit numbering.
        # The level is based on the actual numbering depth, not assumed parent existence.
        if m and len(m.group(1)) <= 16:
            number, heading = m.group(1), m.group(2).strip()
            # Avoid interpreting numbered classification list items as section headings.
            if number.count(".") == 0 and number in {"1", "2", "3", "4", "5", "6", "7", "8"}:
                # Top-level sections are short title-like lines. Exclude numbered
                # classification/list entries such as "1. Normal: ...".
                is_heading = not heading.casefold().startswith(("normal:", "elevated:", "hypertension", "hypertensive crisis:")) and len(heading) < 80
            else:
                is_heading = bool(re.match(r"^\d+(?:\.\d+)*\s+\D", text)) and len(heading) < 100
            if is_heading:
                level = number.count(".") + 1
                node = {"id": "", "logical_id": "", "number": number, "heading": heading,
                        "level": level, "body": "", "parent_id": None, "children": [],
                        "page_start": item["page"], "page_end": item["page"], "version": version}
                # Pop equal/deeper levels. Missing levels remain missing instead of being fabricated.
                while stack and stack[-1]["level"] >= level:
                    stack.pop()
                parent = stack[-1] if stack else None
                node["parent_id"] = parent["id"] if parent else None
                node["logical_id"] = sha((parent["logical_id"] if parent else "ROOT") + "|" + number + "|" + heading.casefold())[:20]
                node["id"] = f"v{version}_{node['logical_id']}"
                node["content_hash"] = sha("")
                nodes.append(node)
                if parent:
                    parent["children"].append(node["id"])
                stack.append(node)
                current = node
                continue
        if current:
            current["body"] = (current["body"] + "\n" + text).strip()
            current["page_end"] = item["page"]
    # Finalize hashes after all body text is collected.
    for n in nodes:
        n["content_hash"] = sha(n["body"])
    return {"document_title": TITLE, "version": version, "source_file": Path(pdf_path).name,
            "page_count": len(fitz.open(pdf_path)), "empty_text_pages": empty_pages,
            "nodes": nodes, "parser_notes": ["Digitally-readable text extracted with PyMuPDF.",
            "Pages without text are reported; OCR fallback is not bundled.",
            "Hierarchy is inferred from numbered headings; irregular numbering is preserved."]}

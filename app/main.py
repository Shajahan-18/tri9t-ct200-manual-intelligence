from __future__ import annotations
import json, os, uuid, difflib
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from .parser import parse_pdf, sha
from . import store

app = FastAPI(title="CT-200 Manual Intelligence API", version="0.1.0", description="Versioned PDF structure, selections, QA ideas and staleness tracking.")
DATA = Path(__file__).resolve().parent.parent / "data"

class SelectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    node_ids: list[str] = Field(min_length=1)
    version: int | None = None
class GenerateIn(BaseModel):
    selection_id: str
    provider: str = "rules"
    # Optional API key is read from environment, never stored in the request.
class IngestIn(BaseModel):
    version: int

@app.on_event("startup")
def startup():
    store.init_db()
    # Seed local sample documents only when the database has no versions.
    with store.connect() as c:
        exists = c.execute("SELECT COUNT(*) n FROM versions").fetchone()['n']
    if exists == 0:
        for v, p in [(1, DATA/'ct200_manual_v1.pdf'), (2, DATA/'ct200_manual_v2.pdf')]:
            if p.exists(): store.save_document(parse_pdf(p, v))

@app.get("/")
def root(): return {"name":"CT-200 Manual Intelligence API", "docs":"/docs", "versions":"/versions"}

@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/versions")
def versions():
    with store.connect() as c:
        return [dict(r) for r in c.execute("SELECT version,source_file,page_count,created_at FROM versions ORDER BY version").fetchall()]

@app.post("/ingest/{version}")
async def ingest(version: int, file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'): raise HTTPException(400,"Upload a PDF file")
    raw = await file.read()
    if not raw: raise HTTPException(400,"Uploaded file is empty")
    tmp = DATA / f"upload_v{version}.pdf"; tmp.write_bytes(raw)
    try: parsed = parse_pdf(tmp, version)
    except Exception as e: raise HTTPException(422, f"PDF parsing failed: {e}")
    store.save_document(parsed)
    return {"version":version,"node_count":len(parsed['nodes']),"page_count":parsed['page_count'],"empty_text_pages":parsed['empty_text_pages']}

@app.get("/sections")
def sections(version: int | None = None):
    try: v = store.get_version(version)
    except ValueError as e: raise HTTPException(404,str(e))
    return {"version":v,"sections":[n for n in store.all_nodes(v) if n['parent_id'] is None]}

@app.get("/nodes/{node_id}")
def node_detail(node_id: str):
    n = store.find_node(node_id)
    if not n: raise HTTPException(404,"Node not found")
    n['child_nodes'] = [store.find_node(cid) for cid in n['children']]
    return n

@app.get("/search")
def search(q: str, version: int | None = None):
    try: v = store.get_version(version)
    except ValueError as e: raise HTTPException(404,str(e))
    ql = q.casefold()
    hits = [n for n in store.all_nodes(v) if ql in n['heading'].casefold() or ql in n['body'].casefold()]
    return {"version":v,"query":q,"count":len(hits),"results":hits}

@app.get("/changes/{logical_id}")
def changes(logical_id: str):
    with store.connect() as c:
        rows = c.execute("SELECT * FROM nodes WHERE logical_id=? ORDER BY version",(logical_id,)).fetchall()
    if not rows: raise HTTPException(404,"Logical node not found")
    items = [store.row_node(r) for r in rows]
    changed = len({n['content_hash'] for n in items}) > 1
    diff = None
    if len(items) >= 2 and changed:
        diff = list(difflib.unified_diff(items[-2]['body'].splitlines(),items[-1]['body'].splitlines(),fromfile=f"v{items[-2]['version']}",tofile=f"v{items[-1]['version']}",lineterm=""))
    return {"logical_id":logical_id,"changed":changed,"versions":[{"version":n['version'],"node_id":n['id'],"heading":n['heading'],"content_hash":n['content_hash']} for n in items],"diff":diff}

@app.post("/selections", status_code=201)
def create_selection(payload: SelectionIn):
    try: v = store.get_version(payload.version)
    except ValueError as e: raise HTTPException(404,str(e))
    snapshots=[]
    for nid in payload.node_ids:
        n=store.find_node(nid)
        if not n or n['version'] != v: raise HTTPException(400,f"Node {nid} does not belong to version {v}; selections must be version-pinned")
        snapshots.append({"node_id":nid,"logical_id":n['logical_id'],"version":v,"heading":n['heading'],"body":n['body'],"content_hash":n['content_hash']})
    sid=str(uuid.uuid4())
    with store.connect() as c:
        c.execute("INSERT INTO selections(id,name,version,node_ids_json,snapshots_json) VALUES(?,?,?,?,?)",(sid,payload.name,v,json.dumps(payload.node_ids),json.dumps(snapshots)))
    return {"selection_id":sid,"name":payload.name,"version":v,"nodes":snapshots}

@app.get("/selections/{selection_id}")
def get_selection(selection_id: str):
    with store.connect() as c: r=c.execute("SELECT * FROM selections WHERE id=?",(selection_id,)).fetchone()
    if not r: raise HTTPException(404,"Selection not found")
    return {"selection_id":r['id'],"name":r['name'],"version":r['version'],"node_ids":json.loads(r['node_ids_json']),"snapshots":json.loads(r['snapshots_json']),"created_at":r['created_at']}

def make_rule_cases(snapshots: list[dict[str,Any]]) -> list[dict[str,str]]:
    text='\n'.join(s['heading']+'\n'+s['body'] for s in snapshots)
    cases=[]
    patterns=[("boundary",r"(\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*mmHg|\d+(?:\.\d+)?\s*seconds?|\d+\s*measurement cycles?)"),
              ("error_code",r"\bE[1-9]\b"),("export",r"CSV|export|Bluetooth sync"),("safety",r"must not|should not|immediately|within")]
    for typ,pat in patterns:
        import re
        found=re.findall(pat,text,re.I)
        if found:
            val=found[0]
            cases.append({"title":f"Validate {typ.replace('_',' ')} behavior", "preconditions":"Use the selected CT-200 manual requirement as the source of truth.","steps":f"Exercise the behavior associated with '{val}' and verify the documented boundary or condition.","expected_result":f"Observed behavior matches the selected manual text containing '{val}'.","source":"rules_fallback"})
    while len(cases)<3:
        i=len(cases)+1
        cases.append({"title":f"Manual requirement verification {i}","preconditions":"Device/app is configured for the selected requirement.","steps":"Execute the behavior described in the selected section and repeat at its boundary conditions.","expected_result":"The observed result matches the exact selected source text.","source":"rules_fallback"})
    return cases[:5]

@app.post("/generate", status_code=201)
def generate(payload: GenerateIn):
    with store.connect() as c: r=c.execute("SELECT * FROM selections WHERE id=?",(payload.selection_id,)).fetchone()
    if not r: raise HTTPException(404,"Selection not found")
    snapshots=json.loads(r['snapshots_json']); provider="rules_fallback"; cases=None
    # Optional OpenAI-compatible call; robustly falls back if missing, malformed, or failing.
    api_key=os.getenv('OPENAI_API_KEY')
    if payload.provider.lower() in {'openai','llm'} and api_key:
        try:
            from openai import OpenAI
            client=OpenAI(api_key=api_key)
            prompt="Generate 3-5 QA test case ideas from the source text. Return only a JSON array of objects with title, preconditions, steps, expected_result. Do not invent requirements. Source:\n"+json.dumps(snapshots)
            resp=client.chat.completions.create(model=os.getenv('OPENAI_MODEL','gpt-4o-mini'),messages=[{"role":"system","content":"You are a careful QA test designer. Output valid JSON only."},{"role":"user","content":prompt}],temperature=0.1)
            parsed=json.loads(resp.choices[0].message.content or '')
            if isinstance(parsed,list) and 3<=len(parsed)<=5 and all(isinstance(x,dict) and all(k in x for k in ('title','preconditions','steps','expected_result')) for x in parsed):
                cases=parsed; provider="openai"
        except Exception:
            cases=None
    if cases is None: cases=make_rule_cases(snapshots)
    gid=str(uuid.uuid4()); hashes=[s['content_hash'] for s in snapshots]
    with store.connect() as c: c.execute("INSERT INTO generations(id,selection_id,cases_json,source_hashes_json,provider) VALUES(?,?,?,?,?)",(gid,payload.selection_id,json.dumps(cases),json.dumps(hashes),provider))
    return {"generation_id":gid,"selection_id":payload.selection_id,"provider":provider,"cases":cases,"source_hashes":hashes,"staleness":"current_at_generation_time"}

@app.get("/generations/{generation_id}")
def get_generation(generation_id: str):
    with store.connect() as c: r=c.execute("SELECT * FROM generations WHERE id=?",(generation_id,)).fetchone()
    if not r: raise HTTPException(404,"Generation not found")
    hashes=json.loads(r['source_hashes_json'])
    with store.connect() as c:
        sel=c.execute("SELECT snapshots_json FROM selections WHERE id=?",(r['selection_id'],)).fetchone()
    snapshots=json.loads(sel['snapshots_json']) if sel else []
    current=[]
    for s in snapshots:
        # Compare the stored source node with the latest version of the same logical node.
        with store.connect() as c: latest=c.execute("SELECT * FROM nodes WHERE logical_id=? ORDER BY version DESC LIMIT 1",(s['logical_id'],)).fetchone()
        latest_node=store.row_node(latest) if latest else None
        current.append({"logical_id":s['logical_id'],"source_hash":s['content_hash'],"current_hash":latest_node['content_hash'] if latest_node else None,"stale":(not latest_node or latest_node['content_hash']!=s['content_hash']),"current_version":latest_node['version'] if latest_node else None})
    return {"generation_id":r['id'],"selection_id":r['selection_id'],"provider":r['provider'],"cases":json.loads(r['cases_json']),"staleness":{"stale":any(x['stale'] for x in current),"nodes":current},"created_at":r['created_at']}

@app.get("/generations")
def list_generations(selection_id: str | None = None, node_id: str | None = None):
    with store.connect() as c:
        if selection_id: rows=c.execute("SELECT * FROM generations WHERE selection_id=? ORDER BY created_at DESC",(selection_id,)).fetchall()
        else: rows=c.execute("SELECT * FROM generations ORDER BY created_at DESC").fetchall()
    out=[]
    for r in rows:
        item=get_generation(r['id'])
        if node_id:
            s=get_selection(item['selection_id'])
            if node_id not in s['node_ids']: continue
        out.append(item)
    return {"count":len(out),"results":out}

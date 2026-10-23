from __future__ import annotations
import json, sqlite3
from pathlib import Path
from typing import Any
DB_PATH = Path(__file__).resolve().parent.parent / "ct200.db"

def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS versions(version INTEGER PRIMARY KEY, source_file TEXT, page_count INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, logical_id TEXT, version INTEGER, number TEXT, heading TEXT, level INTEGER, body TEXT, parent_id TEXT, children_json TEXT, content_hash TEXT, page_start INTEGER, page_end INTEGER, FOREIGN KEY(version) REFERENCES versions(version));
        CREATE INDEX IF NOT EXISTS idx_nodes_version ON nodes(version);
        CREATE INDEX IF NOT EXISTS idx_nodes_logical ON nodes(logical_id);
        CREATE TABLE IF NOT EXISTS selections(id TEXT PRIMARY KEY, name TEXT, version INTEGER, node_ids_json TEXT, snapshots_json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS generations(id TEXT PRIMARY KEY, selection_id TEXT, cases_json TEXT, source_hashes_json TEXT, provider TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')

def save_document(parsed: dict[str, Any]):
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO versions(version,source_file,page_count) VALUES(?,?,?)", (parsed['version'],parsed['source_file'],parsed['page_count']))
        # Re-ingesting the same version is idempotent: replace that version's rows.
        c.execute("DELETE FROM nodes WHERE version=?", (parsed['version'],))
        for n in parsed['nodes']:
            c.execute('''INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (n['id'],n['logical_id'],n['version'],n['number'],n['heading'],n['level'],n['body'],n['parent_id'],json.dumps(n['children']),n['content_hash'],n['page_start'],n['page_end']))

def get_version(requested: int | None = None) -> int:
    with connect() as c:
        row = c.execute("SELECT MAX(version) v FROM versions").fetchone()
        latest = row['v'] or 1
        if requested is None: return latest
        exists = c.execute("SELECT 1 FROM versions WHERE version=?", (requested,)).fetchone()
        if not exists: raise ValueError(f"Version {requested} does not exist")
        return requested

def row_node(row):
    d = dict(row); d['children'] = json.loads(d.pop('children_json')); return d

def all_nodes(version: int):
    with connect() as c:
        return [row_node(r) for r in c.execute("SELECT * FROM nodes WHERE version=? ORDER BY rowid", (version,)).fetchall()]

def find_node(node_id: str):
    with connect() as c:
        r = c.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        return row_node(r) if r else None

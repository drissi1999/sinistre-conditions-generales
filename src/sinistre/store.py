"""Stockage SQLite : un seul fichier (data/contracts.db) contient clauses, définitions,
tables extraites (garanties, exclusions, conditions) et embeddings. Il est versionné avec
le dépôt pour que l'application déployée n'ait jamais à ré-ingérer ni ré-extraire.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Iterable

import numpy as np

from .parse import Clause, ParsedContract, normalize_term

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    contract_id TEXT PRIMARY KEY,
    insurer     TEXT NOT NULL,
    product     TEXT,
    edition     TEXT,
    source_url  TEXT,
    file_sha256 TEXT NOT NULL,
    pages       INTEGER
);

CREATE TABLE IF NOT EXISTS clauses (
    contract_id  TEXT NOT NULL REFERENCES contracts(contract_id),
    clause_id    TEXT NOT NULL,
    ord          INTEGER NOT NULL,
    section_path TEXT NOT NULL,          -- JSON : ["Chap. 4 — LES ÉVÉNEMENTS GARANTIS", "Art. 4.7 — VOL"]
    title        TEXT,
    kind_hint    TEXT NOT NULL,          -- garantie | exclusion | prevention | definition | texte
    page_start   INTEGER NOT NULL,
    page_end     INTEGER NOT NULL,
    text         TEXT NOT NULL,
    embedding    BLOB,
    PRIMARY KEY (contract_id, clause_id)
);

CREATE TABLE IF NOT EXISTS definitions (
    contract_id TEXT NOT NULL,
    term        TEXT NOT NULL,
    term_norm   TEXT NOT NULL,
    clause_id   TEXT NOT NULL,
    PRIMARY KEY (contract_id, clause_id)
);

-- Tables issues de l'extraction structurée (une fois par contrat). Chaque ligne pointe
-- vers sa clause source et porte la citation exacte qui la justifie.
CREATE TABLE IF NOT EXISTS guarantees (
    contract_id   TEXT NOT NULL,
    peril         TEXT NOT NULL,
    label         TEXT NOT NULL,
    scope         TEXT,
    ceiling       TEXT,
    deductible    TEXT,
    optional      INTEGER,
    clause_id     TEXT NOT NULL,
    quote         TEXT NOT NULL,
    quote_ok      INTEGER NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'a_valider'
);

CREATE TABLE IF NOT EXISTS exclusions (
    contract_id   TEXT NOT NULL,
    peril         TEXT,                  -- NULL = exclusion générale (toutes garanties)
    description   TEXT NOT NULL,
    clause_id     TEXT NOT NULL,
    quote         TEXT NOT NULL,
    quote_ok      INTEGER NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'a_valider'
);

CREATE TABLE IF NOT EXISTS conditions (
    contract_id    TEXT NOT NULL,
    peril          TEXT,
    condition_type TEXT NOT NULL,
    description    TEXT NOT NULL,
    parameter      TEXT,
    clause_id      TEXT NOT NULL,
    quote          TEXT NOT NULL,
    quote_ok       INTEGER NOT NULL,
    review_status  TEXT NOT NULL DEFAULT 'a_valider'
);

CREATE TABLE IF NOT EXISTS extraction_runs (
    contract_id    TEXT PRIMARY KEY,
    file_sha256    TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    stats          TEXT
);

CREATE INDEX IF NOT EXISTS ix_guar ON guarantees(contract_id, peril);
CREATE INDEX IF NOT EXISTS ix_excl ON exclusions(contract_id, peril);
CREATE INDEX IF NOT EXISTS ix_cond ON conditions(contract_id, peril);
"""

EXTRACTED_TABLES = ("guarantees", "exclusions", "conditions")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# --------------------------------------------------------------------------- écriture

def contract_sha(conn: sqlite3.Connection, contract_id: str) -> str | None:
    row = conn.execute("SELECT file_sha256 FROM contracts WHERE contract_id=?", (contract_id,)).fetchone()
    return row["file_sha256"] if row else None


def save_parsed(conn: sqlite3.Connection, meta: dict, sha: str, parsed: ParsedContract) -> None:
    """Remplace les clauses d'un contrat. Les tables extraites sont purgées : elles dépendent du texte."""
    cid = meta["contract_id"]
    with conn:
        for table in ("clauses", "definitions", *EXTRACTED_TABLES, "extraction_runs"):
            conn.execute(f"DELETE FROM {table} WHERE contract_id=?", (cid,))
        conn.execute(
            "INSERT OR REPLACE INTO contracts VALUES (?,?,?,?,?,?,?)",
            (cid, meta["insurer"], meta.get("product"), meta.get("edition"),
             meta.get("source_url"), sha, parsed.pages))
        conn.executemany(
            "INSERT INTO clauses (contract_id, clause_id, ord, section_path, title, kind_hint,"
            " page_start, page_end, text) VALUES (?,?,?,?,?,?,?,?,?)",
            [(cid, c.clause_id, c.ord, json.dumps(c.section_path, ensure_ascii=False), c.title,
              c.kind_hint, c.page_start, c.page_end, c.text) for c in parsed.clauses])
        conn.executemany(
            "INSERT INTO definitions VALUES (?,?,?,?)",
            [(cid, c.term, normalize_term(c.term), c.clause_id) for c in parsed.definitions])


def save_embeddings(conn: sqlite3.Connection, contract_id: str, ids: list[str], vectors: np.ndarray) -> None:
    with conn:
        conn.executemany(
            "UPDATE clauses SET embedding=? WHERE contract_id=? AND clause_id=?",
            [(v.astype(np.float32).tobytes(), contract_id, i) for i, v in zip(ids, vectors)])


def save_extraction(conn: sqlite3.Connection, contract_id: str, sha: str, model: str,
                    prompt_version: str, rows: dict[str, list[dict]], stats: dict) -> None:
    with conn:
        for table in EXTRACTED_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE contract_id=?", (contract_id,))
            for r in rows.get(table, []):
                cols = ["contract_id", *r.keys()]
                conn.execute(
                    f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [contract_id, *r.values()])
        conn.execute("INSERT OR REPLACE INTO extraction_runs (contract_id, file_sha256, model,"
                     " prompt_version, stats) VALUES (?,?,?,?,?)",
                     (contract_id, sha, model, prompt_version, json.dumps(stats)))


# --------------------------------------------------------------------------- lecture

def _clause(row: sqlite3.Row) -> Clause:
    return Clause(clause_id=row["clause_id"], section_path=json.loads(row["section_path"]),
                  title=row["title"], kind_hint=row["kind_hint"], page_start=row["page_start"],
                  page_end=row["page_end"], text=row["text"], ord=row["ord"])


def list_contracts(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM contracts ORDER BY insurer")]


def get_clauses(conn: sqlite3.Connection, contract_id: str) -> list[Clause]:
    rows = conn.execute("SELECT * FROM clauses WHERE contract_id=? ORDER BY ord", (contract_id,))
    return [_clause(r) for r in rows]


def get_clause(conn: sqlite3.Connection, contract_id: str, clause_id: str) -> Clause | None:
    row = conn.execute("SELECT * FROM clauses WHERE contract_id=? AND clause_id=?",
                       (contract_id, clause_id)).fetchone()
    return _clause(row) if row else None


def get_embeddings(conn: sqlite3.Connection, contract_id: str) -> tuple[list[str], np.ndarray | None]:
    rows = conn.execute("SELECT clause_id, embedding FROM clauses WHERE contract_id=? AND embedding"
                        " IS NOT NULL ORDER BY ord", (contract_id,)).fetchall()
    if not rows:
        return [], None
    return [r["clause_id"] for r in rows], np.stack([np.frombuffer(r["embedding"], np.float32) for r in rows])


def extraction_done(conn: sqlite3.Connection, contract_id: str, sha: str, prompt_version: str) -> bool:
    row = conn.execute("SELECT 1 FROM extraction_runs WHERE contract_id=? AND file_sha256=? AND"
                       " prompt_version=?", (contract_id, sha, prompt_version)).fetchone()
    return row is not None


def find_definitions(conn: sqlite3.Connection, contract_id: str, words: Iterable[str]) -> list[str]:
    """clause_id des définitions dont le terme apparaît dans les mots fournis (comparaison sans accents)."""
    haystack = " ".join(normalize_term(w) for w in words)
    out = []
    for r in conn.execute("SELECT term_norm, clause_id FROM definitions WHERE contract_id=?", (contract_id,)):
        term = r["term_norm"]
        if not term:
            continue
        # « dépendances » doit trouver « dépendance » : on tolère un pluriel en s/x
        stem = term[:-1] if term.endswith(("s", "x")) and len(term) > 4 else term
        if re.search(rf"\b{re.escape(stem)}[sx]?\b", haystack):
            out.append(r["clause_id"])
    return out


def candidate_rows(conn: sqlite3.Connection, contract_id: str, perils: list[str]) -> dict[str, list[dict]]:
    """Recherche ciblée dans les tables extraites : garanties, exclusions (propres au péril et
    générales) et conditions applicables aux périls du sinistre."""
    ph = ",".join("?" * len(perils)) or "''"
    q = lambda sql, *a: [dict(r) for r in conn.execute(sql, a)]
    return {
        "guarantees": q(f"SELECT * FROM guarantees WHERE contract_id=? AND peril IN ({ph})", contract_id, *perils),
        "exclusions": q(f"SELECT * FROM exclusions WHERE contract_id=? AND (peril IN ({ph}) OR peril IS NULL)",
                        contract_id, *perils),
        "conditions": q(f"SELECT * FROM conditions WHERE contract_id=? AND (peril IN ({ph}) OR peril IS NULL)",
                        contract_id, *perils),
    }

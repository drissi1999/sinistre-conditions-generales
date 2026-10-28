"""Pipeline question -> verdict vérifié.

    faits (LLM) -> recherche SQL dans les tables extraites -> recherche hybride dans les clauses
    -> assemblage du contexte (garantie + toutes les exclusions/conditions + définitions)
    -> raisonnement (LLM, JSON strict) -> vérification des citations -> rétrogradation éventuelle
"""

from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import store
from .parse import Clause
from .reason import reason, understand_claim
from .retrieve import ContractIndex
from .schemas import Answer, ClaimFacts
from .verify import QuoteCheck, check_quote

MAX_CONTEXT_CHARS = 18000
TOP_K = 6


@dataclass
class CitationCheck:
    clause_id: str
    page: int | None
    quote: str
    role: str
    ok: bool
    reason: str
    clause_text: str = ""
    spans: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class Result:
    contract_id: str
    insurer: str
    facts: ClaimFacts
    answer: Answer
    model_verdict: str                  # verdict proposé par le modèle, avant vérification
    downgraded: bool
    downgrade_reason: str
    checks: list[CitationCheck]
    context_ids: list[str]
    sql_rows: dict[str, list[dict]]
    seconds: float

    @property
    def citations_ok(self) -> int:
        return sum(c.ok for c in self.checks)


_indexes: dict[str, ContractIndex] = {}


def _index(conn: sqlite3.Connection, contract_id: str) -> ContractIndex:
    if contract_id not in _indexes:
        ids, vecs = store.get_embeddings(conn, contract_id)
        _indexes[contract_id] = ContractIndex(store.get_clauses(conn, contract_id), ids, vecs)
    return _indexes[contract_id]


def build_context(conn: sqlite3.Connection, contract_id: str, claim: str,
                  facts: ClaimFacts) -> tuple[list[Clause], dict[str, list[dict]]]:
    idx = _index(conn, contract_id)
    rows = store.candidate_rows(conn, contract_id, list(facts.perils))
    rows = {t: [r for r in rs if r.get("quote_ok", 1)] for t, rs in rows.items()}

    query = " ".join([claim, *facts.termes_cles, *facts.biens_endommages])
    retrieved = [cid for cid, _ in idx.search(query, k=TOP_K)]

    # Priorité : articles de garantie concernés (avec TOUTES leurs clauses : garantie, exclusions,
    # prévention), puis exclusions et conditions issues de la base, puis définitions, puis le reste.
    # La recherche seule ne suffit pas : sur Altima, l'exclusion décisive du vol (locaux communs)
    # n'est pas dans le top 6 de la recherche hybride, mais elle est dans le même article.
    def article(cid: str) -> list[str]:
        c = idx.by_id.get(cid)
        if c is None or c.kind_hint == "definition":
            return [cid] if c else []
        return [o.clause_id for o in idx.clauses if o.section_path == c.section_path]

    ordered: list[str] = []
    for g in rows["guarantees"]:
        ordered += article(g["clause_id"])
    for cid in retrieved[:3]:
        ordered += article(cid)
    ordered += [r["clause_id"] for r in rows["exclusions"] + rows["conditions"]]
    words = [claim, *facts.termes_cles, *facts.biens_endommages]
    ordered += store.find_definitions(conn, contract_id, words)
    ordered += retrieved[3:]

    seen, picked, size = set(), [], 0
    for cid in ordered:
        c = idx.by_id.get(cid)
        if c is None or cid in seen:
            continue
        if size + len(c.text) > MAX_CONTEXT_CHARS and picked:
            continue
        seen.add(cid)
        picked.append(c)
        size += len(c.text)
    picked.sort(key=lambda c: c.ord)  # ordre du contrat : plus lisible pour le modèle et l'humain
    return picked, rows


def verify_answer(answer: Answer, context: list[Clause]) -> tuple[list[CitationCheck], str]:
    by_id = {c.clause_id: c for c in context}
    checks = []
    for cit in answer.clauses_citees:
        c = by_id.get(cit.clause_id)
        if c is None:
            checks.append(CitationCheck(cit.clause_id, cit.page, cit.citation, cit.role, False,
                                        "clause inconnue ou non fournie au modèle"))
            continue
        r: QuoteCheck = check_quote(cit.citation, c.text)
        checks.append(CitationCheck(c.clause_id, c.page_start, cit.citation, cit.role, r.ok, r.reason,
                                    c.text, r.spans))
    failed = [c for c in checks if not c.ok]
    if not checks:
        return checks, "Aucune clause citée : la réponse n'est pas justifiable."
    if failed:
        return checks, (f"{len(failed)} citation(s) sur {len(checks)} introuvable(s) mot pour mot dans le contrat "
                        f"({', '.join(c.clause_id for c in failed)}).")
    return checks, ""


def answer_claim(conn: sqlite3.Connection, contract_id: str, claim: str,
                 facts: ClaimFacts | None = None) -> Result:
    t0 = time.time()
    facts = facts or understand_claim(claim)
    meta = next(c for c in store.list_contracts(conn) if c["contract_id"] == contract_id)
    context, rows = build_context(conn, contract_id, claim, facts)
    ans = reason(claim, facts, meta["insurer"], context, rows)
    checks, problem = verify_answer(ans, context)

    model_verdict = ans.verdict
    final = ans.model_copy(deep=True)
    for cit, chk in zip(final.clauses_citees, checks):
        cit.page = chk.page  # la page vient de la base, pas du modèle
    downgraded = bool(problem) and ans.verdict != "indéterminé"
    if problem:
        final.verdict = "indéterminé"
        final.confiance = "faible"
        final.raison_confiance = f"Vérification des citations : {problem} {ans.raison_confiance}".strip()
    return Result(contract_id, meta["insurer"], facts, final, model_verdict, downgraded, problem, checks,
                  [c.clause_id for c in context], rows, round(time.time() - t0, 1))


def compare(conn_factory, contract_ids: list[str], claim: str) -> list[Result]:
    """Même sinistre sur plusieurs contrats : les faits sont extraits une seule fois."""
    facts = understand_claim(claim)

    def one(cid: str) -> Result:
        conn = conn_factory()  # une connexion SQLite par thread
        try:
            return answer_claim(conn, cid, claim, facts)
        finally:
            conn.close()

    with ThreadPoolExecutor(max(1, min(4, len(contract_ids)))) as pool:
        return list(pool.map(one, contract_ids))

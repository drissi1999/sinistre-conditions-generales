"""Recherche hybride (BM25 + embeddings) restreinte à un contrat.

BM25 rattrape les termes exacts du métier (« effraction », « parties communes ») ;
les embeddings rattrapent les formulations différentes (« local à vélos » ~ « locaux à usage commun »).
Les deux classements sont fusionnés par Reciprocal Rank Fusion, qui ne demande aucun calibrage
de scores entre les deux méthodes.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

from .config import EMBED_MODEL
from .parse import Clause

RRF_K = 60
_STOP = set("""a au aux avec ce ces dans de des du elle en et il ils je la le les leur lui ma mais me mes
mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes ton tu un une vos votre
vous y est sont été etre être a ont fait cette cet tout tous toute toutes si plus""".split())


def tokenize(text: str) -> list[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    toks = re.findall(r"[a-z0-9]+", t)
    # racinisation minimale : pluriels et féminins courants
    return [re.sub(r"(es|s|x)$", "", w) if len(w) > 4 else w for w in toks if w not in _STOP and len(w) > 1]


def clause_document(c: Clause) -> str:
    """Texte indexé : le chemin de section accompagne la clause (une clause seule perd son contexte,
    comme une ligne de tableau sans ses en-têtes)."""
    return " > ".join(c.section_path) + "\n" + c.text


@lru_cache(maxsize=1)
def _embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(EMBED_MODEL)


def embed(texts: list[str]) -> np.ndarray:
    vecs = np.array(list(_embedder().embed(texts)), dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True).clip(1e-9)


class ContractIndex:
    def __init__(self, clauses: list[Clause], ids: list[str], vectors: np.ndarray | None):
        self.clauses = clauses
        self.by_id = {c.clause_id: c for c in clauses}
        self.bm25 = BM25Okapi([tokenize(clause_document(c)) for c in clauses])
        self.vec_ids, self.vectors = ids, vectors

    def search(self, query: str, k: int = 8, exclude_kinds: tuple[str, ...] = ("definition",)) -> list[tuple[str, float]]:
        scores = self.bm25.get_scores(tokenize(query))
        bm25_rank = [self.clauses[i].clause_id for i in np.argsort(-scores) if scores[i] > 0]
        rankings = [bm25_rank]
        if self.vectors is not None:
            q = embed([query])[0]
            sims = self.vectors @ q
            rankings.append([self.vec_ids[i] for i in np.argsort(-sims)])
        fused: dict[str, float] = {}
        for ranking in rankings:
            for r, cid in enumerate(ranking):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + r + 1)
        ranked = sorted(fused.items(), key=lambda x: -x[1])
        return [(cid, s) for cid, s in ranked if self.by_id[cid].kind_hint not in exclude_kinds][:k]

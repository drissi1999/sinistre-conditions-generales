"""Extraction structurée, une fois par contrat : garanties, exclusions, conditions -> tables SQL.

Le contrat est envoyé article par article (lots de quelques milliers de caractères), jamais en
entier : chaque appel reste court, et chaque ligne extraite doit citer sa clause source.
La citation de chaque ligne est vérifiée comme celles des réponses ; une ligne non vérifiable
est conservée mais marquée « rejete_citation » pour revue humaine, et ignorée par le moteur.
"""

from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from . import config
from .llm import LLMError, complete_json
from .parse import Clause
from .schemas import PERILS, ConditionType, SectionExtraction
from .verify import check_quote

PROMPT_VERSION = "extract-v1"
BATCH_CHARS = 7000
WORKERS = 4

# Sections sans portée sur la couverture (vie du contrat, cotisation…) : pas d'appel LLM.
ADMIN = re.compile(r"cotisation|prescription|donn[ée]es personnelles|r[ée]clamation|m[ée]diation|"
                   r"textes l[ée]gaux|vie de votre contrat|subrogation|r[ée]siliation|fonctionnement de votre"
                   r"|d[ée]clarations|examen des r[ée]clamations|d[ée]marchage", re.I)

SYSTEM = f"""Tu es un analyste en assurance habitation. Tu lis des extraits de conditions générales et tu
remplis une base de données. Règles :
- N'extrais que ce qui est écrit. Aucune connaissance extérieure, aucune supposition.
- Chaque ligne cite sa source : "clause_id" exactement comme fourni entre crochets, et "quote" = un extrait
  recopié MOT POUR MOT de cette clause (une phrase ou un membre de phrase, 15 à 300 caractères).
- peril ∈ {list(PERILS)} : c'est la garantie de l'article où figure la clause (une condition ou une
  exclusion de l'article « Vol » a peril = "vol"). null uniquement pour ce qui vaut pour toutes les garanties.
- guarantees : ce qui est couvert (scope en une phrase), plafond (ceiling) et franchise (deductible) si écrits.
- exclusions : chaque exclusion distincte ; peril = garantie restreinte, null si exclusion générale à
  toutes les garanties.
- conditions : conditions de mise en jeu ou obligations dont dépend l'indemnisation ;
  condition_type ∈ {list(ConditionType.__args__)} ; parameter = valeur chiffrée éventuelle (« 90 jours »).
- Si un extrait ne contient rien de pertinent, renvoie des listes vides.
Réponds uniquement en JSON : {{"guarantees": [...], "exclusions": [...], "conditions": [...]}}"""


def batches(clauses: list[Clause]) -> list[list[Clause]]:
    """Regroupe les clauses par article puis en lots bornés, sans couper un article si possible."""
    by_article: dict[str, list[Clause]] = defaultdict(list)
    for c in clauses:
        if c.kind_hint == "definition" or ADMIN.search(" ".join(c.section_path)):
            continue
        by_article[" > ".join(c.section_path)].append(c)
    out, cur, size = [], [], 0
    for group in by_article.values():
        gsize = sum(len(c.text) for c in group)
        if cur and size + gsize > BATCH_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.extend(group)
        size += gsize
    if cur:
        out.append(cur)
    return out


def _render(batch: list[Clause]) -> str:
    parts = []
    for c in batch:
        path = " > ".join(c.section_path)
        parts.append(f"[{c.clause_id}] (p. {c.page_start}) {path}\n{c.text}")
    return "\n\n---\n\n".join(parts)


def _locate(quote: str, claimed: str, batch: list[Clause]) -> tuple[str, bool]:
    """Vérifie la citation dans la clause annoncée ; à défaut, dans les autres clauses du lot
    (le modèle se trompe parfois de clause voisine : on corrige l'identifiant, pas le texte)."""
    by_id = {c.clause_id: c for c in batch}
    if claimed in by_id and check_quote(quote, by_id[claimed].text).ok:
        return claimed, True
    for c in batch:
        if check_quote(quote, c.text).ok:
            return c.clause_id, True
    return claimed, False


def extract_contract(clauses: list[Clause], progress=None) -> tuple[dict[str, list[dict]], dict]:
    rows: dict[str, list[dict]] = {"guarantees": [], "exclusions": [], "conditions": []}
    bs = batches(clauses)
    done = 0

    def run(batch: list[Clause]) -> SectionExtraction | Exception:
        nonlocal done
        try:
            res = complete_json(SYSTEM, "Extraits du contrat :\n\n" + _render(batch), SectionExtraction,
                                max_tokens=6000)
        except Exception as e:  # les autres lots continuent ; ils restent en cache
            res = e
        done += 1
        if progress:
            progress(done, len(bs))
        return res

    with ThreadPoolExecutor(WORKERS) as pool:
        results = list(pool.map(run, bs))
    failed = [r for r in results if isinstance(r, Exception)]
    if failed:
        # pas d'enregistrement partiel : relancer reprend uniquement les lots échoués (cache)
        raise LLMError(f"{len(failed)}/{len(bs)} lots en échec, relancer la commande. Premier : {failed[0]}")
    for batch, res in zip(bs, results):
        for table, items in (("guarantees", res.guarantees), ("exclusions", res.exclusions),
                             ("conditions", res.conditions)):
            for item in items:
                d = item.model_dump()
                d["clause_id"], ok = _locate(d["quote"], d["clause_id"], batch)
                if isinstance(d.get("optional"), bool):
                    d["optional"] = int(d["optional"])
                d["quote_ok"] = int(ok)
                d["review_status"] = "a_valider" if ok else "rejete_citation"
                rows[table].append(d)
    return rows, _stats(rows, len(bs))


def _stats(rows: dict[str, list[dict]], n_batches: int) -> dict:
    """Indicateurs de qualité par table : taux de citations vérifiées et taux de remplissage
    des colonnes optionnelles (une colonne presque vide n'est pas filtrable de façon fiable)."""
    stats: dict = {"batches": n_batches, "model": config.LLM_MODEL}
    for table, items in rows.items():
        n = len(items)
        s = {"rows": n, "quote_ok_rate": round(sum(r["quote_ok"] for r in items) / n, 3) if n else None}
        for col in ("ceiling", "deductible", "parameter", "peril"):
            if n and col in items[0]:
                s[f"fill_{col}"] = round(sum(1 for r in items if r.get(col)) / n, 3)
        stats[table] = s
    return stats

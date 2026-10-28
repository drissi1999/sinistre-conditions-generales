"""Vérification des citations : chaque extrait cité doit figurer mot pour mot dans la clause citée.

La comparaison ignore uniquement ce qui varie à l'extraction PDF sans changer le sens :
espaces et retours à la ligne (y compris les espaces manquants du PDF), casse, apostrophes et
guillemets typographiques, tirets, puces. Une paraphrase, elle, échoue.
Une citation peut contenir « … » ou « [...] » pour sauter un passage : chaque fragment doit
alors être trouvé, dans l'ordre.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MIN_FRAGMENT = 12  # caractères normalisés : empêche de « citer » trois mots génériques

_EQUIV = {"’": "'", "‘": "'", "`": "'", "´": "'", "«": '"', "»": '"', "“": '"', "”": '"',
          "–": "-", "—": "-", "‑": "-", "œ": "oe", "æ": "ae"}
_SKIP = set(" \t\r\n•·▪-") | {chr(0xA0), chr(0x202F), chr(0x2009)}
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\s*(?:\.\.\.|…)\s*\]|\(\s*(?:\.\.\.|…)\s*\))\s*")


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Texte normalisé + position d'origine de chaque caractère normalisé (pour surligner)."""
    out, idx = [], []
    for i, ch in enumerate(text):
        ch = unicodedata.normalize("NFKC", ch).lower()
        for c in ch:
            c = _EQUIV.get(c, c)
            for cc in c:
                if cc in _SKIP:
                    continue
                out.append(cc)
                idx.append(i)
    return "".join(out), idx


def normalize(text: str) -> str:
    return normalize_with_map(text)[0]


@dataclass
class QuoteCheck:
    ok: bool
    reason: str = ""
    spans: list[tuple[int, int]] = field(default_factory=list)  # positions dans le texte d'origine


def check_quote(quote: str, clause_text: str) -> QuoteCheck:
    fragments = [f for f in _ELLIPSIS.split(quote.strip().strip('"«» ')) if f.strip()]
    if not fragments:
        return QuoteCheck(False, "citation vide")
    norm_text, idx = normalize_with_map(clause_text)
    pos, spans = 0, []
    for frag in fragments:
        nf = normalize(frag)
        if len(nf) < MIN_FRAGMENT:
            return QuoteCheck(False, f"fragment trop court pour être vérifiable : « {frag.strip()} »")
        found = norm_text.find(nf, pos)
        if found < 0:
            where = "" if norm_text.find(nf) < 0 else " (présent mais pas dans l'ordre)"
            return QuoteCheck(False, f"extrait introuvable dans la clause{where} : « {frag.strip()[:80]} »")
        spans.append((idx[found], idx[found + len(nf) - 1] + 1))
        pos = found + len(nf)
    return QuoteCheck(True, "citation retrouvée mot pour mot", spans)

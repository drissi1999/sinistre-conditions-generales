"""PDF de conditions générales -> arbre de clauses (titre > article > sous-article > clause).

Choix : PyMuPDF + profil de mise en page par modèle de contrat (voir data/contracts.yaml).
Le parsing est déterministe et testable : aucune IA ici, le texte stocké est celui du PDF,
ce qui permet ensuite de vérifier mot pour mot les citations produites par le LLM.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

# Intertitres génériques qui découpent un article en clauses typées.
# Le découpage des exclusions est le plus important : une exclusion doit être citable seule.
SUBLABELS: list[tuple[str, re.Pattern]] = [
    ("exclusion", re.compile(
        r"^(Ce que nous ne garantissons pas|Ce qui est exclu|Ce qui n.est pas garanti|"
        r"Outre les exclusions|Sont exclus|Ne sont pas garantis|Exclusions?\b)", re.I)),
    ("garantie", re.compile(r"^(Ce que nous garantissons|Sont également garantis|LES \+ DE)", re.I)),
    ("prevention", re.compile(r"^(Prévention|Mesures de prévention|Mesures de sécurité|ATTENTION\b)", re.I)),
]

# Espaces insécables/fines et puces de la police Symbol, écrits en points de code pour rester lisibles.
_SPACES = "".join(map(chr, (0xA0, 0x2002, 0x2003, 0x2009, 0x202F)))
_BULLETS = [chr(c) for c in (0xF0A7, 0xF0B7, 0xF0D8, 0xF0FC, 0x2022)]
_PUA = re.compile("[" + chr(0xE000) + "-" + chr(0xF8FF) + "]")
_LIGATURES = {chr(0xFB01): "fi", chr(0xFB02): "fl", chr(0x00AD): ""}
_GUARANTEE_OPENER = re.compile(r"^(Nous garantissons|La garantie couvre)", re.I)
_WS = re.compile("[ 	" + _SPACES + "]+")
_CTRL = re.compile("[" + re.escape("".join(map(chr, [*range(0, 9), *range(11, 32), 127]))) + "]")


def clean(text: str) -> str:
    """Nettoyage léger, conservé dans la base (pas de minuscules, pas de suppression de ponctuation)."""
    for src, dst in _LIGATURES.items():
        text = text.replace(src, dst)
    for glyph in _BULLETS:
        text = text.replace(glyph, "•")
    text = _PUA.sub("", text)
    text = _CTRL.sub(" ", text)
    text = re.sub(r"•(\s*•)+", "•", text)
    return _WS.sub(" ", text).strip()


@dataclass
class Line:
    page: int
    x0: float
    y0: float
    x1: float
    size: float
    bold_ratio: float  # part des caractères (hors espaces) en gras
    text: str

    @property
    def bold(self) -> bool:
        return self.bold_ratio >= 0.9


@dataclass
class Clause:
    clause_id: str
    section_path: list[str]
    title: str
    kind_hint: str  # garantie | exclusion | prevention | definition | texte
    page_start: int
    page_end: int
    text: str
    ord: int = 0
    term: str | None = None  # renseigné pour les définitions du lexique


@dataclass
class ParsedContract:
    contract_id: str
    pages: int
    clauses: list[Clause] = field(default_factory=list)

    @property
    def definitions(self) -> list[Clause]:
        return [c for c in self.clauses if c.kind_hint == "definition"]


# --------------------------------------------------------------------------- extraction des lignes

def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or "bold" in span["font"].lower()


def extract_lines(doc: pymupdf.Document, profile: dict) -> list[Line]:
    skip = set(profile.get("skip_pages", []))
    two_cols = profile.get("columns", 1) == 2
    lines: list[Line] = []
    for pno, page in enumerate(doc, start=1):
        if pno in skip:
            continue
        mid = page.rect.width / 2
        page_lines = []
        for block in page.get_text("dict")["blocks"]:
            for l in block.get("lines", []):
                spans = [s for s in l["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = clean("".join(s["text"] for s in l["spans"]))
                if not text:
                    continue
                n = sum(len(s["text"].replace(" ", "")) for s in spans) or 1
                nb = sum(len(s["text"].replace(" ", "")) for s in spans if _is_bold(s))
                x0, y0, x1 = l["bbox"][0], l["bbox"][1], l["bbox"][2]
                page_lines.append(Line(pno, x0, y0, x1, round(spans[0]["size"], 1), nb / n, text))
        if two_cols:
            page_lines = _two_column_order(page_lines, mid)
        lines.extend(page_lines)
    return _drop_running_headers(lines, n_pages=len(doc) - len(skip))


def _two_column_order(page_lines: list[Line], mid: float) -> list[Line]:
    """Ordre de lecture en 2 colonnes, par bandes horizontales.

    Un titre de chapitre pleine largeur (ou très gros) coupe la page en bandes :
    on lit colonne gauche puis droite à l'intérieur de chaque bande.
    """
    breaks = sorted(ln.y0 for ln in page_lines
                    if (ln.x0 < mid - 10 and ln.x1 > mid + 10) or ln.size >= 13)

    def key(ln: Line):
        band = sum(1 for b in breaks if b <= ln.y0 + 0.5)
        spanning = ln.y0 in breaks
        return (band, -1 if spanning else (0 if ln.x0 < mid - 10 else 1), ln.y0)
    return sorted(page_lines, key=key)


def _drop_running_headers(lines: list[Line], n_pages: int) -> list[Line]:
    """Retire numéros de page et en-têtes/pieds répétés (texte présent sur >= 40 % des pages)."""
    key = lambda ln: re.sub(r"\d+", "", ln.text).strip().lower()
    pages_by_key: dict[str, set[int]] = {}
    for ln in lines:
        pages_by_key.setdefault(key(ln), set()).add(ln.page)
    frequent = {k for k, p in pages_by_key.items() if len(p) >= max(3, 0.4 * n_pages)}
    out, seen = [], set()
    for ln in lines:
        if re.fullmatch(r"[\d\s]+", ln.text) or key(ln) in frequent:
            continue
        # même ligne dupliquée au même endroit (artefact PDF fréquent)
        sig = (ln.page, round(ln.x0), round(ln.y0), ln.text)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(ln)
    return out


# --------------------------------------------------------------------------- titres

@dataclass
class Heading:
    level: int
    number: str | None
    title: str


def match_heading(line: Line, profile: dict) -> Heading | None:
    for h in profile.get("headings", []):
        if h.get("bold") and not line.bold:
            continue
        if line.size < h.get("min_size", 0):
            continue
        m = re.match(h["pattern"], line.text)
        if m:
            number = m.group(1).strip()
            title = (m.group(2) if m.lastindex and m.lastindex >= 2 else "").strip(" -–:")
            return Heading(h["level"], number, title)
    return None


def heading_label(h: Heading) -> str:
    if h.number is None:
        return h.title
    if re.match(r"^(TITRE|CHAPITRE)", h.number, re.I):
        return h.number.title()
    return f"Art. {h.number}" if h.level > 1 else f"Chap. {h.number}"


def _sublabel(text: str) -> str | None:
    for kind, pat in SUBLABELS:
        if pat.match(text):
            return kind
    return None


# --------------------------------------------------------------------------- arbre de clauses

def parse_pdf(path: str | Path, contract_id: str, profile: dict) -> ParsedContract:
    doc = pymupdf.open(str(path))
    lines = extract_lines(doc, profile)
    page_sections = profile.get("page_sections", [])
    lexicon_title = profile.get("lexicon_title")

    result = ParsedContract(contract_id, len(doc))
    stack: list[Heading] = []          # titres ouverts
    buf: list[Line] = []               # lignes de la clause courante
    kind = "texte"
    para_idx: Counter[str] = Counter()  # numérotation des clauses dans un même article
    used_ids: set[str] = set()
    forced: dict | None = None         # section imposée par plage de pages
    last_heading_line: Line | None = None

    def in_lexicon() -> bool:
        if forced is not None:
            return bool(forced.get("lexicon"))
        return bool(lexicon_title) and any(lexicon_title.lower() in h.title.lower() for h in stack)

    def flush():
        nonlocal buf, kind
        if not buf:
            return
        if in_lexicon():
            for c in _split_lexicon(buf, _path(), result.contract_id):
                c.clause_id = _unique(c.clause_id, used_ids)
                c.ord = len(result.clauses)
                result.clauses.append(c)
        else:
            if stack:
                base = heading_label(stack[-1])
            elif forced is not None:
                base = f"{forced['title']} (p. {buf[0].page})"
            else:
                base = "Préambule"
            para_idx[base] += 1
            cid = base if para_idx[base] == 1 else f"{base} §{para_idx[base]}"
            k = kind
            if k == "texte" and stack and re.search(r"exclu", stack[-1].title, re.I):
                k = "exclusion"
            text = "\n".join(l.text for l in buf)
            result.clauses.append(Clause(
                clause_id=_unique(cid, used_ids), section_path=_path(),
                title=stack[-1].title if stack else base, kind_hint=k,
                page_start=buf[0].page, page_end=buf[-1].page, text=text, ord=len(result.clauses)))
        buf, kind = [], "texte"

    def _path() -> list[str]:
        if forced is not None:
            return [forced["title"]]
        return [f"{heading_label(h)} — {h.title}".strip(" —") for h in stack]

    for ln in lines:
        section = next((s for s in page_sections if s["pages"][0] <= ln.page <= s["pages"][1]), None)
        if section is not forced:
            flush()
            forced = section
            if section is not None:
                stack = []
        if forced is not None:
            # sections déclarées par pages (tableaux, préambule) : une clause par page
            if buf and ln.page != buf[-1].page and not forced.get("lexicon"):
                flush()
            buf.append(ln)
            continue

        h = match_heading(ln, profile)
        if h:
            flush()
            while stack and stack[-1].level >= h.level:
                stack.pop()
            stack.append(h)
            last_heading_line = ln
            continue
        # titre sur deux lignes : "4.4 CATASTROPHES NATURELLES ET" / "TECHNOLOGIQUES"
        if (last_heading_line is not None and not buf and ln.bold and len(ln.text) <= 60
                and not _sublabel(ln.text) and not ln.text.endswith(":")
                and abs(ln.size - last_heading_line.size) < 0.5 and ln.page == last_heading_line.page):
            stack[-1].title = f"{stack[-1].title} {ln.text}".strip()
            last_heading_line = ln
            continue
        last_heading_line = None

        sk = _sublabel(ln.text)
        continues_label = len(buf) <= 2 and buf and _sublabel(buf[0].text) == sk
        if sk and buf and not continues_label:
            flush()
        if sk:
            kind = sk
        elif not buf and _GUARANTEE_OPENER.match(ln.text):
            kind = "garantie"
        buf.append(ln)
    flush()
    return result


def _unique(cid: str, used: set[str]) -> str:
    out, i = cid, 2
    while out in used:
        out, i = f"{cid} ({i})", i + 1
    used.add(out)
    return out


def _split_lexicon(lines: list[Line], path: list[str], contract_id: str) -> list[Clause]:
    """Découpe un lexique en une clause par terme défini.

    Un terme = ligne quasi entièrement en gras, courte, commençant par une majuscule.
    Une ligne en gras qui commence par une minuscule prolonge le terme précédent
    (cas Altima : « Dommages » … « corporels » sur deux lignes, en marge de la définition).
    """
    entries: list[tuple[str, list[Line]]] = []
    for ln in lines:
        is_term = ln.bold and len(ln.text) <= 70 and not ln.text.endswith((".", ",", ";"))
        if is_term and ln.text[0].isupper():
            entries.append((ln.text.rstrip(" :"), [ln]))
        elif is_term and entries and ln.text[0].islower():
            term, ls = entries[-1]
            entries[-1] = (f"{term} {ln.text.rstrip(' :')}", ls)
        elif entries:
            entries[-1][1].append(ln)
    out = []
    for term, ls in entries:
        body = [l for l in ls if not (l.bold and l.text.rstrip(" :") in term)]
        if not body:
            continue
        text = "\n".join(l.text for l in body)
        out.append(Clause(
            clause_id=f"Déf. {term}", section_path=path, title=term, kind_hint="definition",
            page_start=ls[0].page, page_end=ls[-1].page, text=text, term=term))
    return out


def normalize_term(term: str) -> str:
    t = unicodedata.normalize("NFKD", term.lower())
    return re.sub(r"[^a-z0-9 ]", "", "".join(c for c in t if not unicodedata.combining(c))).strip()

from pathlib import Path

import pytest

from sinistre.ingest import load_registry
from sinistre.parse import Line, _split_lexicon, clean, match_heading, parse_pdf

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def L(text, bold=False, size=9.0, page=1, y=0.0):
    return Line(page=page, x0=50, y0=y, x1=300, size=size, bold_ratio=1.0 if bold else 0.0, text=text)


def test_clean_removes_control_chars_and_symbol_bullets():
    assert clean("•\x07 Le vol  commis") == "• Le vol commis"
    assert clean(chr(0xF0A7) + " par effraction") == "• par effraction"


def test_heading_patterns_respect_bold_and_size():
    profile = {"headings": [
        {"level": 1, "pattern": r"^(\d{1,2})\s*-\s+(.+)$", "min_size": 13},
        {"level": 2, "pattern": r"^(\d{1,2}\.\d{1,2})\s*[-–]?\s*([A-ZÉ].*)$", "bold": True}]}
    h = match_heading(L("4.7 VOL - VANDALISME", bold=True), profile)
    assert (h.level, h.number, h.title) == (2, "4.7", "VOL - VANDALISME")
    assert match_heading(L("4.7 VOL - VANDALISME", bold=False), profile) is None
    assert match_heading(L("4 - LES ÉVÉNEMENTS GARANTIS", size=9), profile) is None
    assert match_heading(L("4 - LES ÉVÉNEMENTS GARANTIS", size=14.3), profile).level == 1


def test_lexicon_merges_lowercase_term_continuation():
    lines = [L("Dommages", bold=True, y=0), L("Il s'agit de toute atteinte à l'intégrité physique.", y=2),
             L("corporels", bold=True, y=11), L("Franchise", bold=True, y=30),
             L("Somme déduite de l'indemnisation.", y=31)]
    defs = _split_lexicon(lines, ["Lexique"], "x")
    assert [d.term for d in defs] == ["Dommages corporels", "Franchise"]
    assert defs[0].text.startswith("Il s'agit")


@pytest.fixture(scope="module")
def altima():
    src = next(s for s in load_registry() if s.contract_id == "altima_mrh")
    if not src.path.exists():
        pytest.skip("PDF Altima absent")
    return parse_pdf(src.path, src.contract_id, src.profile)


def test_altima_vol_exclusion_is_its_own_clause(altima):
    c = next(c for c in altima.clauses if c.clause_id == "Art. 4.7 §2")
    assert c.kind_hint == "exclusion"
    assert c.page_start == 6
    assert "locaux à usage commun" in c.text.replace("\n", " ")
    assert c.section_path[-1].startswith("Art. 4.7")


def test_altima_two_column_order_and_two_line_title(altima):
    ids = [c.clause_id for c in altima.clauses]
    assert ids.index("Art. 4.8") < ids.index("Chap. 5")  # colonne droite lue avant le chapitre suivant
    t = next(c for c in altima.clauses if c.clause_id == "Art. 4.4")
    assert t.title == "CATASTROPHES NATURELLES ET TECHNOLOGIQUES"


def test_altima_definitions_indexed(altima):
    terms = {d.term for d in altima.definitions}
    assert {"Dépendances", "Dommages corporels", "Objets de valeur"} <= terms
    assert all(d.clause_id.startswith("Déf. ") for d in altima.definitions)


def test_running_headers_and_page_numbers_dropped():
    src = next(s for s in load_registry() if s.contract_id == "macsf_mh")
    if not src.path.exists():
        pytest.skip("PDF MACSF absent")
    parsed = parse_pdf(src.path, src.contract_id, src.profile)
    vol = next(c for c in parsed.clauses if c.clause_id == "Art. 2.5 §2")
    assert "MULTIRISQUE HABITATION" not in vol.text
    assert "effraction" in vol.text

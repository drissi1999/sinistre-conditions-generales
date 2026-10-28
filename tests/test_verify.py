from sinistre.verify import check_quote

CLAUSE = ("Ce que nous ne garantissons pas\n• Le vol des objets déposés ou fixés à l’extérieur des\n"
          "bâtiments assurés, ou dans des bâtiments non entièrement\nclos et couverts, ou dans les "
          "locaux à usage commun de\nplusieurs occupants locataires ou copropriétaires.")


def test_exact_quote_across_line_breaks():
    r = check_quote("dans les locaux à usage commun de plusieurs occupants locataires", CLAUSE)
    assert r.ok
    start, end = r.spans[0]
    assert CLAUSE[start:end].startswith("dans les locaux")


def test_typographic_apostrophe_case_and_bullets_are_tolerated():
    assert check_quote("LE VOL DES OBJETS déposés ou fixés à l'extérieur des bâtiments assurés", CLAUSE).ok


def test_missing_spaces_in_pdf_text_are_tolerated():
    assert check_quote("les dommages matériels directs causés", "les dommages matérielsdirects causés").ok


def test_ellipsis_fragments_must_appear_in_order():
    assert check_quote("Le vol des objets déposés […] locaux à usage commun de plusieurs occupants", CLAUSE).ok
    bad = check_quote("locaux à usage commun de plusieurs occupants … Le vol des objets déposés", CLAUSE)
    assert not bad.ok and "ordre" in bad.reason


def test_paraphrase_fails():
    r = check_quote("le vol dans les parties communes de l'immeuble n'est pas garanti", CLAUSE)
    assert not r.ok


def test_too_short_fragment_fails():
    assert not check_quote("Le vol", CLAUSE).ok
    assert not check_quote("", CLAUSE).ok

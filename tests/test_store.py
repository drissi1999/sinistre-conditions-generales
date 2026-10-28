import numpy as np
import pytest

from sinistre import store
from sinistre.parse import Clause, ParsedContract

META = {"contract_id": "c1", "insurer": "Test", "product": "MRH", "edition": "1", "source_url": ""}


def _clause(cid, kind, text, term=None, page=1):
    return Clause(cid, ["Chap. 4", cid], cid, kind, page, page, text, term=term)


@pytest.fixture
def conn():
    c = store.connect(":memory:")
    parsed = ParsedContract("c1", 10, [
        _clause("Art. 4.7", "garantie", "Le vol par effraction."),
        _clause("Art. 4.7 §2", "exclusion", "Le vol dans les locaux à usage commun."),
        _clause("Déf. Dépendances", "definition", "Locaux autres que les pièces d'habitation.", term="Dépendances"),
        _clause("Déf. Vol", "definition", "Soustraction frauduleuse.", term="Vol"),
    ])
    store.save_parsed(c, META, "sha-1", parsed)
    store.save_extraction(c, "c1", "sha-1", "m", "v1", {
        "guarantees": [dict(peril="vol", label="Vol", scope="Vol par effraction", ceiling=None, deductible=None,
                            optional=0, clause_id="Art. 4.7", quote="Le vol par effraction", quote_ok=1,
                            review_status="a_valider")],
        "exclusions": [dict(peril="vol", description="Locaux communs", clause_id="Art. 4.7 §2",
                            quote="locaux à usage commun", quote_ok=1, review_status="a_valider"),
                       dict(peril=None, description="Faute intentionnelle", clause_id="Chap. 11",
                            quote="faute intentionnelle", quote_ok=1, review_status="a_valider"),
                       dict(peril="incendie", description="Brûlures", clause_id="Art. 4.1 §2",
                            quote="brûlures", quote_ok=1, review_status="a_valider")],
        "conditions": []}, {})
    return c


def test_candidate_lookup_includes_general_exclusions_only_for_requested_peril(conn):
    rows = store.candidate_rows(conn, "c1", ["vol"])
    assert [g["clause_id"] for g in rows["guarantees"]] == ["Art. 4.7"]
    assert {e["description"] for e in rows["exclusions"]} == {"Locaux communs", "Faute intentionnelle"}


def test_definition_lookup_handles_plural_and_accents(conn):
    found = store.find_definitions(conn, "c1", ["dependance", "volé"])
    assert "Déf. Dépendances" in found
    assert "Déf. Vol" not in found  # « volé » n'est pas « vol » : pas de faux positif par préfixe
    assert "Déf. Vol" in store.find_definitions(conn, "c1", ["vol de vélo"])


def test_extraction_idempotence_key(conn):
    assert store.extraction_done(conn, "c1", "sha-1", "v1")
    assert not store.extraction_done(conn, "c1", "sha-2", "v1")  # nouvelle édition du PDF
    assert not store.extraction_done(conn, "c1", "sha-1", "v2")  # nouveau prompt


def test_reparse_purges_extracted_rows(conn):
    store.save_parsed(conn, META, "sha-2", ParsedContract("c1", 10, [_clause("Art. 1", "texte", "x")]))
    assert store.candidate_rows(conn, "c1", ["vol"])["exclusions"] == []


def test_embeddings_roundtrip(conn):
    store.save_embeddings(conn, "c1", ["Art. 4.7"], np.ones((1, 4), dtype=np.float32))
    ids, vecs = store.get_embeddings(conn, "c1")
    assert ids == ["Art. 4.7"] and vecs.shape == (1, 4)

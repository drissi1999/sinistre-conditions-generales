"""Construction de la base : ingestion -> parsing -> embeddings -> extraction structurée.

Idempotent : chaque étape est sautée si l'empreinte du PDF (et la version du prompt
d'extraction) n'a pas changé. Ajouter un contrat = l'ajouter au registre et relancer.

    sinistre-build                 # tous les contrats
    sinistre-build --only altima_mrh --skip-extract
"""

from __future__ import annotations

import argparse
import json
import sys

from . import config, store
from .extract import PROMPT_VERSION, extract_contract
from .ingest import load_registry, sha256
from .parse import parse_pdf
from .retrieve import clause_document, embed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="contract_id à traiter")
    ap.add_argument("--skip-extract", action="store_true", help="parsing + embeddings seulement")
    ap.add_argument("--force", action="store_true", help="ignore les empreintes et refait tout")
    args = ap.parse_args(argv)

    conn = store.connect(config.DB_PATH)
    for src in load_registry():
        if args.only and src.contract_id not in args.only:
            continue
        if not src.path.exists():
            print(f"[{src.contract_id}] PDF absent : {src.path} (voir data/sources.md)", file=sys.stderr)
            continue
        sha = sha256(src.path)
        if args.force or store.contract_sha(conn, src.contract_id) != sha:
            parsed = parse_pdf(src.path, src.contract_id, src.profile)
            store.save_parsed(conn, src.meta, sha, parsed)
            vecs = embed([clause_document(c) for c in parsed.clauses])
            store.save_embeddings(conn, src.contract_id, [c.clause_id for c in parsed.clauses], vecs)
            print(f"[{src.contract_id}] {len(parsed.clauses)} clauses, {len(parsed.definitions)} définitions")
        else:
            print(f"[{src.contract_id}] inchangé, parsing sauté")

        if args.skip_extract:
            continue
        if not args.force and store.extraction_done(conn, src.contract_id, sha, PROMPT_VERSION):
            print(f"[{src.contract_id}] extraction déjà faite ({PROMPT_VERSION})")
            continue
        clauses = store.get_clauses(conn, src.contract_id)
        rows, stats = extract_contract(
            clauses, progress=lambda i, n: print(f"[{src.contract_id}] extraction lot {i}/{n}", flush=True))
        store.save_extraction(conn, src.contract_id, sha, config.LLM_MODEL, PROMPT_VERSION, rows, stats)
        print(f"[{src.contract_id}] extraction : {json.dumps(stats, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

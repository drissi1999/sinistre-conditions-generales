"""Affiche un résumé du parsing d'un contrat (outil de mise au point des profils)."""
import sys, yaml
from sinistre.parse import parse_pdf

reg = yaml.safe_load(open("data/contracts.yaml", encoding="utf-8"))
for c in reg["contracts"]:
    if len(sys.argv) > 1 and c["contract_id"] not in sys.argv[1:]:
        continue
    pc = parse_pdf("data/" + c["file"], c["contract_id"], c["profile"])
    kinds = {}
    for cl in pc.clauses:
        kinds[cl.kind_hint] = kinds.get(cl.kind_hint, 0) + 1
    print(f"===== {c['contract_id']}: {len(pc.clauses)} clauses {kinds}")
    for cl in pc.clauses:
        if cl.kind_hint != "definition":
            print(f"  p{cl.page_start:<3} {cl.kind_hint[:4]:4} {cl.clause_id:28.28} | {cl.title[:45]:45} | {cl.text[:50]!r}")
    print("  DEFS:", [d.term for d in pc.definitions])

"""Évaluation : exactitude du verdict, validité des citations, gestion de l'incertitude.

    python eval/run_eval.py              # écrit eval/results.md et eval/results.json
    python eval/run_eval.py --only bougie_jardin_altima

Les réponses LLM sont en cache (data/cache) : relancer sans changer le code ou les prompts
redonne exactement les mêmes résultats, sans appel réseau.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from sinistre import config, store
from sinistre.pipeline import answer_claim

HERE = Path(__file__).resolve().parent


def run_case(case: dict) -> dict:
    conn = store.connect(config.DB_PATH)
    try:
        r = answer_claim(conn, case["contract_id"], case["claim"])
    except Exception as e:  # un cas en échec est compté comme tel, l'éval continue
        return {**case, "error": str(e)}
    finally:
        conn.close()
    cited_ok = {c.clause_id for c in r.checks if c.ok}
    return {
        **case,
        "verdict": r.answer.verdict,
        "model_verdict": r.model_verdict,
        "downgraded": r.downgraded,
        "confiance": r.answer.confiance,
        "strict_ok": r.answer.verdict == case["expected"][0],
        "acceptable_ok": r.answer.verdict in case["expected"],
        "citations": len(r.checks),
        "citations_ok": r.citations_ok,
        "expected_clause_cited": bool(cited_ok & set(case["expected_clauses"])),
        "cited": sorted(cited_ok),
        "questions": r.answer.informations_manquantes,
        "resume": r.answer.resume,
        "seconds": r.seconds,
    }


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f} % ({n}/{d})" if d else "n/a"


def report(rows: list[dict]) -> str:
    ok = [r for r in rows if "error" not in r]
    n = len(ok)
    cits = sum(r["citations"] for r in ok)
    cits_ok = sum(r["citations_ok"] for r in ok)
    pref_indet = [r for r in ok if r["expected"][0] == "indéterminé"]
    clear = [r for r in ok if r["category"] != "ambigu"]
    wrong_confident = [r for r in ok if not r["acceptable_ok"] and r["verdict"] != "indéterminé"]
    lines = [
        f"Modèle : `{config.LLM_MODEL}` · {len(rows)} cas · {len(rows) - n} en erreur",
        "",
        "| Indicateur | Résultat |",
        "|---|---|",
        f"| Verdict exact (verdict attendu) | {pct(sum(r['strict_ok'] for r in ok), n)} |",
        f"| Verdict acceptable (attendu ou prudent admis) | {pct(sum(r['acceptable_ok'] for r in ok), n)} |",
        f"| Citations vérifiées mot pour mot | {pct(cits_ok, cits)} |",
        f"| Clause attendue citée et vérifiée | {pct(sum(r['expected_clause_cited'] for r in ok), n)} |",
        f"| « Indéterminé » quand il est attendu | {pct(sum(r['verdict'] == 'indéterminé' for r in pref_indet), len(pref_indet))} |",
        f"| « Indéterminé » sur un cas clair (prudence excessive) | {pct(sum(r['verdict'] == 'indéterminé' for r in clear), len(clear))} |",
        f"| Erreurs affirmées (verdict faux, non « indéterminé ») | {pct(len(wrong_confident), n)} |",
        f"| Verdicts rétrogradés par la vérification | {sum(r['downgraded'] for r in ok)} |",
        "",
        "| Cas | Catégorie | Attendu | Obtenu | Citations OK | Clause attendue |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(f"| `{r['id']}` | {r['category']} | {r['expected'][0]} | ERREUR | | |")
            continue
        mark = "✅" if r["strict_ok"] else ("🟡" if r["acceptable_ok"] else "❌")
        lines.append(f"| `{r['id']}` | {r['category']} | {' / '.join(r['expected'])} | {mark} {r['verdict']}"
                     f"{' (rétrogradé)' if r['downgraded'] else ''} | {r['citations_ok']}/{r['citations']} | "
                     f"{'✅' if r['expected_clause_cited'] else '❌'} |")
    lines += ["", "✅ verdict attendu · 🟡 verdict prudent admis · ❌ verdict faux"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    cases = yaml.safe_load((HERE / "cases.yaml").read_text(encoding="utf-8"))["cases"]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(run_case, cases))
    md = report(rows)
    print(md)
    if not args.only:
        (HERE / "results.md").write_text(md + "\n", encoding="utf-8")
        (HERE / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

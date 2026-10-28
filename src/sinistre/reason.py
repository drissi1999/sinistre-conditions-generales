"""Prompts et appels LLM de la phase question : compréhension du sinistre, raisonnement."""

from __future__ import annotations

import json

from .llm import complete_json
from .parse import Clause
from .schemas import PERILS, Answer, ClaimFacts

CLAIM_SYSTEM = f"""Tu aides un gestionnaire sinistre habitation. Transforme la déclaration en faits structurés.
- N'invente rien : un fait non mentionné vaut null (ex. on ne sait pas s'il y a eu effraction -> null).
- perils ∈ {list(PERILS)} : toutes les garanties qui pourraient être concernées, la plus probable d'abord
  (ex. une bougie qui fond : incendie en premier).
- lieu ∈ interieur_logement | dependance_privative | partie_commune | exterieur_jardin | hors_domicile | inconnu.
- termes_cles : 4 à 8 mots du vocabulaire des contrats d'assurance utiles pour chercher les clauses
  (ex. "vol", "effraction", "parties communes", "dépendances", "incendie", "mobilier de jardin", "plein air").
Réponds uniquement en JSON avec les clés : resume, perils, biens_endommages, lieu, local_ferme_a_cle, effraction,
assure_absent, duree_absence_jours, flammes_ou_incendie, cause, termes_cles."""

ANSWER_SYSTEM = """Tu es gestionnaire sinistre senior. Tu dis si un sinistre est couvert par CE contrat,
en t'appuyant uniquement sur les clauses fournies, jamais sur ta connaissance d'autres contrats.

Méthode, dans l'ordre :
1. Garantie : quelle garantie pourrait jouer ? L'événement correspond-il à ce qu'elle couvre et aux
   définitions du lexique fournies ?
2. Conditions : lieu des biens, effraction, mesures de prévention, absence… sont-elles remplies ?
3. Exclusions : examine chaque exclusion fournie, celles de la garantie ET les exclusions générales.
4. Conclusion :
   - "couvert" : une garantie s'applique et aucune condition ni exclusion ne l'écarte ;
   - "non couvert" : aucune garantie ne vise l'événement, ou une exclusion / condition l'écarte clairement ;
   - "indéterminé" : la réponse dépend d'un fait inconnu, d'une option ou formule non connue (conditions
     particulières), ou le texte est ambigu. Un « indéterminé » bien justifié vaut mieux qu'un verdict fragile.

Citations (vérifiées automatiquement, une citation inexacte invalide toute la réponse) :
- "citation" = copier-coller exact d'un passage de la clause, 1 à 2 phrases, sans reformuler ni corriger.
- "clause_id" exactement comme indiqué entre crochets. Cite au moins la garantie examinée et chaque
  exclusion ou condition déterminante.
- Chaque étape du raisonnement renvoie à une clause (ex. « Art. 4.7 »).

Style : français métier, phrases courtes, compréhensible par un gestionnaire sinistre.
"informations_manquantes" : questions concrètes à poser à l'assuré ou points à vérifier aux conditions
particulières (ex. « Y a-t-il eu effraction ? »). Liste vide si rien ne manque.
"confiance" ∈ faible | moyenne | élevée, avec "raison_confiance".

Réponds uniquement en JSON :
{"verdict": "...", "resume": "...", "raisonnement": ["...", "..."],
 "clauses_citées": [{"clause_id": "...", "page": 0, "citation": "...", "role": "garantie|exclusion|condition|definition|autre"}],
 "informations_manquantes": ["..."], "confiance": "...", "raison_confiance": "..."}"""


def understand_claim(claim: str) -> ClaimFacts:
    return complete_json(CLAIM_SYSTEM, f"Déclaration de sinistre :\n{claim.strip()}", ClaimFacts, max_tokens=1200)


def render_context(clauses: list[Clause], rows: dict[str, list[dict]]) -> str:
    parts = []
    for c in clauses:
        label = "DÉFINITION" if c.kind_hint == "definition" else c.kind_hint.upper()
        parts.append(f"[{c.clause_id}] (p. {c.page_start}, {label}) {' > '.join(c.section_path)}\n{c.text}")
    index = []
    for table, title in (("guarantees", "Garanties"), ("exclusions", "Exclusions"), ("conditions", "Conditions")):
        for r in rows.get(table, []):
            desc = r.get("scope") or r.get("description")
            extra = f" — plafond : {r['ceiling']}" if r.get("ceiling") else ""
            extra += f" — paramètre : {r['parameter']}" if r.get("parameter") else ""
            index.append(f"- {title} | {r.get('peril') or 'toutes garanties'} | {desc}{extra} [{r['clause_id']}]")
    head = ("Fiche structurée du contrat (extraite au préalable, pour t'orienter ; seules les clauses font foi) :\n"
            + "\n".join(index) + "\n\n") if index else ""
    return head + "Clauses du contrat :\n\n" + "\n\n---\n\n".join(parts)


def reason(claim: str, facts: ClaimFacts, insurer: str, clauses: list[Clause], rows: dict) -> Answer:
    user = (f"Contrat : conditions générales {insurer}.\n\nDéclaration :\n{claim.strip()}\n\n"
            f"Faits extraits :\n{json.dumps(facts.model_dump(), ensure_ascii=False)}\n\n"
            + render_context(clauses, rows))
    return complete_json(ANSWER_SYSTEM, user, Answer, max_tokens=3000)

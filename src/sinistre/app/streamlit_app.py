"""Interface gestionnaire sinistre (Streamlit)."""

from __future__ import annotations

import html
import os
import sqlite3

import pandas as pd
import streamlit as st

# Streamlit Cloud : les secrets (LLM_API_KEY, LLM_MODEL…) ne deviennent des variables d'environnement
# qu'une fois st.secrets lu. On les copie AVANT d'importer la config, qui lit l'environnement.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float)):
            os.environ.setdefault(_k, str(_v))
except Exception:  # pas de secrets.toml en local : la config lit alors .env
    pass

from sinistre import config, store  # noqa: E402
from sinistre.llm import LLMError  # noqa: E402
from sinistre.pipeline import Result, answer_claim, compare  # noqa: E402

EXEMPLES = {
    "1 · vélo volé (local commun)": "Je me fais voler mon vélo dans le local commun de l'immeuble, "
                                      "qui n'était pas fermé à clé. Suis-je couvert ?",
    "2 · bougie au jardin": "Un assuré laisse une bougie sur la table de son jardin pendant "
                                            "ses vacances. Avec la chaleur, la bougie fond et abîme la table. "
                                            "Est-ce couvert ?",
}
COMPARE = "Comparer tous les contrats"
BADGE = {"couvert": ("#1e7d32", "#e8f5e9", "COUVERT"),
         "non couvert": ("#b71c1c", "#ffebee", "NON COUVERT"),
         "indéterminé": ("#8a5a00", "#fff8e1", "INDÉTERMINÉ")}
ROLE = {"garantie": "Garantie", "exclusion": "Exclusion", "condition": "Condition",
        "definition": "Définition", "autre": "Autre"}

st.set_page_config(page_title="Sinistre & conditions générales", page_icon="🏠", layout="wide")
st.markdown("""<style>
mark {background:#ffe58f; padding:0 2px; border-radius:2px}
.clause {white-space:pre-wrap; font-size:0.88rem; line-height:1.45; background:var(--secondary-background-color);
         padding:0.7rem 0.9rem; border-radius:6px; max-height:320px; overflow:auto}
.badge {display:inline-block; padding:0.45rem 1rem; border-radius:8px; font-weight:700; font-size:1.25rem; white-space:nowrap;
        letter-spacing:0.04em; border:2px solid}
.small-badge {display:inline-block; padding:0.2rem 0.7rem; border-radius:6px; font-weight:700; border:2px solid}
</style>""", unsafe_allow_html=True)


def connect() -> sqlite3.Connection:
    return store.connect(config.DB_PATH)


@st.cache_resource
def shared_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def badge(verdict: str, small: bool = False) -> str:
    fg, bg, label = BADGE[verdict]
    cls = "small-badge" if small else "badge"
    return f'<span class="{cls}" style="color:{fg};background:{bg};border-color:{fg}">{label}</span>'


def highlight(text: str, spans: list[tuple[int, int]]) -> str:
    out, pos = [], 0
    for a, b in sorted(spans):
        out += [html.escape(text[pos:a]), "<mark>", html.escape(text[a:b]), "</mark>"]
        pos = b
    out.append(html.escape(text[pos:]))
    return f'<div class="clause">{"".join(out)}</div>'


def verification_banner(r: Result) -> None:
    n, ok = len(r.checks), r.citations_ok
    if r.downgraded:
        st.error(f"**Vérification des citations : {ok}/{n} retrouvées.** Le modèle proposait "
                 f"« {r.model_verdict} » ; verdict ramené à « indéterminé ». {r.downgrade_reason}")
    elif n and ok == n:
        st.success(f"**Vérification des citations : {ok}/{n}** retrouvées mot pour mot dans le contrat.")
    else:
        st.warning(f"**Vérification des citations : {ok}/{n}.** {r.downgrade_reason}")


def show_result(r: Result) -> None:
    a = r.answer
    c1, c2 = st.columns([1, 3])
    with c1:
        st.markdown(badge(a.verdict), unsafe_allow_html=True)
        st.caption(f"Confiance : **{a.confiance}**")
    with c2:
        st.markdown(f"#### {a.resume}")
        st.caption(a.raison_confiance)
    verification_banner(r)

    left, right = st.columns([3, 2])
    with left:
        st.markdown("##### Raisonnement")
        st.markdown("\n".join(f"{i}. {s}" for i, s in enumerate(a.raisonnement, 1)))
    with right:
        st.markdown("##### Questions à poser à l'assuré")
        if a.informations_manquantes:
            st.markdown("\n".join(f"- {q}" for q in a.informations_manquantes))
        else:
            st.caption("Aucune information manquante identifiée.")

    st.markdown("##### Clauses citées")
    for chk in r.checks:
        status = "✅" if chk.ok else "❌"
        page = f"p. {chk.page}" if chk.page else "page inconnue"
        with st.expander(f"{status} {chk.clause_id} · {ROLE.get(chk.role, chk.role)} · {page}", expanded=chk.ok):
            st.markdown(f"> {html.escape(chk.quote)}")
            if chk.ok:
                st.markdown(highlight(chk.clause_text, chk.spans), unsafe_allow_html=True)
            else:
                st.caption(f"Citation rejetée : {chk.reason}")
                if chk.clause_text:
                    st.markdown(highlight(chk.clause_text, []), unsafe_allow_html=True)

    with st.expander("Détails techniques : faits extraits, clauses consultées"):
        st.json(r.facts.model_dump())
        st.write(f"{len(r.context_ids)} clauses fournies au modèle (sur l'ensemble du contrat) :",
                 ", ".join(r.context_ids))
        st.write({t: len(v) for t, v in r.sql_rows.items()}, "lignes trouvées dans la base structurée")
        st.caption(f"Temps de traitement : {r.seconds} s")


def show_comparison(results: list[Result]) -> None:
    st.markdown("Le même sinistre, analysé contrat par contrat. Chaque colonne est vérifiée indépendamment.")
    cols = st.columns(len(results))
    for col, r in zip(cols, results):
        with col:
            st.markdown(f"**{r.insurer}**")
            st.markdown(badge(r.answer.verdict, small=True), unsafe_allow_html=True)
            st.markdown(r.answer.resume)
            ok, n = r.citations_ok, len(r.checks)
            st.caption(f"{'✅' if ok == n and n else '⚠️'} Citations vérifiées : {ok}/{n} · confiance {r.answer.confiance}")
            st.caption("Clauses : " + ", ".join(c.clause_id for c in r.checks))
    for r in results:
        with st.expander(f"Détail : {r.insurer}"):
            show_result(r)


# --------------------------------------------------------------------------- page

contracts = store.list_contracts(shared_conn())
labels = {f"{c['insurer']} · {c['product']}": c["contract_id"] for c in contracts}

with st.sidebar:
    st.markdown("### Contrat")
    choice = st.radio("Conditions générales", [*labels, COMPARE], label_visibility="collapsed")
    st.divider()
    st.caption(f"{len(contracts)} contrats publics indexés. Modèle : `{config.LLM_MODEL}`.")
    st.caption("Démonstration sur données publiques. Les conditions particulières du client, "
               "qui peuvent modifier ces garanties, ne sont pas connues de l'outil.")

st.title("Ce sinistre est-il couvert ?")
tab_analyse, tab_base, tab_how = st.tabs(["Analyse d'un sinistre", "Base des contrats", "Comment ça marche"])

with tab_analyse:
    if "claim" not in st.session_state:
        st.session_state.claim = ""
    b1, b2, _ = st.columns([2, 2, 3])
    for btn, (name, text) in zip((b1, b2), EXEMPLES.items()):
        if btn.button(f"Exemple {name}", use_container_width=True):
            st.session_state.claim = text
    claim = st.text_area("Déclaration de sinistre", key="claim", height=110,
                         placeholder="Décrivez le sinistre tel que déclaré par l'assuré…")
    go = st.button("Analyser", type="primary", disabled=not claim.strip())

    if go:
        try:
            with st.spinner("Analyse du contrat : recherche des garanties, exclusions et définitions…"):
                if choice == COMPARE:
                    st.session_state.result = ("compare", compare(connect, list(labels.values()), claim))
                else:
                    st.session_state.result = ("single", answer_claim(connect(), labels[choice], claim))
        except LLMError as e:
            st.error(f"Le service d'IA n'a pas pu répondre : {e}")
    if "result" in st.session_state:
        mode, res = st.session_state.result
        st.divider()
        show_comparison(res) if mode == "compare" else show_result(res)

with tab_base:
    st.markdown("Chaque contrat est lu **une seule fois** à l'ingestion : ses garanties, exclusions et "
                "conditions deviennent des lignes de tables, chacune reliée à sa clause source. "
                "Une question ne relit pas le contrat : elle interroge ces tables puis les clauses ciblées.")
    conn = shared_conn()
    table = st.selectbox("Table", ["exclusions", "guarantees", "conditions"],
                         format_func={"exclusions": "Exclusions", "guarantees": "Garanties",
                                      "conditions": "Conditions"}.get)
    peril = st.text_input("Filtrer par garantie (ex. vol, incendie)", "")
    df = pd.read_sql_query(
        f"SELECT c.insurer AS assureur, t.* FROM {table} t JOIN contracts c USING (contract_id)", conn)
    if peril:
        df = df[df["peril"].fillna("toutes garanties").str.contains(peril, case=False)]
    st.dataframe(df.drop(columns=["contract_id"]), use_container_width=True, hide_index=True)
    runs = pd.read_sql_query("SELECT contract_id, model, prompt_version, created_at, stats FROM extraction_runs", conn)
    with st.expander("Traçabilité des extractions"):
        st.dataframe(runs, use_container_width=True, hide_index=True)

with tab_how:
    st.markdown("""
#### Le principe
Ne pas donner le PDF brut à un chatbot : sur un contrat de 70 pages, une exclusion décisive se perd au milieu,
les définitions ne sont pas reliées aux garanties, et rien ne prouve que la citation est réelle.

```
 PDF ──► Parsing (titres, articles, clauses, pages) ──► SQLite : clauses + définitions
                                         │
                                         └─► Extraction IA, 1 fois par contrat ──► tables garanties /
                                                                                   exclusions / conditions
 Sinistre ──► Faits structurés (IA) ──► Recherche ciblée :  tables SQL (garantie, exclusions, conditions)
                                                           + recherche hybride dans les clauses
                                                           + définitions du lexique
          ──► Raisonnement (IA, réponse JSON stricte) ──► Vérification mot pour mot des citations
          ──► Verdict : couvert / non couvert / indéterminé  (+ questions à poser à l'assuré)
```

#### Ce qui garantit la fiabilité
- **Citations vérifiées** : chaque extrait cité est recherché mot pour mot dans la clause. Une seule citation
  introuvable et le verdict devient « indéterminé ».
- **Exclusions toujours examinées** : l'article complet (garantie + exclusions + prévention) et les exclusions
  générales sont fournis au modèle, même s'ils ne ressortent pas de la recherche.
- **« Indéterminé » assumé** : si la réponse dépend d'un fait inconnu ou des conditions particulières,
  l'outil le dit et liste les questions à poser.
""")

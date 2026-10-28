"""Schémas Pydantic : extraction par contrat, compréhension du sinistre, verdict."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Taxonomie commune à tous les contrats : c'est elle qui rend des centaines de contrats comparables.
Peril = Literal[
    "incendie", "degats_des_eaux", "vol", "vandalisme", "bris_de_glace", "evenements_climatiques",
    "catastrophes_naturelles", "dommages_electriques", "attentats", "responsabilite_civile",
    "protection_juridique", "assistance", "autre",
]
PERILS: tuple[str, ...] = Peril.__args__  # type: ignore[attr-defined]

ConditionType = Literal[
    "effraction_requise", "locaux_fermes_a_cle", "local_privatif_requis", "inoccupation_max",
    "biens_a_l_interieur", "mesure_de_prevention", "delai_de_declaration", "preuve_requise",
    "option_ou_formule", "autre",
]


def _peril_or_autre(v):
    return v if v in PERILS else "autre"


# --------------------------------------------------------------------------- extraction

class GuaranteeRow(BaseModel):
    peril: Peril
    label: str = Field(description="Intitulé court de la garantie, en français métier")
    scope: str = Field(description="Ce qui est couvert, en une phrase")
    ceiling: Optional[str] = None
    deductible: Optional[str] = None
    optional: Optional[bool] = Field(None, description="Vrai si la garantie dépend d'une option ou formule")
    clause_id: str
    quote: str = Field(description="Extrait exact de la clause qui fonde la ligne")

    @field_validator("peril", mode="before")
    @classmethod
    def _p(cls, v):
        return _peril_or_autre(v)


class ExclusionRow(BaseModel):
    peril: Optional[Peril] = Field(None, description="Garantie restreinte ; null = exclusion générale")
    description: str
    clause_id: str
    quote: str

    @field_validator("peril", mode="before")
    @classmethod
    def _p(cls, v):
        return None if v in (None, "", "general", "générale", "toutes") else _peril_or_autre(v)


class ConditionRow(BaseModel):
    peril: Optional[Peril] = None
    condition_type: ConditionType
    description: str
    parameter: Optional[str] = Field(None, description="Valeur chiffrée éventuelle : « 48 h », « 90 jours »")
    clause_id: str
    quote: str

    @field_validator("peril", mode="before")
    @classmethod
    def _p(cls, v):
        return None if v in (None, "", "general") else _peril_or_autre(v)

    @field_validator("condition_type", mode="before")
    @classmethod
    def _t(cls, v):
        return v if v in ConditionType.__args__ else "autre"  # type: ignore[attr-defined]


class SectionExtraction(BaseModel):
    guarantees: list[GuaranteeRow] = []
    exclusions: list[ExclusionRow] = []
    conditions: list[ConditionRow] = []


# --------------------------------------------------------------------------- sinistre

Lieu = Literal["interieur_logement", "dependance_privative", "partie_commune", "exterieur_jardin",
               "hors_domicile", "inconnu"]


class ClaimFacts(BaseModel):
    resume: str
    perils: list[Peril] = Field(description="Garanties potentiellement concernées, la plus probable d'abord")
    biens_endommages: list[str] = []
    lieu: Lieu = "inconnu"
    local_ferme_a_cle: Optional[bool] = None
    effraction: Optional[bool] = None
    assure_absent: Optional[bool] = None
    duree_absence_jours: Optional[int] = None
    flammes_ou_incendie: Optional[bool] = Field(None, description="Y a-t-il eu des flammes / un embrasement ?")
    cause: str = ""
    termes_cles: list[str] = Field([], description="Termes contractuels à rechercher (vol, effraction, dépendances…)")

    @field_validator("perils", mode="before")
    @classmethod
    def _ps(cls, v):
        return [_peril_or_autre(x) for x in (v or [])] or ["autre"]

    @field_validator("lieu", mode="before")
    @classmethod
    def _l(cls, v):
        return v if v in Lieu.__args__ else "inconnu"  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- verdict

Verdict = Literal["couvert", "non couvert", "indéterminé"]


class Citation(BaseModel):
    clause_id: str
    page: Optional[int] = None
    citation: str = Field(description="Extrait recopié mot pour mot")
    role: Literal["garantie", "exclusion", "condition", "definition", "autre"] = "autre"

    @field_validator("role", mode="before")
    @classmethod
    def _r(cls, v):
        v = (v or "").replace("é", "e")
        return v if v in ("garantie", "exclusion", "condition", "definition") else "autre"


class Answer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    verdict: Verdict
    resume: str = Field(description="Une phrase de conclusion pour le gestionnaire")
    raisonnement: list[str]
    clauses_citees: list[Citation] = Field(alias="clauses_citées")
    informations_manquantes: list[str] = []
    confiance: Literal["faible", "moyenne", "élevée"]
    raison_confiance: str = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _v(cls, v):
        v = (v or "").strip().lower()
        if v.startswith("non"):
            return "non couvert"
        if v.startswith("couv"):
            return "couvert"
        return "indéterminé"

    @field_validator("confiance", mode="before")
    @classmethod
    def _c(cls, v):
        v = (v or "").strip().lower()
        return {"low": "faible", "medium": "moyenne", "high": "élevée", "elevee": "élevée"}.get(v, v) \
            if v in ("low", "medium", "high", "elevee", "faible", "moyenne", "élevée") else "faible"

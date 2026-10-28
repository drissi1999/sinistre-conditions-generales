# Sources des données

Uniquement des documents publics, téléchargés depuis le site de chaque assureur. Aucune donnée client.

| contract_id | Assureur | Document | Pages | URL |
|---|---|---|---|---|
| `altima_mrh` | Altima Assurances | Conditions générales Multirisques Habitation (2019-08) | 24 | https://www.altima-assurances.fr/sites/default/files/2019-08/Documents%20contractuels%20B2C/Conditions_Generales%20mrh%20altima.pdf |
| `macsf_mh` | MACSF | Conditions générales Assurance Multirisque Habitation (réf. 01 03 200 Y) | 72 | https://www.espacemembre.macsf.fr/cdn/content/download/7333/file/01%2003%20200%20Y%20CG%20ASSURANCE%20MH.pdf |
| `matmut_jeunes` | Matmut | Conditions générales Habitation Résidence principale - Jeunes | 66 | https://www.matmut.fr/services-en-ligne/doc/CG/CGJEUNES.pdf |

Téléchargés le 2026-10-28.

## Foyer (Luxembourg)

Les conditions générales habitation de Foyer ne sont pas publiées en libre accès : la page
https://foyer.lu/en/general-conditions-help indique qu'il faut saisir son numéro client et son numéro
de police (figurant aux conditions particulières) pour obtenir le PDF. Seule la fiche IPID du produit
Mozaïk est publique (https://foyer.lu/fr/mydoc/12704), mais une IPID de 2 pages résume les garanties
sans les clauses : elle ne permet pas de citer une exclusion. Même constat pour Baloise Luxembourg et
AXA Luxembourg (IPID publiques uniquement). Les contrats retenus sont donc français ; le registre
`data/contracts.yaml` accepte un contrat luxembourgeois sans changement de code.

Écartés : MAPA CG75 (lien mort, 404), contrats algériens/marocains/portugais (autre droit applicable).

# Journal des décisions

Chaque choix technique significatif, l'alternative envisagée et la raison. Format : **Décision** —
alternative — pourquoi.

## Données

**D1. Trois CG françaises publiques (Altima, MACSF, Matmut) plutôt que Foyer.**
Alternative : les CG Foyer. Elles ne sont pas publiques : foyer.lu demande le numéro client et le numéro
de police pour les délivrer, et seule la fiche IPID (2 pages) est en libre accès. Une IPID résume sans
clauses : impossible d'y citer une exclusion. Baloise et AXA Luxembourg : même situation (IPID seules).
Les trois contrats retenus ont des mises en page volontairement différentes (deux colonnes, sommaire de
4 pages, tableaux, puces en police Symbol), ce qui teste réellement le passage à plusieurs contrats.

**D2. PDF et sources versionnés dans le dépôt.**
Alternative : téléchargement au build. Les liens d'assureurs cassent (MAPA renvoie déjà 404) ; la
reproductibilité prime. Données publiques, donc versionnables.

## Parsing

**D3. PyMuPDF plutôt que Docling.**
Docling reconstruit mieux la mise en page et les tableaux, mais il est lourd (PyTorch, modèles de layout),
lent, et ses erreurs sont difficiles à corriger de l'extérieur. PyMuPDF donne pour chaque ligne la police,
la taille, le gras et la position : de quoi détecter titres, colonnes et en-têtes de façon déterministe
et testable. Comme le parsing tourne hors ligne, le poids de Docling n'est pas un problème de
déploiement ; c'est la maîtrise et la testabilité qui décident. Docling reste l'option pour les contrats
très tabulaires ou scannés (avec OCR).

**D4. Un profil de mise en page par modèle de contrat (data/contracts.yaml), pas une heuristique universelle.**
Alternative : une détection générique des titres. Essayée : elle échoue sur l'un ou l'autre des trois
documents (« ART 2.5 » et « ART 2-6 » dans le même contrat, chapitres pleine largeur au milieu de deux
colonnes, sommaire qui ressemble à des titres). Un profil = 5 à 10 lignes de regex. À l'échelle :
des centaines de contrats proviennent de quelques dizaines de modèles (un par assureur et par édition),
donc un profil se réutilise sur tous les contrats du même modèle. En production, un profil serait
proposé automatiquement (LLM sur 3 pages + validation humaine).

**D5. Granularité : la clause = un bloc « Ce que nous garantissons / Ce que nous ne garantissons pas /
Prévention » d'un article.**
Alternatives : chunks de taille fixe (coupent les exclusions en deux, perdent l'article), ou l'article
entier (trop gros pour une citation précise). Découper sur ces intertitres rend chaque exclusion citable
seule, avec un identifiant stable (« Art. 4.7 §2 ») et une page. Chaque clause garde son chemin de
section (« Chap. 4 > Art. 4.7 — VOL »), indexé avec le texte : même idée que la ligne de tableau
qui garde ses en-têtes.

**D6. Lexique : une clause par terme défini, avec table `definitions` dédiée, sans LLM.**
Alternative : laisser le LLM extraire les définitions. Le lexique a une structure régulière (terme en
gras, définition en romain) ; le parser déterministe produit un texte verbatim par construction. Les
définitions sont ensuite injectées dès que leur terme apparaît dans le sinistre (« dépendances »).

**D7. Ordre de lecture deux colonnes par bandes horizontales.**
Trier par (colonne, y) plaçait les titres de chapitre pleine largeur avant la colonne droite qui les
précède. Les lignes qui traversent le milieu de la page coupent la page en bandes, lues colonne par colonne.

## Stockage et extraction

**D8. SQLite, un seul fichier versionné (clauses, définitions, tables extraites, embeddings).**
Alternatives : Postgres + pgvector, base vectorielle dédiée. Pour 3 contrats et une démo déployée sans
infrastructure, un fichier suffit et voyage avec le code. Le schéma se transpose tel quel à Postgres
(pgvector pour les embeddings) quand on passe à des centaines de contrats et plusieurs utilisateurs.

**D9. Extraction structurée une fois par contrat, article par article, chaque ligne citée et vérifiée.**
Alternative : extraire tout le contrat en un appel. Un appel par lot d'articles (~7 000 caractères)
garde le modèle concentré, rend chaque ligne vérifiable sur sa clause, et permet le parallélisme.
Les lignes dont la citation n'est pas retrouvée restent en base avec `review_status = rejete_citation`
et ne sont pas utilisées par le moteur : rien n'est jeté silencieusement, tout est relisible.

**D10. Taxonomie de périls fermée (13 valeurs) partagée par tous les contrats.**
C'est elle qui rend les contrats comparables (« toutes les exclusions vol de tous les contrats » =
une requête SQL). Une valeur inconnue proposée par le modèle est ramenée à « autre » par Pydantic
plutôt que de faire échouer la ligne.

**D11. Idempotence : clé = SHA-256 du PDF + version du prompt d'extraction ; cache disque des réponses LLM.**
Une nouvelle édition du PDF change l'empreinte et déclenche une ré-ingestion du seul contrat concerné ;
un changement de prompt incrémente `PROMPT_VERSION`. Le cache (versionné, données publiques) rend
l'évaluation reproductible et permet à la démo de rejouer les exemples sans appel réseau.

**D12. Indicateurs de qualité d'extraction par colonne (taux de citations vérifiées, taux de remplissage).**
Une colonne remplie à 10 % (ex. franchise, souvent renvoyée aux conditions particulières) n'est pas un
filtre fiable : on la garde pour l'affichage, pas pour décider. Les stats sont stockées dans
`extraction_runs`.

## Réponse à une question

**D13. Le sinistre est d'abord transformé en faits structurés (périls, lieu, effraction, flammes…).**
Ces faits pilotent la requête SQL (par péril) et la recherche, et ils sont calculés une seule fois en
mode comparaison. Un fait non mentionné vaut `null`, ce qui nourrit les questions à poser à l'assuré.

**D14. Recherche hybride BM25 + embeddings, fusion RRF (k = 60), restreinte au contrat.**
BM25 trouve les termes exacts du métier, les embeddings les reformulations (« local à vélos » ~
« locaux à usage commun »). RRF fusionne des classements sans calibrer des scores hétérogènes.
Embeddings : `paraphrase-multilingual-MiniLM-L12-v2` via fastembed (ONNX, 220 Mo, sans PyTorch),
alternative `multilingual-e5-large` (2,2 Go) écartée pour le déploiement gratuit.

**D15. Le contexte n'est pas le top-k : l'article entier de la garantie + exclusions et conditions SQL
+ définitions + exclusions générales.**
Constaté sur Altima : l'exclusion décisive du cas vélo (Art. 4.7 §2, « locaux à usage commun ») n'est
pas dans le top 6 de la recherche hybride, car le texte de la garantie ressemble plus à la question que
celui de l'exclusion. La recherche trouve l'article ; la structure apporte ses exclusions. Budget :
18 000 caractères, par priorité.

**D16. Sortie JSON stricte validée par Pydantic, avec un nouvel essai qui renvoie l'erreur au modèle.**
Les validateurs normalisent ce qui est sans ambiguïté (« Non couvert. » → « non couvert », « high » →
« élevée ») et rejettent le reste.

**D17. Vérification des citations : comparaison normalisée, sans tolérance floue.**
On ignore espaces et retours à la ligne (y compris les espaces que le PDF a perdus : « matérielsdirects »),
casse, apostrophes et tirets typographiques, puces. Pas de distance d'édition : une citation « presque
juste » est une paraphrase, et l'outil ne doit pas la présenter comme le texte du contrat. Fragment
minimal de 12 caractères pour empêcher de « citer » trois mots génériques. Les « […] » sont admis, chaque
fragment devant apparaître dans l'ordre.

**D18. Règle de rétrogradation : une citation introuvable ⇒ verdict « indéterminé », confiance faible.**
Alternative : retirer la citation fautive et garder le verdict. Refusé : si le modèle a inventé une
partie de sa justification, le reste du raisonnement n'est pas fiable non plus. Le verdict d'origine
reste affiché (« le modèle proposait… ») pour la transparence. Aucune citation ⇒ « indéterminé ».

**D19. La page affichée vient de la base, pas du modèle.**
Le modèle ne connaît la page que par le contexte ; la base la connaît sûrement.

## Modèle et déploiement

**D20. Couche LLM « compatible OpenAI » + SDK Anthropic, choix par variables d'environnement.**
Le client compatible OpenAI couvre OpenAI, Mistral (`api.mistral.ai/v1`), les routeurs et les modèles
auto-hébergés (vLLM, Ollama) : changer de fournisseur = changer trois variables. Pour un assureur, l'option
souveraine est Mistral (hébergement UE) ou un modèle ouvert auto-hébergé : les déclarations de sinistre
contiennent des données personnelles.

**D21. Modèle de développement : `qwen/qwen3.8-27b:free` via un routeur.**
Choix de coût (gratuit) pour la démo, pas de qualité. Lent (≈ 2 min par lot d'extraction) mais suffisant
pour suivre les consignes de citation exacte. Les résultats d'évaluation sont indiqués avec le modèle
utilisé ; changer de modèle invalide le cache et nécessite de relancer l'éval.

**D22. Température 0.**
Reproductibilité de l'extraction et de l'évaluation.

**D23. Streamlit Community Cloud, base et cache versionnés.**
Alternative : Hugging Face Spaces (équivalent). Streamlit est le plus court chemin vers une URL publique
pour une interface de ce type. L'application déployée ne fait jamais d'ingestion : elle lit
`contracts.db`.

## Volontairement hors périmètre

- **OCR des contrats scannés** : les trois PDF ont une couche texte. Prévu : Docling ou Tesseract en amont du
  même parser.
- **Écran de revue humaine des lignes extraites** : la colonne `review_status` existe ; l'écran non.
- **Conditions particulières** : non publiques. L'outil le dit dans chaque réponse qui en dépend.
- **Lignes des tableaux de garanties (MACSF p. 11-23)** comme chunks individuels : aujourd'hui une clause
  par page. Prochaine étape : `page.find_tables()` de PyMuPDF, une ligne = un chunk avec ses en-têtes.

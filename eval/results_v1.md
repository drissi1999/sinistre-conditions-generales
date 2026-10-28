Modèle : `qwen/qwen3.8-27b:free` · 16 cas · 1 en erreur

| Indicateur | Résultat |
|---|---|
| Verdict exact (verdict attendu) | 47 % (7/15) |
| Verdict acceptable (attendu ou prudent admis) | 73 % (11/15) |
| Citations vérifiées mot pour mot | 72 % (38/53) |
| Clause attendue citée et vérifiée | 67 % (10/15) |
| « Indéterminé » quand il est attendu | 100 % (2/2) |
| « Indéterminé » sur un cas clair (prudence excessive) | 67 % (8/12) |
| Erreurs affirmées (verdict faux, non « indéterminé ») | 0 % (0/15) |
| Verdicts rétrogradés par la vérification | 2 |

| Cas | Catégorie | Attendu | Obtenu | Citations OK | Clause attendue |
|---|---|---|---|---|---|
| `velo_local_commun_altima` | clair_exclu | non couvert | ✅ non couvert | 2/2 | ✅ |
| `velo_local_commun_macsf` | clair_exclu | non couvert / indéterminé | 🟡 indéterminé | 1/4 | ❌ |
| `velo_local_commun_matmut` | clair_exclu | non couvert | ❌ indéterminé (rétrogradé) | 0/2 | ❌ |
| `bougie_jardin_altima` | clair_exclu | non couvert | ✅ non couvert | 3/3 | ✅ |
| `bougie_jardin_macsf` | clair_exclu | non couvert / indéterminé | 🟡 indéterminé | 3/5 | ❌ |
| `bougie_jardin_matmut` | clair_exclu | non couvert | ✅ non couvert | 3/3 | ✅ |
| `cambriolage_effraction_matmut` | clair_couvert | couvert / indéterminé | 🟡 indéterminé | 4/4 | ✅ |
| `foudre_surtension_matmut` | clair_couvert | couvert | ❌ indéterminé (rétrogradé) | 3/4 | ✅ |
| `fuite_canalisation_altima` | clair_couvert | couvert | ❌ indéterminé | 4/4 | ✅ |
| `vitre_ballon_macsf` | clair_couvert | couvert | ❌ indéterminé | 1/4 | ❌ |
| `vitre_ballon_altima` | clair_couvert | couvert | ✅ couvert | 3/3 | ✅ |
| `fer_a_repasser_matmut` | clair_exclu | non couvert | ERREUR | | |
| `velo_cave_matmut` | clair_exclu | non couvert / indéterminé | 🟡 indéterminé | 4/4 | ✅ |
| `salon_jardin_vole_macsf` | ambigu | indéterminé / non couvert | ✅ indéterminé | 1/4 | ❌ |
| `surtension_lave_linge_altima` | ambigu | indéterminé / couvert | ✅ indéterminé | 3/4 | ✅ |
| `gel_absence_altima` | ambigu | couvert / indéterminé | ✅ couvert | 3/3 | ✅ |

✅ verdict attendu · 🟡 verdict prudent admis · ❌ verdict faux

Modèle : `qwen/qwen3.8-27b:free` · 16 cas · 0 en erreur

| Indicateur | Résultat |
|---|---|
| Verdict exact (verdict attendu) | 81 % (13/16) |
| Verdict acceptable (attendu ou prudent admis) | 100 % (16/16) |
| Citations vérifiées mot pour mot | 96 % (49/51) |
| Clause attendue citée et vérifiée | 94 % (15/16) |
| « Indéterminé » quand il est attendu | 100 % (2/2) |
| « Indéterminé » sur un cas clair (prudence excessive) | 23 % (3/13) |
| Erreurs affirmées (verdict faux, non « indéterminé ») | 0 % (0/16) |
| Verdicts rétrogradés par la vérification | 0 |

| Cas | Catégorie | Attendu | Obtenu | Citations OK | Clause attendue |
|---|---|---|---|---|---|
| `velo_local_commun_altima` | clair_exclu | non couvert | ✅ non couvert | 3/3 | ✅ |
| `velo_local_commun_macsf` | clair_exclu | non couvert / indéterminé | 🟡 indéterminé | 2/3 | ❌ |
| `velo_local_commun_matmut` | clair_exclu | non couvert | ✅ non couvert | 2/2 | ✅ |
| `bougie_jardin_altima` | clair_exclu | non couvert | ✅ non couvert | 4/4 | ✅ |
| `bougie_jardin_macsf` | clair_exclu | non couvert / indéterminé | 🟡 indéterminé | 4/4 | ✅ |
| `bougie_jardin_matmut` | clair_exclu | non couvert | ✅ non couvert | 4/4 | ✅ |
| `cambriolage_effraction_matmut` | clair_couvert | couvert / indéterminé | ✅ couvert | 4/4 | ✅ |
| `foudre_surtension_matmut` | clair_couvert | couvert | ✅ couvert | 3/3 | ✅ |
| `fuite_canalisation_altima` | clair_couvert | couvert | ✅ couvert | 4/4 | ✅ |
| `vitre_ballon_macsf` | clair_couvert | couvert | ✅ couvert | 2/2 | ✅ |
| `vitre_ballon_altima` | clair_couvert | couvert | ✅ couvert | 2/2 | ✅ |
| `fer_a_repasser_matmut` | clair_exclu | non couvert | ✅ non couvert | 3/3 | ✅ |
| `velo_cave_matmut` | clair_exclu | non couvert / indéterminé | 🟡 indéterminé | 4/4 | ✅ |
| `salon_jardin_vole_macsf` | ambigu | indéterminé / non couvert | ✅ indéterminé | 3/3 | ✅ |
| `surtension_lave_linge_altima` | ambigu | indéterminé / couvert | ✅ indéterminé | 2/3 | ✅ |
| `gel_absence_altima` | ambigu | couvert / indéterminé | ✅ couvert | 3/3 | ✅ |

✅ verdict attendu · 🟡 verdict prudent admis · ❌ verdict faux

# Kalibreringsbotar

Huvudlösa genomspelningar som ger siffrorna under "Kalibrering" i CLAUDE.md. De är inga tester.
De körs för hand från repots rot efter en medveten ändring av kalibreringen:

```bash
uv run python kalibrering/ja_bot.py ovning-kort,konvoj-kort 8
```

Varje skript beskriver sina argument överst i filen. Botarna är flyttade hit som de var i
scratchpad (2026-11-14–15). En del läser sanningen (`sundet.py --orakel`, `sundet_folj.py` utan
`--följ`). Sådana värden mäter bara scenariot, inte vad besättningen klarar.

| Skript | Scenario | Botar |
|---|---|---|
| `ja_bot.py` | alla (kommaseparerade) | ja-boten, parallellt |
| `ovning.py` | ovning | ja-boten: tid, grund, bestickfel |
| `ovning_lyssna.py` | ovning | lyssningens längd, partnerns svar |
| `ovning_torped.py` | ovning, ovning-kort | ja + skjuter övningstorped |
| `jagad.py` | jagad (`--scen=` annat) | ja, `--passiv`, `--taktisk`, `--sprint` |
| `jagad_djupt.py` | jagad | djupt och fort längs navigatörens väg ut |
| `jagad_kort.py` | jagad-kort | passiv, ja, fast |
| `kuba_kort.py` | kuba-kort | passiv, ja |
| `kuba_flyg.py` | kuba | ja; flygets och jagarens kontakter |
| `kuba_jakt.py` | kuba | ja över 12 frön: upptäckt, sjunkbomber |
| `sundet.py` | sundet | besättningens verktyg, `--ja`, `--orakel` |
| `sundet_folj.py` | sundet | grindtricket (`--följ` = besättningens verktyg) |
| `sundet_in.py` | sundet-in | passiv, ja, grind |
| `sundet_ut.py` | sundet-ut | passiv, ja, ut |
| `konvoj.py` | konvoj | passiv, ja, attack |
| `konvoj_salva.py` | konvoj, konvoj-kort | ja + salva mot stora fartyg |
| `konvoj_mot.py` | konvoj-mot | passiv, ja, bort |
| `arktis.py` | arktis | ja |
| `arktis_kort.py` | arktis-kort | passiv, ja |
| `tma_kvalitet.py` | flera | ja; plottets lösningar mot sanningen per kvalitet |

Provkörda 2026-11-15 med ett frö var. Alla gick utan fel. `konvoj.py` och `kuba_jakt.py`
kördes bara 45 s utan fel, eftersom de har fasta frön och tar lång tid.

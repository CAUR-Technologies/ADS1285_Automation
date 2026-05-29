# CLAUDE.md

## Matériel : APS 0109 Position Controller (SPEKTRA)

### Liaison série
- Baud : **19200**, 8 bits, parité aucune, 1 stop
- Terminaison de commande : `\x00` (octet nul)
- **Format de réponse (confirmé matériel, fw 1.02.01)** : `<commande> <valeur> OK`,
  terminée par `\x00`. Exemples :
  - `FWV?\x00` → `FWV? 1.02.01 OK`
  - `SER?\x00` → `SER? 209 OK`
  - `ZER?\x00` → `ZER? 0 OK`
  - commandes de réglage sans valeur → `<commande> OK`
- **Erreur** : la réponse contient le token `ERR` (détail via `GES`).
- ⚠️ La réponse **n'est PAS** « COMMANDE OK » (erreur d'une version antérieure
  de ce doc). Le driver extrait la valeur entre l'écho de commande et `OK`.

### Commandes RS232

| Commande | Description | Syntaxe | Plage |
|----------|-------------|---------|-------|
| ZER      | Set zero position | `ZER <val>\x00` | -99..99 |
| ZER?     | Get zero position | `ZER?\x00` | — |
| STF      | Set stiffness | `STF <val>\x00` | 0..31 |
| STF?     | Get stiffness | `STF?\x00` | — |
| STA      | Start controller | `STA\x00` | — |
| STA?     | Get start status (1=started) | `STA?\x00` | — |
| STP      | Stop controller | `STP\x00` | — |
| STP?     | Get stop status | `STP?\x00` | — |
| FWV?     | Get firmware version | `FWV?\x00` | — |
| RST      | Full reset (⚠️ perte config) | `RST\x00` | — |
| GES      | Get last error string | `GES\x00` | — |
| SER?     | Get serial number | `SER?\x00` | 0..65535 |
| OTT      | Set overtravel tolerance | `OTT <val>\x00` | 0..1023 |
| OTT?     | Get overtravel tolerance | `OTT?\x00` | — |
| PMA      | Set position max (LED) | `PMA <val>\x00` | 0..1023 |
| PMA?     | Get position max | `PMA?\x00` | — |
| PMI      | Set position min (LED) | `PMI <val>\x00` | 0..1023 |
| PMI?     | Get position min | `PMI?\x00` | — |
| SRV      | Set service mode | `SRV <val>\x00` | 0..1 |
| SRV?     | Get service mode | `SRV?\x00` | — |
| SSS      | Set stiffness start value | `SSS <val>\x00` | 0..31 |
| SSS?     | Get stiffness start value | `SSS?\x00` | — |
| WTR      | Set wait time ramping (ms = val×10+3500) | `WTR <val>\x00` | 0..1000 |
| WTR?     | Get wait time ramping | `WTR?\x00` | — |

### Codes d'erreur (GES)
- `no_error`
- `value_out_of_range`
- `unknown_command`
- `CRC_ERROR`
- `Overtravel_TOP`
- `Overtravel_Bottom`

### Note APS 125
Pas d'interface série propre. Contrôlé indirectement via l'APS 0109 (signaux SPC).
Menu 31=1 (activer RS232), Menu 33=1 (surveillance amplificateur).
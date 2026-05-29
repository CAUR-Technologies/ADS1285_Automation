# CLAUDE.md

## Matériel : Wavetek Model 39A — Générateur de fonction / arbitraire 40 MS/s

> ⚠️ Le 39A n'utilise **PAS** le SCPI. Les commandes ci-dessous proviennent du
> manuel opérateur (réf. 1463827, sections Remote Commands p.68-78). Une version
> antérieure de ce fichier supposait à tort du SCPI (`FUNC`/`FREQ`/`VOLT`/`OUTP`)
> — ces mnémoniques sont rejetées (bip « Command Error ») par l'appareil.

### Liaison série (RS232)
- Baud : **9600 maximum**, variable (réglé sur l'appareil)
- Format : 8 bits, parité aucune, 1 stop
- **Handshaking XON/XOFF requis** (`xonxoff=True`)
- Connecteur 9 broches : TXD=2, RXD=3, GND=5 (mode non-adressable, 3 fils)
- **Terminateur de commande : LF (0Ah)** ; le CR (0Dh) est ignoré
- Réponse : terminée par **CR LF** (0Dh 0Ah)
- Séparateur de commandes multiples : `;`
- Commandes insensibles à la casse ; bit 7 ignoré

### Pré-requis côté appareil
Sur l'écran **REMOTE SETUP** (touche UTILITY → remote) :
- `interface: RS232`
- `baud rate: 9600`
- En 3 fils (TXD/RXD/GND) l'appareil est en mode **non-adressable** : on envoie
  les commandes directement, sans séquence d'adressage.

### Commandes utilisées par le driver

| Fonction | Commande | Exemple |
|----------|----------|---------|
| Forme d'onde | `WAVE <cpd>` | `WAVE SINE` |
| Fréquence (Hz) | `WAVFREQ <nrf>` | `WAVFREQ 10.0` |
| Période (s) | `WAVPER <nrf>` | `WAVPER 0.1` |
| Unité d'amplitude | `AMPUNIT <cpd>` | `AMPUNIT VPP` |
| Amplitude | `AMPL <nrf>` | `AMPL 1.0` |
| Charge supposée | `ZLOAD <cpd>` | `ZLOAD OPEN` (hiZ) ou `TERM` (50Ω) |
| Offset DC (V) | `DCOFFS <nrf>` | `DCOFFS 0.0` |
| Sortie | `OUTPUT <cpd>` | `OUTPUT ON` / `OUTPUT OFF` |
| Mode | `MODE <cpd>` | `MODE CONT` |
| Identification | `*IDN?` | → `<NAME>,<model>,0,<version>` |
| Reset défauts | `*RST` | |
| Bip | `BEEP` | |
| Retour local | `LOCAL` | |

### Mnémoniques de forme d'onde (`WAVE`)
`SINE`, `SQUARE`, `TRIANG`, `DC`, `POSRMP` (rampe +), `NEGRMP` (rampe −),
`COSINE`, `HAVSIN`, `HAVCOS`, `SINC`, `PULSE`, `PULSTRN`, `ARB`, `SEQ`.

> Pas de forme d'onde « noise ». triangle = `TRIANG`, rampe = `POSRMP`/`NEGRMP`.

### Plages (Specifications)
| Paramètre | Plage |
|-----------|-------|
| Fréquence (sinus) | 0,1 mHz – 16 MHz |
| Amplitude | 5 mV – 20 Vpp circuit ouvert (2,5 mV – 10 Vpp sur 50 Ω) |
| Offset DC | ±10 V (offset + crête signal ≤ ±10 V) |

### Codes d'erreur / diagnostic
- Une commande non comprise → **bip** + message « Command Error » (bit 5 du
  Standard Event Status Register). Si chaque commande bipe → mauvais mnémonique
  (SCPI au lieu du protocole natif) ou appareil pas en mode RS232.
- `*IDN?` sans réponse → vérifier interface RS232 sélectionnée, baud, terminateur.

### Notes de conception
1. Délai de stabilisation ~100 ms après changement de fréquence avant acquisition.
2. Les commandes de réglage ne renvoient rien ; seules les query (`?`) répondent.
3. XON/XOFF : l'appareil envoie XOFF quand sa file de 256 octets se remplit.

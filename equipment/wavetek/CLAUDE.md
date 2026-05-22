# CLAUDE.md

## Matériel : Wavetek Model 39A — Générateur de fonction

### Liaison série
- Baud : 9600 (configurable)
- Bits start/stop : 1/1
- Parité : aucune
- Data bits : 8
- Terminaison : `\r\n` (CRLF)
- Echo : dépend du mode instrument

### Protocole SCPI-like

La Wavetek 39A utilise un protocole basé sur SCPI (Standard Commands for Programmable Instruments) avec syntaxe `COMMANDE [paramètre]`.

#### Formes d'onde supportées

```
SINE      → Sinusoïde
SQUARE    → Carré
TRIANGLE  → Triangle
RAMP      → Rampe
PULSE     → Impulsion
NOISE     → Bruit blanc
DC        → Tension continue
```

### Commandes principales

| Commande | Format | Description | Exemple |
|----------|--------|-------------|---------|
| **FUNC** | `FUNC <WAVEFORM>` | Sélectionne la forme d'onde | `FUNC SINE` |
| **FREQ** | `FREQ <value>` | Fréquence en Hz | `FREQ 1000.0` |
| **VOLT** | `VOLT <value> VPP` | Amplitude en Volts peak-to-peak | `VOLT 2.5 VPP` |
| **VOLT:OFFS** | `VOLT:OFFS <value>` | Offset DC en Volts | `VOLT:OFFS 0.5` |
| **OUTP** | `OUTP ON\|OFF` | Sortie activée/désactivée | `OUTP ON` |
| **\*IDN?** | `*IDN?` | Identification (query) | → `Wavetek 39A` |
| **\*RST** | `*RST` | Réinitialise l'instrument | `*RST` |

### Exemple de séquence type

```python
with Wavetek39A() as gen:
    # Identification
    id_str = gen.identify()  # → "*IDN?\"
    
    # Configuration
    gen.set_waveform("sine")           # Sinusoïde
    gen.set_frequency(10.0)             # 10 Hz
    gen.set_amplitude(1.5)              # 1.5 Vpp
    gen.set_offset(0.0)                 # Pas d'offset
    
    # Activation
    gen.enable_output()                 # Sortie ON
    
    # ... mesures/acquisition ...
    
    # Désactivation
    gen.disable_output()                # Sortie OFF
    
    # Réinitialisation
    gen.reset()                         # État par défaut
```

### Plages typiques

| Paramètre | Min | Max | Unité | Notes |
|-----------|-----|-----|-------|-------|
| Fréquence | 0.1 | 10 000 | Hz | Dépend de la forme d'onde |
| Amplitude | 0 | 10 | Vpp | Amplitude crête-à-crête |
| Offset | -5 | +5 | V | Décalage DC autour de 0V |
| Duty cycle | 10 | 90 | % | Pour SQUARE, PULSE, RAMP |

### Notes de conception

1. **Délai de stabilisation** : Après changement de fréquence, ajouter un délai (≈100ms) avant acquisition
2. **Réponse query** : Les commandes avec `?` retournent une valeur (ex: `FREQ?` → `1000.000`)
3. **Echo** : L'instrument peut renvoyer l'écho de la commande reçue (configurable en menu)
4. **Timeout** : Prévoir un timeout série suffisant (≥200ms) pour les réponses
5. **Initialisation** : Toujours utiliser `*RST` avant une nouvelle séquence si état initial inconnu

### Codes d'erreur

L'instrument n'a pas de système d'erreur formel SCPI. Les problèmes courants :
- Syntaxe invalide : aucune réponse ou écho seul
- Valeur hors plage : peut être acceptée avec saturation
- Port fermé : `RuntimeError` levée par la classe

### Intégration typique

```python
from equipment.wavetek import Wavetek39A

# Configuration d'un balayage fréquentiel
frequencies = [1, 2, 5, 10, 20, 50, 100, 200]

with Wavetek39A() as gen:
    gen.set_waveform("sine")
    gen.set_amplitude(1.0)
    
    for freq in frequencies:
        gen.set_frequency(freq)
        time.sleep(0.5)  # Stabilisation
        # ... acquisition ...
    
    gen.disable_output()
```

### Ressources

- Manuel Wavetek 39A : Consulter le datasheet constructeur
- Documentation SCPI : https://www.ivifoundation.org/
- Protocole : Standard SCPI simplifié pour fonction generators

Le rôle de chaque signal
Le signal du Wavetek passe à travers l'APS 0109 — il ne le génère pas. Le chemin du signal est :
Wavetek → [Signal In APS 0109] → [Signal Out] → APS 125 → Shaker
                    ↑
              APS 0109 ajoute
              un offset DC
L'APS 0109 superpose une tension DC de correction au signal AC du Wavetek pour maintenir l'armature centrée.

La relation position ↔ fréquence
Pour un mouvement sinusoïdal, les trois grandeurs physiques sont liées mathématiquement :
x(t) = A · sin(2πft)          → déplacement
v(t) = A·2πf · cos(2πft)      → vitesse  
a(t) = -A·(2πf)² · sin(2πft) → accélération
Ce qui donne, pour une accélération constante (cas typique de calibration) :
A = a / (2πf)²
En pratique pour le shaker APS : le déplacement est inversement proportionnel au carré de la fréquence. Voici ce que ça donne concrètement :
FréquenceDéplacement crête (pour 1g d'accélération)0,1 Hz≈ 2,5 m (impossible → limite mécanique)1 Hz≈ 25 mm5 Hz≈ 1 mm10 Hz≈ 0,25 mm50 Hz≈ 10 µm100 Hz≈ 2,5 µm
C'est pourquoi la fréquence basse est le cas critique pour le contrôleur de position.

Le problème fondamental à basse fréquence
À très basse fréquence, le mouvement du shaker est lent et ample. Le contrôleur APS 0109, qui surveille la position, risque de confondre la vibration voulue avec une dérive de position et tenter de la corriger — ce qui annulerait le mouvement.
Fréquence test trop proche
de la bande du contrôleur
        ↓
Contrôleur "voit" la vibration
comme une erreur de position
        ↓
Il injecte un DC offset croissant
pour "ramener" l'armature
        ↓
Le mouvement est atténué ou
l'armature sature en butée

Le paramètre Stiffness comme solution
La Stiffness (réglage physique + commande STF) contrôle directement la bande passante de la boucle de régulation de position. C'est le paramètre clé qui découple le contrôle de position du signal de vibration :
Stiffness élevée → bande passante large → correction rapide
                → risque d'interférer avec le signal de test

Stiffness faible → bande passante étroite → correction lente
                → n'interfère pas avec la vibration
                → mais moins résistant aux charges asymétriques
La règle issue du manuel : pour des fréquences < 10 Hz, utiliser une stiffness plus faible. En pratique pour la calibration de géophones :
Plage de fréquences ANTStiffness recommandée0,1 – 1 Hz1 à 5 (très faible)1 – 10 Hz5 à 1510 – 50 Hz15 à 25> 50 Hz25 à 31

La règle d'or de séparation des fréquences
Pour que le système fonctionne correctement, il faut respecter une séparation d'au moins une décade entre la fréquence de coupure du contrôleur et la fréquence de test :
f_contrôleur ≪ f_test

Exemple pour tester à 1 Hz :
→ Stiffness faible = bande passante contrôleur ≈ 0,05 Hz
→ Le contrôleur ne "voit" que la dérive DC lente
→ Le signal à 1 Hz passe librement

Ce que ça implique pour votre séquence de sweep géophone
Pour un sweep logarithmique 0,1 → 100 Hz, il faudra idéalement adapter la stiffness dynamiquement en cours de sweep, ou choisir un compromis fixe :
python# Exemple de logique d'adaptation
if freq < 1.0:
    aps0109.set_stiffness(3)    # STF 3
elif freq < 10.0:
    aps0109.set_stiffness(10)   # STF 10
else:
    aps0109.set_stiffness(20)   # STF 20
Notez qu'à chaque changement de stiffness, l'APS 0109 doit stabiliser la position zéro avant de reprendre le signal — il faut donc prévoir un temps d'attente (lié au paramètre WTR).

Le lien physique : déplacement ↔ fréquence ↔ position zéro
Pour un mouvement sinusoïdal à accélération constante a :
A(f) = a / (2πf)²
Le shaker oscille entre −A et +A autour de la position zéro. Si le zéro n'est pas parfaitement centré, l'armature atteint la butée d'un côté avant l'autre :
     ←—— stroke max ——→
     |                 |
  −S_max    ZER=0    +S_max
               ↕ A
          [−A ... +A]   ← OK, symétrique

     |                 |
  −S_max   ZER≠0    +S_max
                  ↕ A
               [ZER−A ... ZER+A]  ← risque overtravel d'un côté
La contrainte fondamentale est donc :
|ZER_physique| + A(f) ≤ S_max

Trouver la bonne valeur de ZER expérimentalement
La méthode la plus fiable est une procédure de centrage en deux étapes :
Étape 1 — Centrage statique (sans signal)
python# 1. Démarrer l'APS 0109 sans signal du Wavetek
aps.start()                  # STA

# 2. Lire la position actuelle via les menus 42/43/44
#    (ou surveiller les LEDs du panneau avant)
# 3. Ajuster ZER jusqu'à ce que le bargraphe soit centré
aps.set_zero(0)              # ZER 0  → commencer au centre mécanique
# Ajuster par pas de 1 jusqu'à centrage parfait
Étape 2 — Vérification dynamique à la fréquence de test
pythonimport numpy as np

def check_safe_operation(freq_hz, accel_g, s_max_mm, zer_value):
    """
    freq_hz   : fréquence du Wavetek (Hz)
    accel_g   : accélération cible (g)
    s_max_mm  : demi-stroke max du shaker (mm) ex: 38 pour APS 113
    zer_value : valeur ZER actuelle (-99 à 99)
    """
    g = 9.81  # m/s²
    a = accel_g * g * 1000  # mm/s²
    
    # Déplacement crête en mm
    A = a / (2 * np.pi * freq_hz) ** 2
    
    # Offset physique approximatif du ZER
    # ZER ±99 ≈ ±10% de S_max (selon manuel)
    zer_mm = (zer_value / 99) * (0.10 * s_max_mm)
    
    # Marge disponible de chaque côté
    margin_plus  = s_max_mm - (zer_mm + A)
    margin_minus = s_max_mm - (-zer_mm + A)
    
    return {
        'displacement_mm': A,
        'zer_offset_mm': zer_mm,
        'margin_plus_mm': margin_plus,
        'margin_minus_mm': margin_minus,
        'safe': margin_plus > 0 and margin_minus > 0
    }

# Exemple pour APS 113 (stroke ±38 mm)
result = check_safe_operation(
    freq_hz=1.0, 
    accel_g=0.1,    # 0.1g → raisonnable à basse fréquence
    s_max_mm=38, 
    zer_value=0
)
print(result)
# {'displacement_mm': 24.8, 'zer_offset_mm': 0.0, 
#  'margin_plus_mm': 13.2, 'margin_minus_mm': 13.2, 'safe': True}

Courbe pratique : ZER max toléré selon la fréquence
Pour 0,1g d'accélération sur APS 113 (stroke ±38 mm), voici l'espace disponible pour un offset ZER :
Fréq (Hz)  | Déplacement A | Marge pour ZER offset
-----------+---------------+----------------------
  0.1 Hz   |   248 mm      | IMPOSSIBLE (> stroke)
  0.5 Hz   |    10 mm      | ZER doit être ≈ 0
  1.0 Hz   |    25 mm      | ZER très proche de 0
  5.0 Hz   |    1.0 mm     | ZER peut varier légèrement
 10.0 Hz   |    0.25 mm    | ZER peu critique
 50.0 Hz   |    0.01 mm    | ZER non critique

La procédure de calibration automatisée
Pour un sweep géophone, voici la logique à implémenter dans votre code :
pythondef find_optimal_zer(aps, wavetek, target_freq, target_accel_g, 
                     s_max_mm=38, n_cycles=10):
    """
    Trouve le ZER optimal pour une fréquence et accélération données.
    Procédure :
    1. Arrêter le signal
    2. Centrer statiquement
    3. Appliquer le signal à faible amplitude
    4. Lire les limites overtravel PMA/PMI
    5. Ajuster ZER pour symétriser
    """
    
    # 1. Vérifier si la fréquence est physiquement réalisable
    info = check_safe_operation(target_freq, target_accel_g, s_max_mm, 0)
    if not info['safe']:
        raise ValueError(
            f"Impossible à {target_freq} Hz / {target_accel_g}g : "
            f"déplacement {info['displacement_mm']:.1f} mm > stroke {s_max_mm} mm"
        )
    
    # 2. Partir du centre
    aps.set_zero(0)           # ZER 0
    
    # 3. Appliquer signal à 10% de l'amplitude cible
    wavetek.set_frequency(target_freq)
    wavetek.set_amplitude(target_accel_g * 0.1)
    wavetek.output_on()
    
    # 4. Attendre stabilisation (WTR + n_cycles)
    wait_time = (1 / target_freq) * n_cycles
    time.sleep(wait_time)
    
    # 5. Lire les positions extrêmes mesurées
    pos_max = aps.query('PMA?')   # lecture via RS232
    pos_min = aps.query('PMI?')
    
    # 6. Calculer le déséquilibre et corriger
    asymmetry = (pos_max + pos_min) / 2  # devrait être ≈ 0
    if abs(asymmetry) > 5:               # seuil en unités ADC
        correction = int(-asymmetry / 10)
        aps.set_zero(correction)          # ZER <correction>
    
    # 7. Monter progressivement à l'amplitude cible
    for level in [0.25, 0.5, 0.75, 1.0]:
        wavetek.set_amplitude(target_accel_g * level)
        time.sleep(wait_time)
        # Vérifier qu'on ne déclenche pas les limites OTT
        error = aps.query('GES')
        if 'Overtravel' in error:
            raise RuntimeError(f"Overtravel détecté à {level*100}% de l'amplitude")
    
    return aps.query('ZER?')   # retourner la valeur ZER finale optimale

Résumé pratique
La valeur ZER optimale en fonction de la fréquence suit cette logique :

< 1 Hz → ZER doit être exactement 0 (centrage critique), réduire l'accélération
1–10 Hz → ZER ≈ 0, vérifier expérimentalement via PMA?/PMI?
> 10 Hz → ZER peu critique, la marge est large

En pratique, ZER reste à 0 pour la grande majorité des tests — c'est la charge statique asymétrique (poids du géophone en vertical) qui nécessite une valeur non nulle, pas la fréquence elle-même.Vous avez dit : Donc, avec un shaker APS 113, c'est impossible de faire vibrer à 0.




La vraie contrainte : le triangle fréquence / amplitude / déplacement
Le shaker peut opérer à n'importe quelle fréquence dans sa plage, tant que le déplacement résultant reste dans sa limite mécanique :
A(f) = a / (2πf)²  ≤  S_max
Pour l'APS 113 (stroke ±38 mm), voici ce qui est réellement possible :
FréquenceAccél. max dans le strokeAccél. max en g0,1 Hz0,015 m/s²0,0015 g0,5 Hz0,375 m/s²0,038 g1 Hz1,5 m/s²0,15 g5 Hz37 m/s²3,8 g10 Hz150 m/s²15 g
À 0,1 Hz vous pouvez donc vibrer, mais uniquement jusqu'à 1,5 mg d'accélération.

Bonne nouvelle pour la calibration de géophones
C'est en réalité parfaitement adapté à votre application ANT. Les géophones sont des capteurs très sensibles, conçus pour mesurer de très faibles accélérations. À 0,1 Hz, 1,5 mg est généralement largement suffisant pour les exciter et mesurer leur réponse.
La contrainte réelle à gérer dans votre code est donc de calculer l'amplitude maximale admissible pour chaque fréquence :
pythondef max_accel_for_freq(freq_hz, s_max_mm=38):
    """Accélération crête max (en g) pour rester dans le stroke."""
    s_max_m = s_max_mm / 1000
    a_max = s_max_m * (2 * np.pi * freq_hz) ** 2
    return a_max / 9.81  # en g

# Envelope complète pour un sweep
freqs = np.logspace(-1, 2, 200)  # 0.1 à 100 Hz
a_max = [max_accel_for_freq(f) for f in freqs]
Ce qui donne cette enveloppe d'opération :
Accél (g)
  10  |                                    ___________
      |                               ____/
   1  |                          ____/
      |                     ____/
  0.1 |                ____/
      |           ____/
 0.01 |      ____/
      | ____/
0.001 |/________________________
      0.1    1     10    100  Hz
                ↑
         Zone de calibration géophone ANT
Pour un sweep de calibration propre, votre code devrait adapter l'amplitude du Wavetek à chaque fréquence pour rester à une fraction constante de cette enveloppe — typiquement 50 à 70% du maximum pour garder une marge de sécurité.
"""
Génère le rapport de calibration des géophones horizontaux au format Word
(.docx), en-tête société GDD Instrumentation + logo.

Réutilise les figures produites par tools/rapport_geophones.py.
Sortie : data/rapport_geophones_H_2026-05-28/Rapport_calibration_geophones_H.docx

Lancer :  python tools/rapport_geophones_docx.py
"""

import os
import sys

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REP = os.path.join(DATA, "rapport_geophones_H_2026-05-28")
FIG = os.path.join(REP, "figures")
LOGO = os.path.join(ROOT, "Documents", "gdd-logo1.png")
OUT = os.path.join(REP, "Rapport_calibration_geophones_H.docx")

BLUE = RGBColor(0x1B, 0x4E, 0x8C)      # bleu GDD pour les titres
GREY = RGBColor(0x55, 0x55, 0x55)


def fig(name):
    return os.path.join(FIG, name)


# ----------------------------------------------------------------- document
doc = Document()

# Police par défaut
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(10.5)

# Couleur des titres
for lvl in ("Heading 1", "Heading 2", "Heading 3", "Title"):
    try:
        doc.styles[lvl].font.color.rgb = BLUE
    except KeyError:
        pass


# En-tête (logo + société) sur chaque page
sec = doc.sections[0]
sec.top_margin = Cm(2.2)
sec.bottom_margin = Cm(2.0)
sec.left_margin = Cm(2.2)
sec.right_margin = Cm(2.2)

hp = sec.header.paragraphs[0]
hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
run = hp.add_run()
if os.path.exists(LOGO):
    run.add_picture(LOGO, height=Cm(1.05))
r2 = hp.add_run("    Instrumentation GDD inc.")
r2.bold = True
r2.font.size = Pt(11)
r2.font.color.rgb = BLUE

# Pied de page
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr = fp.add_run("Instrumentation GDD inc.  ·  Rapport de calibration de géophones  ·  "
                "Confidentiel")
fr.font.size = Pt(8)
fr.font.color.rgb = GREY


def heading(text, level=1):
    h = doc.add_heading(text, level=level)
    for r in h.runs:
        r.font.color.rgb = BLUE
    return h


def para(text, *, italic=False, bold=False, size=None, color=None, align=None,
         mono=False):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    r = p.add_run(text)
    r.italic = italic
    r.bold = bold
    if mono:
        r.font.name = "Consolas"
        r.font.size = Pt(8.5)
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    return p


def bullet(text):
    return doc.add_paragraph(text, style="List Bullet")


def numbered(text):
    return doc.add_paragraph(text, style="List Number")


def table(headers, rows, *, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        rr = hdr[i].paragraphs[0].add_run(h)
        rr.bold = True
        rr.font.size = Pt(9.5)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            rr = cells[i].paragraphs[0].add_run(str(v))
            rr.font.size = Pt(9.5)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = w
    doc.add_paragraph()
    return t


def figure(name, caption, width_cm=16.0):
    path = fig(name)
    if not os.path.exists(path):
        para(f"[figure manquante : {name}]", italic=True, color=GREY)
        return
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cr = cap.add_run(caption)
    cr.italic = True
    cr.font.size = Pt(8.5)
    cr.font.color.rgb = GREY


# =============================================================== PAGE DE TITRE
title = doc.add_heading("Rapport de calibration", level=0)
for r in title.runs:
    r.font.color.rgb = BLUE
sub = para("Géophones horizontaux — Banc de caractérisation ANT",
           bold=True, size=14)
sub.alignment = WD_ALIGN_PARAGRAPH.LEFT
para("Axe horizontal  ·  Données du 2026-05-28", color=GREY, size=11)
para("Géophones testés : HG-6 HB · VAS-H-200 · ST-2A (H)", size=11)
para("Application : étalonnage de géophones pour l'Ambient Noise Tomography (ANT)",
     italic=True, color=GREY, size=10)
doc.add_paragraph()

# =============================================================== 1. RÉSUMÉ
heading("1. Résumé exécutif", 1)
para("Trois géophones horizontaux ont été caractérisés en fréquence (0,1–50 Hz) "
     "sur le banc shaker. La chaîne complète — Wavetek → APS 0109/125 → shaker "
     "APS 113 → accéléromètre de référence Silicon Designs ; géophone numérisé "
     "par l'ADS1285 EVM — fonctionne et fournit des fonctions de transfert "
     "exploitables sur la bande utile.")
table(
    ["Géophone", "Bande fiable", "Sensibilité plateau mesurée", "Spec datasheet", "Verdict"],
    [
        ["ST-2A (H)", "2–50 Hz (5 pts)", "265 V/(m/s)", "260 V/(m/s)", "+2 % — excellent"],
        ["HG-6 HB", "1–50 Hz (5 pts)", "36 V/(m/s)", "28,8 V/(m/s)", "+24 % — cohérent (tolérance unité)"],
        ["VAS-H-200", "5–50 Hz (3 pts)", "≥ 129 V/(m/s) (non plafonné)", "220 V/(m/s)", "anomalie — coupure trop haute"],
    ],
)
para("Résultat marquant : la sensibilité du ST-2A (H) mesurée par le banc "
     "(265 V/(m/s)) coïncide à 2 % près avec la valeur datasheet (260 V/(m/s)). "
     "Cette concordance absolue valide toute la chaîne métrologique (calibration "
     "de l'accéléromètre de référence, conversion counts→volts de l'ADS1285, et "
     "conversion accélération→vitesse). Le VAS-H-200 présente en revanche une "
     "réponse qui continue de monter jusqu'à 50 Hz sans atteindre son plateau : "
     "sa fréquence de coupure effective est bien plus haute que les 4,5 Hz "
     "annoncés — à investiguer.")

# =============================================================== 2. CONDITIONS
heading("2. Conditions du run", 1)
table(
    ["Paramètre", "Valeur"],
    [
        ["Axe", "Horizontal"],
        ["Gain ampli APS 125 (H)", "50"],
        ["Limite de courant APS 125 (H)", "50"],
        ["Plancher de bruit (accél. réf., H)", "0,57 mg RMS"],
        ["Échantillonnage géophone (ADS1285)", "1000 éch/s, 1024 points (1,024 s)"],
        ["Échantillonnage accél. réf. (NI)", "10 000 éch/s, 10 240 points"],
        ["Fréquences balayées", "0,1 / 0,2 / 0,5 / 1 / 2 / 5 / 10 / 20 / 50 Hz"],
    ],
)
para("Note : l'axe vertical est hors service (étage de puissance de l'APS 125 "
     "vertical endommagé) ; seules les chaînes horizontales sont opérationnelles. "
     "Ce rapport ne couvre donc que l'axe H.", italic=True, color=GREY)

# =============================================================== 3. MÉTHODOLOGIE
heading("3. Méthodologie", 1)

heading("3.1 Chaîne de mesure", 2)
para(
    "Wavetek 39A -> APS 0109 (position) -> APS 125 (ampli) -> shaker APS 113\n"
    "                                                |-> accéléromètre réf. (NI) -> a_table(f) [g]\n"
    "                                                |-> géophone (DUT) -> ADS1285 EVM -> counts(f)",
    mono=True)
para("Le banc impose une accélération mécanique connue (mesurée en temps réel par "
     "l'accéléromètre de référence Silicon Designs 2240-005, 800 mV/g, via la "
     "carte NI USB-6221). Le géophone, monté sur la même armature, voit la même "
     "excitation ; sa sortie est numérisée par l'ADS1285 (ADC 32 bits, ±2,5 V "
     "crête à gain 1).")

heading("3.2 Mesure en deux étapes", 2)
numbered("Fonction de transfert du banc  H_banc(f) = a_table(f) / V_wavetek(f) "
         "[g/V] — caractérise la réponse électromécanique de la chaîne (sans "
         "géophone monté).")
numbered("Sensibilité du géophone : à chaque point, on calcule directement le "
         "rapport S(f) = counts_crête(f) / a_table(f) [counts/g], où a_table est "
         "l'accélération réellement mesurée par l'accéléromètre de référence. La "
         "sensibilité du géophone est donc indépendante de la forme de H_banc : "
         "l'accéléromètre de référence est la grandeur de comparaison.")

heading("3.3 Conversion en réponse vitesse", 2)
para("Un géophone est un capteur de vitesse, alors que le banc impose une "
     "accélération. Pour un sinus, v = a/(2πf), d'où :")
para("S_v [counts/(m/s)] = S_g [counts/g] · 2πf / g        (g = 9,80665 m/s²)",
     italic=True, bold=True)
para("Cette conversion retire le facteur 1/f artificiel et révèle la vraie "
     "réponse du géophone : plate au-dessus de la fréquence propre f0, en "
     "roll-off f² en dessous.")

heading("3.4 Modèle du géophone (2ᵉ ordre)", 2)
para("|S_v(f)| = G0 · r² / √[(1−r²)² + (2ζr)²]   avec r = f/f0",
     italic=True, bold=True)
para("G0 = sensibilité de bande plate (asymptote HF), f0 = fréquence propre, "
     "ζ = amortissement. Pour ζ < 1/√2 ≈ 0,707 (sous-amorti), la réponse présente "
     "un pic de résonance |H|max = 1/(2ζ√(1−ζ²)) près de f0.")

heading("3.5 Extraction de l'amplitude, SNR et THD", 2)
bullet("Détection cohérente (lock-in) : l'amplitude à la fréquence d'excitation "
       "est extraite par projection sur des références sin/cos exactes, ce qui "
       "rejette le bruit hors-bande et permet une mesure même à faible SNR.")
bullet("SNR : rapport signal/bruit hors-bande, en dB.")
bullet("THD : distorsion harmonique totale √(ΣA_k²)/A_1, k = 2…5 — pureté du sinus.")

heading("3.6 Enveloppe limitée en vitesse (anti-saturation)", 2)
para("L'amplitude de commande est plafonnée pour que la vitesse crête de "
     "l'armature ne fasse pas saturer le géophone "
     "(v_max = 0,5·V_pleine_échelle / (G·|H|max)), tout en respectant la course "
     "mécanique (±38 mm) et un plafond d'accélération.")

heading("3.7 Critère de fiabilité", 2)
para("Un point est jugé fiable si SNR ≥ 20 dB. En basse fréquence (≤ 0,5–1 Hz), "
     "deux effets dégradent la mesure : (a) le bruit de l'accéléromètre de "
     "référence domine (accélération ~1 mg à 0,1 Hz), et (b) la fenêtre "
     "d'acquisition du géophone (1,024 s) contient moins d'un cycle à 0,1–0,5 Hz. "
     "Les points non fiables sont tracés en symboles creux et exclus des "
     "ajustements et conclusions.")

# =============================================================== 4. RÉSULTATS
heading("4. Résultats", 1)

heading("4.1 Fonction de transfert du banc", 2)
figure("fig1_transfert_banc.png",
       "Fig. 1 — Transfert de banc H_banc(f), axe horizontal.", 13)
para("H_banc(f) culmine à 0,081 g/V vers 5 Hz puis décroît de part et d'autre : "
     "c'est la signature électromécanique de l'ensemble ampli + shaker + "
     "armature. Les deux points les plus bas (0,1 et 0,2 Hz) sont rejetés "
     "(SNR < 20 dB).")
table(
    ["f (Hz)", "0,5", "1", "2", "5", "10", "20", "50"],
    [["H_banc (g/V)", "0,0164", "0,0333", "0,0615", "0,0811", "0,0586", "0,0351", "0,0173"]],
)

heading("4.2 Fonctions de transfert des géophones (réponse vitesse)", 2)
figure("fig2_sensibilite_velocite.png",
       "Fig. 2 — Sensibilité en vitesse ; points pleins SNR ≥ 20 dB, creux = bruit, "
       "tirets = modèle 2ᵉ ordre.")
para("Sensibilité en vitesse S_v [counts/(m/s)], points fiables (SNR ≥ 20 dB) :")
table(
    ["f (Hz)", "HG-6 HB", "VAS-H-200", "ST-2A (H)"],
    [
        ["1", "1,48e9", "—", "—"],
        ["2", "—", "—", "7,26e10"],
        ["5", "2,85e10", "3,32e10", "1,59e11"],
        ["10", "3,25e10", "—", "2,04e11"],
        ["20", "3,06e10", "9,81e10", "2,28e11"],
        ["50", "3,02e10", "1,24e11", "2,36e11"],
        ["Plateau", "3,06e10", "(non atteint)", "2,28e11"],
    ],
)
para("Le HG-6 et le ST-2A atteignent un plateau franc (réponse de bande plate). "
     "Le VAS-H-200 continue de croître jusqu'à 50 Hz : il n'a pas plafonné dans "
     "la bande mesurée.")

heading("4.3 Validation absolue vs datasheet", 2)
para("En convertissant le plateau (counts/(m/s)) en volts via le facteur ADS1285 "
     "2³¹ / 2,5 V = 8,59·10⁸ counts/V (gain 1) :")
table(
    ["Géophone", "Plateau mesuré [V/(m/s)]", "Datasheet [V/(m/s)]", "Écart"],
    [
        ["ST-2A (H)", "265", "260", "+2 %"],
        ["HG-6 HB", "36", "28,8 (≈ SM-6)", "+24 %"],
        ["VAS-H-200", "≥ 129 (non plafonné)", "220", "non concluant"],
    ],
)
para("La concordance à 2 % du ST-2A est la preuve de validité du banc : elle ne "
     "serait pas possible si un maillon de la chaîne était biaisé. Le HG-6 lit "
     "~24 % au-dessus du nominal SM-6, écart compatible avec la dispersion "
     "unité-à-unité. Le VAS n'ayant pas plafonné, sa valeur de 50 Hz n'est qu'une "
     "borne inférieure.")

heading("4.4 Réponses normalisées — fréquences de coupure", 2)
figure("fig3_normalisee.png",
       "Fig. 3 — Réponses normalisées au plateau ; lecture directe des coupures.", 13)
para("Le ST-2A (capteur 2 Hz) coupe le plus bas, le HG-6 (4,5 Hz) au milieu, et "
     "le VAS le plus haut — encore en pente montante à 20 Hz, ce qui confirme sa "
     "coupure anormalement élevée.")
para("Ajustement du modèle 2ᵉ ordre :")
table(
    ["Géophone", "f0 ajusté", "f0 spec", "ζ ajusté", "ζ spec", "RMS résiduel"],
    [
        ["ST-2A (H)", "3,13 Hz", "2,0 Hz", "0,86", "0,7", "3,0 dB (bon)"],
        ["HG-6 HB", "5,59 Hz", "4,5 Hz", "0,40", "0,56", "6,7 dB"],
        ["VAS-H-200", "4,83 Hz", "4,5 Hz", "1,75", "0,73", "7,3 dB (mal conditionné)"],
    ],
)
para("Les ajustements de HG-6 et VAS sont dégradés par les points basse fréquence "
     "bruités et, pour le VAS, par l'absence de plateau (ζ plafonne à la borne "
     "2,0). Le ST-2A, qui plafonne proprement, donne le meilleur ajustement.",
     italic=True, color=GREY)

heading("4.5 Pureté spectrale — FFT normalisée et THD", 2)
figure("fig4_fft_normalisee.png",
       "Fig. 4 — FFT normalisée à 5 Hz ; pointillés = harmoniques 2f…6f.")
para("Pour les trois capteurs, la fondamentale domine ; les harmoniques sont "
     "30–40 dB en dessous, soit une THD de l'ordre de 4–6 % — excitation "
     "sinusoïdale propre.")
figure("fig5_thd.png", "Fig. 5 — THD vs fréquence (points fiables).", 13)
para("La THD décroît avec la fréquence (de ~6–9 % vers 1–2 Hz à < 1 % à 50 Hz) ; "
     "tous les points fiables restent sous ~7 %.")

heading("4.6 Exemple de signaux bruts", 2)
figure("fig6_ondes.png",
       "Fig. 6 — Signaux simultanés ST-2A (H) @ 5 Hz : accéléromètre (haut) et "
       "géophone (bas).", 13)
para("Le géophone (vitesse) et l'accéléromètre (accélération) sont décalés "
     "d'environ un quart de cycle (~90°) — relation attendue puisque a = dv/dt : "
     "confirmation physique que les deux capteurs voient la même excitation.")

# =============================================================== 5. ANALYSE
heading("5. Analyse par géophone", 1)
heading("5.1 ST-2A (H) — référence de validation", 3)
para("Plateau 265 V/(m/s) (spec 260, +2 %), f0 ajusté 3,1 Hz (spec 2 Hz), "
     "ζ ≈ 0,86, meilleur ajustement (RMS 3 dB), THD < 5 %. Capteur le mieux "
     "caractérisé du lot ; sa concordance absolue valide la métrologie du banc.")
heading("5.2 HG-6 HB — conforme", 3)
para("Plateau franc 36 V/(m/s) au-dessus de ~10 Hz, f0 ≈ 5,6 Hz, ζ ≈ 0,40 "
     "(sous-amorti → léger pic de résonance vers 5–6 Hz). Sensibilité ~24 % "
     "au-dessus du nominal SM-6, dans la dispersion attendue. Comportement de "
     "géophone 4,5 Hz typique.")
heading("5.3 VAS-H-200 — anomalie à investiguer", 3)
para("La réponse vitesse monte encore à 50 Hz sans plateau ; la pente log-log "
     "passe de ~2 (région f²) en BF à ~0,3 à 50 Hz, soit une coupure effective "
     "bien plus haute que les 4,5 Hz annoncés. L'ajustement est mal conditionné "
     "(ζ saturé). Sa sensibilité réelle ne peut pas être confirmée dans la bande "
     "0,1–50 Hz. À faire : étendre le balayage au-delà de 50 Hz (100–200 Hz) pour "
     "atteindre son plateau, et vérifier le montage du capteur horizontal.")

# =============================================================== 6. LIMITES
heading("6. Limites et incertitudes", 1)
bullet("Basse fréquence (≤ 1 Hz) : peu fiable — bruit de l'accéléromètre de "
       "référence dominant + < 2 cycles dans la fenêtre de 1,024 s. Pour calibrer "
       "< 1 Hz, augmenter la durée d'acquisition et, si possible, l'amplitude.")
bullet("Conversion counts→volts : suppose l'ADS1285 en 32 bits, ±2,5 V, gain 1. "
       "La concordance à 2 % du ST-2A confirme cette hypothèse.")
bullet("Sensibilités datasheet : données circuit ouvert ; chargé, le géophone "
       "sort un peu moins. Les écarts ≤ ±25 % observés sont dans l'enveloppe "
       "attendue.")
bullet("VAS-H-200 : non plafonné dans la bande → sensibilité absolue non "
       "déterminée.")

# =============================================================== 7. CONCLUSIONS
heading("7. Conclusions et recommandations", 1)
numbered("Le banc horizontal est validé : la sensibilité absolue du ST-2A "
         "concorde à 2 % avec sa fiche technique, et les formes de réponse "
         "(plateau + roll-off f²) sont conformes au modèle 2ᵉ ordre.")
numbered("ST-2A (H) et HG-6 HB sont correctement caractérisés sur leur bande "
         "utile et exploitables pour l'ANT.")
numbered("VAS-H-200 : refaire un balayage étendu au-delà de 50 Hz pour atteindre "
         "son plateau et confirmer/infirmer la coupure anormale ; vérifier le "
         "montage.")
numbered("Basse fréquence : pour exploiter la bande 0,1–1 Hz (utile en ANT), "
         "allonger la fenêtre d'acquisition (≥ 4–8 s) afin de capturer plusieurs "
         "cycles et relever le SNR.")

doc.add_paragraph()
para("Données : 2026-05-28. Figures et synthèse générées par "
     "tools/rapport_geophones.py ; document Word par tools/rapport_geophones_docx.py.",
     italic=True, color=GREY, size=8.5)

doc.save(OUT)
print(f"Rapport Word écrit : {OUT}")

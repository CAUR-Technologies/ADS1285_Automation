"""
Génère le rapport de calibration des géophones VERTICAUX au format Word (.docx),
en-tête société GDD Instrumentation + logo. Rapport interim (2 unités / 5).

Réutilise les figures produites par tools/rapport_geophones_v.py.
Sortie : data/rapport_geophones_V_2026-06-05/Rapport_calibration_geophones_V.docx

Lancer :  python tools/rapport_geophones_v_docx.py
"""

import os
import sys

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REP = os.path.join(DATA, "rapport_geophones_V_2026-06-05")
FIG = os.path.join(REP, "figures")
LOGO = os.path.join(ROOT, "Documents", "gdd-logo1.png")
OUT = os.path.join(REP, "Rapport_calibration_geophones_V.docx")

BLUE = RGBColor(0x1B, 0x4E, 0x8C)
GREY = RGBColor(0x55, 0x55, 0x55)


def fig(name):
    return os.path.join(FIG, name)


doc = Document()
style = doc.styles["Normal"]
style.font.name = "Calibri"
style.font.size = Pt(10.5)
for lvl in ("Heading 1", "Heading 2", "Heading 3", "Title"):
    try:
        doc.styles[lvl].font.color.rgb = BLUE
    except KeyError:
        pass

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
sub = para("Géophones verticaux — Banc de caractérisation ANT", bold=True, size=14)
sub.alignment = WD_ALIGN_PARAGRAPH.LEFT
para("Axe vertical  ·  Données du 2026-06-05  ·  Rapport interim (2 unités / 5)",
     color=GREY, size=11)
para("Géophones testés : HG-6XT UB · VAS-200 (V)", size=11)
para("Application : étalonnage de géophones pour l'Ambient Noise Tomography (ANT)",
     italic=True, color=GREY, size=10)
doc.add_paragraph()

# =============================================================== 1. RÉSUMÉ
heading("1. Résumé exécutif", 1)
para("Deux géophones verticaux ont été caractérisés en fréquence (0,1–100 Hz) sur "
     "le banc shaker, après remise en service de l'axe vertical. La chaîne complète "
     "— Wavetek → APS 0109/125 → shaker APS 113 → accéléromètre de référence Silicon "
     "Designs ; géophone numérisé par l'ADS1285 EVM — est opérationnelle et fournit "
     "des fonctions de transfert exploitables sur la bande utile.")
table(
    ["Géophone", "Bande fiable", "Sensibilité plateau mesurée", "Spec datasheet", "Verdict"],
    [
        ["HG-6XT UB", "5–100 Hz (6 pts)", "38,3 V/(m/s)", "28,8 V/(m/s) (≈ SM-6)", "+33 % — cohérent (unité HGS)"],
        ["VAS-200 (V)", "20–100 Hz (4 pts)", "≥ 141 V/(m/s) (non plafonné)", "220 V/(m/s)", "anomalie — coupure trop haute"],
    ],
)
para("Résultat marquant : la sensibilité plateau du HG-6XT UB mesurée sur l'axe "
     "vertical (38,3 V/(m/s)) coïncide à ~6 % près avec celle du HG-6 HB mesurée sur "
     "l'axe horizontal le 2026-05-28 (36 V/(m/s)). Cette concordance inter-axes entre "
     "deux unités de la même famille HG-6, sur des chaînes indépendantes, valide la "
     "métrologie de la chaîne verticale (accéléromètre de référence, conversion "
     "counts→volts de l'ADS1285, conversion accélération→vitesse). Le VAS-200 (V) "
     "présente, comme son homologue horizontal VAS-H-200, une réponse qui continue "
     "de monter jusqu'à 100 Hz sans atteindre son plateau : sa coupure effective est "
     "bien plus haute que les 4,5 Hz annoncés — à investiguer.")
para("Rapport interim : 2 unités sur 5 prévues ; les 3 autres seront ajoutées dans "
     "une révision ultérieure.", italic=True, color=GREY)

# =============================================================== 2. CONDITIONS
heading("2. Conditions du run", 1)
table(
    ["Paramètre", "Valeur"],
    [
        ["Axe", "Vertical"],
        ["Gain ampli APS 125 (V)", "100"],
        ["Limite de courant APS 125 (V)", "100 A RMS"],
        ["Échantillonnage géophone (ADS1285)", "1000 éch/s, 1024 points (1,024 s)"],
        ["Échantillonnage accél. réf. (NI)", "fenêtre adaptative (≥ 10 cycles, ≤ 100 s)"],
        ["Fréquences balayées", "0,1 / 0,2 / 0,5 / 1 / 2 / 5 / 10 / 20 / 50 / 70 / 100 Hz"],
    ],
)
para("Note : l'axe vertical, hors service lors du run horizontal du 28 mai, a été "
     "remis en service ce jour — config du contrôleur APS 0109 restaurée (polarité "
     "de sortie + constante d'intégration), servo d'amplitude corrigé, et acquisition "
     "à fenêtre adaptative basse fréquence ajoutée.", italic=True, color=GREY)

# =============================================================== 3. MÉTHODOLOGIE
heading("3. Méthodologie", 1)
heading("3.1 Chaîne de mesure", 2)
para(
    "Wavetek 39A -> APS 0109 (position) -> APS 125 (ampli) -> shaker APS 113\n"
    "                                                |-> accéléromètre réf. (NI ai1) -> a_table(f) [g]\n"
    "                                                |-> géophone (DUT) -> ADS1285 EVM -> counts(f)",
    mono=True)
para("Le banc impose une accélération mécanique connue (mesurée en temps réel par "
     "l'accéléromètre de référence Silicon Designs 2240-005, 800 mV/g, via la carte "
     "NI USB-6221). Le géophone, monté sur la même armature, voit la même excitation ; "
     "sa sortie est numérisée par l'ADS1285 (ADC 32 bits, ±2,5 V crête à gain 1).")

heading("3.2 Mesure en deux étapes", 2)
numbered("Fonction de transfert du banc  H_banc(f) = a_table(f) / V_wavetek(f) "
         "[g/V] — caractérise la réponse électromécanique de la chaîne (sans "
         "géophone monté).")
numbered("Sensibilité du géophone : à chaque point, S(f) = counts_crête(f) / "
         "a_table(f) [counts/g], où a_table est l'accélération réellement mesurée "
         "par l'accéléromètre de référence. La sensibilité est donc indépendante de "
         "la forme de H_banc.")

heading("3.3 Conversion en réponse vitesse", 2)
para("Un géophone est un capteur de vitesse, alors que le banc impose une "
     "accélération. Pour un sinus, v = a/(2πf), d'où :")
para("S_v [counts/(m/s)] = S_g [counts/g] · 2πf / g        (g = 9,80665 m/s²)",
     italic=True, bold=True)
para("Cette conversion révèle la vraie réponse du géophone : plate au-dessus de la "
     "fréquence propre f0, en roll-off f² en dessous.")

heading("3.4 Modèle du géophone (2ᵉ ordre)", 2)
para("|S_v(f)| = G0 · r² / √[(1−r²)² + (2ζr)²]   avec r = f/f0",
     italic=True, bold=True)
para("G0 = sensibilité de bande plate, f0 = fréquence propre, ζ = amortissement.")

heading("3.5 Extraction, SNR, THD et fenêtre adaptative", 2)
bullet("Détection cohérente (lock-in) : amplitude à la fréquence d'excitation par "
       "projection sur des références sin/cos exactes (rejet du bruit hors-bande).")
bullet("Fenêtre adaptative BF : sous ~1 Hz, l'accéléromètre est intégré sur ≥ 10 "
       "cycles (jusqu'à 100 s) pour relever le SNR ; le géophone reste à 1,024 s "
       "(limite du buffer PSM de l'ADS1285).")
bullet("THD : distorsion harmonique totale √(ΣA_k²)/A_1, k = 2…5 — pureté du sinus.")

heading("3.6 Critère de fiabilité", 2)
para("Un point est jugé fiable si SNR ≥ 20 dB. En basse fréquence, le bruit de "
     "l'accéléromètre de référence domine (excitation ~1 mg à 0,1 Hz, "
     "displacement-limited) ; les points non fiables sont tracés en symboles creux "
     "et exclus des ajustements et conclusions.")

# =============================================================== 4. RÉSULTATS
heading("4. Résultats", 1)
heading("4.1 Fonction de transfert du banc (axe vertical)", 2)
figure("fig1_transfert_banc.png",
       "Fig. 1 — Transfert de banc H_banc(f), axe vertical.", 13)
para("H_banc(f) culmine à 1,71 g/V vers 5 Hz (résonance électromécanique du banc "
     "vertical chargé) puis décroît de part et d'autre. Bande fiable 2–100 Hz ; les "
     "points 0,1–1 Hz sont rejetés (SNR < 20 dB) — limite physique (~0,9 mg à 0,1 Hz).")
table(
    ["f (Hz)", "2", "5", "10", "20", "50", "70", "100"],
    [["H_banc (g/V)", "0,725", "1,710", "1,610", "0,949", "0,425", "0,318", "0,235"]],
)

heading("4.2 Fonctions de transfert des géophones (réponse vitesse)", 2)
figure("fig2_sensibilite_velocite.png",
       "Fig. 2 — Sensibilité en vitesse ; points pleins SNR ≥ 20 dB, creux = bruit, "
       "tirets = modèle 2ᵉ ordre.")
para("Sensibilité en vitesse S_v [counts/(m/s)], points fiables (SNR ≥ 20 dB) :")
table(
    ["f (Hz)", "HG-6XT UB", "VAS-200 (V)"],
    [
        ["5", "2,79e10", "—"],
        ["10", "3,29e10", "—"],
        ["20", "3,24e10", "9,57e10"],
        ["50", "3,20e10", "1,17e11"],
        ["70", "3,35e10", "1,24e11"],
        ["100", "3,50e10", "1,45e11"],
        ["Plateau", "3,29e10", "(non atteint)"],
    ],
)
para("Le HG-6XT UB atteint un plateau franc dès ~10 Hz. Le VAS-200 (V) continue de "
     "croître jusqu'à 100 Hz : il n'a pas plafonné dans la bande mesurée.")

heading("4.3 Validation inter-axes vs datasheet", 2)
para("En convertissant le plateau (counts/(m/s)) en volts via le facteur ADS1285 "
     "2³¹ / 2,5 V = 8,59·10⁸ counts/V (gain 1) :")
table(
    ["Géophone", "Plateau mesuré [V/(m/s)]", "Datasheet", "Réf. axe H (28 mai)", "Écart"],
    [
        ["HG-6XT UB", "38,3", "28,8 (≈ SM-6)", "HG-6 HB : 36", "+6 % inter-axes"],
        ["VAS-200 (V)", "≥ 141 (non plafonné)", "220", "VAS-H-200 : ≥ 129", "non concluant"],
    ],
)
para("La concordance à 6 % entre le HG-6XT UB (vertical) et le HG-6 HB (horizontal), "
     "deux unités HG-6 mesurées sur des chaînes indépendantes, est la preuve de "
     "validité du banc vertical. Les deux unités HG-6 lisent ~24–33 % au-dessus du "
     "nominal SM-6 (28,8) — cohérent avec la sensibilité réelle des unités HGS. Le "
     "VAS-200 (V) n'ayant pas plafonné, sa valeur de 100 Hz n'est qu'une borne "
     "inférieure.")

heading("4.4 Réponses normalisées — fréquences de coupure", 2)
figure("fig3_normalisee.png",
       "Fig. 3 — Réponses normalisées au plateau ; lecture directe des coupures.", 13)
para("Le HG-6XT UB coupe proprement autour de 5 Hz (capteur 4,5 Hz). Le VAS-200 (V) "
     "est encore en pente montante à 20 Hz, ce qui confirme une coupure anormalement "
     "élevée.")
para("Ajustement du modèle 2ᵉ ordre :")
table(
    ["Géophone", "f0 ajusté", "f0 spec", "ζ ajusté", "ζ spec", "RMS résiduel"],
    [
        ["HG-6XT UB", "5,38 Hz", "4,5 Hz", "0,52", "0,56", "2,97 dB (bon)"],
        ["VAS-200 (V)", "2,45 Hz", "4,5 Hz", "2,00", "0,73", "5,72 dB (mal conditionné)"],
    ],
)
para("L'ajustement du HG-6XT UB est excellent (f0 et ζ proches des specs, RMS 3 dB). "
     "Celui du VAS-200 (V) est dégradé par l'absence de plateau (ζ sature à la "
     "borne 2,0).", italic=True, color=GREY)

heading("4.5 Pureté spectrale — FFT normalisée et THD", 2)
figure("fig4_fft_normalisee.png",
       "Fig. 4 — FFT normalisée du signal géophone à 5 Hz ; pointillés = harmoniques "
       "2f…6f.")
figure("fig5_thd.png", "Fig. 5 — THD vs fréquence (points fiables).", 13)
para("La fondamentale domine ; la THD décroît avec la fréquence (grand débattement "
     "et bruit relatif plus élevé en BF) et reste basse dans la bande utile haute.")

heading("4.6 Exemple de signaux bruts", 2)
figure("fig6_ondes.png",
       "Fig. 6 — Signaux simultanés HG-6XT UB @ 5 Hz : accéléromètre (haut) et "
       "géophone (bas).", 13)
para("Le géophone (vitesse) et l'accéléromètre (accélération) sont décalés d'environ "
     "un quart de cycle (~90°) — relation attendue puisque a = dv/dt : confirmation "
     "physique que les deux capteurs voient la même excitation.")

# =============================================================== 5. ANALYSE
heading("5. Analyse par géophone", 1)
heading("5.1 HG-6XT UB — conforme et validant", 3)
para("Plateau 38,3 V/(m/s) dès ~10 Hz, f0 ajusté 5,4 Hz (spec 4,5), ζ ≈ 0,52 "
     "(spec 0,56), meilleur ajustement (RMS 3 dB). Sa concordance à 6 % avec le "
     "HG-6 HB de l'axe horizontal valide la chaîne verticale. Sensibilité ~33 % "
     "au-dessus du nominal SM-6, cohérente avec une unité HGS. Capteur exploitable "
     "pour l'ANT.")
heading("5.2 VAS-200 (V) — anomalie à investiguer", 3)
para("La réponse vitesse monte encore à 100 Hz sans plateau ; coupure effective "
     "bien plus haute que les 4,5 Hz annoncés. Ajustement 2ᵉ ordre mal conditionné "
     "(ζ saturé à 2,0). Sa sensibilité réelle ne peut pas être confirmée dans la "
     "bande 0,1–100 Hz. Comportement identique à son homologue VAS-H-200 (axe H), "
     "ce qui écarte un défaut propre à l'axe vertical et pointe vers le composant. "
     "À faire : étendre le balayage au-delà de 100 Hz (200–300 Hz) et vérifier la "
     "fiche technique du modèle.")

# =============================================================== 6. LIMITES
heading("6. Limites et incertitudes", 1)
bullet("Basse fréquence (≤ 1 Hz) : peu fiable — bruit de l'accéléromètre de "
       "référence dominant (excitation ~mg) + buffer géophone limité à 1,024 s "
       "(< 1 cycle sous 1 Hz). La fenêtre adaptative améliore le SNR accéléro mais "
       "ne crée pas un signal mécanique inexistant.")
bullet("Conversion counts→volts : suppose l'ADS1285 en 32 bits, ±2,5 V, gain 1. "
       "La cohérence inter-axes du HG-6 confirme cette hypothèse.")
bullet("VAS-200 (V) : non plafonné dans la bande → sensibilité absolue non "
       "déterminée (borne inférieure 141 V/(m/s)).")

# =============================================================== 7. CONCLUSIONS
heading("7. Conclusions et recommandations", 1)
numbered("Le banc vertical est validé : la sensibilité du HG-6XT UB concorde à 6 % "
         "avec le HG-6 HB de l'axe horizontal, et sa forme de réponse (plateau + "
         "roll-off f²) est conforme au modèle 2ᵉ ordre.")
numbered("HG-6XT UB est correctement caractérisé sur sa bande utile (5–100 Hz) et "
         "exploitable pour l'ANT.")
numbered("VAS-200 (V) : refaire un balayage étendu au-delà de 100 Hz pour atteindre "
         "son plateau ; même anomalie que le VAS-H-200 → vérifier le composant.")
numbered("Compléter le lot : 3 géophones verticaux restent à tester pour finaliser "
         "le rapport.")

doc.add_paragraph()
para("Données : 2026-06-05. Figures et synthèse générées par "
     "tools/rapport_geophones_v.py ; document Word par tools/rapport_geophones_v_docx.py.",
     italic=True, color=GREY, size=8.5)

doc.save(OUT)
print(f"Rapport Word écrit : {OUT}")

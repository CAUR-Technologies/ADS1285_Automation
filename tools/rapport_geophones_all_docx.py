"""
Rapport COMBINÉ Word (.docx) — 8 géophones (V+H), en-tête GDD + logo.
Réutilise les figures de tools/rapport_geophones_all.py.
Sortie : data/rapport_geophones_ALL_2026-06-08/Rapport_calibration_8_geophones.docx
Lancer :  python tools/rapport_geophones_all_docx.py
"""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REP = os.path.join(DATA, "rapport_geophones_ALL_2026-06-08")
FIG = os.path.join(REP, "figures")
LOGO = os.path.join(ROOT, "Documents", "gdd-logo1.png")
OUT = os.path.join(REP, "Rapport_calibration_8_geophones.docx")
BLUE = RGBColor(0x1B, 0x4E, 0x8C); GREY = RGBColor(0x55, 0x55, 0x55)

doc = Document()
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(10.5)
for lvl in ("Heading 1", "Heading 2", "Heading 3", "Title"):
    try: doc.styles[lvl].font.color.rgb = BLUE
    except KeyError: pass
sec = doc.sections[0]
for m in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
    setattr(sec, m, Cm(2.1))
hp = sec.header.paragraphs[0]; hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
run = hp.add_run()
if os.path.exists(LOGO): run.add_picture(LOGO, height=Cm(1.05))
r2 = hp.add_run("    Instrumentation GDD inc."); r2.bold = True
r2.font.size = Pt(11); r2.font.color.rgb = BLUE
fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr = fp.add_run("Instrumentation GDD inc.  ·  Calibration de géophones (V+H)  ·  Confidentiel")
fr.font.size = Pt(8); fr.font.color.rgb = GREY


def heading(t, lvl=1):
    h = doc.add_heading(t, level=lvl)
    for r in h.runs: r.font.color.rgb = BLUE
    return h


def para(t, *, italic=False, bold=False, size=None, color=None, mono=False):
    p = doc.add_paragraph(); r = p.add_run(t)
    r.italic = italic; r.bold = bold
    if mono: r.font.name = "Consolas"; r.font.size = Pt(8.5)
    if size: r.font.size = Pt(size)
    if color: r.font.color.rgb = color
    return p


def bullet(t): return doc.add_paragraph(t, style="List Bullet")
def numbered(t): return doc.add_paragraph(t, style="List Number")


def table(headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]; c.text = ""
        rr = c.paragraphs[0].add_run(h); rr.bold = True; rr.font.size = Pt(9)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            rr = cells[i].paragraphs[0].add_run(str(v)); rr.font.size = Pt(9)
    doc.add_paragraph(); return t


def figure(name, caption, width_cm=15.5):
    path = os.path.join(FIG, name)
    if not os.path.exists(path):
        para(f"[figure manquante : {name}]", italic=True, color=GREY); return
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width_cm))
    cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cr = cap.add_run(caption); cr.italic = True; cr.font.size = Pt(8.5); cr.font.color.rgb = GREY


# ---- TITRE
t = doc.add_heading("Rapport de calibration", level=0)
for r in t.runs: r.font.color.rgb = BLUE
para("8 géophones (5 verticaux + 3 horizontaux) — Banc de caractérisation ANT",
     bold=True, size=14)
para("Données du 2026-06-05 au 2026-06-08", color=GREY, size=11)
para("Verticaux : HG-6XT UB · VAS-200 (V) · HG-5VHS · HG-2 U · ST-2A (V)", size=10)
para("Horizontaux : HG-6 HB · VAS-H-200 · ST-2A (H)", size=10)
doc.add_paragraph()

# ---- 1. RÉSUMÉ
heading("1. Résumé exécutif", 1)
para("Huit géophones ont été caractérisés en fréquence (0,1–100 Hz) sur les deux axes du "
     "banc shaker (chaînes V et H indépendantes : contrôleur APS 0109, ampli APS 125, "
     "shaker APS 113 et accéléromètre de référence dédiés par axe).")
table(["Géophone", "Axe", "Sensibilité mes.", "Spec", "Écart", "f0/ζ", "Bande fiable", "Verdict"],
      [["ST-2A (V)", "V", "293,8 V/(m/s)", "260", "+13 %", "3,3/1,00", "10–100 Hz", "excellent"],
       ["ST-2A (H)", "H", "272,0 V/(m/s)", "260", "+5 %", "5,9/0,50", "5–100 Hz", "excellent"],
       ["HG-6XT UB", "V", "38,3 V/(m/s)", "28,8", "+33 %", "5,4/0,52", "5–100 Hz", "conforme"],
       ["HG-6 HB", "H", "35,6 V/(m/s)", "28,8", "+24 %", "6,5/0,25", "1–100 Hz", "conforme"],
       ["HG-5VHS", "V", "118,0 V/(m/s)", "100,4", "+18 %", "4,5/0,63", "20–100 Hz", "conforme"],
       ["HG-2 U", "V", "169,7 V/(m/s)", "~50 est.", "—", "3,6/0,52", "5–70 Hz", "spec à confirmer"],
       ["VAS-200 (V)", "V", "≥140,6 V/(m/s)", "220", "non plaf.", "2,5/2,0", "20–100 Hz", "anomalie"],
       ["VAS-H-200", "H", "≥144,5 V/(m/s)", "220", "non plaf.", "7,2/1,16", "5–100 Hz", "anomalie"]])
para("Résultat marquant — validation croisée inter-axes. Trois familles ont été mesurées "
     "sur les deux bancs indépendants :")
table(["Famille", "Vertical", "Horizontal", "Accord"],
      [["ST-2A", "293,8", "272,0", "±4 %"],
       ["HG-6", "38,3", "35,6", "±4 %"],
       ["VAS", "140,6", "144,5", "±1 % (anomalie commune)"]])
para("Ces accords à quelques % entre des chaînes V et H totalement séparées constituent la "
     "preuve de validité des deux bancs. Le ST-2A concorde en outre à +5…+13 % avec sa "
     "datasheet (260 V/(m/s)), validant la métrologie absolue.")
para("Plancher de bruit (accéléromètre de référence) : V = 0,62 mg RMS · H = 0,57 mg RMS "
     "(fixe la limite basse fréquence, §4).", bold=True)

# ---- 2. CONDITIONS
heading("2. Conditions du run", 1)
table(["Paramètre", "Vertical", "Horizontal"],
      [["Dates", "2026-06-05", "2026-06-08"],
       ["Gain ampli APS 125", "100 (max)", "100 (max)"],
       ["Limite de courant", "100 A RMS", "100 A RMS"],
       ["Canal accél. réf. (NI)", "ai1", "ai0"],
       ["Plancher de bruit", "0,62 mg RMS", "0,57 mg RMS"],
       ["Géophone (ADS1285)", "1000 éch/s, 1024 pts", "idem"],
       ["Accél. réf. (NI)", "fenêtre adaptative (≥10 cyc, ≤100 s)", "idem"],
       ["Fréquences", "0,1 → 100 Hz (11 pts)", "idem"]])
para("Note métrologique — un géophone mesuré deux fois. Le ST-2A (V) a d'abord été balayé "
     "à 10:55 alors que le géophone n'était pas branché sur l'ADS1285 : le balayage s'est "
     "déroulé normalement mais la sortie « géophone » ne lisait que le bruit du convertisseur "
     "(counts crête ≈ 101, ~7 ordres de grandeur sous un vrai signal). Le run a été refait "
     "correctement à 11:09 (counts ≈ 7,5·10⁸) — c'est ce dernier qui figure ici. L'épisode "
     "rappelle que le banc ne « sait » pas qu'aucun géophone n'est connecté : il mesure le "
     "bruit de l'ADC.", italic=True, color=GREY)

# ---- 3. MÉTHODOLOGIE
heading("3. Méthodologie", 1)
bullet("Chaîne : le banc impose une accélération connue, mesurée par l'accéléromètre de "
       "référence Silicon Designs 2240-005 (800 mV/g, NI USB-6221). Le géophone, sur la "
       "même armature, est numérisé par l'ADS1285 (32 bits, ±2,5 V crête à gain 1).")
bullet("Sensibilité : S(f) = counts_crête / a_table [counts/g], indépendante du H_banc.")
bullet("Réponse vitesse : S_v = S_g · 2πf / g [counts/(m/s)] ; plate au-dessus de f0, "
       "roll-off f² en dessous. Modèle 2ᵉ ordre -> (G0, f0, ζ).")
bullet("Conversion V/(m/s) : plateau ÷ (2³¹/2,5 = 8,59·10⁸ counts/V). Critère SNR ≥ 20 dB.")

# ---- 4. LIMITE BF
heading("4. Pourquoi la basse fréquence est limitée", 1)
para("Sous ~1–2 Hz, aucun géophone n'atteint un point fiable (SNR ≥ 20 dB). Ce n'est pas un "
     "défaut logiciel mais la conjonction de cinq effets physiques :")
figure("fig5_limite_bf.png",
       "Fig. 4 — L'accélération réalisable (limitée par la course) rejoint le plancher de "
       "bruit du capteur de référence vers 0,1–0,2 Hz.", 14)
numbered("Excitation limitée par la course. A(f) = a/(2πf)² : à basse fréquence, une "
         "accélération donnée exige un déplacement énorme, plafonné par la course du shaker "
         "(±38 mm). L'accélération max réalisable s'effondre en f² (≈ 0,9 mg à 0,1 Hz, "
         "≈ 90 mg à 1 Hz, plafond 200 mg au-delà de 2 Hz).")
numbered("Plancher de bruit de l'accéléromètre de référence (0,62 mg V / 0,57 mg H). À "
         "0,1 Hz l'accélération réalisable (~0,9 mg) est à peine au-dessus du plancher "
         "(~0,6 mg) -> SNR ≈ 0 dB. C'est la limite dure : on ne mesure pas un signal plus "
         "petit que le bruit du capteur de référence.")
numbered("Roll-off f² propre au géophone : capteur de vitesse, sa sortie chute en f² sous "
         "sa fréquence propre f0 (~2–7 Hz) -> très peu de signal intrinsèque en BF.")
numbered("Fenêtre géophone bornée à 1,024 s (buffer PSM de l'ADS1285) : sous 1 Hz, moins "
         "d'un cycle -> lock-in bruité. (Seul l'accéléromètre étend sa fenêtre en BF.)")
numbered("Bande passante du contrôleur de position : en BF elle approche la fréquence de "
         "test -> stiffness faible obligatoire (séparation de bande), donc petites amplitudes.")
para("En résumé : la BF est plafonnée par le produit « peu d'accélération réalisable × peu "
     "de sortie géophone (f²) », rapporté au plancher de bruit du capteur de référence. Pour "
     "descendre plus bas, il faudrait un capteur de référence bas-bruit (sismomètre) et/ou "
     "une course de shaker bien plus grande — pas un réglage logiciel.")

# ---- 5. RÉSULTATS
heading("5. Résultats", 1)
heading("5.1 Transferts de banc (V et H)", 2)
figure("fig1_hbanc_VH.png", "Fig. 5 — H_banc(f) des deux axes (creux = SNR < 20 dB).", 13.5)
heading("5.2 Sensibilité en vitesse — verticaux", 2)
figure("fig2v_sensibilite_V.png", "Fig. 6 — Sensibilité vitesse, 5 géophones verticaux + fits.")
heading("5.3 Sensibilité en vitesse — horizontaux", 2)
figure("fig2h_sensibilite_H.png", "Fig. 7 — Sensibilité vitesse, 3 géophones horizontaux + fits.")
heading("5.4 Réponses normalisées (les 8)", 2)
figure("fig3_normalisee.png", "Fig. 8 — Réponses normalisées au plateau (pleins=V, tirets=H).")
heading("5.5 Distorsion harmonique (THD)", 2)
figure("fig4_thd.png", "Fig. 9 — THD vs fréquence (points fiables).", 13.5)

# ---- 6. ANALYSE
heading("6. Analyse par géophone", 1)
bullet("ST-2A (V) / (H) — composantes Z et H d'un capteur 3C. 294 et 272 V/(m/s) (spec 260 : "
       "+13 % / +5 %), meilleurs ajustements. Concordance datasheet -> valide la métrologie.")
bullet("HG-6XT UB (V) / HG-6 HB (H) — famille HG-6 (≈ SM-6, nominal 28,8). 38,3 et 35,6 V/(m/s) "
       "(+33 % / +24 %), cohérents entre eux ; écart = sensibilité réelle des unités HGS.")
bullet("HG-5VHS (V) — 118 V/(m/s) (+18 %), bon ajustement (f0 = 4,5 Hz pile sur la spec).")
bullet("HG-2 U (V) — 169,7 V/(m/s), très au-dessus de la spec ESTIMÉE (~40–50). Fit propre "
       "-> mesure fiable ; c'est la spec qu'il faut confirmer auprès du fabricant.")
bullet("VAS-200 (V) / VAS-H-200 (H) — encore montants à 100 Hz sur les deux axes (anomalie "
       "identique -> composant/fiche, pas le banc). À rebalayer au-delà de 100 Hz.")

# ---- 7. BRUIT
heading("7. Plancher de bruit par axe", 1)
table(["Axe", "Plancher de bruit (accél. réf.)"],
      [["Vertical (ai1)", "0,62 mg RMS"], ["Horizontal (ai0)", "0,57 mg RMS"]])
para("C'est la grandeur de référence de la limite basse fréquence (§4) : tout point dont "
     "l'accélération appliquée s'approche de ce plancher devient non fiable. Les deux axes "
     "sont comparables (~0,6 mg), cohérent avec une chaîne accéléro identique. (Mesures de "
     "référence du 2026-05-28 ; chaîne accéléro inchangée.)", italic=True, color=GREY)

# ---- 8. ANT
heading("8. Appréciation — meilleurs candidats pour l'ANT (2 Hz et 5 Hz)", 1)
para("Critère déterminant pour l'ANT : la sensibilité en vitesse à la fréquence d'intérêt "
     "(plus elle est haute, mieux le capteur extrait le faible bruit ambiant). On compare la "
     "sensibilité réellement mesurée à 2 Hz et 5 Hz (qui intègre le roll-off f² de chaque "
     "capteur), pas seulement le plateau.")
table(["Géophone", "Axe", "@ 2 Hz", "@ 5 Hz", "f0", "ζ"],
      [["ST-2A (V)", "V", "79 V/(m/s)", "187 V/(m/s)", "3,3", "1,00"],
       ["ST-2A (H)", "H", "79 V/(m/s)", "182 V/(m/s)", "5,9", "0,50"],
       ["HG-2 U", "V", "71 V/(m/s)", "127 V/(m/s)", "3,6", "0,52"],
       ["HG-5VHS", "V", "18 V/(m/s)", "122 V/(m/s)", "4,5", "0,63"],
       ["VAS-H-200", "H", "14 V/(m/s)", "39 V/(m/s)", "7,2", "1,16"],
       ["HG-6XT UB", "V", "6,8 V/(m/s)", "33 V/(m/s)", "5,4", "0,52"],
       ["HG-6 HB", "H", "6,8 V/(m/s)", "34 V/(m/s)", "6,5", "0,25"],
       ["VAS-200 (V)", "V", "6,0 V/(m/s)", "21 V/(m/s)", "2,5", "2,00"]])
para("À 5 Hz — choix large : ST-2A (≈185), HG-2 U (127) et HG-5VHS (122) sont ~4 à 6× plus "
     "sensibles que les HG-6 (≈33), tous au plateau ou proches.")
para("À 2 Hz — beaucoup plus sélectif : tous les capteurs sont sous/près de leur f0 "
     "(roll-off f²), donc seuls ceux à plateau élevé tiennent : ST-2A (≈79) et HG-2 U (≈71) "
     "dominent ; les autres décrochent (HG-5VHS 18, HG-6 6,8, VAS 6).")
para("Précision : à 2 Hz le banc excite faiblement (§4), donc les valeurs absolues des plus "
     "sensibles portent une incertitude plus grande (SNR banc < 20 dB) — mais le classement "
     "est robuste (confirmé par les plateaux et les valeurs à 5 Hz). Ce SNR faible est une "
     "limite du banc, pas du capteur : sur le terrain c'est la sensibilité intrinsèque qui "
     "prime.", italic=True, color=GREY)
para("Recommandations ANT :", bold=True)
numbered("1er choix, 2 Hz ET 5 Hz : ST-2A. Sensibilité la plus haute aux deux fréquences, "
         "f0 basse (≈ 3,3 Hz côté V), amortissement proche du critique (réponse lisse), "
         "concordance datasheet validée. Idéal pour la bande basse de l'ANT.")
numbered("2ᵉ choix : HG-2 U. Quasi égal au ST-2A à 2 Hz, excellent à 5 Hz, petit capteur "
         "2,5 Hz — sous réserve de confirmer sa spec.")
numbered("HG-5VHS : bon à partir de 5 Hz, décroche à 2 Hz -> bande ≥ 5 Hz.")
numbered("HG-6 (XT UB / HB) : sensibilité modeste, mieux adaptés ≥ 5–10 Hz ; robustes et "
         "très bien caractérisés (HG-6 HB fiable 1–100 Hz).")
numbered("VAS (200 / H-200) : à écarter tant que l'anomalie n'est pas résolue.")

# ---- 9. CONCLUSIONS
heading("9. Conclusions et recommandations", 1)
numbered("Les deux bancs (V et H) sont validés : accords inter-axes à ±4 % sur 3 familles, "
         "et concordance absolue du ST-2A à la datasheet.")
numbered("6 géophones sur 8 sont correctement caractérisés et exploitables pour l'ANT "
         "(ST-2A V/H, HG-6 V/H, HG-5VHS, HG-2 U).")
numbered("VAS-200 (V) et VAS-H-200 : anomalie reproductible sur les deux axes -> rebalayer "
         "au-delà de 100 Hz et vérifier la fiche du modèle.")
numbered("HG-2 U : confirmer la spec (sensibilité mesurée ~170 vs estimation ~50).")
numbered("Basse fréquence : limite physique (course + plancher de bruit + roll-off f²), non "
         "logicielle.")
numbered("Pour l'ANT : ST-2A en 1er choix (2 et 5 Hz), HG-2 U en second.")

doc.add_paragraph()
para("Données : 2026-06-05 → 2026-06-08. Figures et synthèse : tools/rapport_geophones_all.py ; "
     "document Word : tools/rapport_geophones_all_docx.py.", italic=True, color=GREY, size=8.5)
doc.save(OUT)
print(f"Rapport Word écrit : {OUT}")

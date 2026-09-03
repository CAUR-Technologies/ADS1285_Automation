"""Rapport de campagne V&V (Word .docx) — enregistreur geophone CAUR.

Genere docs/Rapport_VV_campagne.docx a partir du contenu de docs/vv-campaign-report.md,
avec la charte GDD (logo, titres bleus, Calibri) reutilisee des rapports de calibration.
Lancer :  python tools/vv_campaign_docx.py
"""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(ROOT, "Documents", "gdd-logo1.png")
LOGO_CAUR = os.path.join(ROOT, "Documents", "Caur-Logo.png")
OUT = os.path.join(ROOT, "docs", "Rapport_VV_campagne.docx")
BLUE = RGBColor(0x1B, 0x4E, 0x8C)
GREY = RGBColor(0x55, 0x55, 0x55)
GREEN = RGBColor(0x1E, 0x7A, 0x33)
AMBER = RGBColor(0xB0, 0x6A, 0x00)
RED = RGBColor(0xB0, 0x1E, 0x1E)

doc = Document()
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(10.5)
for lvl in ("Heading 1", "Heading 2", "Heading 3", "Title"):
    try:
        doc.styles[lvl].font.color.rgb = BLUE
    except KeyError:
        pass
sec = doc.sections[0]
for m in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
    setattr(sec, m, Cm(2.1))
# En-tete en tableau 2 cellules (sans bordure) : GDD a gauche, CAUR cale a droite.
htab = sec.header.add_table(rows=1, cols=2, width=Cm(16.8))
htab.autofit = False
htab.allow_autofit = False
cell_l, cell_r = htab.rows[0].cells
cell_l.width = Cm(11.3)
cell_r.width = Cm(5.5)
# gauche : logo GDD + raison sociale
lp = cell_l.paragraphs[0]
lp.alignment = WD_ALIGN_PARAGRAPH.LEFT
lrun = lp.add_run()
if os.path.exists(LOGO):
    lrun.add_picture(LOGO, height=Cm(1.05))
r2 = lp.add_run("    Instrumentation GDD inc.")
r2.bold = True
r2.font.size = Pt(11)
r2.font.color.rgb = BLUE
# droite : logo CAUR (produit), aligne a droite
rp = cell_r.paragraphs[0]
rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
if os.path.exists(LOGO_CAUR):
    rp.add_run().add_picture(LOGO_CAUR, height=Cm(1.10))
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
fr = fp.add_run("Instrumentation GDD inc.  ·  Campagne V&V — enregistreur geophone CAUR  ·  Confidentiel")
fr.font.size = Pt(8)
fr.font.color.rgb = GREY


def heading(t, lvl=1):
    h = doc.add_heading(t, level=lvl)
    for r in h.runs:
        r.font.color.rgb = BLUE
    return h


def para(t, *, italic=False, bold=False, size=None, color=None):
    p = doc.add_paragraph()
    r = p.add_run(t)
    r.italic = italic
    r.bold = bold
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    return p


def note(t):
    """Encadre-info : paragraphe indente, italique, gris."""
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.6)
    r = p.add_run(t)
    r.italic = True
    r.font.size = Pt(9.5)
    r.font.color.rgb = GREY
    return p


def bullet(t):
    return doc.add_paragraph(t, style="List Bullet")


def numbered(t):
    return doc.add_paragraph(t, style="List Number")


def table(headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        rr = c.paragraphs[0].add_run(h)
        rr.bold = True
        rr.font.size = Pt(9)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            rr = cells[i].paragraphs[0].add_run(str(v))
            rr.font.size = Pt(9)
    doc.add_paragraph()
    return t


# ============================ TITRE ============================
t = doc.add_heading("Rapport de campagne V&V", level=0)
for r in t.runs:
    r.font.color.rgb = BLUE
para("Enregistreur geophone CAUR — validation & verification (2026-08)", bold=True, size=14)
para("Firmware de test uniforme 0.1.0.211 / dae370c+ (branche gp/fix-cdc-get-large-tx, "
     "config test-bench.conf), flashe sur les 9 prototypes par USB DFU.", color=GREY, size=10)
doc.add_paragraph()

# ============================ 1. VERDICT ============================
heading("1. Verdict", 1)
para("GO. Les 8 unites config-production passent l'acceptation : 7 PASS, 1 WARN, 0 FAIL + "
     "checklist manuelle. Aucun defaut de design bloquant. La 9e (CG0-000008) est exclue "
     "(board modifie — resistances d'entree retirees). Les ecarts releves sont des correctifs "
     "firmware (backlog), pas des defauts materiels. Le bruit propre de la chaine ADC est "
     "valide vs la fiche ADS1285 (±11 % sur 4 gains, §5.2). Seul V14 (watchdog) reste vraiment "
     "non couvert (trou firmware) ; V3 et V5 sont caracterises. Aucun de ces points ne "
     "conditionne le go/no-go design.", bold=False)

# ============================ 2. PERIMETRE ============================
heading("2. Perimetre & methode", 1)
bullet("Acceptation automatisee — tools/acceptance.py (USB seul, sans shaker, ~2 min/unite) : "
       "V1/V13/V6/CFG/V11/V7/V2/V8. Freeze-robuste (chaque commande sous timeout).")
bullet("Checklist manuelle : V9 (USB-MSD), V10 (LEDs), V15 (enregistrement reel au bouton).")
bullet("Bruit propre ADC (ACQ-09) : entrees court-circuitees, 4 gains, PSD Welch vs fiche "
       "ADS1285 (§5.2 ; doc produit bruit-plancher-v31.md).")
bullet("Caracterisation metrologique (banc shaker+GNSS+accelero ref. NI) : reponse en frequence "
       "3 axes (§5) + campagne 8 geophones mono-axe (§5.3).")
bullet("Validation banc/instrumentation : 1PPS, GNSS, correlation temporelle (TIME-05), "
       "holdover PPS (§6).")

# ============================ 3. MATRICE V1-V15 ============================
heading("3. Matrice de validation V1–V15", 1)
table(["Test", "Objet", "Statut", "Methode / resultat"],
      [["V1", "Boot & console", "PASS (8)", "STATUS x3, uptime monotone, pas de reboot"],
       ["V2", "ADS1285 x3", "PASS (8)", "3 voies vivantes ; ADC exerce a fond en caracterisation"],
       ["V3", "Synchro ADC (<=1 ech.)", "partiel", "firmware aligne les 3 voies (0,000 ech) ; "
        "synchro physique par conception (common clock + SYNC PD4)"],
       ["V4", "GNSS (fix + 1PPS)", "PASS", "LC86G fix=1, 4-7 sats, Montreal ; ProPak 1PPS = 0,99 Hz"],
       ["V5", "Horodatage (derive/PPS)", "partiel", "cadence 250,07 Hz stable, suit l'UTC ; "
        "plancher 3,9 ms (RTC 1/256 s) = cause racine TIME-05"],
       ["V6", "IMU", "PASS (8)", "STREAM, |g| ~ 1,00 (0,8-1,2)"],
       ["V7", "uSD / transfert", "PASS (8)", "3 voies ecrites+relues ; corruption en transit CDC "
        "seulement, SD intacte"],
       ["V8", "MiniSEED", "PASS (8)", "fichiers valides (simplemseed v3)"],
       ["V9", "USB (MSD + CDC)", "PASS", "manuel : disque de masse monte ; CDC de bout en bout"],
       ["V10", "LEDs WS2812", "PASS", "manuel : 4 pixels repondent (D13 = Health)"],
       ["V11", "Tension batterie", "partiel", "lecture dans la plage MAIS jauge fausse (§8.3)"],
       ["V12", "BLE", "PASS", "controleur monte sur toutes + app companion fonctionnelle"],
       ["V13", "Detection revision", "PASS (8)", "hwrev: 1 sur toutes"],
       ["V14", "Watchdog / RTC", "ABSENT", "aucun watchdog dans le firmware (trou FW, backlog #7)"],
       ["V15", "Acquisition E2E", "PASS", "record bouton + parse : miniSEED 3 voies date GNSS"],
       ["CFG", "Config USB", "PASS (8)", "CONFIG SET/GET aller-retour"]])

# ============================ 4. FLOTTE ============================
heading("4. Resultats acceptation flotte (8 unites config-production)", 1)
table(["Unite", "Overall", "V1", "V13", "V6", "CFG", "V11", "V7", "V2", "V8"],
      [["CG0-000001", "PASS", "OK", "OK", "OK", "OK", "OK", "OK", "OK", "OK"],
       ["CG0-000002", "PASS", "OK", "OK", "OK", "OK", "OK", "OK", "OK", "OK"],
       ["CG0-000003", "PASS", "OK", "OK", "OK", "OK", "OK", "OK", "OK", "OK"],
       ["CG0-000004", "PASS", "OK", "OK", "OK", "OK", "OK", "OK", "OK", "OK"],
       ["CG0-000005", "PASS", "OK", "OK", "OK", "OK", "OK", "OK", "OK", "OK"],
       ["CG0-000006", "PASS", "OK", "OK", "OK", "OK", "OK", "OK", "OK", "OK"],
       ["CG0-000007", "PASS", "OK", "OK", "OK", "OK", "OK", "OK", "OK", "OK"],
       ["CG0-000009", "WARN", "OK", "OK", "OK", "OK", "OK", "OK", "!", "OK"]])
para("7 PASS · 1 WARN · 0 FAIL. 009·V2 = saturation d'un ancien enregistrement a forte amplitude "
     "teste (l'amplitude reflete le run, pas la sante de la voie). Resultats bruts : "
     "data/acceptance/*.json.")

# ============================ 5. CARACTERISATION ============================
heading("5. Caracterisation metrologique (calibration)", 1)
para("Reponse en frequence 3 axes de CG0-000009 (banc shaker APS + accelero de ref. NI), "
     "0,2–100 Hz, correlation par segmentation :")
table(["Axe", "voie", "plateau V/(m/s)", "pic (resonance)", "zeta"],
      [["X", "ch1", "~160", "~234 @ 4-5 Hz", "0,41"],
       ["Y", "ch2", "~160", "~250 @ 4-5 Hz", "0,37"],
       ["Z", "ch3", "~157", "~510 @ 5-6 Hz", "0,23"]])
para("Geophone UHS confirme ; Z nettement plus haut-Q (repete 2x, ecarts <= 8 %). Plateau "
     "homogene ~155-160 sur les 3 axes -> chaine de mesure saine.")
note("Convention de pleine echelle TRANCHEE le 2026-09-02 sur la fiche ADS1285 : ±VREF/(1,6384 x "
     "Gain) = ±2,5 V a gain 1 pour notre reference de 4,096 V. La fiche donne trois expressions "
     "selon la reference employee (VREF/2 pour 5 V, VREF/1,6384 pour 4,096 V, VREF pour 2,5 V) qui "
     "valent TOUTES ±2,5 V ; confirmation au §7.5, qui recommande 2,4 V pour l'etalonnage de gain — "
     "impossible si la pleine echelle valait 2,048 V. Les sensibilites ci-dessus, calculees avec "
     "±2,5 V, sont donc correctes et inchangees. C'est le rapport de bruit produit qui etait faux "
     "(il concluait ±VREF/2 par elimination entre deux hypotheses dont la bonne etait absente) ; "
     "il a ete corrige, toutes ses valeurs en volts multipliees par 1,2207.")

heading("5.2 Bruit propre de la chaine d'acquisition (ACQ-09) — ADS1285", 2)
para("Validation du bruit propre de l'electronique (ADC + PGA), entrees court-circuitees (MUX "
     "ADS1285 en court, 400 ohm, aucun geophone), sur CG0-000006 — le test « design vs fiche "
     "ADS1285 ». 4 gains, 634-708 s, PSD Welch moyennee sur les 3 voies, compare a la table 6-1 "
     "de la fiche. Doc canonique : geophones-product/docs/bruit-plancher-v31.md.")
table(["Gain", "Bruit mesure", "Fiche ADS1285", "Ecart", "Dynamique mesuree"],
      [["1", "0,271 uVrms", "0,25", "+8 %", "134,6 dB (22,1 bits)"],
       ["2", "0,156 uVrms", "0,14", "+11 %", "133,3 dB"],
       ["8", "0,064 uVrms", "0,07", "-9 %", "129,0 dB"],
       ["16", "0,054 uVrms", "0,06", "-10 %", "124,4 dB"]])
para("Verdict : PASS — la chaine se comporte comme le composant l'annonce : les 4 gains collent "
     "a la fiche a ±11 %, aucun bruit parasite ajoute par la carte (non trivial sur un 1er proto). "
     "Les 3 voies sont equivalentes a quelques %. Bruit 1/f classique (pente f^-0,44), coude "
     "passant de 3,23 Hz (g1) a 0,15 Hz (g16).")
para("Point d'attention ANT : la bande 0,1-1 Hz est entierement en zone 1/f (bruit x3-8 vs "
     "plancher) — la ou le geophone produit le moins. Le gain corrige largement (÷10-12 a g16) au "
     "prix de la pleine echelle (±128 mV). Choix du gain de production ouvert (ACQ-09) : gain 2 "
     "quasi gratuit (-1,2 dB), gain 16 le moins bruyant en bande ANT. Mesure sans geophone — a "
     "refaire capteur raccorde pour la chaine complete.")

heading("5.3 Campagne de calibration geophones (banc mono-axe V/H)", 2)
para("8 geophones caracterises en frequence 0,1-100 Hz sur les 2 axes independants "
     "(2026-06-05 au 08), data/rapport_geophones_ALL_2026-06-08/.")
table(["Geophone", "Axe", "Sensibilite", "Spec", "f0 / zeta", "Verdict"],
      [["ST-2A", "V/H", "294 / 272 V/(m/s)", "260", "3,3 / 5,9 Hz", "excellent (datasheet ±5-13 %)"],
       ["HG-6 (XT UB / HB)", "V/H", "38 / 36", "28,8", "5,4 / 6,5 Hz", "conforme (classe HGS)"],
       ["HG-5VHS", "V", "118", "100", "4,5 / 0,63", "conforme"],
       ["HG-2 U", "V", "170", "~50 (est.)", "3,6 / 0,52", "spec a confirmer"],
       ["VAS-200 / VAS-H-200", "V/H", ">=141 / >=145", "220", "anomalie", "a rebalayer > 100 Hz"]])
para("Validation croisee : 3 familles mesurees sur les deux chaines V/H totalement separees "
     "concordent a ±4 % (ST-2A 294/272, HG-6 38/36, VAS 141/145) + ST-2A concorde a la datasheet "
     "(+5-13 %) -> metrologie des deux bancs validee. Plancher de bruit accelero de ref. : "
     "V = 0,62 mg RMS · H = 0,57 mg RMS (2026-05-28) — fixe la limite basse frequence (sous "
     "~1-2 Hz, SNR < 20 dB : course shaker ±38 mm + plancher + roll-off f² du geophone ; limite "
     "physique, non logicielle).")

# ============================ 6. BANC / INSTRUMENTATION ============================
heading("6. Validation banc / instrumentation", 1)
bullet("1PPS : ProPak sur PFI0 de la crate NI = 0,99 Hz (stable).")
bullet("GNSS : fix unite (LC86G) et reference (ProPak) confirmes en exterieur/antenne.")
bullet("Correlation temporelle (TIME-05) : pipeline materiel operationnel. CAUSE RACINE DU BRUIT "
       "IDENTIFIEE (tools/pps_stability.py, run GNSS fixe) : les horodatages .dat sont quantifies "
       "a 3,9 ms (1/256 s) — la RTC STM32 tourne au prescaler par defaut. La cadence est saine "
       "(250,073 Hz, +291 ppm quartz ADC) et suit l'UTC record par record (pas de derive), mais "
       "3,9 ms est le plancher de precision. Fix : prescaler RTC async ~0 / sync ~32767 -> ~30 us "
       "(x128), puis re-mesurer TIME-05 (backlog FW #8). Un saut d'horodatage occasionnel "
       "(~140 ms au demarrage) reste a qualifier.")
bullet("Holdover PPS (V5) (tools/v5_holdover.py, antenne debranchee en cours d'acquisition) : RTC "
       "en holdover -> derive ~16 ppm (~1,4 s/jour) sur le LSE seul. Discipline sous PPS : pas de "
       "derive tant que le fix tient. Le saut de recalage a la reprise du fix n'a pas encore ete "
       "capture (warm start > fenetre, puis coupure batterie) -> a reconfirmer, batterie chargee, "
       "3 min apres rebranchement.")

# ============================ 7. COUVERTURE ============================
heading("7. Couverture — points a completer", 1)
bullet("V3 (synchro inter-voies) : PASS par conception — common ADC clock + ligne SYNC (MCU PD4) "
       "cablees aux 3 ADS1285 (netlist), horodatage inter-voies aligne (0,000 ech). Le test par tap "
       "confond la mecanique des 3 axes ; confirmation empirique = injection electrique commune "
       "(J4/J5/J6, board 008).")
bullet("V5 (derive/recalage PPS) : bien caracterise — cadence stable, holdover ~16 ppm, plancher "
       "3,9 ms identifie ; reste a capturer visuellement le recalage (batterie chargee + 3 min).")
bullet("V14 (watchdog) : ABSENT du firmware (verifie — aucun CONFIG_WATCHDOG/wdt_feed). Trou "
       "firmware : les gels observes ont exige un reset manuel. A implementer (backlog #7, prio "
       "haute) puis tester par hang volontaire. Incoherence : la matrice V&V produit marque "
       "FW-03 « couvert ».")

# ============================ 8. FINDINGS ============================
heading("8. Findings & backlog firmware", 1)
para("Traces au backlog geophones-firmware/doc/test-bench-to-production.md :")
numbered("TX CDC non-bloquante (CDC_LARGE_TX) -> a porter en production (robustesse generale).")
numbered("START/STOP idempotents BLE -> correctif controle app (le BLE reste un toggle).")
numbered("Jauge batterie fausse (dans les deux sens) : sous-estime en haut (74 % a 7,57 V pleine) "
         "ET surestime en bas (a lu 74 % puis s'est eteint faute de charge) + glitches. Observation "
         "liee : le board s'est eteint alors que l'USB etait branche -> l'USB ne semble pas "
         "alimenter/charger (gotcha HW J8-USB-sans-GND) -> autonomie = batterie seule, prevoir un "
         "vrai chargeur.")
numbered("Gel sous charge : autour de l'USB-pendant-acquisition (condition test-only ; en prod "
         "l'USB preempte l'acquisition). Reset manuel requis (cf. V14). A confirmer non-latent.")
numbered("Ecriture SD : open+append+close par record (durable mais lourd) -> keep-open + fs_sync "
         "periodique. records_per_file n'est pas un levier de securite (crash => <= 1 record perdu).")
numbered("Transfert CDC — corruption EN TRANSIT (prouve) : meme .dat recupere 3x -> 3 md5 "
         "differents, corruption a positions differentes/nulle -> le lien USB-CDC corrompt, la SD "
         "est intacte. ~0,2-0,5 % de records. Recuperable sans perte par CRC + retry.")
numbered("Watchdog ABSENT (V14) : pas d'auto-recuperation sur hang -> hang = reset manuel. "
         "Implementer CONFIG_TASK_WDT + IWDG (prio haute, fiabilite terrain).")
numbered("Horodatage RTC quantifie a 3,9 ms (1/256 s) = plancher TIME-05. Reconfigurer le "
         "prescaler RTC (async ~0 / sync ~32767) -> ~30 us (prio haute pour l'ANT).")

# ============================ 9. CONCLUSION ============================
heading("9. Conclusion & suites", 1)
para("GO pour le design : flotte homogene, saine, aucun FAIL. La chaine ADC est conforme a sa "
     "fiche. Suivis :", bold=True)
bullet("Correctifs firmware (non bloquants) : jauge batterie + charge/USB · BLE idempotent · "
       "integrite+retry transfert CDC · TX CDC en prod · ecriture SD · prescaler RTC (debloque "
       "TIME-05) · watchdog (fiabilite terrain).")
bullet("Convention de pleine echelle ADC : RESOLUE (2026-09-02) a ±2,5 V a gain 1 sur la fiche "
       "ADS1285. Les sensibilites 3 axes de ce rapport sont inchangees ; c'est le rapport de "
       "bruit produit qui a ete corrige.")
bullet("Completer la couverture : V3 (injection electrique), V5 (capturer le recalage PPS), "
       "V14 (implementer le watchdog).")
bullet("Choix du gain de production (ACQ-09) : arbitrer bruit BF vs pleine echelle sur "
       "l'amplitude geophone max (mesure capteur raccorde).")
bullet("CG0-000008 : retablir la config prod puis re-accepter, ou statuer « exclu ».")
bullet("Calibration ANT : StationXML + convention SID (DATA-07) avec le geophysicien.")

doc.add_paragraph()
para("Genere a partir de docs/vv-campaign-report.md (resultats data/acceptance/*.json, "
     "caracterisation data/3axis/, backlog firmware, doc bruit produit).", italic=True,
     size=8.5, color=GREY)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
doc.save(OUT)
print(f"OK -> {OUT}")

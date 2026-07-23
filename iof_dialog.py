# -*- coding: utf-8 -*-
"""
IOF Exporter - Diàleg d'exportació
Genera el fitxer TXT per importació a PDF.

Format de cada registre: ID#CODI#MIDA#FORESTAL#ARBRAT#TIPUSZZ

Millores incloses:
  - #2  Capçalera identificativa al fitxer exportat (versió + data)
  - #3  Log d'exportació al costat del fitxer TXT
  - #8  QSettings per recordar l'últim directori d'exportació
"""

import os
import datetime
import re
from collections import defaultdict

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFileDialog,
    QGroupBox, QMessageBox,
    QTextEdit, QScrollArea, QWidget, QGridLayout,
)
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes

from .iof_utils import get_layer as _get_std_layer
from .iof_utils import find_interior_polygons, finca_te_unitats_completes

PLUGIN_VERSION = "1.0.2"
SETTINGS_KEY_DIR = "iof_assistent/last_export_dir"

FIELD_NOT_USED = "(no s'utilitza)"

STD_LAYER_NAMES = {
    "finques": "IOF_Finques",
    "unitats": ["IOF_Unitats_Actuacio", "IOF_Rodals"],
    "camins": "IOF_Camins",
    "canvis_us": "IOF_Canvis_Us",
    "infraestructures": "IOF_Infraestructures_PI",
    "punts_aigua": "IOF_Punts_Aigua",
    "elements_singulars": "IOF_Elements_Singulars",
    "punts_inventari": "IOF_Punts_Inventari",
}


def _unitats_codi_field(layer):
    field_names = {f.name() for f in layer.fields()}
    if "codi_ua" in field_names:
        return "codi_ua"
    if "codi_rodal" in field_names:
        return "codi_rodal"
    return None


LAYER_CONFIGS = {
    "finques": {
        "label": "Finques",
        "geom": ["Polygon"],
        "fields": [
            ("codi_finca", "Codi de finca", True),
            ("nom_finca", "Nom de la finca", False),
            ("municipi", "Municipi", True),
            ("comarca", "Comarca", False),
            ("superficie", "Superfície (ha)", False),
        ],
    },
    "unitats": {
        "label": "Unitats d'actuació / Rodals",
        "geom": ["Polygon"],
        "fields": [
            ("codi_ua", "Codi UA / Rodal", True),
            ("for_forestal", "Formació forestal", False),
            ("codi_us", "Codi d'ús", False),
            ("sup_forestal", "Sup. forestal (ha)", False),
            ("sup_arbrada", "Sup. arbrada (ha)", False),
        ],
    },
    "camins": {
        "label": "Camins",
        "geom": ["Line"],
        "fields": [
            ("codi_cami", "Codi del camí", True),
            ("longitud", "Longitud dins IOF (m)", False),
        ],
    },
    "canvis_us": {
        "label": "Canvis d'ús",
        "geom": ["Polygon"],
        "fields": [
            ("codi_canvi", "Codi de canvi d'ús", True),
        ],
    },
    "infraestructures": {
        "label": "Infraestructures PI",
        "geom": ["Polygon"],
        "fields": [
            ("codi_infra", "Codi d'infraestructura", True),
        ],
    },
    "punts_aigua": {
        "label": "Punts d'aigua",
        "geom": ["Point"],
        "fields": [
            ("codi_pa", "Codi punt d'aigua", True),
        ],
    },
}


def _round_str(value, decimals=2):
    """Formata un valor numeric amb coma decimal, SENSE separador de
    milers — un punt de milers als números pot provocar errors en
    importar el fitxer de text al PDF."""
    if value is None or value == "":
        return ""
    try:
        s = f"{float(value):.{decimals}f}"
        # Coma decimal (no punt): 1234.56 -> 1234,56. Sense separador
        # de milers (no s'usa el format ",.{decimals}f" que n'afegiria).
        s = s.replace(".", ",")
        return s
    except (ValueError, TypeError):
        return str(value)


def _val(feature, field_name):
    if not field_name:
        return ""
    try:
        v = feature[field_name]
        if v is None or v != v:
            return ""
        return str(v).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Diàleg principal
# ---------------------------------------------------------------------------

class IOFExporterDialog(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("IOF Exporter — Exportació del fitxer TXT per a PDF")
        self.setMinimumWidth(720)
        self.setMinimumHeight(600)
        self._layer_combos = {}
        self._field_combos = {}
        self._build_ui()
        self._autodetect_layers()
        self._do_preview()

    # ------------------------------------------------------------------
    # Construcció de la interfície
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = QVBoxLayout(self)

        title = QLabel(
            "<b>Exportació de dades GIS per a l'elaboració d'un IOF</b>"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "padding:8px; background:#e8f4e8; border-radius:4px;"
        )
        main.addWidget(title)

        info = QLabel(
            "<small>ℹ️ Si has creat les capes amb <b>Crear capes IOF</b>, "
            "es detecten automàticament i els camps ja estan assignats.</small>"
        )
        info.setStyleSheet("padding:4px; color:#555;")
        main.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        for key, config in LAYER_CONFIGS.items():
            scroll_layout.addWidget(self._build_layer_group(key, config))

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        main.addWidget(scroll, stretch=3)

        prev_group = QGroupBox("Vista prèvia")
        prev_layout = QVBoxLayout(prev_group)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(110)
        self._preview.setStyleSheet("font-family:monospace; font-size:11px;")
        prev_layout.addWidget(self._preview)
        main.addWidget(prev_group)

        btn_layout = QHBoxLayout()

        btn_copy = QPushButton("Copiar al porta-retalls")
        btn_copy.setStyleSheet(
            "background:#1565c0; color:white; font-weight:bold; padding:6px 16px;"
        )
        btn_copy.clicked.connect(self._do_copy)

        btn_exp = QPushButton("Exportar fitxer TXT…")
        btn_exp.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:6px 16px;"
        )
        btn_exp.clicked.connect(self._do_export)

        btn_close = QPushButton("Tancar")
        btn_close.clicked.connect(self.close)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_copy)
        btn_layout.addWidget(btn_exp)
        btn_layout.addWidget(btn_close)
        main.addLayout(btn_layout)

    def _build_layer_group(self, key, config):
        group = QGroupBox(config["label"])
        layout = QGridLayout(group)

        combo_layer = QComboBox()
        combo_layer.addItem("(no seleccionada)", None)
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                geom_type = QgsWkbTypes.geometryDisplayString(lyr.geometryType())
                if any(g.lower() in geom_type.lower() for g in config["geom"]):
                    combo_layer.addItem(f"{lyr.name()}  [{geom_type}]", lyr.id())
        combo_layer.currentIndexChanged.connect(
            lambda _, k=key: self._on_layer_changed(k)
        )
        self._layer_combos[key] = combo_layer
        layout.addWidget(QLabel("Capa:"), 0, 0)
        layout.addWidget(combo_layer, 0, 1, 1, 3)

        self._field_combos[key] = {}
        for row, (fkey, flabel, required) in enumerate(config["fields"], start=1):
            combo_field = QComboBox()
            combo_field.addItem(
                "(selecciona camp…)" if required else FIELD_NOT_USED, None
            )
            self._field_combos[key][fkey] = combo_field
            layout.addWidget(
                QLabel(f"{flabel}{' *' if required else ''}:"), row, 0
            )
            layout.addWidget(combo_field, row, 1, 1, 3)

        layout.setColumnStretch(1, 1)
        return group

    def _autodetect_layers(self):
        layers_by_name = {
            lyr.name(): lyr
            for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer)
        }
        for key, std_name in STD_LAYER_NAMES.items():
            if key not in self._layer_combos:
                continue
            combo = self._layer_combos[key]
            candidates = std_name if isinstance(std_name, list) else [std_name]
            lyr = next(
                (layers_by_name[n] for n in candidates if n in layers_by_name), None
            )
            if not lyr:
                continue

            if key == "unitats":
                label = (
                    "Rodals"
                    if lyr.name() == "IOF_Rodals"
                    else "Unitats d'actuació"
                )
                for grp in self.findChildren(
                    __import__(
                        "qgis.PyQt.QtWidgets", fromlist=["QGroupBox"]
                    ).QGroupBox
                ):
                    if "actuació" in grp.title() or "Rodal" in grp.title():
                        grp.setTitle(label)
                        break

            for i in range(combo.count()):
                if combo.itemData(i) == lyr.id():
                    combo.setCurrentIndex(i)
                    break

            config = LAYER_CONFIGS[key]
            field_names = {f.name() for f in lyr.fields()}
            for fkey, _, _ in config["fields"]:
                actual_fkey = fkey
                if fkey == "codi_ua" and "codi_ua" not in field_names:
                    actual_fkey = "codi_rodal"
                fc = self._field_combos[key].get(fkey)
                if fc and actual_fkey in field_names:
                    for j in range(fc.count()):
                        if fc.itemData(j) == actual_fkey:
                            fc.setCurrentIndex(j)
                            break

    def _on_layer_changed(self, key):
        combo_layer = self._layer_combos[key]
        layer_id = combo_layer.currentData()
        layer = QgsProject.instance().mapLayer(layer_id) if layer_id else None
        config = LAYER_CONFIGS[key]
        for fkey, _, required in config["fields"]:
            combo_field = self._field_combos[key][fkey]
            combo_field.clear()
            combo_field.addItem(
                "(selecciona camp…)" if required else FIELD_NOT_USED, None
            )
            if layer:
                for field in layer.fields():
                    combo_field.addItem(field.name(), field.name())
                field_names = {f.name() for f in layer.fields()}
                if fkey in field_names:
                    for j in range(combo_field.count()):
                        if combo_field.itemData(j) == fkey:
                            combo_field.setCurrentIndex(j)
                            break

    # ------------------------------------------------------------------
    # Accessors interns
    # ------------------------------------------------------------------

    def _get_layer(self, key):
        lid = self._layer_combos[key].currentData()
        return QgsProject.instance().mapLayer(lid) if lid else None

    def _get_field(self, key, fkey):
        c = self._field_combos[key].get(fkey)
        return c.currentData() if c else None

    # ------------------------------------------------------------------
    # Generació de línies
    # ------------------------------------------------------------------

    def _build_header(self):
        """Retorna la línia de capçalera (#2)."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"# IOF Assistent v{PLUGIN_VERSION} — Exportat el {now}"

    def _generate_lines(self, include_header=True):
        lines = []
        if include_header:
            lines.append(self._build_header())

        # FI — Finques
        lyr = self._get_layer("finques")
        if lyr and lyr.featureCount() > 0:
            f_codi = self._get_field("finques", "codi_finca")
            f_nom = self._get_field("finques", "nom_finca")
            f_munis = self._get_field("finques", "municipi")
            f_com = self._get_field("finques", "comarca")
            f_sup = self._get_field("finques", "superficie")
            finques_data = {}
            for feat in lyr.getFeatures():
                codi = _val(feat, f_codi)
                if not codi or codi == "NULL":
                    continue
                # Geometria o camp superficie
                if f_sup:
                    try:
                        area = float(_val(feat, f_sup) or 0)
                    except (ValueError, TypeError):
                        area = feat.geometry().area() / 10000 if feat.geometry() else 0.0
                else:
                    area = feat.geometry().area() / 10000 if feat.geometry() else 0.0
                nom = _val(feat, f_nom) if f_nom else ""
                municipi = _val(feat, f_munis)
                comarca = _val(feat, f_com) if f_com else ""
                if codi not in finques_data:
                    finques_data[codi] = {
                        "area": 0.0, "nom": nom,
                        "municipis": set(), "comarca": comarca
                    }
                finques_data[codi]["area"] += area
                if municipi:
                    for m in municipi.split(","):
                        m = m.strip()
                        if m:
                            finques_data[codi]["municipis"].add(m)
            for codi, data in sorted(
                finques_data.items(),
                key=lambda x: (int(x[0]) if str(x[0]).isdigit() else 0),
            ):
                mida = _round_str(data["area"])
                munis = ",".join(sorted(data["municipis"]))
                lines.append(f"FI#{codi}#{mida}###{munis}ZZ")

        # UT + US — Unitats
        lyr = self._get_layer("unitats")
        if lyr and lyr.featureCount() > 0:
            f_ua = self._get_field("unitats", "codi_ua")
            if not f_ua:
                field_names = {f.name() for f in lyr.fields()}
                f_ua = "codi_rodal" if "codi_rodal" in field_names else None
            f_ff = self._get_field("unitats", "for_forestal")
            f_us = self._get_field("unitats", "codi_us")
            f_sfo = self._get_field("unitats", "sup_forestal")
            f_sar = self._get_field("unitats", "sup_arbrada")

            ua_data = defaultdict(lambda: {
                "area": 0.0, "for_forestal": "",
                "sup_forestal": "", "sup_arbrada": "",
                "usos": set(),
            })
            for feat in lyr.getFeatures():
                codi_ua = _val(feat, f_ua)
                if not codi_ua:
                    continue
                ua_data[codi_ua]["area"] += (
                    feat.geometry().area() / 10000 if feat.geometry() else 0.0
                )
                if _val(feat, f_ff):
                    ua_data[codi_ua]["for_forestal"] = _val(feat, f_ff)
                v_sfo = _val(feat, f_sfo)
                v_sar = _val(feat, f_sar)
                if v_sfo != "":
                    try:
                        ua_data[codi_ua]["sup_forestal"] = (
                            float(ua_data[codi_ua]["sup_forestal"] or 0) + float(v_sfo)
                        )
                    except (ValueError, TypeError):
                        ua_data[codi_ua]["sup_forestal"] = v_sfo
                if v_sar != "":
                    try:
                        ua_data[codi_ua]["sup_arbrada"] = (
                            float(ua_data[codi_ua]["sup_arbrada"] or 0) + float(v_sar)
                        )
                    except (ValueError, TypeError):
                        ua_data[codi_ua]["sup_arbrada"] = v_sar
                if _val(feat, f_us):
                    ua_data[codi_ua]["usos"].add(_val(feat, f_us))

            for codi_ua, d in sorted(ua_data.items()):
                mida = _round_str(d["area"])
                sf = d["sup_forestal"]
                sa = d["sup_arbrada"]
                forestal = _round_str(sf) if sf != "" else mida
                arbrada = _round_str(sa) if sa != "" else "0"
                tipus = d["for_forestal"]
                lines.append(f"UT#{codi_ua}#{mida}#{forestal}#{arbrada}#{tipus}ZZ")
                for us_code in sorted(d["usos"]):
                    lines.append(f"US#{codi_ua}####{us_code}ZZ")

        # CA — Camins
        lyr = self._get_layer("camins")
        if lyr and lyr.featureCount() > 0:
            f_codi = self._get_field("camins", "codi_cami")
            f_long = self._get_field("camins", "longitud")
            JERARQUIA = {"PR": 0, "PM": 1, "SC": 2, "DB": 3}

            def _sort_cami(feat):
                codi = _val(feat, f_codi) or ""
                prefix = codi[:2].upper()
                ordre = JERARQUIA.get(prefix, 99)
                m = re.search(r'(\d+)', codi[2:])
                num = int(m.group(1)) if m else 0
                return (ordre, num, codi)

            for feat in sorted(lyr.getFeatures(), key=_sort_cami):
                codi = _val(feat, f_codi)
                if not codi:
                    continue
                if f_long and feat[f_long] and feat[f_long] == feat[f_long]:
                    mida = _round_str(feat[f_long])
                else:
                    mida = (
                        _round_str(feat.geometry().length())
                        if feat.geometry() else ""
                    )
                lines.append(f"CA#{codi}#{mida}#0#0#ZZ")

        # IE — Canvis d'ús
        lyr = self._get_layer("canvis_us")
        if lyr and lyr.featureCount() > 0:
            f_codi = self._get_field("canvis_us", "codi_canvi")
            for feat in lyr.getFeatures():
                codi = _val(feat, f_codi)
                mida = (
                    _round_str(feat.geometry().area() / 10000)
                    if feat.geometry() else ""
                )
                lines.append(f"IE#{codi}#{mida}###ZZ")

        # IE — Infraestructures PI
        lyr = self._get_layer("infraestructures")
        if lyr and lyr.featureCount() > 0:
            f_codi = self._get_field("infraestructures", "codi_infra")
            for feat in lyr.getFeatures():
                codi = _val(feat, f_codi)
                mida = (
                    _round_str(feat.geometry().area() / 10000)
                    if feat.geometry() else ""
                )
                lines.append(f"IE#{codi}#{mida}###ZZ")

        # IE — Punts d'aigua
        lyr = self._get_layer("punts_aigua")
        if lyr and lyr.featureCount() > 0:
            f_codi = self._get_field("punts_aigua", "codi_pa")
            for feat in lyr.getFeatures():
                codi = _val(feat, f_codi)
                coords = ""
                if feat.geometry() and not feat.geometry().isEmpty():
                    pt = feat.geometry().asPoint()
                    coords = f"{int(pt.x())},{int(pt.y())}"
                lines.append(f"IE#{codi}####{coords}ZZ")

        lines.append("FINAL DEL PROGRAMA")
        return lines

    # ------------------------------------------------------------------
    # Log d'exportació (#3)
    # ------------------------------------------------------------------

    def _write_log(self, output_path, lines):
        """Escriu el fitxer .log al costat del TXT exportat."""
        log_path = os.path.splitext(output_path)[0] + "_exportacio.log"
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Comptar registres per tipus
        counts = {"FI": 0, "UT": 0, "US": 0, "CA": 0, "IE": 0}
        for line in lines:
            prefix = line[:2]
            if prefix in counts:
                counts[prefix] += 1

        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"# Log d'exportació IOF Assistent v{PLUGIN_VERSION}\n")
            f.write(f"# Data i hora : {now}\n")
            f.write(f"# Fitxer TXT  : {os.path.basename(output_path)}\n")
            f.write(f"# Projecte    : {QgsProject.instance().fileName() or '(sense guardar)'}\n")
            f.write("\n")
            f.write("## Resum de registres exportats\n")
            f.write(f"  FI (Finques)           : {counts['FI']}\n")
            f.write(f"  UT (Unitats)           : {counts['UT']}\n")
            f.write(f"  US (Usos vegetació)    : {counts['US']}\n")
            f.write(f"  CA (Camins)            : {counts['CA']}\n")
            f.write(f"  IE (Infra/Canvis/Punt) : {counts['IE']}\n")
            total = sum(counts.values())
            f.write(f"  TOTAL                  : {total}\n")

        return log_path

    # ------------------------------------------------------------------
    # Últim directori exportat (#8)
    # ------------------------------------------------------------------

    def _last_export_dir(self):
        return QSettings().value(SETTINGS_KEY_DIR, "")

    def _save_export_dir(self, path):
        QSettings().setValue(SETTINGS_KEY_DIR, os.path.dirname(path))

    # ------------------------------------------------------------------
    # Accions principals
    # ------------------------------------------------------------------

    def _do_copy(self):
        if not self._validate_obligatories():
            return
        try:
            lines = self._generate_lines(include_header=False)
            text = "\n".join(lines) + "\n"
            from qgis.PyQt.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            self._preview.setPlainText("\n".join(lines[:25]))
            QMessageBox.information(
                self, "Copiat",
                f"El text ({len(lines) - 1} registres) s'ha copiat al porta-retalls.\n\n"
                "Ara pots enganxar-lo directament al PDF."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error generant el text:\n{e}")

    def _layer_status(self, key):
        """
        Retorna ('buida' | 'incompleta' | 'correcta', [detalls]) per a
        la capa seleccionada per a `key`.
        """
        lyr = self._get_layer(key)
        if not lyr or lyr.featureCount() == 0:
            return "buida", []

        config = LAYER_CONFIGS[key]
        problemes = []
        for fkey, flabel, required in config["fields"]:
            if not required:
                continue
            actual_fkey = self._get_field(key, fkey)
            if not actual_fkey:
                problemes.append(f"no s'ha assignat el camp «{flabel}»")
                continue

            if key == "unitats" and fkey == "codi_ua":
                # Les unitats que només tenen codi_us (p.ex. edificis,
                # conreus, erm...) no necessiten un codi_ua propi — no
                # compten com a incompletes només per no tenir-lo,
                # sempre que sí que tinguin codi_us assignat. Mateix
                # criteri que ja fa servir iof_format_dialog.py per no
                # generar-los un límit de rodal propi.
                f_us = self._get_field("unitats", "codi_us")
                n_buits = sum(
                    1 for feat in lyr.getFeatures()
                    if not _val(feat, actual_fkey)
                    and not (f_us and _val(feat, f_us))
                )
            else:
                n_buits = sum(
                    1 for feat in lyr.getFeatures() if not _val(feat, actual_fkey)
                )
            if n_buits > 0:
                problemes.append(f"{n_buits} element(s) sense «{flabel}»")

        if key == "unitats":
            finca_lyr = _get_std_layer("IOF_Finques")
            if finca_lyr is not None and finca_lyr.featureCount() > 0:
                all_finques = list(finca_lyr.getFeatures())
                exclusion_ids = find_interior_polygons(all_finques)
                finques_valides = [
                    f for f in all_finques if f.id() not in exclusion_ids
                ]
                incompletes_finques = [
                    f for f in finques_valides
                    if not finca_te_unitats_completes(lyr, f)
                ]
                if incompletes_finques:
                    problemes.append(
                        f"{len(incompletes_finques)} finca(es) sense "
                        f"tipologies forestals completes"
                    )

        if problemes:
            return "incompleta", problemes
        return "correcta", []

    def _validate_obligatories(self, silent=False):
        if silent:
            return True

        buides, incompletes, correctes = [], [], []
        for key, config in LAYER_CONFIGS.items():
            status, detalls = self._layer_status(key)
            label = config["label"]
            if status == "buida":
                buides.append(label)
            elif status == "incompleta":
                incompletes.append((label, detalls))
            else:
                correctes.append(label)

        if not buides and not incompletes:
            # Tot correcte: no cal amoïnar l'usuari amb un diàleg.
            return True

        text = "Abans d'exportar, revisa l'estat de les capes:\n\n"
        if incompletes:
            text += "⚠️ Amb dades incompletes:\n"
            for label, detalls in incompletes:
                text += f"  • {label}: {'; '.join(detalls)}\n"
            text += "\n"
        if buides:
            text += "🔲 Buides (no exportaran cap dada):\n"
            for label in buides:
                text += f"  • {label}\n"
            text += "\n"
        if correctes:
            text += "✅ Correctes:\n"
            for label in correctes:
                text += f"  • {label}\n"
            text += "\n"
        text += "Vols continuar amb l'exportació de totes maneres?"

        resposta = QMessageBox.question(
            self, "Revisió abans d'exportar", text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return resposta == QMessageBox.StandardButton.Yes

    def _do_preview(self, silent=True):
        if not self._validate_obligatories(silent=silent):
            return
        try:
            lines = self._generate_lines(include_header=False)
            preview = lines[:20]
            text = "\n".join(preview)
            if len(lines) > 21:
                text += f"\n… ({len(lines) - 21} línies més) …\n{lines[-1]}"
            self._preview.setPlainText(text)
        except Exception as e:
            if not silent:
                QMessageBox.critical(
                    self, "Error", f"Error generant la vista prèvia:\n{e}"
                )

    def _do_export(self):
        if not self._validate_obligatories():
            return

        # Diàleg de fitxer, recordant l'últim directori (#8)
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Desa el fitxer TXT",
            self._last_export_dir(),
            "Fitxers de text (*.txt)",
        )
        if not output_path:
            return
        if not output_path.endswith(".txt"):
            output_path += ".txt"

        self._save_export_dir(output_path)

        try:
            lines = self._generate_lines(include_header=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

            # Escriure log (#3)
            log_path = self._write_log(output_path, lines)

            self._preview.setPlainText("\n".join(lines[:25]))

            # Comptar registres (excloure capçalera i "FINAL DEL PROGRAMA")
            data_lines = [
                line for line in lines
                if line and not line.startswith("#") and line != "FINAL DEL PROGRAMA"
            ]
            QMessageBox.information(
                self, "Exportació completada",
                f"Fitxer generat:\n{output_path}\n\n"
                f"Registres exportats: {len(data_lines)}\n\n"
                f"Log d'exportació:\n{log_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error d'exportació", f"Error:\n{e}")

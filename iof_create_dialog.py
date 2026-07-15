# -*- coding: utf-8 -*-
"""
IOF Create Dialog
Crea les 8 capes vectorials d'un IOF amb tots els camps necessaris
per a la seva edició i posterior exportació al fitxer TXT per a PDF.

Capes creades:
  1. Finques               (Polígon)
  2. Unitats d'actuació    (Polígon)
  3. Camins                (Línia)
  4. Canvis d'ús           (Polígon)
  5. Infraestructures PI   (Polígon)
  6. Punts d'aigua         (Punt)
  7. Elements singulars    (Punt)
  8. Punts d'inventari     (Punt)
"""

import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFileDialog, QGroupBox,
    QMessageBox, QProgressBar, QCheckBox, QComboBox,
    QFrame, QScrollArea, QWidget, QRadioButton,
    QButtonGroup
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsVectorFileWriter,
    QgsField, QgsFields, QgsCoordinateReferenceSystem
)
from qgis.PyQt.QtCore import QVariant


# ---------------------------------------------------------------------------
# Definició de les 8 capes IOF amb tots els seus camps
# ---------------------------------------------------------------------------
# Format de cada camp: (nom, tipus_QVariant, longitud, precisió, alias, comentari)

IOF_LAYERS = [
    {
        "id": "finques",
        "name": "IOF_Finques",
        # MultiPolygon (no Polygon): una finca amb un camí que la travessa
        # de banda a banda ha de poder quedar com a 2 parts separades en
        # lloc d'un únic polígon amb un forat que "surt" del contorn
        # (invàlid: "Hole lies outside shell").
        "geom": "MultiPolygon",
        "label": "1. Finques",
        "color": "#e8f5e9",
        "fields": [
            ("codi_finca", QVariant.Int, 10, 0,
             "Codi de finca",
             "Codi numeric identificador de la finca"),
            ("nom_finca", QVariant.String, 200, 0,
             "Nom de la finca",
             "Nom o denominacio de la finca"),
            ("municipi", QVariant.String, 150, 0,
             "Municipi",
             "Municipi on s'ubica la finca"),
            ("comarca", QVariant.String, 100, 0,
             "Comarca",
             "Comarca on s'ubica la finca"),
            ("superficie", QVariant.Double, 10, 2,
             "Superficie (ha)",
             "Superficie calculada en hectarees (camp calculat)"),
        ],
    },
    {
        "id": "punts_aigua",
        "name": "IOF_Punts_Aigua",
        "geom": "Point",
        "label": "2. Punts d'aigua",
        "color": "#e1f5fe",
        "fields": [
            ("codi_pa", QVariant.String, 10, 0,
             "Codi punt d'aigua",
             "Codi del punt d'aigua (p.ex. PA01E, PA02P...)"),
            ("estat", QVariant.String, 1, 0,
             "Estat",
             "E=Existent, P=Projectat"),
            ("coord_x", QVariant.Double, 15, 2,
             "Coord. X (UTM)",
             "Coordenada X en UTM (camp calculat)"),
            ("coord_y", QVariant.Double, 15, 2,
             "Coord. Y (UTM)",
             "Coordenada Y en UTM (camp calculat)"),
        ],
    },
    {
        "id": "elements_singulars",
        "name": "IOF_Elements_Singulars",
        "geom": "Point",
        "label": "3. Elements singulars",
        "color": "#f3e5f5",
        "fields": [
            ("tipus_elem", QVariant.String, 20, 0,
             "Tipus d'element",
             "arquitectonic / natural"),
            ("nom_elem", QVariant.String, 255, 0,
             "Nom de l'element",
             "Nom de l'element singular (p.ex. Roure de Cal Peroi)"),
            ("coord_x", QVariant.Double, 15, 2,
             "Coord. X (UTM)",
             "Coordenada X en UTM (camp calculat)"),
            ("coord_y", QVariant.Double, 15, 2,
             "Coord. Y (UTM)",
             "Coordenada Y en UTM (camp calculat)"),
        ],
    },
    {
        "id": "punts_inventari",
        "name": "IOF_Punts_Inventari",
        "geom": "Point",
        "label": "4. Punts d'inventari",
        "color": "#efebe9",
        "fields": [
            ("codi_pi", QVariant.Int, 10, 0,
             "Numero d'inventari",
             "Numero identificador del punt d'inventari (autoincremental)"),
            ("coord_x", QVariant.Double, 15, 2,
             "Coord. X (UTM)",
             "Coordenada X en UTM (camp calculat)"),
            ("coord_y", QVariant.Double, 15, 2,
             "Coord. Y (UTM)",
             "Coordenada Y en UTM (camp calculat)"),
        ],
    },
    {
        "id": "camins",
        "name": "IOF_Camins",
        "geom": "LineString",
        "label": "5. Camins",
        "color": "#fff8e1",
        "fields": [
            ("codi_cami", QVariant.String, 10, 0,
             "Codi cami",
             "Codi del cami (p.ex. PR01E, SC02E, DB01P...)"),
            ("tipus_vial", QVariant.String, 5, 0,
             "Tipus de vial",
             "PR=Principal, PM=Primari, SC=Secundari, DB=Desembosc"),
            ("estat", QVariant.String, 1, 0,
             "Estat",
             "E=Existent, P=Projectat"),
            ("longitud", QVariant.Double, 10, 2,
             "Longitud (m)",
             "Longitud en metres (camp calculat)"),
        ],
    },
    {
        "id": "infraestructures",
        "name": "IOF_Infraestructures_PI",
        # MultiPolygon (no Polygon): restar/tallar geometries pot deixar
        # el polígon dividit en parts separades (vegeu el comentari a
        # "finques" més amunt per al motiu tècnic exacte).
        "geom": "MultiPolygon",
        "label": "6. Infraestructures de prevencio d'incendis",
        "color": "#fff3e0",
        "fields": [
            ("codi_infra", QVariant.String, 10, 0,
             "Codi infraestructura",
             "Codi de la infraestructura (p.ex. LD01E, LD01P...)"),
            ("tipus_infra", QVariant.String, 5, 0,
             "Tipus",
             "LD=Obertura linies de defensa"),
            ("estat", QVariant.String, 1, 0,
             "Estat",
             "E=Existent, P=Projectada"),
            ("superficie", QVariant.Double, 10, 4,
             "Superficie (ha)",
             "Superficie en hectarees (camp calculat)"),
        ],
    },
    {
        "id": "canvis_us",
        "name": "IOF_Canvis_Us",
        # MultiPolygon pel mateix motiu que "finques" i "infraestructures".
        "geom": "MultiPolygon",
        "label": "7. Canvis d'us",
        "color": "#fce4ec",
        "fields": [
            ("codi_canvi", QVariant.String, 10, 0,
             "Codi canvi d'us",
             "Codi del canvi d'us (p.ex. RM01, TP01...)"),
            ("tipus_canvi", QVariant.String, 2, 0,
             "Tipus",
             "RM=Rompuda, TP=Transformacio a pastures"),
            ("superficie", QVariant.Double, 10, 4,
             "Superficie (ha)",
             "Superficie en hectarees (camp calculat)"),
        ],
    },
    {
        "id": "unitats",
        "name": "IOF_Unitats_Actuacio",
        # MultiPolygon pel mateix motiu que "finques" — confirmat amb un
        # bug real (juliol 2026): _on_feature_added() a
        # iof_unitats_wizard.py resta el polígon nou del contenidor
        # (container_geom.difference(new_geom)), i si el resultat queda
        # dividit en parts separades, GEOS torna un MultiPolygon —
        # incompatible amb una capa definida com a "Polygon" estricte
        # ("geometry type is not compatible with the current layer").
        "geom": "MultiPolygon",
        "label": "8. Unitats d'actuacio",
        "color": "#e3f2fd",
        "fields": [
            ("codi_ua", QVariant.String, 10, 0,
             "Codi UA",
             "Codi de la unitat d'actuacio (1, 2, 3a, 3b...)"),
            ("for_forestal", QVariant.String, 50, 0,
             "Formacio forestal",
             "Codi de formacio forestal (Taula annexa 1, p.ex. PhLIT_Qib)"),
            ("codi_us", QVariant.String, 50, 0,
             "Codi d'us",
             "Codi de vegetacio/us (Taula annexa 2). Opcional."),
            ("sup_ord", QVariant.Double, 10, 4,
             "Sup. ordenada (ha)",
             "Superficie ordenada en hectarees (camp calculat)"),
            ("sup_forestal", QVariant.Double, 10, 4,
             "Sup. forestal (ha)",
             "Superficie forestal ordenada en hectarees"),
            ("sup_arbrada", QVariant.Double, 10, 4,
             "Sup. arbrada (ha)",
             "Superficie arbrada ordenada en hectarees"),
        ],
    },
]
# Tipus d'instrument
INSTRUMENT_PTGMF = "PTGMF"
INSTRUMENT_PSGF = "PSGF"

# Noms de la capa d'unitats segons instrument
UNITATS_CONFIG = {
    INSTRUMENT_PTGMF: {
        "layer_name": "IOF_Unitats_Actuacio",
        "layer_label": "8. Unitats d'actuació",
        "field_label": "Codi UA",
        "field_alias": "Codi d'unitat d'actuació",
        "field_name": "codi_ua",
    },
    INSTRUMENT_PSGF: {
        "layer_name": "IOF_Rodals",
        "layer_label": "8. Rodals",
        "field_label": "Codi rodal",
        "field_alias": "Codi de rodal",
        "field_name": "codi_rodal",
    },
}

# CRS recomanat per IOF a Catalunya
DEFAULT_CRS = "EPSG:25831"  # ETRS89 / UTM zona 31N


# ---------------------------------------------------------------------------
# Diàleg
# ---------------------------------------------------------------------------

class IOFCreateDialog(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("IOF Assistent — Crear capes IOF")
        self.setMinimumWidth(620)
        self.setMinimumHeight(600)
        self._layer_checks = {}   # id -> QCheckBox
        self._instrument = INSTRUMENT_PTGMF  # valor per defecte
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = QVBoxLayout(self)

        # Títol
        title = QLabel(
            "<b>Crear capes vectorials per a un IOF</b><br>"
            "<small>Es crearan les capes amb tots els camps necessaris "
            "per a la digitalització i exportació.</small>"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("padding:8px; background:#e8f4e8; border-radius:4px;")
        main.addWidget(title)

        # Tipus d'instrument
        inst_group = QGroupBox("Tipus d'instrument d'ordenació forestal")
        inst_layout = QHBoxLayout(inst_group)

        self._btn_ptgmf = QRadioButton(
            "PTGMF  —  Projecte Tècnic de Gestió i Millora Forestal"
        )
        self._btn_psgf = QRadioButton(
            "PSGF  —  Pla Simple de Gestió Forestal"
        )
        self._btn_ptgmf.setChecked(True)

        self._instrument_group = QButtonGroup(self)
        self._instrument_group.addButton(self._btn_ptgmf, 0)
        self._instrument_group.addButton(self._btn_psgf, 1)
        self._instrument_group.buttonClicked.connect(self._on_instrument_changed)

        inst_layout.addWidget(self._btn_ptgmf)
        inst_layout.addWidget(self._btn_psgf)
        main.addWidget(inst_group)

        # Carpeta de destí
        dest_group = QGroupBox("Carpeta de destí dels fitxers GeoPackage")
        dest_layout = QHBoxLayout(dest_group)
        self._dest_path = QLineEdit()
        self._dest_path.setPlaceholderText("Selecciona la carpeta on desar les capes…")
        btn_browse = QPushButton("Navega…")
        btn_browse.clicked.connect(self._browse_dest)
        dest_layout.addWidget(self._dest_path)
        dest_layout.addWidget(btn_browse)
        main.addWidget(dest_group)

        # CRS
        crs_group = QGroupBox("Sistema de Referència de Coordenades (CRS)")
        crs_layout = QHBoxLayout(crs_group)
        crs_label = QLabel("CRS:")
        self._crs_combo = QComboBox()
        self._crs_combo.addItem("ETRS89 / UTM zona 31N  (EPSG:25831) — recomanat per Catalunya", "EPSG:25831")
        self._crs_combo.addItem("ETRS89 / UTM zona 30N  (EPSG:25830)", "EPSG:25830")
        self._crs_combo.addItem("WGS84  (EPSG:4326)", "EPSG:4326")
        crs_layout.addWidget(crs_label)
        crs_layout.addWidget(self._crs_combo, stretch=1)
        main.addWidget(crs_group)

        # Selecció de capes a crear
        layers_group = QGroupBox("Capes a crear")
        layers_outer = QVBoxLayout(layers_group)

        # Botó seleccionar/deseleccionar tot
        sel_layout = QHBoxLayout()
        btn_all = QPushButton("Selecciona-ho tot")
        btn_none = QPushButton("Deselecciona-ho tot")
        btn_all.clicked.connect(lambda: self._toggle_all(True))
        btn_none.clicked.connect(lambda: self._toggle_all(False))
        sel_layout.addWidget(btn_all)
        sel_layout.addWidget(btn_none)
        sel_layout.addStretch()
        layers_outer.addLayout(sel_layout)

        # Scroll amb les capes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        for layer_def in IOF_LAYERS:
            row = self._build_layer_row(layer_def)
            scroll_layout.addWidget(row)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layers_outer.addWidget(scroll)
        main.addWidget(layers_group, stretch=1)

        # Barra de progrés
        self._progress = QProgressBar()
        self._progress.setValue(0)
        main.addWidget(self._progress)

        # Botons d'acció
        btn_layout = QHBoxLayout()
        btn_create = QPushButton("Crear capes")
        btn_create.setStyleSheet(
            "background:#1565c0; color:white; font-weight:bold; padding:6px 20px;"
        )
        btn_create.clicked.connect(self._do_create)
        btn_close = QPushButton("Tancar")
        btn_close.clicked.connect(self.close)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_create)
        btn_layout.addWidget(btn_close)
        main.addLayout(btn_layout)

    def _build_layer_row(self, layer_def):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{layer_def['color']}; "
            f"border:1px solid #ccc; border-radius:4px; padding:2px; }}"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)

        check = QCheckBox(layer_def["label"])
        check.setChecked(True)
        check.setStyleSheet("font-size: 12px;")
        self._layer_checks[layer_def["id"]] = check
        layout.addWidget(check, stretch=1)

        # Resum dels camps
        field_names = ", ".join(f[0] for f in layer_def["fields"])
        lbl_fields = QLabel(f"<small style='color:#555'>{field_names}</small>")
        lbl_fields.setWordWrap(True)
        layout.addWidget(lbl_fields, stretch=2)

        return frame

    def _on_instrument_changed(self, btn):
        """Actualitza l'instrument seleccionat i el label de la capa d'unitats."""
        self._instrument = (
            INSTRUMENT_PTGMF if btn == self._btn_ptgmf else INSTRUMENT_PSGF
        )
        cfg = UNITATS_CONFIG[self._instrument]
        # Actualitzar el checkbox de la capa d'unitats si ja existeix
        if "unitats" in self._layer_checks:
            self._layer_checks["unitats"].setText(cfg["layer_label"])

    def _toggle_all(self, state):
        for check in self._layer_checks.values():
            check.setChecked(state)

    def _browse_dest(self):
        path = QFileDialog.getExistingDirectory(
            self, "Selecciona la carpeta de destí"
        )
        if path:
            self._dest_path.setText(path)

    # ------------------------------------------------------------------
    # Creació de capes
    # ------------------------------------------------------------------

    def _do_create(self):
        dest_dir = self._dest_path.text().strip()
        if not dest_dir or not os.path.isdir(dest_dir):
            QMessageBox.warning(
                self, "Carpeta de destí",
                "Selecciona una carpeta de destí vàlida."
            )
            return

        selected = [
            layer_def for layer_def in IOF_LAYERS
            if self._layer_checks[layer_def["id"]].isChecked()
        ]
        if not selected:
            QMessageBox.warning(self, "Sense selecció", "Selecciona almenys una capa.")
            return

        crs_code = self._crs_combo.currentData()
        crs = QgsCoordinateReferenceSystem(crs_code)
        instrument = self._instrument

        # ----------------------------------------------------------------
        # Comprovar si ja existeix un grup de capes IOF al projecte
        # ----------------------------------------------------------------
        from qgis.PyQt.QtWidgets import QMessageBox as QMB
        root = QgsProject.instance().layerTreeRoot()
        group_name = (
            "PTGMF — Capes de treball" if instrument == INSTRUMENT_PTGMF
            else "PSGF — Capes de treball"
        )
        alt_group_name = (
            "PSGF — Capes de treball" if instrument == INSTRUMENT_PTGMF
            else "PTGMF — Capes de treball"
        )

        # Detectar si existeix algun dels dos grups possibles
        existing_group = root.findGroup(group_name) or root.findGroup(alt_group_name)
        replace_group = False  # True = eliminar grup existent i crear-ne un de nou

        if existing_group:
            from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
            from qgis.PyQt.QtCore import Qt as _Qt

            grup_dlg = QDialog(self)
            grup_dlg.setWindowTitle("Grup de capes existent")
            grup_dlg.setMinimumWidth(440)
            grup_dlg.setWindowFlags(grup_dlg.windowFlags() & ~_Qt.WindowContextHelpButtonHint)
            grup_dlg._result = "cancel"

            v = QVBoxLayout(grup_dlg)
            v.setSpacing(12)

            lbl_info = QLabel(
                f"Ja existeix el grup \u00ab{existing_group.name()}\u00bb al projecte.\n\n"
                "Qu\u00e8 vols fer?"
            )
            lbl_info.setWordWrap(True)
            v.addWidget(lbl_info)

            btn_add = QPushButton("Afegir les capes al grup existent")
            btn_add.setToolTip(
                "Crea nom\u00e9s les capes que no existeixen al disc.\n"
                "Les capes existents amb dades no es modifiquen."
            )
            btn_add.setStyleSheet("padding: 6px 14px; text-align: left;")

            lbl_warn = QLabel(
                "\u26a0\ufe0f  Eliminar i crear de nou esborrar\u00e0 tots els fitxers "
                "i es perdran les dades digitalitzades."
            )
            lbl_warn.setWordWrap(True)
            lbl_warn.setStyleSheet("color: #b71c1c; font-size: 11px;")

            btn_replace = QPushButton("Eliminar grup i crear de nou")
            btn_replace.setStyleSheet(
                "background: #c62828; color: white; font-weight: bold; padding: 6px 14px;"
            )

            btn_cancel = QPushButton("Cancel\u00b7lar")
            btn_cancel.setStyleSheet("padding: 6px 14px;")

            def on_add():
                grup_dlg._result = "add"
                grup_dlg.accept()

            def on_replace():
                confirm = QMB.warning(
                    grup_dlg,
                    "Confirmaci\u00f3",
                    "S\u2019eliminaran tots els fitxers GeoPackage i es perdran "
                    "totes les dades digitalitzades.\n\n"
                    "Est\u00e0s segur que vols continuar?",
                    QMB.StandardButton.Yes | QMB.StandardButton.No,
                    QMB.StandardButton.No
                )
                if confirm == QMB.StandardButton.Yes:
                    grup_dlg._result = "replace"
                    grup_dlg.accept()

            def on_cancel():
                grup_dlg.reject()

            btn_add.clicked.connect(on_add)
            btn_replace.clicked.connect(on_replace)
            btn_cancel.clicked.connect(on_cancel)

            btn_row = QHBoxLayout()
            btn_row.addWidget(btn_add)
            btn_row.addStretch()
            btn_row.addWidget(btn_replace)
            btn_row.addWidget(btn_cancel)

            v.addWidget(lbl_warn)
            v.addLayout(btn_row)
            grup_dlg.exec()

            if grup_dlg._result == "cancel":
                return
            replace_group = (grup_dlg._result == "replace")

        # ----------------------------------------------------------------
        # Si l'usuari vol substituir: eliminar el grup de l'arbre
        # Les capes es sobreescriuran amb CreateOrOverwriteFile sense
        # necessitat d'eliminar-les del projecte ni del disc.
        # ----------------------------------------------------------------
        if replace_group and existing_group:
            # Eliminar només el node del grup de l'arbre (sense tocar les capes)
            # Les capes queden al projecte i es reemplaçaran al grup nou
            parent = existing_group.parent()
            if parent:
                parent.removeChildNode(existing_group)
            existing_group = None

        # ----------------------------------------------------------------
        # Construir la llista d'adapted layer_defs per a les seleccionades
        # ----------------------------------------------------------------
        adapted_selected = [
            self._adapt_layer_def(ld, instrument) for ld in selected
        ]

        # Noms de capes que ja estan carregades al grup existent
        from qgis.core import QgsLayerTreeLayer, QgsMessageLog, Qgis
        names_in_group = set()
        if existing_group and not replace_group:
            for child in existing_group.findLayers():
                names_in_group.add(child.name())

        # ================================================================
        # FLUX A: AFEGIR AL GRUP EXISTENT
        # Carregar només les capes que falten al grup (no les que ja hi són)
        # ================================================================
        if existing_group and not replace_group:
            created = []
            kept = []
            errors = []
            total = len(adapted_selected)

            for i, layer_def in enumerate(adapted_selected):
                self._progress.setValue(int((i / total) * 90))
                layer_name = layer_def["name"]
                gpkg_path = os.path.normpath(
                    os.path.join(dest_dir, f"{layer_name}.gpkg")
                )

                # Si ja és al grup, no fer res
                if layer_name in names_in_group:
                    QgsMessageLog.logMessage(
                        f"IOF: {layer_name} ja és al grup, s'omet.",
                        "IOF Assistent", Qgis.MessageLevel.Info
                    )
                    continue

        # Crear la capa (si el fitxer existeix i té la capa al projecte,
        # _create_layer l'eliminarà del projecte per alliberar el handle OGR)
                try:
                    lyr = self._create_layer(
                        layer_def, dest_dir, crs,
                        overwrite=os.path.exists(gpkg_path),
                        instrument=instrument
                    )
                    if lyr:
                        created.append(lyr)
                except Exception as e:
                    errors.append(f"{layer_name}: {e}")

        # ================================================================
        # FLUX B: CREAR GRUP NOU (replace_group=True o no hi havia grup)
        # Comprovar si algun fitxer té dades i preguntar una sola vegada
        # ================================================================
        else:
            # Comprovar quins fitxers existeixen i tenen dades
            gpkg_with_data = []
            for layer_def in adapted_selected:
                gpkg_path = os.path.normpath(
                    os.path.join(dest_dir, f"{layer_def['name']}.gpkg")
                )
                if os.path.exists(gpkg_path) and self._gpkg_has_features(gpkg_path, layer_def["name"]):
                    feat_count = self._gpkg_feature_count(gpkg_path, layer_def["name"])
                    gpkg_with_data.append((layer_def["name"], feat_count))

            # Si hi ha fitxers amb dades, preguntar una sola vegada
            # Conjunt de noms a conservar (decidit per l'usuari)
            names_to_keep = set()

            if gpkg_with_data:
                from qgis.PyQt.QtWidgets import (
                    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                    QPushButton, QCheckBox, QFrame, QScrollArea, QWidget
                )
                from qgis.PyQt.QtCore import Qt as _Qt

                data_dlg = QDialog(self)
                data_dlg.setWindowTitle("Capes amb dades existents")
                data_dlg.setMinimumWidth(480)
                data_dlg.setWindowFlags(
                    data_dlg.windowFlags() & ~_Qt.WindowContextHelpButtonHint
                )
                data_dlg._cancelled = True

                vl = QVBoxLayout(data_dlg)
                vl.setSpacing(10)

                lbl_text = QLabel(
                    "Les capes següents ja contenen dades digitalitzades.\n"
                    "Marca les que vols <b>conservar</b>; "
                    "les desmarcades es generaran de nou (buides)."
                )
                lbl_text.setWordWrap(True)
                vl.addWidget(lbl_text)

                # Checkboxes individuals per cada capa amb dades
                chk_list = []
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setMaximumHeight(220)
                scroll_w = QWidget()
                scroll_vl = QVBoxLayout(scroll_w)
                scroll_vl.setSpacing(4)

                for layer_name_d, feat_count in gpkg_with_data:
                    chk = QCheckBox(
                        f"{layer_name_d}  "
                        f"({feat_count} entitat{'s' if feat_count != 1 else ''})"
                    )
                    chk.setChecked(True)  # conservar per defecte
                    chk.setStyleSheet("padding: 4px;")
                    scroll_vl.addWidget(chk)
                    chk_list.append((layer_name_d, chk))

                scroll_vl.addStretch()
                scroll.setWidget(scroll_w)
                vl.addWidget(scroll)

                # Botons seleccionar/deseleccionar tot
                sel_row = QHBoxLayout()
                btn_all = QPushButton("Conservar totes")
                btn_none = QPushButton("Generar totes de nou")
                btn_all.setStyleSheet("padding: 4px 10px; font-size: 11px;")
                btn_none.setStyleSheet("padding: 4px 10px; font-size: 11px;")
                btn_all.clicked.connect(lambda: [c.setChecked(True) for _, c in chk_list])
                btn_none.clicked.connect(lambda: [c.setChecked(False) for _, c in chk_list])
                sel_row.addWidget(btn_all)
                sel_row.addWidget(btn_none)
                sel_row.addStretch()
                vl.addLayout(sel_row)

                lbl_warn = QLabel(
                    "⚠️  Les capes desmarcades es crearan buides "
                    "i es perdran les dades que contenien."
                )
                lbl_warn.setStyleSheet("color: #b71c1c; font-size: 11px;")
                lbl_warn.setWordWrap(True)
                vl.addWidget(lbl_warn)

                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet("color: #ddd;")
                vl.addWidget(sep)

                btn_ok = QPushButton("Continuar")
                btn_ok.setStyleSheet(
                    "background: #1565c0; color: white; "
                    "font-weight: bold; padding: 6px 16px;"
                )
                btn_cancel_d = QPushButton("Cancel·lar")
                btn_cancel_d.setStyleSheet("padding: 6px 14px;")

                def _on_ok():
                    data_dlg._cancelled = False
                    data_dlg.accept()

                def _on_cancel_d():
                    data_dlg.reject()

                btn_ok.clicked.connect(_on_ok)
                btn_cancel_d.clicked.connect(_on_cancel_d)

                btn_row = QHBoxLayout()
                btn_row.addStretch()
                btn_row.addWidget(btn_ok)
                btn_row.addWidget(btn_cancel_d)
                vl.addLayout(btn_row)

                data_dlg.exec()

                if data_dlg._cancelled:
                    self._progress.setValue(0)
                    return

                # Recollir els noms de les capes marcades per conservar
                names_to_keep = {
                    name for name, chk in chk_list if chk.isChecked()
                }

            # Les capes carregades s'eliminen del projecte a _create_layer
            # just abans de sobreescriure el fitxer, alliberant el handle OGR.

            created = []
            kept = []
            errors = []
            total = len(adapted_selected)

            for i, layer_def in enumerate(adapted_selected):
                self._progress.setValue(int((i / total) * 90))
                layer_name = layer_def["name"]
                gpkg_path = os.path.normpath(
                    os.path.join(dest_dir, f"{layer_name}.gpkg")
                )

                if layer_name in names_to_keep and os.path.exists(gpkg_path) and self._gpkg_has_features(gpkg_path, layer_name):
                    # Conservar: carregar la capa existent
                    lyr = self._load_existing_layer(gpkg_path, layer_name)
                    if lyr:
                        kept.append(lyr)
                else:
                    # Crear de nou
                    try:
                        lyr = self._create_layer(
                            layer_def, dest_dir, crs,
                            overwrite=os.path.exists(gpkg_path),
                            instrument=instrument
                        )
                        if lyr:
                            created.append(lyr)
                    except Exception as e:
                        errors.append(f"{layer_name}: {e}")

        self._progress.setValue(100)

        # ----------------------------------------------------------------
        # Afegir les capes creades al projecte i construir el grup
        # ----------------------------------------------------------------
        all_layers = created + kept
        if all_layers:
            # Afegir al projecte les capes noves (sense afegir a l'arbre)
            existing_ids = set(QgsProject.instance().mapLayers().keys())
            to_add = [lyr for lyr in all_layers if lyr.id() not in existing_ids]
            if to_add:
                QgsProject.instance().addMapLayers(to_add, False)

            # Obtenir o crear el grup
            group = root.findGroup(group_name)
            if group is None and existing_group is not None:
                existing_group.setName(group_name)
                group = existing_group
            elif group is None:
                group = root.insertGroup(0, group_name)

            UNITATS_NAMES = {"IOF_Unitats_Actuacio", "IOF_Rodals"}

            # Mapa nom -> capa per a les capes que acabem de crear/carregar
            lyr_by_name = {}
            for lyr in all_layers:
                lyr_by_name[lyr.name()] = lyr
                if lyr.name() in UNITATS_NAMES:
                    for un in UNITATS_NAMES:
                        lyr_by_name[un] = lyr

            # Ordre canònic: segueix exactament IOF_LAYERS adaptat a l'instrument
            ordered_names = [
                self._adapt_layer_def(ld, instrument)["name"]
                for ld in IOF_LAYERS
            ]

            # Primer eliminar tots els nodes del grup que corresponen
            # a capes que anem a (re)inserir, per evitar duplicats
            for lyr in all_layers:
                layer_name = lyr.name()
                search_names = (UNITATS_NAMES if layer_name in UNITATS_NAMES
                                else {layer_name})
                for child in list(group.children()):
                    if isinstance(child, QgsLayerTreeLayer) and child.name() in search_names:
                        group.removeChildNode(child)
                node_outside = root.findLayer(lyr.id())
                if node_outside and node_outside.parent() != group:
                    node_outside.parent().removeChildNode(node_outside)

            # Inserir les capes en l'ordre canònic a la posició correcta
            insert_pos = 0
            for canonical_name in ordered_names:
                lyr = lyr_by_name.get(canonical_name)
                if lyr is None:
                    # Capa no present en aquesta operació: comprovar si ja és al grup
                    # per avançar la posició d'inserció
                    for child in group.children():
                        search_names = (
                            UNITATS_NAMES if canonical_name in UNITATS_NAMES else {canonical_name}
                        )
                        if isinstance(child, QgsLayerTreeLayer) and child.name() in search_names:
                            insert_pos += 1
                            break
                    continue
                group.insertLayer(insert_pos, lyr)
                insert_pos += 1

        if errors:
            QMessageBox.warning(
                self, "Errors en la creació",
                "Les capes següents no s'han pogut crear:\n\n" + "\n".join(errors)
            )
        if created:
            msg = (
                f"✅  Creades correctament: {len(created)} capes\n\n"
                f"Carpeta: {dest_dir}\n\n"
                "Ara pots editar cada capa amb les eines de digitalització "
                "de QGIS i omplir els camps corresponents."
            )
            QMessageBox.information(self, "Capes IOF", msg)
            self.close()

    def _gpkg_first_layer_name(self, gpkg_path):
        """
        Retorna el nom de la primera capa vectorial dins d'un GPKG,
        independentment del nom esperat. Útil quan el fitxer pot tenir
        un nom de capa diferent del fitxer (p.ex. IOF_Rodals dins IOF_Unitats.gpkg).
        """
        try:
            info = QgsVectorLayer(gpkg_path, "tmp_info", "ogr")
            if info.isValid():
                return info.name()
            # Alternativa: llegir les sublayers
            from qgis.core import QgsProviderRegistry
            metadata = QgsProviderRegistry.instance().providerMetadata("ogr")
            if metadata:
                sublayers = metadata.querySublayers(gpkg_path)
                if sublayers:
                    return sublayers[0].name()
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        return None

    def _gpkg_open_layer(self, gpkg_path, layer_name):
        """
        Obre una capa d'un GPKG pel nom esperat. Si no és vàlida,
        prova amb el primer layer disponible al fitxer.
        """
        lyr = QgsVectorLayer(f"{gpkg_path}|layername={layer_name}", "tmp", "ogr")
        if lyr.isValid():
            return lyr
        # Intent amb el primer layer del fitxer
        actual_name = self._gpkg_first_layer_name(gpkg_path)
        if actual_name and actual_name != layer_name:
            lyr2 = QgsVectorLayer(f"{gpkg_path}|layername={actual_name}", "tmp", "ogr")
            if lyr2.isValid():
                return lyr2
        return None

    def _gpkg_has_features(self, gpkg_path, layer_name):
        """Retorna True si el fitxer gpkg existeix i la capa conté almenys una entitat."""
        try:
            lyr = self._gpkg_open_layer(gpkg_path, layer_name)
            if lyr is None:
                return False
            return lyr.featureCount() > 0
        except Exception:
            return False

    def _gpkg_feature_count(self, gpkg_path, layer_name):
        """Retorna el nombre d'entitats d'una capa gpkg."""
        try:
            lyr = self._gpkg_open_layer(gpkg_path, layer_name)
            return lyr.featureCount() if lyr is not None else 0
        except Exception:
            return 0

    def _load_existing_layer(self, gpkg_path, layer_name):
        """
        Carrega una capa existent des d'un GeoPackage i la retorna.
        Si la capa ja és al projecte (mateixa ruta), la retorna directament
        sense duplicar-la.
        """
        # Comprovar si ja hi ha una capa amb la mateixa font al projecte
        gpkg_path = os.path.normpath(gpkg_path)
        uri = f"{gpkg_path}|layername={layer_name}"
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer):
                src_norm = os.path.normpath(lyr.source().split("|")[0])
                if src_norm.lower() == gpkg_path.lower():
                    return lyr  # ja és al projecte, la reutilitzem

        # Carregar-la de nou des del fitxer
        lyr = QgsVectorLayer(uri, layer_name, "ogr")
        if not lyr.isValid():
            return None
        self._apply_style(lyr, next(
            (ld for ld in IOF_LAYERS
             if ld["name"] == layer_name or layer_name in ("IOF_Rodals",) and ld["id"] == "unitats"),
            {"geom": "Polygon", "color": "#eeeeee"}
        ))
        return lyr

    def _adapt_layer_def(self, layer_def, instrument):
        """
        Retorna una còpia de layer_def adaptada a l'instrument
        (PTGMF o PSGF). Només afecta la capa d'unitats/rodals.
        """
        if layer_def["id"] != "unitats":
            return layer_def

        cfg = UNITATS_CONFIG[instrument]
        adapted = dict(layer_def)
        adapted["name"] = cfg["layer_name"]
        adapted["label"] = cfg["layer_label"]

        # Adaptar el camp principal (codi_ua / codi_rodal)
        new_fields = []
        for field_tuple in layer_def["fields"]:
            fname, ftype, flength, fprecision, falias, fcomment = field_tuple
            if fname == "codi_ua":
                new_fields.append((
                    cfg["field_name"], ftype, flength, fprecision,
                    cfg["field_alias"], fcomment
                ))
            else:
                new_fields.append(field_tuple)
        adapted["fields"] = new_fields
        return adapted

    def _create_layer(self, layer_def, dest_dir, crs, overwrite=True,
                      instrument=INSTRUMENT_PTGMF):
        """
        Crea o sobreescriu un fitxer GeoPackage per a la capa donada.

        Estratègia per evitar conflictes de fitxer obert (WinError 32 / OGR
        'already exists'):
          1. Si el GPKG ja existeix i té la capa carregada al projecte QGIS,
             s'elimina la capa del projecte per alliberar el handle OGR
             abans de sobreescriure el fitxer.
          2. S'escriu el fitxer nou amb CreateOrOverwriteFile.
          3. Es carrega la capa nova i es retorna.
        """
        geom_type = layer_def["geom"]
        layer_name = layer_def["name"]
        gpkg_path = os.path.normpath(os.path.join(dest_dir, f"{layer_name}.gpkg"))

        # Construir els camps
        fields = QgsFields()
        for fname, ftype, flength, fprecision, falias, _ in layer_def["fields"]:
            field = QgsField(fname, ftype)
            if flength > 0:
                field.setLength(flength)
            if fprecision > 0:
                field.setPrecision(fprecision)
            field.setAlias(falias)
            fields.append(field)

        # Capa de memòria buida amb els camps correctes
        mem_layer = QgsVectorLayer(
            f"{geom_type}?crs={crs.authid()}", layer_name, "memory"
        )
        mem_layer.dataProvider().addAttributes(fields)
        mem_layer.updateFields()

        # Si el fitxer existeix i la capa ja és al projecte, cal eliminar-la
        # del projecte per alliberar el handle OGR abans de sobreescriure.
        if os.path.exists(gpkg_path):
            ids_to_remove = [
                lid for lid, lyr in QgsProject.instance().mapLayers().items()
                if isinstance(lyr, QgsVectorLayer) and os.path.normpath(lyr.source().split("|")[0]) == gpkg_path
            ]
            if ids_to_remove:
                QgsProject.instance().removeMapLayers(ids_to_remove)

        save_options = QgsVectorFileWriter.SaveVectorOptions()
        save_options.driverName = "GPKG"
        save_options.fileEncoding = "UTF-8"
        save_options.layerName = layer_name
        save_options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile

        err, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
            mem_layer,
            gpkg_path,
            QgsProject.instance().transformContext(),
            save_options
        )

        if err != QgsVectorFileWriter.WriterError.NoError:
            raise RuntimeError(f"Error desant {layer_name}: {msg}")

        # Carregar la capa des del GPKG
        loaded = QgsVectorLayer(
            f"{gpkg_path}|layername={layer_name}", layer_name, "ogr"
        )
        if not loaded.isValid():
            raise RuntimeError(f"La capa {layer_name} no és vàlida després de crear-la.")

        # Aplicar format 2 decimals als camps Double

        # Aplicar estil mínim segons el tipus de geometria
        self._apply_style(loaded, layer_def)

        return loaded

    def _apply_style(self, layer, layer_def):
        """Aplica un estil de color bàsic a la capa."""
        from qgis.PyQt.QtGui import QColor
        color = layer_def.get("color", "#ffffff")
        geom = layer_def["geom"]

        # Convertir color hex a RGB
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)

        try:
            if geom in ("Polygon", "MultiPolygon"):
                sym = layer.renderer().symbol()
                sym.setColor(QColor(r, g, b, 180))
                sym.symbolLayer(0).setStrokeColor(QColor(50, 50, 50))
            elif geom == "LineString":
                sym = layer.renderer().symbol()
                sym.setColor(QColor(r, g, b))
                sym.setWidth(0.5)
            elif geom == "Point":
                sym = layer.renderer().symbol()
                sym.setColor(QColor(r, g, b))
                sym.setSize(3.0)
            layer.triggerRepaint()
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass  # L'estil és opcional; si falla no interromp la creació

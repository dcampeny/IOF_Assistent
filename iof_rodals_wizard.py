# -*- coding: utf-8 -*-
"""
IOF Assistent — Omplir camps de IOF_Rodals / IOF_Unitats_Actuacio.

Per a cada polígon demana:
  - Codi rodal/UA (text: pot ser numèric o alfanumèric com 1a, 2b, etc.)
  - Formació forestal (desplegable taula annexa 1)
  - Codi d'ús (desplegable taula annexa 2)
  - Superfície ordenada (calculada automàticament)
  - Superfície forestal (calculada segons taula annexa 2)
  - Superfície arbrada (calculada segons taula annexa 2)

Pregunta si hi ha parts no ordenades i les exclou del càlcul.
"""

from .iof_utils import (
    get_layer as _get_layer,
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox,
    QMessageBox, QProgressBar, QFrame,
    QCheckBox, QScrollArea, QWidget, QListWidget,
    QListWidgetItem
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor

from .iof_taules import FORMACIONS, USOS_VEGETACIO, is_forestal, is_arbrat

LAYERS_UNITATS = ["IOF_Unitats_Actuacio", "IOF_Rodals"]


def _sense_accents(text):
    """Retorna el text en minúscules i sense accents, per fer
    comparacions de cerca insensibles a accents (p. ex. "platan" ha de
    trobar "plàtan")."""
    import unicodedata
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


class RodalsWizard(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self._layer = None
        self._features = []
        self._current = 0
        self._rubber_band = None
        # True si no es troba la capa d'unitats: qui crea el diàleg
        # (iof_exporter.py) ha de comprovar-ho i no cridar .show() en
        # aquest cas.
        self._cancelled = False

        # Selecció per clic al mapa
        self._map_tool = None
        self._map_tool_backup = None
        self._form_modified = False

        # Darrer codi UA/rodal (suggerit a la unitat següent)
        self._last_codi = ''

        # IDs dels polígons no ordenats (pregunta inicial)
        self._no_ordenats = set()
        # Rubber bands temporals per al diàleg de no ordenats
        self._temp_rbs = []
        # Ressaltat (toggle) de totes les unitats encara sense definir
        self._show_undefined = False
        self._undefined_highlights = []
        # Renderer i labeling guardats per restaurar-los en tancar
        self._saved_renderer = None
        self._saved_labeling = None
        self._saved_labels_enabled = False

        self.setWindowTitle("IOF Assistent — Omplir camps d'unitats")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(520)

        self._build_ui()
        self._load_layer()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(12)

        title = QLabel("<b>Omplir camps de les tipologies forestals</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "padding:8px; background:#e8f4e8; border-radius:4px; font-weight:bold;"
        )
        main.addWidget(title)

        self._lbl_progress = QLabel()
        self._lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_progress.setStyleSheet("color:#555; font-size:12px;")
        main.addWidget(self._lbl_progress)

        # Toggle: ressaltar al mapa totes les unitats encara sense definir
        toggle_row = QHBoxLayout()
        toggle_row.addStretch()
        self._btn_toggle_undefined = QPushButton("Ressaltar unitats sense definir")
        self._btn_toggle_undefined.setCheckable(True)
        self._btn_toggle_undefined.setToolTip(
            "Marca al mapa, amb un contorn vermell, totes les unitats "
            "d'aquesta capa que encara no tenen el codi d'ús omplert."
        )
        self._btn_toggle_undefined.toggled.connect(self._on_toggle_undefined)
        toggle_row.addWidget(self._btn_toggle_undefined)
        toggle_row.addStretch()
        main.addLayout(toggle_row)

        # Formulari
        self._form_group = QGroupBox("Dades de la unitat")
        form = QGridLayout(self._form_group)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        # Checkbox "no ordenada" — fila 0, amplada total
        self._chk_no_ordenat = QCheckBox("Tipologia forestal / ús no ordenada")
        self._chk_no_ordenat.setStyleSheet(
            "QCheckBox { font-weight:bold; color:#b71c1c; padding:4px; }"
            "QCheckBox::indicator { width:16px; height:16px; }"
        )
        self._chk_no_ordenat.toggled.connect(self._on_no_ordenat_toggled)
        form.addWidget(self._chk_no_ordenat, 0, 0, 1, 4)

        # Separador visual sota el checkbox
        sep_chk = QFrame()
        sep_chk.setFrameShape(QFrame.Shape.HLine)
        sep_chk.setStyleSheet("color:#eee;")
        form.addWidget(sep_chk, 1, 0, 1, 4)

        # Codi rodal/UA  (fila 2)
        self._lbl_codi = QLabel("Codi *:")
        self._spin_codi = QLineEdit()
        self._spin_codi.setFixedWidth(90)
        self._spin_codi.setPlaceholderText("ex: 1, 1a, 2b")
        form.addWidget(self._lbl_codi, 2, 0)
        form.addWidget(self._spin_codi, 2, 1, Qt.AlignmentFlag.AlignLeft)

        # Formació forestal (taula annexa 1) — cerca amb filtre
        self._lbl_form_label = QLabel("Formació forestal *:")
        form.addWidget(self._lbl_form_label, 2, 2)

        form_container = QWidget()
        form_vbox = QVBoxLayout(form_container)
        form_vbox.setContentsMargins(0, 0, 0, 0)
        form_vbox.setSpacing(2)

        # Caixa de cerca amb botó ✕ per esborrar el filtre
        search_form_row = QHBoxLayout()
        search_form_row.setContentsMargins(0, 0, 0, 0)
        search_form_row.setSpacing(2)
        self._btn_clear_formacio = QPushButton("✕")
        self._btn_clear_formacio.setFixedSize(22, 22)
        self._btn_clear_formacio.setToolTip("Esborra el filtre")
        self._btn_clear_formacio.setStyleSheet(
            "QPushButton { background:#e0e0e0; border:1px solid #bbb;"
            " border-radius:3px; font-size:10px; padding:0; }"
            "QPushButton:hover { background:#ef9a9a; }"
        )
        self._btn_clear_formacio.clicked.connect(
            lambda: self._search_formacio.clear()
        )
        self._search_formacio = QLineEdit()
        self._search_formacio.setPlaceholderText("Cerca per nom o codi (ex: surera, Qs)...")
        self._search_formacio.textChanged.connect(self._filter_formacio)
        search_form_row.addWidget(self._search_formacio)
        search_form_row.addWidget(self._btn_clear_formacio)

        self._list_formacio = QListWidget()
        self._list_formacio.setMaximumHeight(120)
        self._list_formacio.setMinimumWidth(350)
        self._list_formacio.currentItemChanged.connect(self._on_formacio_selected)
        self._list_formacio.currentItemChanged.connect(lambda *a: self._mark_modified())

        # Omplir la llista
        item0 = QListWidgetItem("(cap formació seleccionada)")
        item0.setData(32, None)
        self._list_formacio.addItem(item0)
        for codi, desc in FORMACIONS:
            item = QListWidgetItem(f"{codi} — {desc}")
            item.setData(32, codi)
            self._list_formacio.addItem(item)

        self._lbl_formacio_sel = QLabel("—")
        self._lbl_formacio_sel.setStyleSheet("color:#1a237e; font-weight:bold; font-size:11px;")
        self._list_formacio.setCurrentRow(0)

        form_vbox.addLayout(search_form_row)
        form_vbox.addWidget(self._list_formacio)
        form_vbox.addWidget(self._lbl_formacio_sel)
        form.addWidget(form_container, 2, 3)

        # Codi d'ús (taula annexa 2) — cerca amb filtre
        lbl_us = QLabel("Codi d'ús:")
        form.addWidget(lbl_us, 3, 2)

        us_container = QWidget()
        us_vbox = QVBoxLayout(us_container)
        us_vbox.setContentsMargins(0, 0, 0, 0)
        us_vbox.setSpacing(2)

        # Caixa de cerca amb botó ✕ per esborrar el filtre
        search_us_row = QHBoxLayout()
        search_us_row.setContentsMargins(0, 0, 0, 0)
        search_us_row.setSpacing(2)
        self._btn_clear_us = QPushButton("✕")
        self._btn_clear_us.setFixedSize(22, 22)
        self._btn_clear_us.setToolTip("Esborra el filtre")
        self._btn_clear_us.setStyleSheet(
            "QPushButton { background:#e0e0e0; border:1px solid #bbb;"
            " border-radius:3px; font-size:10px; padding:0; }"
            "QPushButton:hover { background:#ef9a9a; }"
        )
        self._btn_clear_us.clicked.connect(
            lambda: self._search_us.clear()
        )
        self._search_us = QLineEdit()
        self._search_us.setPlaceholderText("Cerca per nom o codi (ex: conreu, u)...")
        self._search_us.textChanged.connect(self._filter_us)
        search_us_row.addWidget(self._search_us)
        search_us_row.addWidget(self._btn_clear_us)

        self._list_us = QListWidget()
        self._list_us.setMaximumHeight(120)
        self._list_us.setMinimumWidth(350)
        self._list_us.currentItemChanged.connect(self._on_us_selected)
        self._list_us.currentItemChanged.connect(lambda *a: self._mark_modified())

        # Omplir la llista
        item0u = QListWidgetItem("(sense codi d'ús)")
        item0u.setData(32, None)
        self._list_us.addItem(item0u)
        for codi, nom, forestal, arbrat in USOS_VEGETACIO:
            etiqueta = f"{codi} — {nom}"
            if forestal and arbrat:
                etiqueta += " [F+A]"
            elif forestal:
                etiqueta += " [F]"
            item = QListWidgetItem(etiqueta)
            item.setData(32, codi)
            self._list_us.addItem(item)

        self._lbl_us_sel = QLabel("—")
        self._lbl_us_sel.setStyleSheet("color:#1a237e; font-weight:bold; font-size:11px;")
        self._list_us.setCurrentRow(0)

        us_vbox.addLayout(search_us_row)
        us_vbox.addWidget(self._list_us)
        us_vbox.addWidget(self._lbl_us_sel)
        form.addWidget(us_container, 3, 3)

        # Superfície ordenada
        lbl_sup_ord = QLabel("Sup. ordenada (ha):")
        self._lbl_sup_ord_val = QLabel("—")
        self._lbl_sup_ord_val.setStyleSheet(
            "font-weight:bold; color:#1a237e; font-size:12px;"
        )
        form.addWidget(lbl_sup_ord, 3, 0)
        form.addWidget(self._lbl_sup_ord_val, 3, 1, Qt.AlignmentFlag.AlignLeft)

        # Superfície forestal
        lbl_sup_for = QLabel("Sup. forestal (ha):")
        self._lbl_sup_for_val = QLabel("—")
        self._lbl_sup_for_val.setStyleSheet(
            "font-weight:bold; color:#2e7d32; font-size:12px;"
        )
        form.addWidget(lbl_sup_for, 4, 0)
        form.addWidget(self._lbl_sup_for_val, 4, 1, Qt.AlignmentFlag.AlignLeft)

        # Superfície arbrada
        lbl_sup_arb = QLabel("Sup. arbrada (ha):")
        self._lbl_sup_arb_val = QLabel("—")
        self._lbl_sup_arb_val.setStyleSheet(
            "font-weight:bold; color:#558b2f; font-size:12px;"
        )
        form.addWidget(lbl_sup_arb, 5, 0)
        form.addWidget(self._lbl_sup_arb_val, 5, 1, Qt.AlignmentFlag.AlignLeft)

        form.setColumnStretch(3, 1)
        main.addWidget(self._form_group)
        self._form_group.setEnabled(False)

        # Etiqueta de resum (s'actualitza en desar)
        self._lbl_resum = QLabel("—")
        self._lbl_resum.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_resum.setWordWrap(True)
        self._lbl_resum.setStyleSheet(
            "padding:6px 10px; background:#e8f5e9; border:1px solid #a5d6a7;"
            " border-radius:4px; color:#1b5e20; font-weight:bold; font-size:12px;"
        )
        main.addWidget(self._lbl_resum)

        # Barra de progrés
        self._progress = QProgressBar()
        main.addWidget(self._progress)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#ddd;")
        main.addWidget(sep)

        # Botons navegació
        nav = QHBoxLayout()
        self._btn_prev = QPushButton("◀ Anterior")
        self._btn_prev.setEnabled(False)
        self._btn_prev.clicked.connect(self._go_prev)

        self._btn_next = QPushButton("Desar i continuar ▶")
        self._btn_next.setStyleSheet(
            "background:#1565c0; color:white; font-weight:bold; padding:6px 14px;"
        )
        self._btn_next.setEnabled(False)
        self._btn_next.clicked.connect(self._go_next)

        self._btn_finish = QPushButton("✔ Finalitzar")
        self._btn_finish.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:6px 14px;"
        )
        self._btn_finish.setVisible(False)
        self._btn_finish.setEnabled(False)
        self._btn_finish.clicked.connect(self._finish)

        btn_cancel = QPushButton("Cancel·lar")
        btn_cancel.clicked.connect(self.reject)

        nav.addWidget(self._btn_prev)
        nav.addStretch()
        nav.addWidget(btn_cancel)
        nav.addWidget(self._btn_next)
        nav.addWidget(self._btn_finish)
        main.addLayout(nav)

        # Avís de selecció al mapa
        self._lbl_map_hint = QLabel(
            "🖱 Fes clic al mapa per seleccionar una tipologia forestal / d'ús"
        )
        self._lbl_map_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_map_hint.setStyleSheet(
            "padding:6px; background:#fff3e0; border:1px solid #ffb74d; "
            "border-radius:4px; font-weight:bold; color:#e65100;"
        )
        self._lbl_map_hint.setVisible(False)
        main.addWidget(self._lbl_map_hint)

    # ------------------------------------------------------------------
    # Cerca i filtre de formació forestal i codi d'ús
    # ------------------------------------------------------------------

    def _filter_formacio(self, text):
        text = _sense_accents(text.strip())
        for i in range(self._list_formacio.count()):
            item = self._list_formacio.item(i)
            item.setHidden(bool(text) and text not in _sense_accents(item.text()))

    def _filter_us(self, text):
        text = _sense_accents(text.strip())
        for i in range(self._list_us.count()):
            item = self._list_us.item(i)
            item.setHidden(bool(text) and text not in _sense_accents(item.text()))

    def _on_formacio_selected(self, item):
        if item:
            self._lbl_formacio_sel.setText(item.text() if item.data(32) else "—")

    def _set_forestal_fields_enabled(self, enabled):
        """Activa o desactiva els camps codi UA i formació forestal.
        No buida els valors: el buidat es fa explícitament a _show_feature."""
        no_ord = (
            self._features and self._current < len(self._features) and self._features[self._current].id() in self._no_ordenats
        )
        if not no_ord:
            self._spin_codi.setEnabled(enabled)
            self._lbl_codi.setEnabled(enabled)
        self._list_formacio.setEnabled(enabled)
        self._search_formacio.setEnabled(enabled)
        self._btn_clear_formacio.setEnabled(enabled)

    def _on_us_selected(self, item):
        if item:
            self._lbl_us_sel.setText(item.text() if item.data(32) else "—")
            codi_us = item.data(32)
            if codi_us and not is_forestal(codi_us):
                self._set_forestal_fields_enabled(False)
            else:
                self._set_forestal_fields_enabled(True)
            self._recalcular_superficies()

    def _on_no_ordenat_toggled(self, checked):
        """Gestiona el canvi del checkbox 'no ordenada'."""
        if not self._features or self._current >= len(self._features):
            return
        feat = self._features[self._current]
        fid = feat.id()
        if checked:
            self._no_ordenats.add(fid)
            # Esborrar el codi UA si s'activa no ordenada
            self._spin_codi.clear()
        else:
            self._no_ordenats.discard(fid)
        self._apply_no_ordenat_style(checked)
        self._recalcular_superficies()

    def _apply_no_ordenat_style(self, no_ordenat):
        """Quan la unitat és no ordenada:
          - Amaga i buida el codi rodal/UA.
          - Buida els camps formació forestal i codi d'ús, però els deixa
            editables: l'usuari pot definir-los o deixar-los en blanc.
          - Si els defineix, s'aplicarà l'estil de la formació.
          - Si no, el farciment serà blanc ("Exclòs de l'IOF").
        Quan es desmarca, restaura tots els camps a l'estat editable normal.
        """
        if no_ordenat:
            # Amagar i buidar codi rodal/UA
            self._lbl_codi.setVisible(False)
            self._spin_codi.setVisible(False)
            # Buidar formació forestal (mantenint editables)
            self._search_formacio.blockSignals(True)
            self._search_formacio.clear()
            self._search_formacio.blockSignals(False)
            self._list_formacio.blockSignals(True)
            self._list_formacio.clearSelection()
            self._list_formacio.setCurrentRow(-1)
            self._list_formacio.blockSignals(False)
            self._lbl_formacio_sel.setText("—")
            # Buidar codi d'ús (mantenint editables)
            self._search_us.blockSignals(True)
            self._search_us.clear()
            self._search_us.blockSignals(False)
            self._list_us.blockSignals(True)
            self._list_us.clearSelection()
            self._list_us.setCurrentRow(-1)
            self._list_us.blockSignals(False)
            self._lbl_us_sel.setText("—")
            # Mantenir tots els camps editables (sense canvi d'estil)
            self._list_formacio.setEnabled(True)
            self._list_formacio.setStyleSheet("")
            self._search_formacio.setEnabled(True)
            self._search_formacio.setStyleSheet("")
            self._btn_clear_formacio.setEnabled(True)
            self._list_us.setEnabled(True)
            self._list_us.setStyleSheet("")
            self._search_us.setEnabled(True)
            self._search_us.setStyleSheet("")
            self._btn_clear_us.setEnabled(True)
        else:
            # Restaurar codi rodal/UA
            self._lbl_codi.setVisible(True)
            self._spin_codi.setVisible(True)
            # Restaurar estils normals i reactivar camps
            self._list_formacio.setEnabled(True)
            self._list_formacio.setStyleSheet("")
            self._search_formacio.setEnabled(True)
            self._search_formacio.setStyleSheet("")
            self._btn_clear_formacio.setEnabled(True)
            self._list_us.setEnabled(True)
            self._list_us.setStyleSheet("")
            self._search_us.setEnabled(True)
            self._search_us.setStyleSheet("")
            self._btn_clear_us.setEnabled(True)

    def _get_formacio_data(self):
        item = self._list_formacio.currentItem()
        return item.data(32) if item else None

    def _get_us_data(self):
        item = self._list_us.currentItem()
        return item.data(32) if item else None

    def _set_formacio(self, codi):
        self._list_formacio.blockSignals(True)
        for i in range(self._list_formacio.count()):
            item = self._list_formacio.item(i)
            if item.data(32) == codi:
                item.setHidden(False)
                self._list_formacio.setCurrentItem(item)
                self._list_formacio.scrollToItem(item)
                self._lbl_formacio_sel.setText(item.text())
                self._list_formacio.blockSignals(False)
                return
        self._list_formacio.setCurrentRow(-1)
        self._lbl_formacio_sel.setText("—")
        self._list_formacio.blockSignals(False)

    def _set_us(self, codi):
        self._list_us.blockSignals(True)
        for i in range(self._list_us.count()):
            item = self._list_us.item(i)
            if item.data(32) == codi:
                item.setHidden(False)
                self._list_us.setCurrentItem(item)
                self._list_us.scrollToItem(item)
                self._lbl_us_sel.setText(item.text())
                self._list_us.blockSignals(False)
                return
        self._list_us.setCurrentRow(-1)
        self._lbl_us_sel.setText("—")
        self._list_us.blockSignals(False)

    # ------------------------------------------------------------------
    # Càrrega i pregunta inicial sobre parts no ordenades
    # ------------------------------------------------------------------

    def _load_layer(self):
        # Desactivar etiquetes temporals de IOF_Finques si n'hi ha
        try:
            from qgis.core import QgsProject, QgsVectorLayer, QgsWkbTypes
            for lyr in QgsProject.instance().mapLayers().values():
                if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Finques" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                    lyr.setLabelsEnabled(False)
                    lyr.triggerRepaint()
                    break
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass

        self._layer = _get_layer(LAYERS_UNITATS)
        if self._layer is None:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(
                self, "IOF_Rodals / IOF_Unitats_Actuacio", accio="omplir les dades"
            )
            self._cancelled = True
            self.reject()
            return

        # Nom del camp codi
        if "codi_ua" in self._layer.fields().names():
            self._codi_field = "codi_ua"
            self._lbl_codi.setText("Codi UA *:")
        else:
            self._codi_field = "codi_rodal"
            self._lbl_codi.setText("Codi rodal *:")

        # Suspendre l'estil aplicat mentre s'omplen els camps:
        # guardar el renderer actual i aplicar-ne un de neutre
        self._suspend_style()

        all_feats = list(self._layer.getFeatures())
        if not all_feats:
            QMessageBox.information(
                self, "Capa buida",
                "La capa d'unitats no conté cap polígon.\n"
                "Digitalitza les tipologies forestals primer."
            )
            self._cancelled = True
            self.reject()
            return

        self._features = all_feats

        # Comprova que TOTES les finques ja tinguin tipologies forestals
        # completes; si n'hi ha alguna sense (p. ex. una finca afegida
        # després d'omplir les altres), avisa i cancel·la en lloc de
        # deixar omplir dades tenint una finca sense digitalitzar.
        finca_lyr = _get_layer("IOF_Finques")
        if finca_lyr is not None:
            from .iof_utils import find_interior_polygons, finca_te_unitats_completes
            all_finques = list(finca_lyr.getFeatures())
            exclusion_ids = find_interior_polygons(all_finques)
            finques_valides = [f for f in all_finques if f.id() not in exclusion_ids]
            incompletes = [
                f for f in finques_valides
                if not finca_te_unitats_completes(self._layer, f)
            ]
            if incompletes:
                fields_lower = {n.lower(): n for n in finca_lyr.fields().names()}
                codi_field = fields_lower.get("codi_finca")
                if codi_field:
                    noms = ", ".join(str(f[codi_field]) for f in incompletes)
                else:
                    noms = ", ".join(str(f.id()) for f in incompletes)
                QMessageBox.information(
                    self, "Unitats incompletes",
                    f"Hi ha finques sense tipologies forestals completes: "
                    f"{noms}.\n\n"
                    "Digitalitza primer les unitats que falten "
                    "(Digitalitzar → Digitalitzar tipologies forestals) "
                    "abans d'omplir les dades."
                )
                self._cancelled = True
                self.reject()
                return

        # Si la capa ja té el camp _label (edició per segon cop),
        # regenerar TOTES les etiquetes llegint la taula d'atributs
        if "_label" in self._layer.fields().names():
            try:
                self._regenerar_etiquetes()
                from .iof_format_dialog import _apply_preview_labels
                _apply_preview_labels(self._layer, '"_label"', '_label')
            except Exception:
                import traceback
                traceback.print_exc()

        # Preguntar si totes les unitats s'ordenen
        self._ask_no_ordenats()

    def _sup_finca_neta(self):
        """
        Retorna la superfície neta de la finca en ha:
        àrea de IOF_Finques menys les àrees dels polígons interiors (exclusions).
        """
        from .iof_utils import get_layer as _get_lyr, find_interior_polygons as _find_exclusions
        layer_f = _get_lyr("IOF_Finques")
        if layer_f is None or layer_f.featureCount() == 0:
            return None

        all_feats = list(layer_f.getFeatures())
        excl_ids = _find_exclusions(all_feats)

        area_total = sum(
            f.geometry().area() for f in all_feats
            if f.id() not in excl_ids and f.geometry() and not f.geometry().isEmpty()
        )
        area_exclosa = sum(
            f.geometry().area() for f in all_feats
            if f.id() in excl_ids and f.geometry() and not f.geometry().isEmpty()
        )
        neta = (area_total - area_exclosa) / 10000
        return round(neta, 2)

    def _ask_no_ordenats(self):
        """Ja no fa cap pregunta: la casella de verificació al formulari gestiona les no ordenades."""
        self._no_ordenats = set()
        self._update_progress()
        self._activate_map_select()

    def _select_no_ordenats(self):
        """
        Diàleg de checkboxes per marcar les unitats no ordenades.
        Mentre l'usuari navega, ressalta cada unitat al mapa.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Selecciona les unitats no ordenades")
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumWidth(440)
        layout = QVBoxLayout(dlg)

        lbl = QLabel(
            "Marca les unitats que <b>NO s'ordenen</b>.\n"
            "Fes clic a cada fila per veure-la ressaltada al mapa."
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(200)
        container = QWidget()
        vbox = QVBoxLayout(container)

        # QgsHighlight per ressaltar les unitats marcades (respecta forats)
        # Un highlight per unitat marcada; es crea/elimina en marcar/desmarcar
        canvas = self.iface.mapCanvas()
        highlights = {}  # f_idx -> QgsHighlight

        checkboxes = []
        for i, feat in enumerate(self._features):
            codi = feat[self._codi_field]
            geom = feat.geometry()
            area_ha = round(geom.area() / 10000, 2) if geom and not geom.isEmpty() else 0.0
            label = f"Unitat {i + 1}"
            if codi and codi == codi:
                label += f" (codi: {codi})"
            label += f"  —  {area_ha} ha"

            cb = QCheckBox(label)
            cb.setProperty("feat_idx", i)
            cb.setStyleSheet("padding: 4px;")

            def make_hover(f_idx, _canvas):
                def on_toggle(checked):
                    feat_i = self._features[f_idx]
                    g = feat_i.geometry()
                    if checked and g and not g.isEmpty():
                        from qgis.gui import QgsHighlight
                        h = QgsHighlight(_canvas, feat_i, self._layer)
                        h.setColor(QColor(255, 165, 0, 220))
                        h.setFillColor(QColor(255, 165, 0, 60))
                        h.setWidth(4)
                        h.show()
                        highlights[f_idx] = h
                    else:
                        if f_idx in highlights:
                            highlights[f_idx].hide()
                            del highlights[f_idx]
                    _canvas.refresh()
                return on_toggle

            cb.clicked.connect(make_hover(i, canvas))
            checkboxes.append(cb)
            vbox.addWidget(cb)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        btns = QHBoxLayout()
        btn_ok = QPushButton("Confirmar selecció")
        btn_ok.setStyleSheet(
            "background:#1565c0; color:white; font-weight:bold; padding:6px 12px;"
        )
        btn_cap = QPushButton("Cap (totes s'ordenen)")
        btn_ok.clicked.connect(dlg.accept)
        btn_cap.clicked.connect(dlg.reject)
        btns.addStretch()
        btns.addWidget(btn_cap)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

        result = dlg.exec()

        # Netejar tots els highlights temporals
        for h in highlights.values():
            h.hide()
        highlights.clear()

        if result == QDialog.DialogCode.Accepted:
            self._no_ordenats = {
                self._features[cb.property("feat_idx")].id()
                for cb in checkboxes if cb.isChecked()
            }
        else:
            self._no_ordenats = set()

        self._update_progress()
        self._activate_map_select()

    # ------------------------------------------------------------------
    # Mostrar polígon
    # ------------------------------------------------------------------

    def _show_feature(self, idx):
        self._current = idx
        total = len(self._features)

        # Bloquejar _mark_modified ABANS d'activar el formulari
        self._loading_feature = True
        self._form_modified = False

        # Activar formulari i botons en seleccionar una unitat
        self._form_group.setEnabled(True)
        self._btn_next.setEnabled(True)
        self._btn_finish.setEnabled(True)

        self._update_progress()

        # Recarregar la feature directament de la capa per obtenir
        # els valors desats (self._features pot tenir còpies antigues)
        feat_orig = self._features[idx]
        from qgis.core import QgsFeatureRequest
        feats_frescos = list(self._layer.getFeatures(
            QgsFeatureRequest().setFilterFid(feat_orig.id())
        ))
        feat = feats_frescos[0] if feats_frescos else feat_orig

        # Ressaltar al mapa
        self._highlight(feat.geometry())

        # Netejar filtres de cerca i mostrar tots els items
        # (bloquejar signals; no forçar scroll per no perdre posició)
        if self._search_formacio.text():
            self._search_formacio.blockSignals(True)
            self._search_formacio.clear()
            self._search_formacio.blockSignals(False)
            for i in range(self._list_formacio.count()):
                self._list_formacio.item(i).setHidden(False)
        if self._search_us.text():
            self._search_us.blockSignals(True)
            self._search_us.clear()
            self._search_us.blockSignals(False)
            for i in range(self._list_us.count()):
                self._list_us.item(i).setHidden(False)

        # Llegir camps actuals de la capa
        no_ordenat = feat_orig.id() in self._no_ordenats

        # Sincronitzar el checkbox (bloquejar el senyal per evitar efectes secundaris)
        self._chk_no_ordenat.blockSignals(True)
        self._chk_no_ordenat.setChecked(no_ordenat)
        self._chk_no_ordenat.blockSignals(False)
        self._apply_no_ordenat_style(no_ordenat)

        fields = feat.fields().names()
        codi_val = feat[self._codi_field]
        for_val = feat["for_forestal"] if "for_forestal" in fields else None
        us_val = feat["codi_us"] if "codi_us" in fields else None

        def val_ok(v):
            if v is None or v != v:
                return False
            s = str(v).strip()
            return s != "" and s.upper() != "NULL"

        # Codi UA
        self._lbl_codi.setVisible(not no_ordenat)
        self._spin_codi.setVisible(not no_ordenat)
        if no_ordenat:
            self._spin_codi.clear()
        elif val_ok(codi_val):
            self._spin_codi.setText(str(codi_val).strip())
        elif val_ok(us_val) and not is_forestal(str(us_val).strip()):
            # Codi d'ús no forestal: el codi UA no aplica
            self._spin_codi.clear()
        else:
            # Feature nova: caixa buida, l'usuari ha d'entrar el valor
            self._spin_codi.clear()
        # Formació forestal: valor desat > buit
        if val_ok(for_val):
            self._set_formacio(str(for_val).strip())
        else:
            self._list_formacio.blockSignals(True)
            self._list_formacio.clearSelection()
            self._list_formacio.setCurrentRow(-1)
            self._lbl_formacio_sel.setText("—")
            self._list_formacio.blockSignals(False)
            self._list_formacio.scrollToTop()

        # Codi d'ús: valor desat > buit
        if val_ok(us_val):
            self._set_us(str(us_val).strip())
        else:
            self._list_us.blockSignals(True)
            self._list_us.clearSelection()
            self._list_us.setCurrentRow(-1)
            self._lbl_us_sel.setText("—")
            self._list_us.blockSignals(False)
            self._list_us.scrollToTop()

        # Si el codi d'ús desat és no forestal, desactivar camps corresponents
        if val_ok(us_val) and not is_forestal(str(us_val).strip()):
            self._set_forestal_fields_enabled(False)
        else:
            self._set_forestal_fields_enabled(True)

        # Calcular superfícies
        self._recalcular_superficies()

        # Navegació
        self._btn_prev.setEnabled(idx > 0)
        # "És l'última pendent" NO es determina per la posició a la
        # llista interna (idx == total - 1): self._features no té cap
        # ordre lògic garantit, ja que la navegació és per clic al
        # mapa, no seqüencial. Si es feia servir la posició, en
        # omplir les unitats en un ordre diferent de l'intern podia
        # sortir el botó "Finalitzar" (i tancar l'assistent donant-lo
        # per acabat) tot i quedar unitats sense definir. Ara només és
        # "última" si TOTES LES ALTRES unitats ja tenen dades desades.
        altres_pendents = any(
            not self._feat_te_dades(f) for i, f in enumerate(self._features) if i != idx
        )
        is_last = not altres_pendents
        self._btn_next.setVisible(not is_last)
        self._btn_finish.setVisible(is_last)
        self._loading_feature = False  # Ara l'usuari pot modificar camps

    def _area_neta(self, feat):
        """Retorna l'àrea en ha del polígon (2 decimals)."""
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return 0.0
        return round(geom.area() / 10000, 2)

    def _recalcular_superficies(self):
        """Calcula les superfícies basant-se en la geometria neta i el codi d'ús."""
        if not self._features or self._current >= len(self._features):
            return  # crida prematura durant la construcció de la UI
        feat = self._features[self._current]
        area_ha = self._area_neta(feat)

        no_ordenat = feat.id() in self._no_ordenats

        if no_ordenat:
            sup_ord = 0.0
            sup_for = 0.0
            sup_arb = 0.0
        else:
            sup_ord = area_ha
            codi_us = self._get_us_data()
            if codi_us:
                sup_for = area_ha if is_forestal(codi_us) else 0.0
                sup_arb = area_ha if is_arbrat(codi_us) else 0.0
            else:
                sup_for = area_ha
                sup_arb = area_ha

        self._lbl_sup_ord_val.setText(
            "0.00 ha (no s'ordena)" if no_ordenat else f"{sup_ord:.2f} ha"
        )
        self._lbl_sup_for_val.setText(f"{sup_for:.2f} ha")
        self._lbl_sup_arb_val.setText(f"{sup_arb:.2f} ha")

        self._area_ha = area_ha
        self._sup_ord = round(sup_ord, 2)
        self._sup_for = round(sup_for, 2)
        self._sup_arb = round(sup_arb, 2)

    # ------------------------------------------------------------------
    # Validació i desament
    # ------------------------------------------------------------------

    def _validate(self):
        no_ordenat = self._features[self._current].id() in self._no_ordenats
        codi_us = self._get_us_data()
        no_forest = codi_us and not is_forestal(codi_us)
        # El codi UA és opcional per a no ordenats i per a usos no forestals
        if not no_ordenat and not no_forest and not self._spin_codi.text().strip():
            QMessageBox.warning(self, "Camp obligatori", "Introdueix el codi de la unitat.")
            return False
        # La formació forestal és obligatòria excepte si:
        # - el codi d'ús és no arbrat, o
        # - la unitat no està ordenada (pot no tenir ni formació ni ús)
        if not no_ordenat:
            codi_us = self._get_us_data()
            from .iof_taules import is_arbrat
            us_es_arbrat = is_arbrat(codi_us) if codi_us else True
            if us_es_arbrat and self._get_formacio_data() is None:
                QMessageBox.warning(
                    self, "Camp obligatori",
                    "Selecciona una formació forestal.\n\n"
                    "(Només és opcional quan el codi d\'ús és no arbrat)"
                )
                return False
        return True

    def _save_current(self):
        feat = self._features[self._current]
        fid = feat.id()
        fields = self._layer.fields().names()

        no_ordenat = feat.id() in self._no_ordenats
        codi_us_val = self._get_us_data()
        no_forest = codi_us_val and not is_forestal(codi_us_val)
        if not no_ordenat:
            self._last_codi = self._spin_codi.text().strip()

        def cv(field, val):
            if field in fields:
                self._layer.changeAttributeValue(
                    fid, self._layer.fields().indexOf(field), val
                )

        self._layer.startEditing()
        cv(self._codi_field, None if (no_ordenat or no_forest) else self._spin_codi.text().strip())
        cv("for_forestal", None if no_forest else (self._get_formacio_data() or ""))
        cv("codi_us", self._get_us_data() or "")
        cv("sup_ord", self._sup_ord)
        cv("sup_forestal", self._sup_for)
        cv("sup_arbrada", self._sup_arb)
        if not self._layer.commitChanges():
            errs = "; ".join(self._layer.commitErrors())
            self._layer.rollBack()
            QMessageBox.critical(
                self, "Error desant",
                f"No s'han pogut desar les dades de la unitat:\n{errs}"
            )
        else:
            try:
                # Desar l'etiqueta directament al camp _label d'aquesta feature.
                # Usem un camp real per evitar que l'expressió s'apliqui
                # a features no desades.
                from qgis.core import QgsField
                from qgis.PyQt.QtCore import QVariant
                lyr = self._layer
                if "_label" not in lyr.fields().names():
                    lyr.dataProvider().addAttributes(
                        [QgsField("_label", QVariant.String)]
                    )
                    lyr.updateFields()
                idx_lbl = lyr.fields().indexOf("_label")
                feat_id = self._features[self._current].id()
                _no_ord = feat_id in self._no_ordenats
                # Llegir valors del camp desat (no de la UI, que pot estar buidada)
                from qgis.core import QgsFeatureRequest as _QFR
                _saved = list(lyr.getFeatures(_QFR().setFilterFid(feat_id)))
                _sf = _saved[0] if _saved else None
                _flds = lyr.fields().names()
                _for = (
                    str(_sf['for_forestal']).strip()
                    if _sf and 'for_forestal' in _flds and _sf['for_forestal'] not in (None, '', 'NULL') else ''
                )
                _us_val = (
                    str(_sf['codi_us']).strip()
                    if _sf and 'codi_us' in _flds and _sf['codi_us'] not in (None, '', 'NULL') else ''
                )
                _codi = (
                    str(_sf[self._codi_field]).strip()
                    if _sf and self._codi_field in _flds and _sf[self._codi_field] not in (None, '', 'NULL') else ''
                )
                bool(_us_val) and not is_forestal(_us_val)
                if _no_ord:
                    lbl = f"{_for} Exclòs de l'IOF" if _for else "Exclòs de l'IOF"
                else:
                    parts = [p for p in [_codi, _for, _us_val] if p]
                    lbl = " | ".join(parts) if parts else None
                lyr.startEditing()
                lyr.changeAttributeValue(feat_id, idx_lbl, lbl)
                lyr.commitChanges()
                # Activar etiquetes simples sobre _label
                from .iof_format_dialog import _apply_preview_labels
                _apply_preview_labels(lyr, '"_label"', "_label")
            except Exception:
                import traceback
                traceback.print_exc()
            # Actualitzar etiqueta de resum
            codi_desat = self._spin_codi.text().strip()
            for_desat = self._get_formacio_data() or ""
            us_desat = self._get_us_data() or ""
            nom_codi = "Rodal" if self._codi_field == "codi_rodal" else "UA"
            no_ord = self._features[self._current].id() in self._no_ordenats
            no_forest = us_desat and not is_forestal(us_desat)

            if no_ord:
                # No ordenat: codi formació + "Exclòs de l'IOF"
                text = for_desat + " Exclòs de l'IOF" if for_desat else "Exclòs de l'IOF"
                self._lbl_resum.setText(f"✔  {text} — desat")
            elif no_forest:
                # No forestal: només el codi d'ús (sense cap /)
                self._lbl_resum.setText(f"✔  {us_desat} — desat")
            else:
                parts = [p for p in [for_desat, us_desat] if p]
                codis = " / ".join(parts) if parts else "—"
                self._lbl_resum.setText(
                    f"✔  {nom_codi} {codi_desat} desat  —  {codis}"
                )
            # Si el toggle de ressaltat està actiu, refrescar-lo: la
            # unitat que s'acaba de desar ha de deixar de sortir-hi si
            # ja té codi_us omplert.
            self._refresh_undefined_highlights()

    # ------------------------------------------------------------------
    # Navegació
    # ------------------------------------------------------------------

    def _go_prev(self):
        if self._current > 0:
            self._show_feature(self._current - 1)

    def _go_next(self):
        if not self._validate():
            return
        self._deactivate_map_select()
        self._save_current()
        self._update_progress()
        self._clear_highlight()
        # Bloquejar el formulari fins que es seleccioni la unitat següent
        self._form_group.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._btn_finish.setEnabled(False)
        self._form_modified = False
        # Mateix criteri que a _show_feature: si queda alguna unitat
        # sense dades (en qualsevol posició, no només després de
        # l'actual a la llista interna), cal reactivar la selecció al
        # mapa perquè l'usuari en pugui triar una altra.
        falten = any(not self._feat_te_dades(f) for f in self._features)
        if falten:
            self._activate_map_select()

    def _finish(self):
        if not self._validate():
            return
        self._deactivate_map_select()
        self._save_current()

        # Comprovació defensiva: encara que el botó "Finalitzar" ja
        # només s'hauria de mostrar quan no queda cap altra unitat
        # pendent, es torna a comprovar aquí abans de tancar
        # l'assistent -- per si de cas queda alguna unitat sense
        # dades, s'avisa en lloc de donar per acabat silenciosament.
        pendents = [
            f for f in self._features if not self._feat_te_dades(f)
        ]
        if pendents:
            QMessageBox.warning(
                self, "Encara falten unitats",
                f"Encara queden {len(pendents)} "
                f"{'tipologies forestals' if len(pendents) != 1 else 'tipologia forestal'} "
                "sense definir. Fes clic al mapa per continuar-les omplint."
            )
            self._update_progress()
            self._activate_map_select()
            return

        self._clear_highlight()
        had_saved_labeling = self._saved_labeling is not None
        self._restore_style()
        # Si no hi havia estil aplicat prèviament, mantenir etiquetes provisionals
        if not had_saved_labeling and self._layer is not None:
            from .iof_format_dialog import _apply_preview_labels
            _apply_preview_labels(self._layer, '"_label"', '_label')
        n = len(self._features)
        no_ord = len(self._no_ordenats)
        suma = sum(self._area_neta(f) for f in self._features
                   if f.id() not in self._no_ordenats)
        msg = (
            f"S'han desat les dades de {n} "
            f"{'tipologies forestals' if n != 1 else 'tipologia forestal'}.\n\n"
            f"Superfície ordenada total: {suma:.2f} ha"
        )
        if no_ord:
            msg += (
                f"\n{no_ord} unitat{'s' if no_ord != 1 else ''} "
                f"marcada{'es' if no_ord != 1 else ''} com a no ordenada"
                f"{'es' if no_ord != 1 else ''} (superfície = 0)."
            )
        QMessageBox.information(self, "Completat", msg)
        self.accept()

    def _regenerar_etiquetes(self):
        """
        Recalcula el camp _label per a totes les features a partir
        dels valors actuals de la taula d'atributs.
        S'executa en obrir el wizard quan la capa ja havia estat editada.
        """
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant
        lyr = self._layer
        flds = lyr.fields().names()

        if "_label" not in flds:
            lyr.dataProvider().addAttributes([QgsField("_label", QVariant.String)])
            lyr.updateFields()
            flds = lyr.fields().names()

        idx_lbl = lyr.fields().indexOf("_label")
        lyr.startEditing()
        for feat in lyr.getFeatures():
            _codi = (
                str(feat[self._codi_field]).strip()
                if self._codi_field in flds and feat[self._codi_field] not in (None, "", "NULL") else ""
            )
            _for = (
                str(feat["for_forestal"]).strip()
                if "for_forestal" in flds and feat["for_forestal"] not in (None, "", "NULL") else ""
            )
            _us = (
                str(feat["codi_us"]).strip()
                if "codi_us" in flds and feat["codi_us"] not in (None, "", "NULL") else ""
            )
            parts = [p for p in [_codi, _for, _us] if p]
            lbl = " | ".join(parts) if parts else None
            lyr.changeAttributeValue(feat.id(), idx_lbl, lbl)
        lyr.commitChanges()

    # ------------------------------------------------------------------
    # Selecció per clic al mapa
    # ------------------------------------------------------------------

    def _activate_map_select(self):
        """Activa l'eina de clic al mapa per seleccionar una unitat."""
        from qgis.gui import QgsMapToolEmitPoint
        canvas = self.iface.mapCanvas()
        self._map_tool_backup = canvas.mapTool()
        self._map_tool = QgsMapToolEmitPoint(canvas)
        self._map_tool.canvasClicked.connect(self._on_map_clicked)
        canvas.setMapTool(self._map_tool)
        self._lbl_map_hint.setVisible(True)

    def _deactivate_map_select(self):
        """Desactiva l'eina de clic al mapa."""
        try:
            if self._map_tool:
                self._map_tool.canvasClicked.disconnect(self._on_map_clicked)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        canvas = self.iface.mapCanvas()
        if self._map_tool_backup:
            canvas.setMapTool(self._map_tool_backup)
        self._map_tool = None
        self._lbl_map_hint.setVisible(False)

    def _on_map_clicked(self, point, button):
        """Quan l'usuari clica al mapa, selecciona la unitat corresponent."""
        from qgis.core import QgsGeometry, QgsFeatureRequest
        clicked_geom = QgsGeometry.fromPointXY(point)
        tolerance = self.iface.mapCanvas().mapUnitsPerPixel() * 5

        found_idx = None
        for i, feat in enumerate(self._features):
            if feat.geometry() and feat.geometry().intersects(
                    clicked_geom.buffer(tolerance, 5)):
                found_idx = i
                break

        if found_idx is None:
            return  # Clic fora de qualsevol unitat, ignorar

        feat = self._features[found_idx]

        # Comprovar si la unitat ja té dades desades
        f_actual = next(self._layer.getFeatures(
            QgsFeatureRequest().setFilterFid(feat.id())), None)
        ja_definida = False
        if f_actual:
            if feat.id() in self._no_ordenats:
                ja_definida = True
            else:
                for camp in [self._codi_field, "for_forestal", "codi_us"]:
                    if camp in f_actual.fields().names():
                        val = f_actual[camp]
                        if val is not None and str(val).strip() not in ("", "NULL"):
                            ja_definida = True
                            break

        if ja_definida:
            reply = QMessageBox.question(
                self, "Unitat ja definida",
                "Aquesta unitat ja té dades desades.\nVols modificar-la?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                return

        self._show_feature(found_idx)
        self._lbl_map_hint.setVisible(False)
        self.raise_()
        self.activateWindow()

    def _mark_modified(self):
        """Marca que l'usuari ha tocat algun camp del formulari."""
        if getattr(self, '_loading_feature', False):
            return
        self._form_modified = True

    def _feat_te_dades(self, feat):
        """Retorna True si la unitat ja té les dades desades a la capa
        (llegides en directe de la capa, no de la còpia a
        self._features, que pot estar desactualitzada)."""
        from qgis.core import QgsFeatureRequest
        f = next(self._layer.getFeatures(
            QgsFeatureRequest().setFilterFid(feat.id())), None)
        if not f:
            return False
        fields = self._layer.fields().names()
        if "sup_ord" in fields:
            # sup_ord s'escriu sempre en desar (fins i tot val 0.0),
            # però NULL significa que mai s'ha desat
            val = f["sup_ord"]
            return val is not None and str(val).strip() not in ("", "NULL")
        # Fallback si la capa no té sup_ord
        codi = f[self._codi_field]
        us_val = f["codi_us"] if "codi_us" in fields else None
        for_val = f["for_forestal"] if "for_forestal" in fields else None
        te_codi = codi is not None and str(codi).strip() not in ("", "NULL")
        te_us = us_val is not None and str(us_val).strip() not in ("", "NULL")
        te_for = for_val is not None and str(for_val).strip() not in ("", "NULL")
        return te_codi or te_us or te_for

    def _update_progress(self):
        """Actualitza la barra de progrés comptant les unitats desades."""
        total = len(self._features)
        n_desades = sum(1 for feat in self._features if self._feat_te_dades(feat))
        self._progress.setMaximum(total)
        self._progress.setValue(n_desades)
        if n_desades >= total:
            self._lbl_progress.setText(
                f"Totes les {total} unitats estan definides — "
                "fes clic al mapa per editar-ne una"
            )
        else:
            self._lbl_progress.setText(
                f"{n_desades} de {total} tipologies forestals / ús estan definides"
            )

    # ------------------------------------------------------------------
    # Rubber band
    # ------------------------------------------------------------------

    @staticmethod
    def _exterior_only(geom):
        """Retorna una geometria amb només els anells exteriors (sense forats)."""
        from qgis.core import QgsGeometry
        if not geom or geom.isEmpty():
            return geom
        if geom.isMultipart():
            parts = geom.asMultiPolygon()
            return QgsGeometry.fromMultiPolygonXY(
                [[part[0]] for part in parts if part]
            )
        rings = geom.asPolygon()
        return QgsGeometry.fromPolygonXY([rings[0]]) if rings else geom

    # ------------------------------------------------------------------
    # Suspensió i restauració de l'estil aplicat
    # ------------------------------------------------------------------

    def _suspend_style(self):
        """Substitueix el renderer actual per un de neutre (edició activa).
        Guarda el renderer i el labeling originals per restaurar-los en tancar."""
        if self._layer is None:
            return
        from qgis.core import QgsSingleSymbolRenderer, QgsFillSymbol
        if self._saved_renderer is None:
            self._saved_renderer = self._layer.renderer().clone()
        # Guardar labeling actual
        if not hasattr(self, '_saved_labeling'):
            self._saved_labeling = None
        if self._saved_labeling is None and self._layer.labeling() is not None:
            self._saved_labeling = self._layer.labeling().clone()
        self._saved_labels_enabled = self._layer.labelsEnabled()
        # Renderer neutre: contorn gris, fons transparent
        sym = QgsFillSymbol.createSimple({
            'color': '0,0,0,0',
            'outline_color': '#888888',
            'outline_width': '0.4',
        })
        self._layer.setRenderer(QgsSingleSymbolRenderer(sym))
        self._layer.triggerRepaint()

    def _restore_style(self):
        """Restaura el renderer i el labeling guardats i repinta."""
        if self._layer is None or self._saved_renderer is None:
            return
        self._layer.setRenderer(self._saved_renderer.clone())
        self._saved_renderer = None
        # Restaurar labeling:
        # - Si hi havia labeling guardat (estil aplicat), restaurar-lo.
        # - Si no n'hi havia, mantenir el labeling provisional actual
        #   (_apply_preview_labels sobre _label) perquè les etiquetes
        #   "No ordenat" / formació / codi segueixen sent visibles.
        saved_lab = getattr(self, '_saved_labeling', None)
        if saved_lab is not None:
            self._layer.setLabeling(saved_lab.clone())
            self._layer.setLabelsEnabled(getattr(self, '_saved_labels_enabled', True))
            self._saved_labeling = None
        # (si no hi havia labeling guardat, no tocar el labeling actual)
        self._layer.triggerRepaint()

    def _highlight(self, geom):
        self._clear_highlight()
        if not geom or geom.isEmpty():
            return
        feat = self._features[self._current]
        from qgis.gui import QgsHighlight
        self._rubber_band = QgsHighlight(
            self.iface.mapCanvas(), feat, self._layer
        )
        self._rubber_band.setColor(QColor(255, 220, 0, 220))
        self._rubber_band.setFillColor(QColor(255, 235, 0, 60))
        self._rubber_band.setWidth(4)
        self._rubber_band.show()
        self.iface.mapCanvas().refresh()
        self._layer.selectByIds([feat.id()])

    def _clear_highlight(self):
        if self._rubber_band is not None:
            self._rubber_band.hide()
            self._rubber_band = None
        if self._layer:
            self._layer.removeSelection()
        self.iface.mapCanvas().refresh()

    # ------------------------------------------------------------------
    # Ressaltat (toggle) de totes les unitats encara sense definir
    # ------------------------------------------------------------------

    def _on_toggle_undefined(self, checked):
        self._show_undefined = checked
        if checked:
            self._refresh_undefined_highlights()
        else:
            self._clear_undefined_highlights()

    def _refresh_undefined_highlights(self):
        """Repinta el ressaltat de totes les unitats encara no definides.

        Fa servir exactament la mateixa lògica que _on_map_clicked() per
        decidir "ja_definida" (comprova self._codi_field, "for_forestal"
        i "codi_us" — no només "codi_us"), i tracta igual el text
        literal "NULL" que pot haver quedat desat en algun camp com a
        buit real. Si aquesta funció i _on_map_clicked deixen de dir
        el mateix, el ressaltat i el clic al mapa es contradiuen (una
        unitat pot sortir ressaltada com a "sense definir" i alhora el
        clic dir "ja té dades desades").
        """
        self._clear_undefined_highlights()
        if not self._show_undefined or self._layer is None:
            return
        from qgis.gui import QgsHighlight
        from qgis.core import QgsFeatureRequest
        fields = self._layer.fields().names()
        camps = [c for c in (self._codi_field, "for_forestal", "codi_us") if c in fields]
        if not camps:
            return
        condicions = [f'("{c}" IS NULL OR "{c}" = \'\' OR "{c}" = \'NULL\')' for c in camps]
        expr = " AND ".join(condicions)
        req = QgsFeatureRequest().setFilterExpression(expr)
        for feat in self._layer.getFeatures(req):
            if feat.id() in self._no_ordenats:
                continue  # "no ordenat" també compta com a definit
            hl = QgsHighlight(self.iface.mapCanvas(), feat, self._layer)
            hl.setColor(QColor(220, 0, 0, 220))
            hl.setFillColor(QColor(220, 0, 0, 0))
            hl.setWidth(3)
            hl.show()
            self._undefined_highlights.append(hl)
        self.iface.mapCanvas().refresh()

    def _clear_undefined_highlights(self):
        for hl in self._undefined_highlights:
            hl.hide()
        self._undefined_highlights = []
        self.iface.mapCanvas().refresh()

    def reject(self):
        if self._map_tool:
            self._deactivate_map_select()
        # Avisar si hi ha dades no desades al formulari actiu
        if self._form_group.isEnabled() and self._form_modified:
            reply = QMessageBox.warning(
                self, "Sortir sense desar",
                "Les dades de la unitat seleccionada no s'han desat.\n\nVols sortir?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                if self._features:
                    self._activate_map_select()
                return
        self._clear_highlight()
        self._clear_undefined_highlights()
        had_saved = self._saved_labeling is not None
        self._restore_style()
        if not had_saved and self._layer is not None:
            from .iof_format_dialog import _apply_preview_labels
            _apply_preview_labels(self._layer, '"_label"', '_label')
        super().reject()

    def closeEvent(self, event):
        if self._map_tool:
            self._deactivate_map_select()
        if self._form_group.isEnabled() and self._form_modified:
            reply = QMessageBox.warning(
                self, "Sortir sense desar",
                "Les dades de la unitat seleccionada no s'han desat.\n\nVols sortir?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                if self._features:
                    self._activate_map_select()
                return
        self._clear_highlight()
        self._clear_undefined_highlights()
        had_saved = self._saved_labeling is not None
        self._restore_style()
        if not had_saved and self._layer is not None:
            from .iof_format_dialog import _apply_preview_labels
            _apply_preview_labels(self._layer, '"_label"', '_label')
        super().closeEvent(event)

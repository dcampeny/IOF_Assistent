# -*- coding: utf-8 -*-
"""
iof_base_point_dialog.py — Classe base per als diàlegs de digitalització de punts IOF.

Centralitza el codi comú que estava duplicat a:
  - iof_aigua_dialog.py
  - iof_elements_dialog.py
  - iof_inventari_dialog.py

Cada subclasse sobreescriu:
  - LAYER_NAME           : nom de la capa QGIS
  - _dialog_title()      : títol de la finestra
  - _heading_text()      : text del títol interior (QLabel gran)
  - _build_attr_group()  : QGroupBox amb els atributs específics
  - _apply_attrs(fid, x, y) : escriu els atributs al feature pendent
  - _apply_attrs_new(feat, x, y) : emplena la feature nova (mode coord)
  - _reset_attr_fields() : neteja els camps d'atributs
  - _load_attrs_for_mod(feat)    : carrega atributs en mode edició
  - _save_attrs_for_mod(fid)     : desa atributs en mode edició
  - _feature_display_name(feat)  : text per als missatges (p.ex. codi o nom)
  - _counter_text(n)             : text del comptador (p.ex. "Punts afegits: 3")
  - _info_color()                : color de fons del quadre d'informació (hex)
  - _accent_color()              : color d'accent dels botons principals (hex)
  - _post_load_layer()           : hook cridat al final de _load_layer()
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout,
    QLabel, QPushButton, QRadioButton, QButtonGroup,
    QGroupBox, QDoubleSpinBox, QMessageBox, QFrame,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsPointXY, QgsWkbTypes, QgsEditFormConfig,
    QgsFeatureRequest,
)


class IOFBasePointDialog(QDialog):
    """
    Classe base per a diàlegs de digitalització de punts IOF.

    Implementa completament:
      - Mètode mapa (clic → pendent → Desar)
      - Mètode coordenades UTM
      - Modificar element seleccionat
      - Eliminar element seleccionat
      - Restauració de l'eina i del formulari en tancar
    """

    LAYER_NAME = ""          # Sobreescriure a cada subclasse
    GEOM_TYPE = QgsWkbTypes.GeometryType.PointGeometry   # Sobreescriure si cal

    # ------------------------------------------------------------------
    # Constructors i inicialització
    # ------------------------------------------------------------------

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._layer = None
        self._tool_backup = None
        self._form_backup = None
        self._count = 0
        self._pending_fid = None
        self._pending_pt = None
        self._mod_fid = None
        # True si _load_layer() no ha trobat la capa: qui crea el
        # diàleg (iof_exporter.py) ha de comprovar-ho i no cridar
        # .show() en aquest cas.
        self._cancelled = False

        self.setWindowTitle(f"IOF Assistent — {self._dialog_title()}")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(440)
        self._build_ui()
        self._load_layer()

    # ------------------------------------------------------------------
    # Mètodes a sobreescriure (interfície de la subclasse)
    # ------------------------------------------------------------------

    def _dialog_title(self):
        return "Digitalitzar punts"

    def _heading_text(self):
        return "Digitalitzar punts"

    def _build_attr_group(self):
        """Retorna un QGroupBox amb els camps d'atributs específics."""
        return QGroupBox("Atributs")

    def _apply_attrs(self, fid, x, y):
        """Escriu els atributs al feature pendent (mode mapa). Ha de fer commit=False."""

    def _apply_attrs_new(self, feat, x, y):
        """Emplena una QgsFeature nova (mode coordenades)."""

    def _reset_attr_fields(self):
        """Neteja/reinicia els camps d'atributs al formulari."""

    def _load_attrs_for_mod(self, feat):
        """Carrega els valors actuals d'un feature als camps del formulari (mode mod)."""

    def _save_attrs_for_mod(self, fid):
        """
        Escriu els camps del formulari al feature amb id `fid`.
        Ha de fer startEditing + changeAttributeValue + commitChanges.
        Retorna True si correcte, False si error.
        """
        return True

    def _feature_display_name(self, feat):
        """Retorna un text identificador del feature per als missatges."""
        return str(feat.id())

    def _counter_text(self, n):
        return f"Punts afegits: {n}"

    def _info_color(self):
        return "#e3f2fd"

    def _info_border_color(self):
        return "#90caf9"

    def _accent_color(self):
        return "#1976d2"

    def _post_load_layer(self):
        """Hook cridat al final de _load_layer(), quan la capa ja existeix."""

    def _build_import_group(self):
        """
        Retorna un QGroupBox opcional amb una eina d'importació massiva
        (p.ex. des de CSV), o None si la subclasse no ho implementa.
        Només algunes subclasses (p.ex. InventariDialog) el sobreescriuen.
        """
        return None

    # ------------------------------------------------------------------
    # Construcció de la interfície
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(10)

        # Títol
        lbl_title = QLabel(self._heading_text())
        font = QFont()
        font.setBold(True)
        font.setPointSize(11)
        lbl_title.setFont(font)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        main.addWidget(sep)

        # Mètode d'entrada
        grp_met = QGroupBox("Mètode d'entrada")
        lay_met = QVBoxLayout(grp_met)
        self._btn_mapa = QRadioButton("Marcar punts directament al mapa")
        self._btn_coord = QRadioButton("Introduir coordenades UTM manualment")
        self._btn_mapa.setChecked(True)
        self._grp_btns = QButtonGroup(self)
        self._grp_btns.addButton(self._btn_mapa, 0)
        self._grp_btns.addButton(self._btn_coord, 1)
        self._grp_btns.buttonClicked.connect(self._on_metode_changed)
        lay_met.addWidget(self._btn_mapa)
        lay_met.addWidget(self._btn_coord)
        main.addWidget(grp_met)

        # Coordenades manuals
        self._grp_coord = QGroupBox("Coordenades UTM (ETRS89 / UTM zona 31N)")
        lay_c = QGridLayout(self._grp_coord)
        lay_c.addWidget(QLabel("X (m):"), 0, 0)
        self._spin_x = QDoubleSpinBox()
        self._spin_x.setDecimals(1)
        self._spin_x.setRange(200000, 1000000)
        self._spin_x.setValue(430000)
        self._spin_x.setFixedWidth(160)
        self._spin_x.setToolTip(
            "Coordenada X en metres, sistema ETRS89 / UTM zona 31N (EPSG:25831).\n"
            "Rang habitual a Catalunya: 250 000 – 550 000 m."
        )
        lay_c.addWidget(self._spin_x, 0, 1, Qt.AlignmentFlag.AlignLeft)
        lay_c.addWidget(QLabel("Y (m):"), 1, 0)
        self._spin_y = QDoubleSpinBox()
        self._spin_y.setDecimals(1)
        self._spin_y.setRange(3000000, 5000000)
        self._spin_y.setValue(4620000)
        self._spin_y.setFixedWidth(160)
        self._spin_y.setToolTip(
            "Coordenada Y en metres, sistema ETRS89 / UTM zona 31N (EPSG:25831).\n"
            "Rang habitual a Catalunya: 4 480 000 – 4 750 000 m."
        )
        lay_c.addWidget(self._spin_y, 1, 1, Qt.AlignmentFlag.AlignLeft)

        btn_afegir_coord = QPushButton("Afegir punt")
        btn_afegir_coord.setStyleSheet(
            f"background:{self._accent_color()}; color:white;"
            " font-weight:bold; padding:5px 16px;"
        )
        btn_afegir_coord.clicked.connect(self._on_afegir_coord)
        lay_c.addWidget(btn_afegir_coord, 2, 0, 1, 2)
        self._grp_coord.setVisible(False)
        main.addWidget(self._grp_coord)

        # Atributs específics (implementat per cada subclasse)
        grp_attr = self._build_attr_group()
        main.addWidget(grp_attr)

        # Importació massiva (opcional; només la implementen algunes subclasses)
        grp_import = self._build_import_group()
        if grp_import is not None:
            main.addWidget(grp_import)

        # Info mapa
        self._lbl_info = QLabel(
            "Fes clic al mapa per situar el punt.\n"
            "Omple els camps i prem el botó Desar per confirmar-lo."
        )
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet(
            f"padding:8px; background:{self._info_color()};"
            f" border:1px solid {self._info_border_color()}; border-radius:4px;"
        )
        main.addWidget(self._lbl_info)

        self._lbl_pendent = QLabel("")
        self._lbl_pendent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_pendent.setStyleSheet(
            f"color:{self._accent_color()}; font-style:italic;"
        )
        main.addWidget(self._lbl_pendent)

        # Botó Desar
        self._btn_desar = QPushButton("Desar punt")
        self._btn_desar.setStyleSheet(
            f"background:{self._accent_color()}; color:white;"
            " font-weight:bold; padding:6px 16px;"
        )
        self._btn_desar.setEnabled(False)
        self._btn_desar.clicked.connect(self._on_desar)
        main.addWidget(self._btn_desar)

        # Comptador
        self._lbl_comptador = QLabel(self._counter_text(0))
        self._lbl_comptador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_comptador.setStyleSheet(
            f"font-weight:bold; color:{self._accent_color()};"
        )
        main.addWidget(self._lbl_comptador)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        main.addWidget(sep2)

        # Modificar
        self._btn_modificar = QPushButton("✏  Modificar element seleccionat")
        self._btn_modificar.setStyleSheet(
            "background:#e65100; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_modificar.clicked.connect(self._on_modificar)
        main.addWidget(self._btn_modificar)

        self._btn_desar_mod = QPushButton("✔  Desar modificació")
        self._btn_desar_mod.setStyleSheet(
            "background:#bf360c; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_desar_mod.setVisible(False)
        self._btn_desar_mod.clicked.connect(self._on_desar_mod)
        main.addWidget(self._btn_desar_mod)

        self._btn_cancel_mod = QPushButton("Cancel·lar modificació")
        self._btn_cancel_mod.setStyleSheet("padding:5px 16px;")
        self._btn_cancel_mod.setVisible(False)
        self._btn_cancel_mod.clicked.connect(self._on_cancel_mod)
        main.addWidget(self._btn_cancel_mod)

        # Eliminar
        self._btn_eliminar = QPushButton("🗑  Eliminar element seleccionat")
        self._btn_eliminar.setStyleSheet(
            "background:#b71c1c; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_eliminar.clicked.connect(self._on_eliminar)
        main.addWidget(self._btn_eliminar)

        self._btn_confirmar_elim = QPushButton(
            "✔  Confirmar eliminació del punt seleccionat"
        )
        self._btn_confirmar_elim.setStyleSheet(
            "background:#7f0000; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_confirmar_elim.setVisible(False)
        self._btn_confirmar_elim.clicked.connect(self._on_confirmar_elim)
        main.addWidget(self._btn_confirmar_elim)

        self._btn_cancel_elim = QPushButton("Cancel·lar eliminació")
        self._btn_cancel_elim.setStyleSheet("padding:5px 16px;")
        self._btn_cancel_elim.setVisible(False)
        self._btn_cancel_elim.clicked.connect(self._on_cancel_elim)
        main.addWidget(self._btn_cancel_elim)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setFrameShadow(QFrame.Shadow.Sunken)
        main.addWidget(sep3)

        btn_tancar = QPushButton("Tancar")
        btn_tancar.clicked.connect(self.close)
        btn_tancar.setStyleSheet("padding:5px 16px;")
        main.addWidget(btn_tancar, alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------------
    # Capa
    # ------------------------------------------------------------------

    def _load_layer(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == self.LAYER_NAME and QgsWkbTypes.geometryType(lyr.wkbType()) == self.GEOM_TYPE):
                self._layer = lyr
                break

        if not self._layer:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(self, self.LAYER_NAME)
            self._cancelled = True
            return

        self._count = self._layer.featureCount()
        self._lbl_comptador.setText(self._counter_text(self._count))

        cfg = self._layer.editFormConfig()
        self._form_backup = cfg.suppress()
        cfg.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
        self._layer.setEditFormConfig(cfg)

        self._post_load_layer()

    # ------------------------------------------------------------------
    # Mode mapa
    # ------------------------------------------------------------------

    def _activate_map_tool(self):
        if not self._layer:
            return
        self.iface.setActiveLayer(self._layer)
        self._layer.startEditing()
        try:
            self._layer.featureAdded.disconnect(self._on_feature_added)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        self._layer.featureAdded.connect(
            self._on_feature_added, Qt.ConnectionType.UniqueConnection)
        self._tool_backup = self.iface.mapCanvas().mapTool()
        self.iface.actionAddFeature().trigger()

    def _deactivate_map_tool(self):
        try:
            if self._layer:
                self._layer.featureAdded.disconnect(self._on_feature_added)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        if self._tool_backup:
            self.iface.mapCanvas().setMapTool(self._tool_backup)
            self._tool_backup = None

    def _on_feature_added(self, fid):
        lyr = self._layer
        feat = next(lyr.getFeatures(QgsFeatureRequest().setFilterFid(fid)), None)
        if feat is None:
            return
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return

        # Eliminar punt pendent anterior sense desar
        if self._pending_fid is not None:
            lyr.deleteFeature(self._pending_fid)

        pt = geom.asPoint()
        self._pending_fid = fid
        self._pending_pt = (pt.x(), pt.y())
        self._btn_desar.setEnabled(True)
        self._lbl_pendent.setText(
            f"Punt situat a ({pt.x():.1f}, {pt.y():.1f}) — omple els camps i desa"
        )
        self.iface.mapCanvas().refresh()

    # ------------------------------------------------------------------
    # Desar (mode mapa)
    # ------------------------------------------------------------------

    def _on_desar(self):
        lyr = self._layer
        if self._grp_btns.checkedId() == 0:
            # Mode mapa
            if self._pending_fid is None or self._pending_pt is None:
                QMessageBox.warning(
                    self, "Sense punt",
                    "Fes primer clic al mapa per situar el punt."
                )
                return
            x, y = self._pending_pt
            self._apply_attrs(self._pending_fid, x, y)

            # Desconnectar ABANS de commitChanges
            try:
                lyr.featureAdded.disconnect(self._on_feature_added)
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass
            if not lyr.commitChanges():
                errs = "; ".join(lyr.commitErrors())
                lyr.rollBack()
                QMessageBox.critical(self, "Error", f"No s'ha pogut desar:\n{errs}")
                return
        else:
            # Mode coordenades
            x, y = self._spin_x.value(), self._spin_y.value()
            lyr.startEditing()
            feat = QgsFeature(lyr.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            self._apply_attrs_new(feat, x, y)
            lyr.addFeature(feat)
            if not lyr.commitChanges():
                errs = "; ".join(lyr.commitErrors())
                lyr.rollBack()
                QMessageBox.critical(self, "Error", f"No s'ha pogut desar:\n{errs}")
                return

        self._count += 1
        self._lbl_comptador.setText(self._counter_text(self._count))
        self._reset_attr_fields()
        self._pending_fid = None
        self._pending_pt = None
        self._btn_desar.setEnabled(False)
        self._lbl_pendent.setText("")
        self.iface.mapCanvas().refresh()

        # Reprendre mode mapa
        if self._grp_btns.checkedId() == 0:
            lyr.startEditing()
            lyr.featureAdded.connect(self._on_feature_added, Qt.ConnectionType.UniqueConnection)
            self.iface.actionAddFeature().trigger()

    # ------------------------------------------------------------------
    # Mode coordenades
    # ------------------------------------------------------------------

    def _on_afegir_coord(self):
        if not self._layer:
            QMessageBox.warning(
                self, "Capa no disponible",
                f"No s'ha trobat la capa «{self.LAYER_NAME}»."
            )
            return
        x, y = self._spin_x.value(), self._spin_y.value()
        lyr = self._layer
        lyr.startEditing()
        feat = QgsFeature(lyr.fields())
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        self._apply_attrs_new(feat, x, y)
        lyr.addFeature(feat)
        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error", f"No s'ha pogut afegir el punt:\n{errs}")
            return
        self._count += 1
        self._lbl_comptador.setText(self._counter_text(self._count))
        self._reset_attr_fields()
        self.iface.mapCanvas().refresh()

    # ------------------------------------------------------------------
    # Modificar
    # ------------------------------------------------------------------

    def _on_modificar(self):
        if not self._layer:
            return
        self._deactivate_map_tool()
        self.iface.setActiveLayer(self._layer)
        self.iface.actionSelect().trigger()
        self._mod_fid = None
        self._btn_modificar.setVisible(False)
        self._btn_desar_mod.setVisible(True)
        self._btn_cancel_mod.setVisible(True)
        self._btn_desar.setEnabled(False)
        self._lbl_pendent.setText(
            "Selecciona l'element al mapa i prem «Desar modificació»."
        )
        self._layer.selectionChanged.connect(self._on_selection_for_mod)
        self.adjustSize()

    def _on_selection_for_mod(self, selected, deselected, clear):
        feats = self._layer.selectedFeatures()
        if len(feats) != 1:
            return
        feat = feats[0]
        self._mod_fid = feat.id()
        self._load_attrs_for_mod(feat)
        name = self._feature_display_name(feat)
        self._lbl_pendent.setText(
            f"Editant «{name}» — modifica els camps i prem «Desar modificació»."
        )

    def _on_desar_mod(self):
        if self._mod_fid is None:
            QMessageBox.information(
                self, "Cap element seleccionat",
                "Selecciona primer un element al mapa."
            )
            return
        if not self._save_attrs_for_mod(self._mod_fid):
            return
        if self._layer:
            self._layer.removeSelection()
        self.iface.mapCanvas().refresh()
        self._on_cancel_mod()

    def _on_cancel_mod(self):
        try:
            self._layer.selectionChanged.disconnect(self._on_selection_for_mod)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        self._mod_fid = None
        if self._layer:
            self._layer.removeSelection()
        self._btn_modificar.setVisible(True)
        self._btn_desar_mod.setVisible(False)
        self._btn_cancel_mod.setVisible(False)
        self._lbl_pendent.setText("")
        self._reset_attr_fields()
        self._activate_map_tool()
        self.adjustSize()

    # ------------------------------------------------------------------
    # Eliminar
    # ------------------------------------------------------------------

    def _on_eliminar(self):
        if not self._layer:
            return
        self._deactivate_map_tool()
        self.iface.setActiveLayer(self._layer)
        self.iface.actionSelect().trigger()
        self._btn_eliminar.setVisible(False)
        self._btn_confirmar_elim.setVisible(True)
        self._btn_cancel_elim.setVisible(True)
        self._btn_desar.setEnabled(False)
        self._lbl_pendent.setText(
            "Selecciona l'element al mapa i prem «Confirmar eliminació»."
        )
        self.adjustSize()

    def _on_confirmar_elim(self):
        lyr = self._layer
        selected = lyr.selectedFeatures()
        if not selected:
            QMessageBox.information(
                self, "Cap element seleccionat",
                "Selecciona primer un element al mapa."
            )
            return
        if len(selected) > 1:
            QMessageBox.warning(
                self, "Selecció múltiple",
                "Selecciona només un element a la vegada."
            )
            return
        feat = selected[0]
        name = self._feature_display_name(feat)
        reply = QMessageBox.question(
            self, "Confirmar eliminació",
            f"Vols eliminar l'element «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        lyr.startEditing()
        lyr.deleteFeature(feat.id())
        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error", f"No s'ha pogut eliminar:\n{errs}")
            return
        lyr.removeSelection()
        self._count = self._layer.featureCount()
        self._lbl_comptador.setText(self._counter_text(self._count))
        self.iface.mapCanvas().refresh()
        self._on_cancel_elim()

    def _on_cancel_elim(self):
        if self._layer:
            self._layer.removeSelection()
        self._btn_eliminar.setVisible(True)
        self._btn_confirmar_elim.setVisible(False)
        self._btn_cancel_elim.setVisible(False)
        self._pending_fid = None
        self._pending_pt = None
        self._btn_desar.setEnabled(False)
        self._lbl_pendent.setText("")
        self._activate_map_tool()
        self.adjustSize()

    # ------------------------------------------------------------------
    # Events de mètode i cicle de vida
    # ------------------------------------------------------------------

    def _on_metode_changed(self, btn):
        es_coord = (self._grp_btns.checkedId() == 1)
        self._grp_coord.setVisible(es_coord)
        self._lbl_info.setVisible(not es_coord)
        self._btn_desar.setEnabled(es_coord)
        if es_coord:
            self._deactivate_map_tool()
            if self._pending_fid is not None and self._layer and self._layer.isEditable():
                self._layer.deleteFeature(self._pending_fid)
                self.iface.mapCanvas().refresh()
            self._pending_fid = None
            self._pending_pt = None
            self._lbl_pendent.setText("")
        else:
            self._pending_fid = None
            self._pending_pt = None
            self._btn_desar.setEnabled(False)
            self._activate_map_tool()
        self.adjustSize()

    def showEvent(self, event):
        super().showEvent(event)
        if self._btn_mapa.isChecked():
            self._activate_map_tool()

    def closeEvent(self, event):
        if self._layer:
            self._layer.removeSelection()
        self._deactivate_map_tool()
        if self._layer and self._form_backup is not None:
            cfg = self._layer.editFormConfig()
            cfg.setSuppress(self._form_backup)
            self._layer.setEditFormConfig(cfg)
        if self._layer and self._layer.isEditable():
            self._layer.rollBack()
        self.iface.actionSelect().trigger()
        super().closeEvent(event)

# -*- coding: utf-8 -*-
"""
IOF Assistent — Digitalitzar canvis d'ús (rompudes i transformacions a pastures).

Quan l'usuari digitalitza cada polígon, el diàleg demana el tipus
(RM=Rompuda, TP=Transformació a pastures) i assigna automàticament
el codi (RM01, RM02, TP01...) i calcula la superfície.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox,
    QGroupBox, QMessageBox, QFrame,
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes,
    QgsEditFormConfig, QgsFeatureRequest,
)

LAYER_NAME = "IOF_Canvis_Us"
TIPUS_OPCIONS = [
    ("RM", "RM — Rompuda"),
    ("TP", "TP — Transformació a pastures"),
]


def _next_codi(layer, tipus):
    """Retorna el proper codi correlatiu per al tipus donat (RM o TP)."""
    idx = layer.fields().indexOf("codi_canvi")
    used = set()
    for feat in layer.getFeatures():
        val = feat.attribute(idx)
        if val and str(val).startswith(tipus):
            used.add(str(val))
    n = 1
    while True:
        codi = f"{tipus}{n:02d}"
        if codi not in used:
            return codi
        n += 1


class CanvisDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self._layer = None
        self._tool_backup = None
        self._form_backup = None
        self._renderer_backup = None
        self._count = 0
        self._pending_fid = None
        # True si _load_layer() no ha trobat la capa: qui crea el
        # diàleg (iof_exporter.py) ha de comprovar-ho i no cridar
        # .show() en aquest cas.
        self._cancelled = False
        self.setWindowTitle("IOF Assistent — Digitalitzar canvis d'ús")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(400)
        self._build_ui()
        self._load_layer()
        if self._layer is not None:
            from .iof_utils import dimmar_altres_capes_iof
            dimmar_altres_capes_iof(self._layer)
            self._apply_digitizing_style()

    def _apply_digitizing_style(self):
        """Farciment transparent + contorn del color propi de la capa
        (paleta compartida a iof_utils._COLORS_DIMMAT_IOF) durant la
        digitalització, igual que Camins/Unitats/Infraestructures PI."""
        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
        from .iof_utils import _COLORS_DIMMAT_IOF
        r, g, b = _COLORS_DIMMAT_IOF.get(self._layer.name(), (0, 188, 212))
        self._renderer_backup = self._layer.renderer().clone()
        sym = QgsFillSymbol.createSimple({
            'color': '0,0,0,0',
            'outline_color': f'{r},{g},{b},255',
            'outline_width': '0.6',
            'outline_style': 'solid',
        })
        self._layer.setRenderer(QgsSingleSymbolRenderer(sym))
        self._layer.triggerRepaint()

    def _restore_digitizing_style(self):
        if self._layer and self._renderer_backup is not None:
            self._layer.setRenderer(self._renderer_backup)
            self._renderer_backup = None
            self._layer.triggerRepaint()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(10)

        lbl_title = QLabel("Digitalitzar canvis d'ús")
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

        # Atributs
        grp_attr = QGroupBox("Atributs del canvi d'ús")
        lay_a = QGridLayout(grp_attr)

        lay_a.addWidget(QLabel("Tipus:"), 0, 0)
        self._combo_tipus = QComboBox()
        for val, desc in TIPUS_OPCIONS:
            self._combo_tipus.addItem(desc, val)
        self._combo_tipus.setMinimumWidth(240)
        self._combo_tipus.currentIndexChanged.connect(self._update_codi_preview)
        lay_a.addWidget(self._combo_tipus, 0, 1)

        lay_a.addWidget(QLabel("Codi generat:"), 1, 0)
        self._lbl_codi = QLabel("—")
        self._lbl_codi.setStyleSheet("font-weight:bold; color:#4a148c;")
        lay_a.addWidget(self._lbl_codi, 1, 1)

        main.addWidget(grp_attr)

        # Info
        self._lbl_info = QLabel(
            "Dibuixa cada canvi d'ús com a polígon al mapa.\n"
            "En finalitzar cada polígon (clic dret), prem «Desar canvi d'ús»."
        )
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet(
            "padding:8px; background:#f3e5f5; border:1px solid #ce93d8;"
            " border-radius:4px;"
        )
        main.addWidget(self._lbl_info)

        self._lbl_pendent = QLabel("")
        self._lbl_pendent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_pendent.setStyleSheet("color:#4a148c; font-style:italic;")
        main.addWidget(self._lbl_pendent)

        self._btn_desar = QPushButton("Desar canvi d'ús")
        self._btn_desar.setStyleSheet(
            "background:#4a148c; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_desar.setEnabled(False)
        self._btn_desar.clicked.connect(self._on_desar)
        main.addWidget(self._btn_desar)

        self._lbl_comptador = QLabel("Canvis d'ús afegits: 0")
        self._lbl_comptador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_comptador.setStyleSheet("font-weight:bold; color:#4a148c;")
        main.addWidget(self._lbl_comptador)

        sep_elim = QFrame()
        sep_elim.setFrameShape(QFrame.Shape.HLine)
        sep_elim.setFrameShadow(QFrame.Shadow.Sunken)
        main.addWidget(sep_elim)

        self._btn_eliminar_existent = QPushButton("🗑  Eliminar canvi d'ús seleccionat")
        self._btn_eliminar_existent.setStyleSheet(
            "background:#b71c1c; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_eliminar_existent.clicked.connect(self._on_eliminar)
        main.addWidget(self._btn_eliminar_existent)

        self._btn_confirmar_elim = QPushButton("✔  Confirmar eliminació del canvi d'ús seleccionat")
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

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        main.addWidget(sep2)

        btn_tancar = QPushButton("Tancar")
        btn_tancar.clicked.connect(self.close)
        btn_tancar.setStyleSheet("padding:5px 16px;")
        main.addWidget(btn_tancar, alignment=Qt.AlignmentFlag.AlignRight)

    # ------------------------------------------------------------------
    # Capa
    # ------------------------------------------------------------------

    def _load_layer(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == LAYER_NAME and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                self._layer = lyr
                break

        if not self._layer:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(self, LAYER_NAME)
            self._cancelled = True
            return

        self._count = self._layer.featureCount()
        self._lbl_comptador.setText(f"Canvis d'ús afegits: {self._count}")

        cfg = self._layer.editFormConfig()
        self._form_backup = cfg.suppress()
        cfg.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
        self._layer.setEditFormConfig(cfg)

        self._update_codi_preview()

    def _update_codi_preview(self):
        if not self._layer:
            return
        tipus = self._combo_tipus.currentData() or "RM"
        codi = _next_codi(self._layer, tipus)
        self._lbl_codi.setText(f"{codi}  (provisional)")

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

        # Snapping
        from .iof_utils import activar_snapping_totes_capes
        activar_snapping_totes_capes(self.iface)

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
        from .iof_utils import restaurar_snapping
        restaurar_snapping(self.iface)

    def _on_feature_added(self, fid):
        lyr = self._layer
        feat = next(lyr.getFeatures(QgsFeatureRequest().setFilterFid(fid)), None)
        if feat is None:
            return
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return

        # Eliminar polígon pendent anterior
        if self._pending_fid is not None:
            lyr.deleteFeature(self._pending_fid)

        # Assignar temporalment el tipus seleccionat perquè el polígon
        # coincideixi amb una categoria de l'estil de gestió i es vegi
        # de seguida — si no, amb "tipus_canvi" buit no coincideix amb
        # cap categoria (RM/TP) i queda invisible fins que es desa de
        # veritat.
        if "tipus_canvi" in lyr.fields().names():
            tipus_previ = self._combo_tipus.currentData() or "RM"
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("tipus_canvi"), tipus_previ)

        area_ha = geom.area() / 10000
        self._pending_fid = fid
        self._btn_desar.setEnabled(True)
        self._lbl_pendent.setText(
            f"Polígon dibuixat ({area_ha:.2f} ha) — prem «Desar canvi d'ús»"
        )
        self.iface.mapCanvas().refresh()

    # ------------------------------------------------------------------
    # Desar
    # ------------------------------------------------------------------

    def _on_desar(self):
        lyr = self._layer
        if self._pending_fid is None:
            QMessageBox.warning(self, "Sense polígon",
                                "Dibuixa primer un polígon al mapa.")
            return

        tipus = self._combo_tipus.currentData() or "RM"
        codi = _next_codi(lyr, tipus)

        feat = next(lyr.getFeatures(
            QgsFeatureRequest().setFilterFid(self._pending_fid)), None)
        area_ha = feat.geometry().area() / 10000 if feat and feat.geometry() else 0.0

        fields = lyr.fields().names()
        if "codi_canvi" in fields:
            lyr.changeAttributeValue(
                self._pending_fid,
                lyr.fields().indexOf("codi_canvi"), codi)
        if "tipus_canvi" in fields:
            lyr.changeAttributeValue(
                self._pending_fid,
                lyr.fields().indexOf("tipus_canvi"), tipus)
        if "superficie" in fields:
            lyr.changeAttributeValue(
                self._pending_fid,
                lyr.fields().indexOf("superficie"), round(area_ha, 2))

        try:
            lyr.featureAdded.disconnect(self._on_feature_added)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass

        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error", f"No s'ha pogut desar:\n{errs}")
            return

        # Reset
        self._count += 1
        self._lbl_comptador.setText(f"Canvis d'ús afegits: {self._count}")
        self._pending_fid = None
        self._btn_desar.setEnabled(False)
        self._lbl_pendent.setText("")
        self._update_codi_preview()
        self.iface.mapCanvas().refresh()

        # Reprendre digitalització
        lyr.startEditing()
        lyr.featureAdded.connect(self._on_feature_added, Qt.ConnectionType.UniqueConnection)
        self.iface.actionAddFeature().trigger()

    # ------------------------------------------------------------------
    # Eliminar
    # ------------------------------------------------------------------

    def _on_eliminar(self):
        if not self._layer:
            return
        self._deactivate_map_tool()
        self.iface.setActiveLayer(self._layer)
        self.iface.actionSelect().trigger()
        self._btn_eliminar_existent.setVisible(False)
        self._btn_confirmar_elim.setVisible(True)
        self._btn_cancel_elim.setVisible(True)
        self._lbl_pendent.setText(
            "Selecciona el canvi d'ús al mapa i prem «Confirmar eliminació»."
        )

    def _on_confirmar_elim(self):
        lyr = self._layer
        selected = lyr.selectedFeatures()
        if not selected:
            QMessageBox.information(
                self, "Cap element seleccionat",
                "Selecciona primer un canvi d'ús al mapa."
            )
            return
        if len(selected) > 1:
            QMessageBox.warning(
                self, "Selecció múltiple",
                "Selecciona només un element a la vegada."
            )
            return
        feat = selected[0]
        codi = feat["codi_canvi"] if "codi_canvi" in lyr.fields().names() else "?"
        reply = QMessageBox.question(
            self, "Confirmar eliminació",
            f"Vols eliminar el canvi d'ús «{codi}»?\n\n"
            "La resta del mateix tipus (Rompuda/Transformació a pastures) "
            "es renumeraran automàticament.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if not lyr.isEditable():
            lyr.startEditing()
        lyr.deleteFeature(feat.id())
        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error", f"No s'ha pogut eliminar:\n{errs}")
            return
        lyr.removeSelection()
        self._renumerar()
        self._count = lyr.featureCount()
        self._lbl_comptador.setText(f"Canvis d'ús afegits: {self._count}")
        self._on_cancel_elim()

    def _renumerar(self):
        """Renumera tots els canvis d'ús agrupant-los per tipus (RM/TP)
        — numeració independent des de l'1 per cada tipus, igual que ja
        fa _next_codi() en crear-ne un de nou. A diferència de Camins/
        Infraestructures/Aigua, aquí NO hi ha estat E/P al codi — només
        tipus + número. Cridar sempre després d'eliminar-ne un."""
        lyr = self._layer
        if not lyr:
            return
        idx = lyr.fields().indexOf("codi_canvi")
        if idx < 0:
            return

        grups = {}
        for feat in lyr.getFeatures():
            codi = feat["codi_canvi"]
            if not codi or not isinstance(codi, str):
                continue
            for tipus in ("RM", "TP"):
                if codi.startswith(tipus):
                    try:
                        num = int(codi[len(tipus):len(tipus) + 2])
                    except (ValueError, IndexError):
                        num = 9999
                    grups.setdefault(tipus, []).append((num, feat))
                    break

        lyr.startEditing()
        for tipus, llista in grups.items():
            llista.sort(key=lambda parell: parell[0])
            for i, (_num_antic, feat_ordenat) in enumerate(llista, start=1):
                lyr.changeAttributeValue(feat_ordenat.id(), idx, f"{tipus}{i:02d}")

        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error renumeració", f"Error:\n{errs}")

    def _on_cancel_elim(self):
        lyr = self._layer
        if lyr:
            lyr.removeSelection()
        self._btn_eliminar_existent.setVisible(True)
        self._btn_confirmar_elim.setVisible(False)
        self._btn_cancel_elim.setVisible(False)
        self._lbl_pendent.setText("")
        self._activate_map_tool()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._activate_map_tool()

    def closeEvent(self, event):
        from .iof_utils import restaurar_opacitat_capes_iof
        restaurar_opacitat_capes_iof()
        self._restore_digitizing_style()
        self._deactivate_map_tool()
        if self._layer and self._form_backup is not None:
            cfg = self._layer.editFormConfig()
            cfg.setSuppress(self._form_backup)
            self._layer.setEditFormConfig(cfg)
        if self._layer and self._layer.isEditable():
            self._layer.rollBack()
        self.iface.actionSelect().trigger()
        super().closeEvent(event)

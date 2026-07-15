# -*- coding: utf-8 -*-
"""
IOF Assistent — Digitalitzar infraestructures de prevenció d'incendis.

Quan l'usuari digitalitza cada polígon, el diàleg demana l'estat
(Existent/Projectat) i assigna automàticament el codi (LD01E, LD01P...).
Tipus sempre LD (única categoria possible).
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

LAYER_NAME = "IOF_Infraestructures_PI"
ESTAT_OPCIONS = [
    ("E", "E — Existent"),
    ("P", "P — Projectat"),
]


def _next_codi(layer, estat):
    """Retorna el proper codi LD correlatiu per a l'estat donat."""
    idx = layer.fields().indexOf("codi_infra")
    used = set()
    for feat in layer.getFeatures():
        val = feat.attribute(idx)
        if val:
            used.add(str(val))
    n = 1
    while True:
        codi = f"LD{n:02d}{estat}"
        if codi not in used:
            return codi
        n += 1


class InfraDialog(QDialog):

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
        self.setWindowTitle("IOF Assistent — Digitalitzar infraestructures PI")
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
        digitalització, igual que Camins/Unitats."""
        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
        from .iof_utils import _COLORS_DIMMAT_IOF
        r, g, b = _COLORS_DIMMAT_IOF.get(self._layer.name(), (255, 140, 0))
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

        lbl_title = QLabel("Digitalitzar infraestructures de prevenció d'incendis")
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
        grp_attr = QGroupBox("Atributs de la infraestructura")
        lay_a = QGridLayout(grp_attr)

        lay_a.addWidget(QLabel("Tipus:"), 0, 0)
        lbl_tipus = QLabel("LD — Obertura de línia de defensa")
        lbl_tipus.setStyleSheet("color:#555;")
        lay_a.addWidget(lbl_tipus, 0, 1)

        lay_a.addWidget(QLabel("Codi generat:"), 1, 0)
        self._lbl_codi = QLabel("—")
        self._lbl_codi.setStyleSheet("font-weight:bold; color:#880e4f;")
        lay_a.addWidget(self._lbl_codi, 1, 1)

        lay_a.addWidget(QLabel("Estat:"), 2, 0)
        self._combo_estat = QComboBox()
        for val, desc in ESTAT_OPCIONS:
            self._combo_estat.addItem(desc, val)
        self._combo_estat.setMinimumWidth(200)
        self._combo_estat.currentIndexChanged.connect(self._update_codi_preview)
        lay_a.addWidget(self._combo_estat, 2, 1)

        main.addWidget(grp_attr)

        # Info
        self._lbl_info = QLabel(
            "Dibuixa cada infraestructura com a polígon al mapa.\n"
            "En finalitzar cada polígon (clic dret), prem «Desar infraestructura»."
        )
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet(
            "padding:8px; background:#fce4ec; border:1px solid #f48fb1;"
            " border-radius:4px;"
        )
        main.addWidget(self._lbl_info)

        self._lbl_pendent = QLabel("")
        self._lbl_pendent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_pendent.setStyleSheet("color:#880e4f; font-style:italic;")
        main.addWidget(self._lbl_pendent)

        self._btn_desar = QPushButton("Desar infraestructura")
        self._btn_desar.setStyleSheet(
            "background:#880e4f; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_desar.setEnabled(False)
        self._btn_desar.clicked.connect(self._on_desar)
        main.addWidget(self._btn_desar)

        self._lbl_comptador = QLabel("Infraestructures afegides: 0")
        self._lbl_comptador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_comptador.setStyleSheet("font-weight:bold; color:#880e4f;")
        main.addWidget(self._lbl_comptador)

        sep_elim = QFrame()
        sep_elim.setFrameShape(QFrame.Shape.HLine)
        sep_elim.setFrameShadow(QFrame.Shadow.Sunken)
        main.addWidget(sep_elim)

        self._btn_eliminar_existent = QPushButton("🗑  Eliminar infraestructura seleccionada")
        self._btn_eliminar_existent.setStyleSheet(
            "background:#b71c1c; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_eliminar_existent.clicked.connect(self._on_eliminar)
        main.addWidget(self._btn_eliminar_existent)

        self._btn_confirmar_elim = QPushButton("✔  Confirmar eliminació de la infraestructura seleccionada")
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
        self._lbl_comptador.setText(f"Infraestructures afegides: {self._count}")

        cfg = self._layer.editFormConfig()
        self._form_backup = cfg.suppress()
        cfg.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
        self._layer.setEditFormConfig(cfg)

        self._update_codi_preview()

    def _update_codi_preview(self):
        if not self._layer:
            return
        estat = self._combo_estat.currentData() or "E"
        codi = _next_codi(self._layer, estat)
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

        # Configurar snapping: vèrtexs i segments de totes les capes
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
        # Desactivar snapping
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

        # Assignar temporalment l'estat seleccionat perquè el polígon
        # coincideixi amb una categoria de l'estil de gestió i es vegi
        # de seguida — si no, amb "estat" buit no coincideix amb cap
        # categoria (E/P) i queda invisible fins que es desa de veritat.
        if "estat" in lyr.fields().names():
            estat_previ = self._combo_estat.currentData() or "E"
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("estat"), estat_previ)

        area_ha = geom.area() / 10000
        self._pending_fid = fid
        self._btn_desar.setEnabled(True)
        self._lbl_pendent.setText(
            f"Polígon dibuixat ({area_ha:.2f} ha) — prem «Desar infraestructura»"
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

        estat = self._combo_estat.currentData() or "E"
        codi = _next_codi(lyr, estat)

        feat = next(lyr.getFeatures(
            QgsFeatureRequest().setFilterFid(self._pending_fid)), None)
        area_ha = feat.geometry().area() / 10000 if feat and feat.geometry() else 0.0

        fields = lyr.fields().names()
        if "codi_infra" in fields:
            lyr.changeAttributeValue(
                self._pending_fid,
                lyr.fields().indexOf("codi_infra"), codi)
        if "tipus_infra" in fields:
            lyr.changeAttributeValue(
                self._pending_fid,
                lyr.fields().indexOf("tipus_infra"), "LD")
        if "estat" in fields:
            lyr.changeAttributeValue(
                self._pending_fid,
                lyr.fields().indexOf("estat"), estat)
        if "superficie" in fields:
            lyr.changeAttributeValue(
                self._pending_fid,
                lyr.fields().indexOf("superficie"), round(area_ha, 2))
        if "sup_infra" in fields:
            lyr.changeAttributeValue(
                self._pending_fid,
                lyr.fields().indexOf("sup_infra"), round(area_ha, 2))

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
        self._lbl_comptador.setText(f"Infraestructures afegides: {self._count}")
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
            "Selecciona la infraestructura al mapa i prem «Confirmar eliminació»."
        )

    def _on_confirmar_elim(self):
        lyr = self._layer
        selected = lyr.selectedFeatures()
        if not selected:
            QMessageBox.information(
                self, "Cap element seleccionat",
                "Selecciona primer una infraestructura al mapa."
            )
            return
        if len(selected) > 1:
            QMessageBox.warning(
                self, "Selecció múltiple",
                "Selecciona només un element a la vegada."
            )
            return
        feat = selected[0]
        codi = feat["codi_infra"] if "codi_infra" in lyr.fields().names() else "?"
        reply = QMessageBox.question(
            self, "Confirmar eliminació",
            f"Vols eliminar la infraestructura «{codi}»?\n\n"
            "La resta del mateix estat (Existent/Projectat) es "
            "renumeraran automàticament.",
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
        self._lbl_comptador.setText(f"Infraestructures afegides: {self._count}")
        self._on_cancel_elim()

    def _renumerar(self):
        """Renumera totes les infraestructures agrupant-les per estat
        (Existent/Projectat) — numeració independent des de l'1 per
        cada estat, igual que ja fa _next_codi() en crear-ne una de
        nova. Cridar sempre després d'eliminar-ne una."""
        lyr = self._layer
        if not lyr:
            return
        idx = lyr.fields().indexOf("codi_infra")
        if idx < 0:
            return

        grups = {}
        for feat in lyr.getFeatures():
            codi = feat["codi_infra"]
            if not codi or not isinstance(codi, str) or not codi.startswith("LD"):
                continue
            estat = codi[-1] if codi[-1] in ("E", "P") else "E"
            try:
                num = int(codi[2:4])
            except (ValueError, IndexError):
                num = 9999
            grups.setdefault(estat, []).append((num, feat))

        lyr.startEditing()
        for estat, llista in grups.items():
            llista.sort(key=lambda parell: parell[0])
            for i, (_num_antic, feat_ordenat) in enumerate(llista, start=1):
                lyr.changeAttributeValue(feat_ordenat.id(), idx, f"LD{i:02d}{estat}")

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

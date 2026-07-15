# -*- coding: utf-8 -*-
"""
IOF Assistent — Digitalitzar camins (polilínies) a la capa IOF_Camins.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QFrame, QMessageBox
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes,
    QgsEditFormConfig
)

LAYER_CAMINS = "IOF_Camins"


def _get_camins_layer():
    for lyr in QgsProject.instance().mapLayers().values():
        if (isinstance(lyr, QgsVectorLayer) and lyr.name() == LAYER_CAMINS and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.LineGeometry):
            return lyr
    return None


class CaminsDialog(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self._layer = None
        # True si _check_layer() no ha trobat la capa: qui crea el
        # diàleg (iof_exporter.py) ha de comprovar-ho i no cridar
        # .show() en aquest cas.
        self._cancelled = False

        self.setWindowTitle("IOF Assistent — Digitalitzar camins")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(False)
        self.setMinimumWidth(360)
        self._build_ui()
        self._check_layer()
        if self._layer is not None:
            from .iof_utils import dimmar_altres_capes_iof
            dimmar_altres_capes_iof(self._layer)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl_title = QLabel("<b>Digitalitzar camins</b>")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet(
            "padding:8px; background:#fff3e0; border-radius:4px; font-weight:bold;"
        )
        layout.addWidget(lbl_title)

        self._lbl_info = QLabel(
            "Passos:\n\n"
            "1. Prem «Activar edició» per iniciar.\n"
            "2. Usa l'eina «Afegir objecte» de la barra d'eines de QGIS\n"
            "   per dibuixar cada camí com a polilínia.\n"
            "3. Clic dret o Supr per finalitzar cada línia.\n"
            "4. Prem «Desar i tancar» quan hagis acabat."
        )
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet("padding:6px; color:#333;")
        layout.addWidget(self._lbl_info)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        self._btn_start = QPushButton("▶  Activar edició")
        self._btn_start.setStyleSheet(
            "background:#e65100; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_start.clicked.connect(self._on_start)
        layout.addWidget(self._btn_start)

        self._btn_stop = QPushButton("✔  Desar i tancar edició")
        self._btn_stop.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.setEnabled(False)
        layout.addWidget(self._btn_stop)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep2)

        self._btn_eliminar = QPushButton("🗑  Eliminar camí seleccionat")
        self._btn_eliminar.setStyleSheet(
            "background:#b71c1c; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_eliminar.clicked.connect(self._on_eliminar)
        layout.addWidget(self._btn_eliminar)

        self._btn_confirmar_elim = QPushButton("✔  Confirmar eliminació del camí seleccionat")
        self._btn_confirmar_elim.setStyleSheet(
            "background:#7f0000; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_confirmar_elim.setVisible(False)
        self._btn_confirmar_elim.clicked.connect(self._on_confirmar_elim)
        layout.addWidget(self._btn_confirmar_elim)

        self._btn_cancel_elim = QPushButton("Cancel·lar eliminació")
        self._btn_cancel_elim.setStyleSheet("padding:5px 16px;")
        self._btn_cancel_elim.setVisible(False)
        self._btn_cancel_elim.clicked.connect(self._on_cancel_elim)
        layout.addWidget(self._btn_cancel_elim)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep3)

        self._lbl_status = QLabel()
        self._lbl_status.setWordWrap(True)
        self._lbl_status.hide()
        layout.addWidget(self._lbl_status)

        btn_close = QPushButton("Tancar")
        btn_close.clicked.connect(self._on_close)
        layout.addWidget(btn_close)

    def _check_layer(self):
        self._layer = _get_camins_layer()
        if self._layer is None:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(self, LAYER_CAMINS)
            self._cancelled = True

    def _on_start(self):
        lyr = self._layer

        # Suprimir formulari d'atributs
        cfg = lyr.editFormConfig()
        cfg.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
        lyr.setEditFormConfig(cfg)

        # Aplicar estil simple per a digitalitzar (farciment transparent +
        # contorn del color propi de la capa, paleta compartida a
        # iof_utils._COLORS_DIMMAT_IOF)
        from qgis.core import QgsSingleSymbolRenderer, QgsLineSymbol
        from .iof_utils import _COLORS_DIMMAT_IOF
        r, g, b = _COLORS_DIMMAT_IOF.get(lyr.name(), (255, 0, 0))
        sym = QgsLineSymbol.createSimple({'color': f'{r},{g},{b}', 'width': '0.6'})
        lyr.setRenderer(QgsSingleSymbolRenderer(sym))
        lyr.triggerRepaint()

        # Activar edició i establir capa activa
        if not lyr.isEditable():
            lyr.startEditing()
        self.iface.setActiveLayer(lyr)

        # Assegurar que la capa és visible al panell
        QgsProject.instance().layerTreeRoot().findLayer(lyr.id()).setItemVisibilityChecked(True)
        self.iface.mapCanvas().refresh()

        # Configurar snapping: vèrtexs i segments de totes les capes
        # (mode AllLayers + individual_layer_settings explícit per capa)
        from .iof_utils import activar_snapping_totes_capes
        activar_snapping_totes_capes(self.iface)

        # Activar l'eina d'afegir objecte
        self.iface.actionAddFeature().trigger()

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._show_status(
            "✔ Edició activada a «IOF_Camins».\n\n"
            "Usa l'eina «Afegir objecte lineal» (W) de la barra\n"
            "d'eines de QGIS per dibuixar els camins."
        )

    def _on_stop(self):
        lyr = self._layer
        if lyr and lyr.isEditable():
            lyr.commitChanges()

        # Restaurar formulari
        cfg = lyr.editFormConfig()
        cfg.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOff)
        lyr.setEditFormConfig(cfg)

        # Desactivar snapping
        from .iof_utils import restaurar_snapping
        restaurar_snapping(self.iface)

        self.iface.actionSelect().trigger()
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self.showNormal()

        n = lyr.featureCount() if lyr else 0
        self._show_status(
            f"✔ Desats {n} camí{'ns' if n != 1 else ''} a «IOF_Camins»."
        )

    def _on_eliminar(self):
        if not self._layer:
            return
        # Desar primer si hi ha edicions en curs
        if self._layer.isEditable():
            self._layer.commitChanges()
        self.iface.setActiveLayer(self._layer)
        self.iface.actionSelect().trigger()
        self._btn_eliminar.setVisible(False)
        self._btn_confirmar_elim.setVisible(True)
        self._btn_cancel_elim.setVisible(True)
        self._show_status(
            "Selecciona el camí al mapa i prem «Confirmar eliminació»."
        )
        self.adjustSize()

    def _on_confirmar_elim(self):
        lyr = self._layer
        selected = lyr.selectedFeatures()
        if not selected:
            QMessageBox.information(
                self, "Cap camí seleccionat",
                "Selecciona primer un camí al mapa."
            )
            return
        if len(selected) > 1:
            QMessageBox.warning(
                self, "Selecció múltiple",
                "Selecciona només un camí a la vegada."
            )
            return
        feat = selected[0]
        codi = feat["codi_cami"] if "codi_cami" in lyr.fields().names() else "?"
        reply = QMessageBox.question(
            self, "Confirmar eliminació",
            f"Vols eliminar el camí «{codi}»?\n\n"
            "La resta de camins del mateix tipus i estat es renumeraran "
            "automàticament.",
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
        self._renumerar_camins()
        self._on_cancel_elim()
        self._show_status(f"✔ Camí «{codi}» eliminat i la resta renumerats correctament.")

    def _renumerar_camins(self):
        """Renumera tots els camins agrupant-los per (tipus, estat) —
        PR/PM/SC/DB creuat amb Existent/Projectat, cadascun amb
        numeració independent des de l'1 — igual que ja fa
        iof_camins_wizard.py._genera_codi() en crear-ne un de nou.
        Cridar sempre després d'eliminar un camí."""
        lyr = self._layer
        if not lyr:
            return
        idx = lyr.fields().indexOf("codi_cami")
        if idx < 0:
            return

        grups = {}
        for feat in lyr.getFeatures():
            codi = feat["codi_cami"]
            if not codi or not isinstance(codi, str):
                continue
            for tipus in ("PR", "PM", "SC", "DB"):
                if codi.startswith(tipus):
                    estat = codi[-1] if codi[-1] in ("E", "P") else "E"
                    try:
                        num = int(codi[len(tipus):len(tipus) + 2])
                    except (ValueError, IndexError):
                        num = 9999
                    grups.setdefault((tipus, estat), []).append((num, feat))
                    break

        lyr.startEditing()
        for (tipus, estat), llista in grups.items():
            llista.sort(key=lambda parell: parell[0])
            for i, (_num_antic, feat_ordenat) in enumerate(llista, start=1):
                nou_codi = f"{tipus}{i:02d}{estat}"
                lyr.changeAttributeValue(feat_ordenat.id(), idx, nou_codi)

        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error renumeració", f"Error:\n{errs}")

    def _on_cancel_elim(self):
        lyr = self._layer
        if lyr:
            lyr.removeSelection()
        self._btn_eliminar.setVisible(True)
        self._btn_confirmar_elim.setVisible(False)
        self._btn_cancel_elim.setVisible(False)
        self.adjustSize()
        # _on_eliminar() (i, si es confirma, _renumerar_camins()) tanquen
        # la sessió d'edició amb el seu propi commitChanges() intern.
        # Reprenem l'edició i l'eina de dibuix aquí perquè es pugui
        # continuar digitalitzant sense haver de desar i tancar l'edició
        # manualment — tant si l'usuari confirma l'eliminació com si la
        # cancel·la.
        if lyr:
            lyr.startEditing()
            self.iface.setActiveLayer(lyr)
            self.iface.actionAddFeature().trigger()
            self.iface.mapCanvas().refresh()

    def _on_close(self):
        if self._layer and self._layer.isEditable():
            reply = QMessageBox.question(
                self, "Desar canvis",
                "Hi ha edicions en curs. Vols desar-les?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._on_stop()
            else:
                self._layer.rollBack()
                cfg = self._layer.editFormConfig()
                cfg.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOff)
                self._layer.setEditFormConfig(cfg)
        self.close()

    def _show_status(self, msg, error=False):
        color = "#b71c1c" if error else "#1b5e20"
        self._lbl_status.setText(msg)
        self._lbl_status.setStyleSheet(
            f"padding:8px; color:{color}; border:1px solid #ddd; "
            "border-radius:4px; background:#fafafa;"
        )
        self._lbl_status.show()
        self.adjustSize()

    def closeEvent(self, event):
        from .iof_utils import restaurar_opacitat_capes_iof
        restaurar_opacitat_capes_iof()
        if self._layer:
            self._layer.removeSelection()
        if self._layer and self._layer.isEditable():
            self._layer.rollBack()
            cfg = self._layer.editFormConfig()
            cfg.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOff)
            self._layer.setEditFormConfig(cfg)
        super().closeEvent(event)

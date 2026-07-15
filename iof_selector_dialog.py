# -*- coding: utf-8 -*-
"""
IOF Assistent — Diàleg selector de capa a editar (Omplir camps).
"""
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QFrame
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject, QgsVectorLayer


LAYER_FINQUES = "IOF_Finques"
LAYERS_UNITATS = ["IOF_Unitats_Actuacio", "IOF_Rodals"]


def _get_layer(names):
    if isinstance(names, str):
        names = [names]
    for lyr in QgsProject.instance().mapLayers().values():
        if isinstance(lyr, QgsVectorLayer) and lyr.name() in names:
            return lyr
    return None


def _sep():
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("color:#ddd;")
    return sep


class SelectorDialog(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        # Quina capa ha triat l'usuari ('unitats' / 'camins'). El wizard
        # corresponent es crea i es mostra des de fora (run_wizard() a
        # iof_exporter.py), un cop aquest diàleg (modal) s'ha tancat del
        # tot — crear un diàleg no modal des d'un slot que alhora tanca
        # el seu propi diàleg modal fa que els clics no arribin als seus
        # botons, encara que la finestra es vegi normal.
        self.choice = None
        self.setWindowTitle("IOF Assistent — Omplir camps")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        lbl = QLabel("<b>Quina capa vols omplir?</b>")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            "padding:8px; background:#e3f2fd; border-radius:4px; font-weight:bold;"
        )
        layout.addWidget(lbl)

        desc = QLabel(
            "Selecciona la capa per a la qual vols introduir les dades "
            "dels atributs polígon a polígon."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#555; padding:2px 4px;")
        layout.addWidget(desc)

        layout.addWidget(_sep())

        # IOF_Finques
        layer_f = _get_layer(LAYER_FINQUES)
        btn_finques = QPushButton("IOF_Finques  (codi finca, municipi, superfície)")
        btn_finques.setStyleSheet(
            "background:#e8f5e9; color:#1b5e20; font-weight:bold; padding:6px 16px;"
        )
        btn_finques.clicked.connect(self._open_finques)
        if layer_f is None:
            btn_finques.setEnabled(False)
            btn_finques.setToolTip("Crea les capes IOF primer")
        layout.addWidget(btn_finques)

        # IOF_Rodals / IOF_Unitats_Actuacio
        layer_u = _get_layer(LAYERS_UNITATS)
        nom_u = layer_u.name() if layer_u else "IOF_Rodals / IOF_Unitats_Actuacio"
        btn_ua = QPushButton(
            f"{nom_u}  (codi, formació forestal, codi d'ús, superfícies)"
        )
        btn_ua.setStyleSheet(
            "background:#e3f2fd; color:#0d47a1; font-weight:bold; padding:6px 16px;"
        )
        btn_ua.clicked.connect(self._open_unitats)
        if layer_u is None:
            btn_ua.setEnabled(False)
            btn_ua.setToolTip("Crea les capes IOF primer")
        layout.addWidget(btn_ua)

        # IOF_Camins
        layer_c = _get_layer(["IOF_Camins"])
        nom_c = layer_c.name() if layer_c else "IOF_Camins"
        btn_camins = QPushButton(f"{nom_c}  (tipus de vial, estat, longitud)")
        btn_camins.setStyleSheet(
            "background:#fff8e1; color:#e65100; font-weight:bold; padding:6px 16px;"
        )
        btn_camins.clicked.connect(self._open_camins)
        if layer_c is None:
            btn_camins.setEnabled(False)
            btn_camins.setToolTip("Crea les capes IOF primer")
        layout.addWidget(btn_camins)

        layout.addWidget(_sep())

        btn_close = QPushButton("Cancel·lar")
        btn_close.setStyleSheet("padding:6px;")
        btn_close.clicked.connect(self.reject)
        layout.addWidget(btn_close)

    def _open_finques(self):
        # Comprova si IOF_Finques ja te totes les dades omplertes (abans
        # de tancar, ja que un QMessageBox niat dins d'un diàleg modal
        # funciona bé — el problema només és amb diàlegs NO modals)
        from qgis.core import QgsProject, QgsVectorLayer
        from qgis.PyQt.QtWidgets import QMessageBox
        layer_finques = None
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Finques":
                layer_finques = lyr
                break
        if layer_finques and layer_finques.featureCount() > 0:
            camps = ["codi_finca", "nom_finca", "municipi", "comarca", "superficie"]
            fields_names = layer_finques.fields().names()
            totes_omplertes = all(
                all(
                    str(feat[camp] or "").strip() not in ("", "NULL")
                    for camp in camps if camp in fields_names
                )
                for feat in layer_finques.getFeatures()
            )
            if totes_omplertes:
                resp = QMessageBox.question(
                    self.iface.mainWindow(),
                    "Dades ja complertes",
                    "Totes les finques ja tenen les dades omplertes "
                    "(carregades des de l'\u00e0mbit IOF).\n\n"

                    "Vols revisar-les igualment?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if resp == QMessageBox.StandardButton.No:
                    self.choice = None
                    self.accept()
                    return
        self.choice = 'finques'
        self.accept()

    def _open_unitats(self):
        self.choice = 'unitats'
        self.accept()

    def _open_camins(self):
        self.choice = 'camins'
        self.accept()

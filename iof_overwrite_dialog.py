# -*- coding: utf-8 -*-
"""
Diàleg de confirmació de sobreescriptura per a capes IOF existents.
Permet decidir capa per capa, o aplicar la mateixa decisió a totes.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QFrame
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont


# Resultats possibles
OVERWRITE = "overwrite"    # Sobreescriu aquesta capa
KEEP = "keep"         # Conserva la capa existent
OVERWRITE_ALL = "overwrite_all"  # Sobreescriu totes les restants
KEEP_ALL = "keep_all"     # Conserva totes les restants
CANCEL = "cancel"       # Cancel·la tota l'operació


class OverwriteDialog(QDialog):
    """
    Diàleg modal que pregunta què fer quan una capa ja existeix.

    Retorna un dels valors constants: OVERWRITE, KEEP,
    OVERWRITE_ALL, KEEP_ALL o CANCEL.
    """

    def __init__(self, layer_name, gpkg_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capa existent")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.result_action = CANCEL
        self._build_ui(layer_name, gpkg_path)

    def _build_ui(self, layer_name, gpkg_path):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Icona + missatge principal
        msg_layout = QHBoxLayout()
        icon_lbl = QLabel("⚠️")
        icon_lbl.setFont(QFont("", 24))
        icon_lbl.setFixedWidth(40)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)

        text_layout = QVBoxLayout()
        lbl_title = QLabel(f"<b>La capa «{layer_name}» ja existeix</b>")
        lbl_title.setWordWrap(True)

        short_path = gpkg_path if len(gpkg_path) <= 60 else "…" + gpkg_path[-57:]
        lbl_path = QLabel(f"<small style='color:#666'>{short_path}</small>")
        lbl_path.setWordWrap(True)

        lbl_question = QLabel("Vols sobreescriure la capa existent o conservar-la?")
        lbl_question.setWordWrap(True)

        text_layout.addWidget(lbl_title)
        text_layout.addWidget(lbl_path)
        text_layout.addSpacing(4)
        text_layout.addWidget(lbl_question)

        msg_layout.addWidget(icon_lbl)
        msg_layout.addLayout(text_layout, stretch=1)
        layout.addLayout(msg_layout)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #ddd;")
        layout.addWidget(sep)

        # Checkbox "aplica a totes"
        self._chk_all = QCheckBox("Aplica aquesta decisió a totes les capes existents")
        self._chk_all.setToolTip(
            "Si està marcat, no es tornaran a fer preguntes per a les capes restants."
        )
        layout.addWidget(self._chk_all)

        # Botons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        btn_overwrite = QPushButton("Sobreescriu")
        btn_overwrite.setStyleSheet(
            "background:#c62828; color:white; font-weight:bold; padding:6px 14px;"
        )
        btn_overwrite.setToolTip("Elimina la capa existent i crea-la de nou")
        btn_overwrite.clicked.connect(self._on_overwrite)

        btn_keep = QPushButton("Conserva")
        btn_keep.setStyleSheet(
            "background:#1565c0; color:white; font-weight:bold; padding:6px 14px;"
        )
        btn_keep.setToolTip("Manté la capa existent i omet la creació d'aquesta capa")
        btn_keep.clicked.connect(self._on_keep)

        btn_cancel = QPushButton("Cancel·la tot")
        btn_cancel.setToolTip("Cancel·la tota l'operació de creació de capes")
        btn_cancel.clicked.connect(self._on_cancel)

        btn_layout.addWidget(btn_overwrite)
        btn_layout.addWidget(btn_keep)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def _on_overwrite(self):
        self.result_action = OVERWRITE_ALL if self._chk_all.isChecked() else OVERWRITE
        self.accept()

    def _on_keep(self):
        self.result_action = KEEP_ALL if self._chk_all.isChecked() else KEEP
        self.accept()

    def _on_cancel(self):
        self.result_action = CANCEL
        self.reject()

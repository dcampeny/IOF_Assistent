# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
)
from qgis.PyQt.QtGui import QPixmap, QFont
from qgis.PyQt.QtCore import Qt


class SobreIOFDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugin_dir = os.path.dirname(__file__)
        self.setWindowTitle("Sobre IOF Assistent")
        self.setFixedWidth(460)
        self.setModal(True)
        self._build_ui()

    def _get_version(self):
        """Llegeix la versió des de metadata.txt, perquè no es pugui
        desquadrar respecte al que veu QGIS al gestor de complements."""
        import configparser
        metadata_path = os.path.join(self.plugin_dir, "metadata.txt")
        cfg = configparser.ConfigParser()
        try:
            cfg.read(metadata_path, encoding="utf-8")
            return cfg.get("general", "version", fallback="?")
        except Exception:
            return "?"

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(10)

        # ── Capçalera: icona + nom del complement ──────────────────────────
        header = QHBoxLayout()
        header.setSpacing(14)

        icon_label = QLabel()
        pix = QPixmap(os.path.join(self.plugin_dir, "icons", "icon.png"))
        if not pix.isNull():
            icon_label.setPixmap(pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(icon_label)

        name_label = QLabel("IOF Assistent")
        f = QFont()
        f.setPointSize(18)
        f.setBold(True)
        name_label.setFont(f)
        name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        header.addWidget(name_label)
        header.addStretch()

        layout.addLayout(header)

        # ── Línia separadora ───────────────────────────────────────────────
        layout.addWidget(self._separator())

        # ── Autor ─────────────────────────────────────────────────────────
        autor_layout = QHBoxLayout()
        autor_layout.setSpacing(1)

        autor_text = QLabel("<b>David Campeny</b>, enginyer forestal a")
        autor_text.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        f_autor = QFont()
        f_autor.setPointSize(10)
        autor_text.setFont(f_autor)
        autor_layout.addWidget(autor_text)

        ev_label = QLabel()
        ev_pix = QPixmap(os.path.join(self.plugin_dir, "icons", "EV.png"))
        if not ev_pix.isNull():
            ev_label.setPixmap(ev_pix.scaled(180, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        ev_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        autor_layout.addWidget(ev_label)
        autor_layout.addStretch()

        layout.addLayout(autor_layout)

        # ── Nom i versió ───────────────────────────────────────────────────
        versio_label = QLabel(f"IOF Assistent v{self._get_version()}")
        f2 = QFont()
        f2.setPointSize(8)
        f2.setItalic(True)
        versio_label.setFont(f2)
        versio_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(versio_label)

        # ── Línia separadora ───────────────────────────────────────────────
        layout.addWidget(self._separator())

        # ── Descripció ────────────────────────────────────────────────────
        desc = QLabel(
            "Complement de QGIS per a la creació dels plànols d'un Instrument "
            "d'Ordenació Forestal (IOF) segons les especificacions del Centre de "
            "la Propietat Forestal de Catalunya, i l'exportació de les seves dades SIG.\n\n"
            "Inclou eines per a la importació de cartografia cadastral i de referència "
            "territorial de l'ICGC, la delimitació "
            "de finques i l'àmbit de l'IOF, la digitalització de límits, "
            "tipologies forestals, camins, infraestructures de prevenció "
            "d'incendis, canvis d'ús, "
            "punts d'aigua, elements singulars i inventaris forestals, així com "
            "l'exportació de les dades SIG per a la importació a PDF de l'IOF.\n\n"
            "Aquest complement utilitza els serveis web de la Direcció General del "
            "Cadastre (servei ATOM INSPIRE) per a la descàrrega de cartografia "
            "cadastral, sense necessitat d'autenticació.\n\n"
            "L'ortofotomapa i el mapa base topogràfic s'obtenen mitjançant els "
            "geoserveis WMS de l'Institut Cartogràfic i Geològic de "
            "Catalunya (ICGC), disponibles a geoserveis.icgc.cat. La base "
            "topogràfica (mapa referencial topogràfic territorial) es descarrega "
            "en format vectorial a través del complement oficial "
            "«Open ICGC» (cal tenir-lo instal·lat a QGIS). "
            "Cartografia © Institut Cartogràfic i Geològic de Catalunya, "
            "llicència CC-BY (https://creativecommons.org/licenses/by/4.0/).\n\n"
            "Les qualificacions especials (ENPE, PEIN, Xarxa Natura 2000, "
            "espais catalogats d'utilitat pública i àrees de fauna protegida) "
            "es descarreguen mitjançant els serveis web WFS de la Generalitat "
            "de Catalunya (sig.gencat.cat). Els perímetres de protecció "
            "prioritària i les zones d'actuació urgent es descarreguen del "
            "Departament d'Agricultura, Ramaderia, Pesca i Alimentació "
            "(agricultura.gencat.cat).\n\n"
            "El tipus de risc d'incendis es descarrega del Centre de la "
            "Propietat Forestal (cpf.gencat.cat, mapa de risc d'incendi "
            "tipus de Catalunya). El mapa urbanístic de Catalunya "
            "(per al càlcul de la qualificació urbanística, LU) es "
            "consulta mitjançant el servei WMS de la Generalitat de "
            "Catalunya (dtes.gencat.cat)."
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignJustify | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(desc)

        layout.addSpacing(6)

        # ── Botó Tancar ────────────────────────────────────────────────────
        btn = QPushButton("Tancar")
        btn.setFixedWidth(90)
        btn.clicked.connect(self.accept)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

    def _separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

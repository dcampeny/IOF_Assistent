# -*- coding: utf-8 -*-
"""
Gestor del Referencial Topogràfic Territorial (capes "IOF_Topografia").

Tres seccions:
  1. Generar una nova capa IOF_Topografia (descàrrega via Open ICGC).
  2. Actualment carregat — un grup numerat ("Topogràfic territorial N")
     per cada descàrrega/càrrega, triable des d'un desplegable, amb
     eliminar del mapa, o del mapa i del disc.
  3. Carregar un GeoPackage existent — reaplica reagrupament + estil.

Cada capa carregada obté el seu propi grup numerat (mai es barregen
subcapes de descàrregues diferents dins d'un sol grup), i es renumeren
sempre consecutivament (1, 2, 3, ..., sense buits) en afegir-ne o
eliminar-ne un — vegeu iof_utils.py: cerca_grups_topografia(),
renumera_grups_topografia(), seguent_numero_topografia().

Diàleg aïllat i sota demanda: no toca initGui() ni s'executa res en
carregar el complement, només quan s'obre expressament des del menú
"Mapes ICGC → Referencial topogràfic territorial vectorial".
"""

import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QMessageBox, QFileDialog, QComboBox
)
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsProviderRegistry, QgsMessageLog, Qgis
)
from .iof_utils import (
    cerca_grups_topografia, renumera_grups_topografia, seguent_numero_topografia
)

NOM_GRUP_PARE = "Cartografia de referència"


class GestorTopografiaDialog(QDialog):

    def __init__(self, iface, exporter, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.exporter = exporter  # instància d'IOFExporter: _get_qlr_style_template() / _aplicar_estil_qlr()

        self.setWindowTitle("IOF Assistent — Gestor de topografia")
        self.setMinimumWidth(480)
        self._build_ui()
        self._actualitza_estat()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _separador(self):
        linia = QFrame()
        linia.setFrameShape(QFrame.Shape.HLine)
        linia.setFrameShadow(QFrame.Shadow.Sunken)
        return linia

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Secció 1: Generar una nova capa ──────────────────────────
        layout.addWidget(QLabel("<b>1. Generar una nova capa IOF_Topografia</b>"))
        lbl1 = QLabel(
            "Descarrega el Referencial Topogràfic Territorial d'una zona "
            "nova a través del complement «Open ICGC». Obtindrà el seu "
            "propi grup numerat."
        )
        lbl1.setWordWrap(True)
        layout.addWidget(lbl1)
        btn_generar = QPushButton("Generar nova capa…")
        btn_generar.clicked.connect(self._generar_nova)
        layout.addWidget(btn_generar)

        layout.addWidget(self._separador())

        # ── Secció 2: Actualment carregat ─────────────────────────────
        layout.addWidget(QLabel("<b>2. Actualment carregat</b>"))
        self._lbl_estat = QLabel()
        self._lbl_estat.setWordWrap(True)
        layout.addWidget(self._lbl_estat)

        self._combo_grups = QComboBox()
        self._combo_grups.currentIndexChanged.connect(self._actualitza_botons_seccio2)
        layout.addWidget(self._combo_grups)

        fila_botons = QHBoxLayout()
        self._btn_eliminar_mapa = QPushButton("Eliminar del mapa")
        self._btn_eliminar_mapa.clicked.connect(lambda: self._eliminar_seleccionat(esborrar_disc=False))
        self._btn_eliminar_disc = QPushButton("Eliminar del mapa i del disc")
        self._btn_eliminar_disc.clicked.connect(lambda: self._eliminar_seleccionat(esborrar_disc=True))
        fila_botons.addWidget(self._btn_eliminar_mapa)
        fila_botons.addWidget(self._btn_eliminar_disc)
        layout.addLayout(fila_botons)

        layout.addWidget(self._separador())

        # ── Secció 3: Carregar un GeoPackage existent ─────────────────
        layout.addWidget(QLabel("<b>3. Carregar un GeoPackage existent</b>"))
        lbl3 = QLabel(
            "Torna a carregar un fitxer .gpkg ja descarregat abans, "
            "aplicant-hi automàticament el reagrupament i l'estil de "
            "referència, com un grup numerat nou."
        )
        lbl3.setWordWrap(True)
        layout.addWidget(lbl3)
        btn_carregar = QPushButton("Tria un fitxer .gpkg…")
        btn_carregar.clicked.connect(self._triar_i_carregar_gpkg)
        layout.addWidget(btn_carregar)

        layout.addWidget(self._separador())

        btn_tancar = QPushButton("Tancar")
        btn_tancar.clicked.connect(self.accept)
        layout.addWidget(btn_tancar)

    # ------------------------------------------------------------------
    # Estat actual
    # ------------------------------------------------------------------

    def _gpkg_paths_del_grup(self, grup):
        paths = set()
        for node in grup.findLayers():
            lyr = node.layer()
            if lyr is None:
                continue
            try:
                uri = lyr.dataProvider().dataSourceUri()
                path = uri.split('|')[0]
                if path.lower().endswith('.gpkg'):
                    paths.add(path)
            except Exception:  # nosec — error no crític, es descarta intencionadament
                continue
        return paths

    def _actualitza_estat(self):
        renumera_grups_topografia()
        grups = cerca_grups_topografia()

        self._combo_grups.blockSignals(True)
        self._combo_grups.clear()
        self._grups_actuals = grups  # llista de (numero, node_grup), mateix ordre que el combo
        if not grups:
            self._lbl_estat.setText("Cap capa de topografia carregada actualment.")
        else:
            self._lbl_estat.setText(f"{len(grups)} grup(s) de topografia carregat(s):")
            for numero, grup in grups:
                paths = self._gpkg_paths_del_grup(grup)
                resum = ", ".join(os.path.basename(p) for p in paths) if paths else "fitxer desconegut"
                self._combo_grups.addItem(f"{grup.name()} — {resum}")
        self._combo_grups.blockSignals(False)
        self._actualitza_botons_seccio2()

    def _actualitza_botons_seccio2(self):
        hi_ha_seleccio = bool(getattr(self, "_grups_actuals", None)) and self._combo_grups.currentIndex() >= 0
        self._btn_eliminar_mapa.setEnabled(hi_ha_seleccio)
        self._btn_eliminar_disc.setEnabled(hi_ha_seleccio)

    # ------------------------------------------------------------------
    # Secció 1: generar nova capa
    # ------------------------------------------------------------------

    def _generar_nova(self):
        self.exporter.run_base_topografica_descarrega()
        self.accept()  # la resta de la descàrrega la porta Open ICGC

    # ------------------------------------------------------------------
    # Secció 2: eliminar el grup seleccionat al desplegable
    # ------------------------------------------------------------------

    def _eliminar_seleccionat(self, esborrar_disc):
        idx = self._combo_grups.currentIndex()
        if idx < 0 or idx >= len(self._grups_actuals):
            return
        _numero, grup = self._grups_actuals[idx]
        self._eliminar_grup(grup, esborrar_disc)
        self._actualitza_estat()

    def _eliminar_grup(self, grup, esborrar_disc):
        if esborrar_disc:
            resp = QMessageBox.question(
                self, "Eliminar del mapa i del disc",
                f"Això eliminarà «{grup.name()}» del mapa I esborrarà el "
                "fitxer GeoPackage corresponent del disc.\n\n"
                "Aquesta acció NO es pot desfer. Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if resp != QMessageBox.StandardButton.Yes:
                return

        gpkg_paths = self._gpkg_paths_del_grup(grup)
        layer_ids = [node.layer().id() for node in grup.findLayers() if node.layer() is not None]

        parent = grup.parent()
        if parent is not None:
            parent.removeChildNode(grup)
        QgsProject.instance().removeMapLayers(layer_ids)

        if esborrar_disc:
            for path in gpkg_paths:
                for sufix in ("", "-wal", "-shm", "-journal"):
                    path_complet = path + sufix
                    if os.path.exists(path_complet):
                        try:
                            os.remove(path_complet)
                        except OSError as e:
                            QgsMessageLog.logMessage(
                                f"IOF Assistent: no s'ha pogut eliminar "
                                f"{path_complet}: {e}",
                                "IOFAssistent", level=Qgis.MessageLevel.Warning
                            )
        # La renumeració es fa a _actualitza_estat(), cridada pel que
        # invoqui aquest mètode — no aquí, per no fer-ho dues vegades
        # quan "Substitueix" elimina diversos grups seguits.

    # ------------------------------------------------------------------
    # Secció 3: carregar un gpkg existent
    # ------------------------------------------------------------------

    def _triar_i_carregar_gpkg(self):
        path, _filtre = QFileDialog.getOpenFileName(
            self, "Tria un fitxer GeoPackage", "", "GeoPackage (*.gpkg)"
        )
        if not path:
            return

        grups_existents = cerca_grups_topografia()
        if grups_existents:
            msg = QMessageBox(self)
            msg.setWindowTitle("Ja hi ha topografia carregada")
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setText(
                f"Ja hi ha {len(grups_existents)} grup(s) de topografia "
                "carregat(s).\n\n"
                "Vols substituir-los (eliminar-los tots primer), o "
                "afegir aquest a més a més (amb el seu propi grup nou)?"
            )
            btn_substitueix = msg.addButton("Substitueix", QMessageBox.ButtonRole.YesRole)
            msg.addButton("Afegeix", QMessageBox.ButtonRole.NoRole)
            btn_cancel = msg.addButton("Cancel·la", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_cancel)
            msg.exec()
            clicat = msg.clickedButton()
            if clicat == btn_cancel:
                return
            if clicat == btn_substitueix:
                for _numero, grup in grups_existents:
                    self._eliminar_grup(grup, esborrar_disc=False)

        self._carregar_gpkg(path)
        self._actualitza_estat()

    def _carregar_gpkg(self, gpkg_path):
        sublayers = QgsProviderRegistry.instance().querySublayers(gpkg_path)
        if not sublayers:
            QMessageBox.warning(
                self, "Error en carregar",
                f"No s'ha trobat cap subcapa dins de:\n{gpkg_path}"
            )
            return

        root = QgsProject.instance().layerTreeRoot()
        grup_pare = root.findGroup(NOM_GRUP_PARE)
        if grup_pare is None:
            grup_pare = root.insertGroup(-1, NOM_GRUP_PARE)

        nom_grup_nou = f"Topogràfic territorial {seguent_numero_topografia()}"
        grup_topo = grup_pare.insertGroup(0, nom_grup_nou)

        estils, visibilitat = self.exporter._get_qlr_style_template()

        carregades = 0
        for sub in sublayers:
            lyr = QgsVectorLayer(sub.uri(), f"IOF_Topografia — {sub.name()}", sub.providerKey())
            if not lyr.isValid():
                continue
            QgsProject.instance().addMapLayer(lyr, False)
            node = grup_topo.addLayer(lyr)
            self.exporter._aplicar_estil_qlr(node, estils, visibilitat)
            carregades += 1

        if carregades == 0:
            grup_pare.removeChildNode(grup_topo)
            QMessageBox.warning(
                self, "Error en carregar",
                f"No s'ha pogut carregar cap subcapa vàlida de:\n{gpkg_path}"
            )

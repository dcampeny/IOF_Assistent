# -*- coding: utf-8 -*-
"""
Diàleg d'importació de capes cadastrals INSPIRE.
Basat en el plugin Spanish_Inspire_Catastral_Downloader (sigdeletras/GitHub).
Usa QNetworkAccessManager de Qt per respectar el proxy de QGIS.
"""

import os
import json
import sys
import zipfile
from urllib import parse

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QProgressBar, QMessageBox, QSizePolicy, QApplication
)
from qgis.PyQt.QtCore import Qt, QUrl, QTimer
from qgis.PyQt.QtGui import QFont
from qgis.PyQt import QtNetwork
from qgis.core import (QgsProject, QgsVectorLayer, Qgis, QgsMessageLog,
                       QgsVectorFileWriter, QgsCoordinateTransformContext)

# defusedxml protegeix contra atacs coneguts d'XML (expansió d'entitats,
# entitats externes...) en analitzar dades que venen d'una font externa
# (el feed ATOM del Cadastre). És una dependència externa obligatòria,
# però per no dependre que l'usuari final l'instal·li manualment amb pip
# (QGIS no instal·la dependències pip dels complements), la incorporem
# vendoritzada a ext_libs/ (còpia oficial de PyPI, llicència PSFL a
# ext_libs/defusedxml/LICENSE) i l'afegim al sys.path abans d'importar-la.
# Sense reserva a xml.etree.ElementTree: els escàners de seguretat
# estàtics (Bandit) marquen la sola presència textual de
# "from xml.etree import ElementTree", encara que mai s'executi.
_EXT_LIBS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ext_libs")
if _EXT_LIBS_DIR not in sys.path:
    sys.path.insert(0, _EXT_LIBS_DIR)
from defusedxml import ElementTree as ET  # noqa: E402

# ── URLs (seguint el plugin de referència) ────────────────────────────────────
_URL_MUNICIPIS = (
    'http://ovc.catastro.meh.es/OVCServWeb/OVCWcfCallejero'
    '/COVCCallejeroCodigos.svc/json/ObtenerMunicipiosCodigos?CodigoProvincia={cp}'
)
_BASE_ATOM = 'https://www.catastro.hacienda.gob.es'
# Feed ATOM provincial: conté un <entry> per cada municipi amb la URL del ZIP
# inecode_catastro = codi INE de 5 dígits (cprov 2 + cmun 3)
_URL_ATOM_PROV = (
    '{base}/INSPIRE/{tipo}/{cprov}/ES.SDGC.{codtipo}.atom_{cprov}.xml'
)

# Dominis oficials del Cadastre (Direcció General del Cadastre, Ministeri
# d'Hisenda). El seu certificat el signa la FNMT-RCM, l'autoritat de
# certificació de l'Estat espanyol, que no ve preinstal·lada per defecte a
# macOS. Com que és un domini .gob.es fix i conegut (no d'entrada d'usuari),
# es confia en el certificat encara que aquell ordinador no reconegui la
# FNMT com a autoritat de confiança, perquè l'usuari no hagi d'instal·lar
# res manualment per poder fer servir la importació de cadastre.
_DOMINIS_CADASTRE_DE_CONFIANCA = ("catastro.hacienda.gob.es", "catastro.meh.es")


def _es_domini_cadastre(url):
    host = QUrl(url).host().lower()
    return any(host == d or host.endswith("." + d) for d in _DOMINIS_CADASTRE_DE_CONFIANCA)


def _confiar_si_es_cadastre(reply):
    """Connecta sslErrors perquè, si la petició és a un domini oficial del
    Cadastre, s'ignorin els errors de certificat (típicament perquè el
    sistema operatiu no té la FNMT-RCM com a autoritat de confiança) en
    lloc de fer fallar la connexió."""
    url_str = reply.url().toString()
    if _es_domini_cadastre(url_str):
        reply.sslErrors.connect(reply.ignoreSslErrors)


# Colors pastels per als polígons cadastrals (un per municipi)
_COLORS_POLIGONS = [
    (255, 230, 180),  # taronja molt clar
    (180, 220, 255),  # blau molt clar
    (200, 255, 200),  # verd molt clar
    (255, 200, 220),  # rosa molt clar
    (220, 200, 255),  # malva molt clar
    (255, 255, 180),  # groc molt clar
    (180, 255, 240),  # turquesa molt clar
    (240, 220, 200),  # crema molt clar
]


class ImportarCadastreDial(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self._inecode = None  # codi INE 5 dígits del municipi seleccionat
        self._wd = None  # directori de destí (darrer municipi)
        # Compta quants municipis (capes de zones) ja existeixen al projecte
        # per assignar colors pastels consecutius
        self._mun_count = sum(
            1 for lyr in QgsProject.instance().mapLayers().values()
            if "polígons cadastrals" in lyr.name().lower() or "cadastralzoning" in lyr.name().lower()
        )
        self._wds = []    # totes les carpetes de municipis carregats
        self._nom_mun = None
        self._inecodes_descarregats = set()  # codis de municipis ja descarregats
        self.setWindowTitle("Importar cadastre")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._build_ui()
        QTimer.singleShot(100, self._load_provincies)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Descàrrega de capes cadastrals INSPIRE")
        f = QFont()
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        info = QLabel(
            "Selecciona la província i el municipi per descarregar les capes "
            "<i>CadastralParcel</i> i <i>CadastralZoning</i> del servei ATOM "
            "de la Direcció General del Cadastre."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        layout.addWidget(QLabel("Província:"))
        self._combo_prov = QComboBox()
        self._combo_prov.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._combo_prov)

        layout.addWidget(QLabel("Municipi:"))
        self._combo_mun = QComboBox()
        self._combo_mun.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._combo_mun)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        btn_layout = QHBoxLayout()
        self._btn_dl = QPushButton("Descarregar")
        self._btn_dl.setEnabled(False)
        self._btn_dl.clicked.connect(self._on_descarregar)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_dl)
        btn_t = QPushButton("Tancar")
        btn_t.clicked.connect(self._tancar_i_netejar)
        btn_layout.addWidget(btn_t)
        layout.addLayout(btn_layout)

    # ── Càrrega de províncies (llista estàtica Catalunya) ────────────────────
    # IOF Assistent és específic per a Catalunya: 4 províncies
    _PROVINCIES_CAT = [
        ("08", "Barcelona"),
        ("17", "Girona"),
        ("25", "Lleida"),
        ("43", "Tarragona"),
    ]

    def _load_provincies(self):
        self._combo_prov.blockSignals(True)
        self._combo_prov.clear()
        self._combo_prov.addItem("— Selecciona una província —", None)
        for cpine, nom in self._PROVINCIES_CAT:
            self._combo_prov.addItem(f"{cpine} - {nom}", cpine)
        self._combo_prov.blockSignals(False)
        self._combo_prov.setEnabled(True)
        self._combo_prov.currentIndexChanged.connect(self._on_prov_changed)

    # ── Canvi de província → carrega municipis (asíncron) ─────────────────────
    def _netejar_gml(self):
        """Elimina tots els fitxers no-GPKG de totes les carpetes de municipis."""
        carpetes = self._wds if self._wds else ([self._wd] if self._wd else [])
        for wd in carpetes:
            if not wd or not os.path.isdir(wd):
                continue
            try:
                for f_aux in os.listdir(wd):
                    if not f_aux.lower().endswith(".gpkg"):
                        fp_aux = os.path.join(wd, f_aux)
                        if os.path.isfile(fp_aux):
                            try:
                                os.remove(fp_aux)
                            except Exception:  # nosec — error no crític, es descarta intencionadament
                                pass
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass

    def _tancar_i_netejar(self):
        """Neteja els GML i tanca el dialeg."""
        self._netejar_gml()
        self.reject()

    def closeEvent(self, event):
        self._netejar_gml()
        super().closeEvent(event)

    def _on_prov_changed(self, _idx):
        self._btn_dl.setEnabled(False)
        self._combo_mun.clear()
        cpine = self._combo_prov.currentData()
        if not cpine:
            return

        self._combo_mun.addItem("Carregant municipis…")
        self._combo_mun.setEnabled(False)
        self._status.setText("Carregant municipis…")

        url = _URL_MUNICIPIS.format(cp=cpine)
        self._mgr_mun = QtNetwork.QNetworkAccessManager()
        self._mgr_mun.finished.connect(self._on_municipis_rebuts)
        req = QtNetwork.QNetworkRequest(QUrl(url))
        self._mgr_mun.get(req)

    def _on_municipis_rebuts(self, reply):
        er = reply.error()
        if er != QtNetwork.QNetworkReply.NetworkError.NoError:
            self._combo_mun.clear()
            self._combo_mun.addItem("Error en carregar municipis")
            self._status.setText(f"Error de xarxa: {reply.errorString()}")
            return

        raw = bytes(reply.readAll())

        if not raw.strip():
            # El servidor ha respost correctament (sense error de xarxa) però
            # amb el cos buit — normalment és una caiguda temporal o una
            # limitació de peticions del servei del Cadastre, no un error
            # del complement. Reintentar al cap d'una estona sol funcionar.
            status = reply.attribute(
                QtNetwork.QNetworkRequest.Attribute.HttpStatusCodeAttribute
            )
            self._combo_mun.clear()
            self._combo_mun.addItem("Error en carregar municipis")
            self._status.setText(
                f"El servei del Cadastre ha retornat una resposta buida "
                f"(codi HTTP: {status}). Sol ser temporal — torna-ho a "
                f"provar d'aquí una estona."
            )
            from .iof_utils import log
            log(
                f"Resposta buida del servei de municipis del Cadastre "
                f"(HTTP {status}).",
                level=Qgis.MessageLevel.Warning,
            )
            return

        try:
            data = json.loads(raw.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._combo_mun.clear()
            self._combo_mun.addItem("Error en carregar municipis")
            self._status.setText(
                "El servei del Cadastre ha retornat una resposta no "
                "vàlida. Sol ser temporal — torna-ho a provar d'aquí "
                "una estona."
            )
            from .iof_utils import log
            avanc = raw[:300].decode('utf-8', errors='replace')
            log(
                f"Resposta no-JSON del servei de municipis del Cadastre: "
                f"{e}\nPrimers 300 bytes: {avanc}",
                level=Qgis.MessageLevel.Warning,
            )
            return

        try:
            munis = data['consulta_municipieroResult']['municipiero']['muni']
        except (KeyError, TypeError):
            munis = []

        self._combo_mun.blockSignals(True)
        self._combo_mun.clear()
        self._combo_mun.addItem("— Selecciona un municipi —", None)
        for m in munis:
            cprov_mun = str(m['locat']['cd']).zfill(2)
            cmun = str(m['locat']['cmc']).zfill(3)
            inecode = cprov_mun + cmun          # 5 dígits INE
            nom = str(m['nm']).strip().title()
            self._combo_mun.addItem(f"{inecode} - {nom}", inecode)
        self._combo_mun.blockSignals(False)
        self._combo_mun.setEnabled(True)
        self._combo_mun.currentIndexChanged.connect(self._on_mun_changed)
        self._status.setText("")

    def _on_mun_changed(self, _idx):
        inecode = self._combo_mun.currentData()
        # Habilita el botó només si hi ha municipi seleccionat
        # i és diferent de l'últim que s'ha descarregat
        self._btn_dl.setEnabled(
            inecode is not None and inecode not in self._inecodes_descarregats
        )

    # ── Descàrrega ────────────────────────────────────────────────────────────
    def _on_descarregar(self):
        from .iof_utils import ensure_project_saved
        proj_path = ensure_project_saved(self)
        if not proj_path:
            return

        self._inecode = self._combo_mun.currentData()  # p.ex. "08019"
        self._nom_mun = self._combo_mun.currentText().split(' - ', 1)[-1]
        if not self._inecode:
            return

        self._wd = os.path.join(proj_path, "cadastre", self._inecode)
        if self._wd not in self._wds:
            self._wds.append(self._wd)

        if os.path.isdir(self._wd) and os.listdir(self._wd):
            resp = QMessageBox.question(
                self, "Ja existeix",
                f"La carpeta '{self._wd}' ja conté fitxers.\n"
                "Vols tornar a descarregar i sobreescriure?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )
            if resp == QMessageBox.StandardButton.No:
                self._load_layers()
                return

        self._btn_dl.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(5)
        self._status.setText("Consultant el feed ATOM…")

        # Construeix la URL del feed ATOM provincial
        cprov = self._inecode[:2]
        atom_url = _URL_ATOM_PROV.format(
            base=_BASE_ATOM,
            tipo='CadastralParcels',
            cprov=cprov,
            codtipo='CP'
        )
        QgsMessageLog.logMessage('IOF Cadastre: ATOM URL = ' + atom_url, 'IOFAssistent', level=Qgis.MessageLevel.Info)

        self._mgr_atom = QtNetwork.QNetworkAccessManager()
        self._mgr_atom.finished.connect(self._on_atom_rebut)
        req = QtNetwork.QNetworkRequest(QUrl(atom_url))
        reply = self._mgr_atom.get(req)
        _confiar_si_es_cadastre(reply)

    def _crear_municipi_cadastral(self, lyr_zoning, sub_grp):
        """
        Crea la capa Municipi Cadastral dissolent la capa de polígons
        i la afegeix al subgrup del municipi amb estil contorn fi sense farciment.
        """
        import processing
        import os
        import tempfile
        from qgis.core import (
            QgsVectorLayer, QgsVectorFileWriter,
            QgsCoordinateTransformContext, QgsFeature, QgsField, QgsFillSymbol,
            QgsSingleSymbolRenderer
        )
        from qgis.PyQt.QtCore import QVariant
        from qgis.PyQt.QtGui import QColor

        proj_path = QgsProject.instance().absolutePath()
        if not proj_path:
            return

        finca_dir = os.path.join(proj_path, "cadastre")
        # El municipiCadastral va a la subcarpeta del municipi (self._wd)
        if not self._wd:
            return
        os.makedirs(self._wd, exist_ok=True)

        # Nom del municipi del nom de la capa de zones
        nom_mun = self._nom_mun

        # Normalitza el nom per al fitxer
        import unicodedata
        nom_net = unicodedata.normalize("NFD", nom_mun)
        nom_net = "".join(c for c in nom_net if unicodedata.category(c) != "Mn")
        nom_net = nom_net.replace(" ", "_").replace("/", "_")
        mun_path = os.path.join(self._wd, "municipiCadastral_" + nom_net + ".gpkg")
        try:
            res_fix = processing.run(
                "native:fixgeometries",
                {"INPUT": lyr_zoning, "METHOD": 1, "OUTPUT": "TEMPORARY_OUTPUT"}
            )
            fixed = res_fix["OUTPUT"]

            # Dissolve
            res_diss = processing.run(
                "native:dissolve",
                {"INPUT": fixed, "FIELD": [], "SEPARATE_DISJOINT": False,
                 "OUTPUT": "TEMPORARY_OUTPUT"}
            )
            dissolved = res_diss["OUTPUT"]

            # Buffer morphological closing
            res_b1 = processing.run(
                "native:buffer",
                {"INPUT": dissolved, "DISTANCE": 0.01, "SEGMENTS": 5,
                 "DISSOLVE": True, "END_CAP_STYLE": 0, "JOIN_STYLE": 0,
                 "MITER_LIMIT": 2, "OUTPUT": "TEMPORARY_OUTPUT"}
            )
            res_b2 = processing.run(
                "native:buffer",
                {"INPUT": res_b1["OUTPUT"], "DISTANCE": -0.01, "SEGMENTS": 5,
                 "DISSOLVE": True, "END_CAP_STYLE": 0, "JOIN_STYLE": 0,
                 "MITER_LIMIT": 2, "OUTPUT": "TEMPORARY_OUTPUT"}
            )
            buf = res_b2["OUTPUT"]

            if not buf or buf.featureCount() == 0:
                return

            # Crea capa neta amb camp municipi
            crs_auth = lyr_zoning.crs().authid()
            mem = QgsVectorLayer("MultiPolygon?crs=" + crs_auth, "mun_tmp", "memory")
            prov = mem.dataProvider()
            prov.addAttributes([QgsField("municipi", QVariant.String, len=100)])
            mem.updateFields()

            for feat in buf.getFeatures():
                nf = QgsFeature(mem.fields())
                nf.setGeometry(feat.geometry())
                nf.setAttribute("municipi", nom_mun)
                prov.addFeature(nf)
            mem.updateExtents()

            # Desa a GPKG
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".gpkg", dir=finca_dir)
            os.close(tmp_fd)
            os.remove(tmp_path)

            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.fileEncoding = "UTF-8"
            error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                mem, tmp_path, QgsCoordinateTransformContext(), opts
            )
            if error != QgsVectorFileWriter.WriterError.NoError:
                return

            if os.path.exists(mun_path):
                os.remove(mun_path)
            os.rename(tmp_path, mun_path)

            # Carrega amb estil inicial: contorn negre fi, sense farciment
            # (el format blau cadastre s'aplica despres amb "Aplicar estil")
            mun_layer = QgsVectorLayer(mun_path, "Municipi cadastral", "ogr")
            if mun_layer.isValid():
                sym = QgsFillSymbol.createSimple({
                    "color": "0,0,0,0",
                    "outline_color": "0,0,0",
                    "outline_width": "0.4",
                    "outline_style": "solid",
                })
                mun_layer.setRenderer(QgsSingleSymbolRenderer(sym))

                # Etiqueta municipi
                from qgis.core import (QgsPalLayerSettings, QgsTextFormat,
                                       QgsVectorLayerSimpleLabeling)
                from qgis.PyQt.QtGui import QFont
                pal = QgsPalLayerSettings()
                pal.fieldName = "municipi"
                pal.enabled = True
                fmt = QgsTextFormat()
                fmt.setFont(QFont("Arial", 10))
                fmt.setColor(QColor(0, 38, 115))
                pal.setFormat(fmt)
                mun_layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
                mun_layer.setLabelsEnabled(True)

                QgsProject.instance().addMapLayer(mun_layer, False)
                sub_grp.insertLayer(0, mun_layer)

        except Exception as e:
            from qgis.core import QgsMessageLog, Qgis
            QgsMessageLog.logMessage(
                "IOF Cadastre: error creant municipi: " + str(e),
                "IOFAssistent", level=Qgis.MessageLevel.Warning
            )

    def _download_zip(self, url_str):
        """Descarrega un ZIP via QNetworkAccessManager de Qt. Retorna els bytes o None.

        S'usa el QNetworkAccessManager de Qt (no QgsNetworkAccessManager)
        deliberadament: el de QGIS mostra sempre el seu propi diàleg natiu
        "Custom Certificate Configuration" en trobar un error SSL,
        independentment que el codi ja l'hagi gestionat amb
        ignoreSslErrors() — exactament el que volem evitar per al domini
        del Cadastre (vegeu _confiar_si_es_cadastre). El feed ATOM ja usa
        aquest mateix patró i funciona net, sense cap diàleg.
        """
        from qgis.PyQt.QtCore import QUrl, QEventLoop, QTimer
        from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
        import io

        nam = QtNetwork.QNetworkAccessManager()
        req = QNetworkRequest(QUrl(url_str))
        req.setRawHeader(b"User-Agent", b"IOFAssistent/1.0 QGIS")
        reply = nam.get(req)
        _confiar_si_es_cadastre(reply)

        buf = io.BytesIO()
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)

        def _on_ready():
            chunk = bytes(reply.readAll())
            buf.write(chunk)

        def _on_progress(recv, total):
            if total > 0:
                pct = int(recv / total * 65) + 15
                self._progress.setValue(min(pct, 80))
                self._status.setText(
                    "Descarregant… " + str(recv // 1024) + " KB"
                )
                QApplication.processEvents()

        reply.readyRead.connect(_on_ready)
        reply.downloadProgress.connect(_on_progress)
        reply.finished.connect(loop.quit)
        timer.start(120000)
        loop.exec()
        timer.stop()
        _on_ready()

        if reply.isRunning():
            reply.abort()
            return None
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return None

        reply.deleteLater()
        buf.seek(0)
        return buf.read()

    def _on_atom_rebut(self, reply):
        er = reply.error()
        if er != QtNetwork.QNetworkReply.NetworkError.NoError:
            self._status.setText("Error en el feed ATOM.")
            self._btn_dl.setEnabled(True)
            QMessageBox.critical(
                self, "Error",
                "No s'ha pogut llegir el feed ATOM:\n" + reply.errorString()
            )
            return

        # Descodifica en iso-8859-1 (com fa el plugin de referència)
        raw = bytes(reply.readAll())
        response = raw.decode('iso-8859-1')

        # Recupera els paràmetres passats a la URL (wd)
        params = parse.parse_qs(
            parse.urlparse(reply.request().url().toString()).query
        )
        params.get('wd', [self._wd])[0]

        # Cerca l'entrada del municipi al feed
        root = ET.fromstring(response)
        ns_atom = '{http://www.w3.org/2005/Atom}'
        zip_url = None

        for entry in root.findall(f'{ns_atom}entry'):
            try:
                url_id = entry.find(f'{ns_atom}id').text
                QgsMessageLog.logMessage('IOF Cadastre: entry id = ' + str(url_id), 'IOFAssistent', level=Qgis.MessageLevel.Info)
                if url_id and url_id.endswith(self._inecode + '.zip'):
                    zip_url = url_id
                    break
            except Exception:  # nosec — error no crític, es descarta intencionadament
                continue

        if not zip_url:
            self._status.setText("Municipi no trobat al feed.")
            self._btn_dl.setEnabled(True)
            QMessageBox.warning(
                self, "Municipi no trobat",
                "No s'ha trobat l'arxiu del municipi " + self._nom_mun + " (codi " + self._inecode + ") al feed ATOM.\n\n"
                "Pot ser que el municipi no tingui cartografia rústica disponible."
            )
            return

        # Descarrega el ZIP
        self._progress.setValue(15)
        self._status.setText("Descarregant dades cadastrals…")
        QgsMessageLog.logMessage('IOF Cadastre: ZIP URL = ' + str(zip_url), 'IOFAssistent', level=Qgis.MessageLevel.Info)

        try:
            os.makedirs(self._wd, exist_ok=True)
            zip_path = os.path.join(self._wd, self._inecode + '_CadastralParcels.zip')

            # Descarrega el ZIP via QNetworkAccessManager (evita problemes de format)
            zip_data = self._download_zip(zip_url)
            if zip_data is None:
                raise ValueError("Error en la descàrrega del fitxer ZIP.")
            with open(zip_path, 'wb') as zf_out:
                zf_out.write(zip_data)

            # Descomprimeix
            self._progress.setValue(85)
            self._status.setText("Descomprimint…")
            QApplication.processEvents()

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(self._wd)
            os.remove(zip_path)

            self._progress.setValue(95)
            self._load_layers()

        except Exception as e:
            self._progress.setValue(0)
            self._status.setText("Error en la descàrrega.")
            self._btn_dl.setEnabled(True)
            QMessageBox.critical(
                self, "Error de descàrrega",
                "No s'ha pogut descarregar el cadastre de " + self._nom_mun + ":\n\n" + str(e)
            )

    # ── Càrrega de capes al projecte ──────────────────────────────────────────
    def _load_layers(self):
        """
        Filtra les capes GML per codi INE (self._inecode),
        desa les features coincidents com a GPKG a la carpeta cadastre/
        i carrega aquestes copies filtrades al projecte.
        """
        self._status.setText("Filtrant i desant capes cadastrals…")
        QApplication.processEvents()

        gml_files = [
            f for f in os.listdir(self._wd)
            if f.lower().endswith('.gml')
        ]
        if not gml_files:
            QMessageBox.warning(
                self, "Sense fitxers GML",
                "No s'han trobat fitxers GML a:\n" + self._wd
            )
            self._status.setText("No s'han trobat fitxers GML.")
            self._btn_dl.setEnabled(True)
            return

        # Crea o obté el grup "Cadastre" > subgrup municipi
        root_tree = QgsProject.instance().layerTreeRoot()
        grp = root_tree.findGroup("Cadastre")
        if grp is None:
            grp = root_tree.insertGroup(0, "Cadastre")
        sub_grp = grp.findGroup(self._nom_mun)
        if sub_grp is None:
            sub_grp = grp.addGroup(self._nom_mun)

        _ORDER = ['cadastralparcel', 'cadastralzoning']

        def _key(fname):
            fl = fname.lower()
            for i, kw in enumerate(_ORDER):
                if kw in fl:
                    return i
            return len(_ORDER)

        loaded = 0
        inecode = self._inecode  # codi INE 5 digits, p.ex. "08081"

        # Nom normalitzat per als fitxers (sense accents ni espais)
        import unicodedata as _uni
        nom_mun_fitxer = _uni.normalize("NFD", self._nom_mun)
        nom_mun_fitxer = "".join(c for c in nom_mun_fitxer
                                 if _uni.category(c) != "Mn")
        nom_mun_fitxer = nom_mun_fitxer.replace(" ", "_").replace("/", "_")

        zoning_layer_carregada = None
        mun_count = self._mun_count
        for gml_file in sorted(gml_files, key=_key):
            gml_path = os.path.join(self._wd, gml_file)
            fl = gml_file.lower()

            if 'cadastralparcel' in fl:
                display = "Parcel·les cadastrals"
                gpkg_name = "CadastralParcel_" + nom_mun_fitxer + ".gpkg"
            elif 'cadastralzoning' in fl:
                display = "Polígons cadastrals"
                gpkg_name = "CadastralZoning_" + nom_mun_fitxer + ".gpkg"
            else:
                continue

            # Carrega el GML, filtra i exporta a GPKG
            gpkg_path = os.path.join(self._wd, gpkg_name)
            if os.path.exists(gpkg_path):
                try:
                    os.remove(gpkg_path)
                except Exception:  # nosec — error no crític, es descarta intencionadament
                    pass

            error = QgsVectorFileWriter.WriterError.ErrCreateDataSource
            msg = ""
            gml_layer = QgsVectorLayer(gml_path, "tmp_gml", "ogr")
            if gml_layer.isValid():
                # Detecta el camp localId
                field_names = [f.name() for f in gml_layer.fields()]
                camp_local_id = next(
                    (c for c in field_names
                     if "localid" in c.lower() or "local_id" in c.lower()),
                    None
                )
                if camp_local_id:
                    expr_inici = '"' + camp_local_id + '" LIKE \'' + inecode + '%\''
                    expr_inspire = '"' + camp_local_id + '" LIKE \'%.' + inecode + '%\''
                    gml_layer.setSubsetString(expr_inici)
                    if gml_layer.featureCount() == 0:
                        gml_layer.setSubsetString(expr_inspire)
                    if gml_layer.featureCount() == 0:
                        gml_layer.setSubsetString("")

                opts = QgsVectorFileWriter.SaveVectorOptions()
                opts.driverName = "GPKG"
                opts.fileEncoding = "UTF-8"
                error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                    gml_layer, gpkg_path,
                    QgsCoordinateTransformContext(), opts
                )
            # Allibera la capa i dona temps a Windows per alliberar el fitxer
            del gml_layer
            import gc as _gc
            _gc.collect()  # força el garbage collector de Python
            from qgis.PyQt.QtWidgets import QApplication as _QA2
            import time as _t2
            _QA2.processEvents()
            _t2.sleep(1.0)  # espera mes llarga per Windows
            _QA2.processEvents()
            _gc.collect()

            if error != QgsVectorFileWriter.WriterError.NoError:
                continue

            # Carrega la copia GPKG al projecte
            layer = QgsVectorLayer(gpkg_path, display, "ogr")
            if not layer.isValid():
                continue

            # Aplica estil segons el tipus de capa
            from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
            if 'cadastralzoning' in fl:
                # Polígons: farciment pastel per municipi + contorn negre fi
                r, g, b = _COLORS_POLIGONS[mun_count % len(_COLORS_POLIGONS)]
                sym = QgsFillSymbol.createSimple({
                    "color": "{},{},{},180".format(r, g, b),
                    "outline_color": "0,0,0",
                    "outline_width": "0.15",
                    "outline_style": "solid",
                })
                layer.setRenderer(QgsSingleSymbolRenderer(sym))
                mun_count += 1
            elif 'cadastralparcel' in fl:
                # Parcel·les: contorn negre molt fi sense farciment
                sym = QgsFillSymbol.createSimple({
                    "color": "0,0,0,0",
                    "outline_color": "0,0,0",
                    "outline_width": "0.15",
                    "outline_style": "solid",
                })
                layer.setRenderer(QgsSingleSymbolRenderer(sym))

            QgsProject.instance().addMapLayer(layer, False)
            sub_grp.addLayer(layer)
            loaded += 1
            # Guarda la capa de zones per crear el municipi despres
            if 'cadastralzoning' in fl:
                zoning_layer_carregada = layer

        self._mun_count = mun_count

        # Crea la capa Municipi Cadastral a partir de la capa de zones
        if loaded > 0 and zoning_layer_carregada is not None:
            self._crear_municipi_cadastral(zoning_layer_carregada, sub_grp)

        # Elimina tots els fitxers de la carpeta que no siguin GPKG
        # (GML, XML, GFS, ZIP i altres auxiliars)
        from qgis.PyQt.QtWidgets import QApplication as _QApp
        import time as _time
        _QApp.processEvents()
        _time.sleep(0.3)
        # Els fitxers GML es netejaran al tancar el dialeg (closeEvent)

        self._progress.setValue(100)
        self._btn_dl.setEnabled(True)

        if loaded:
            self._inecodes_descarregats.add(self._inecode)
            self._btn_dl.setEnabled(False)
            self._status.setText(str(loaded) + " capa(es) carregada(es) correctament.")
            QMessageBox.information(
                self, "Importació completada",
                "S'han carregat " + str(loaded) + " capa(es) de " + self._nom_mun + " al grup 'Cadastre'."
                "\n\nFitxers desats a:\n" + self._wd
            )
        else:
            self._status.setText("Cap capa vàlida carregada.")
            QMessageBox.warning(
                self, "Sense capes vàlides",
                "Els fitxers GML no han generat cap capa vàlida.\n\n"
                "Comprova que el codi de municipi " + inecode + " existeixi al camp localId de les capes descarregades."
            )

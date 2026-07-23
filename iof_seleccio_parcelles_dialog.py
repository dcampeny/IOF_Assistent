# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QSizePolicy, QSpinBox, QGroupBox,
    QFrame, QLineEdit, QWidget, QComboBox
)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QFont, QColor
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsVectorFileWriter,
    QgsFeatureRequest, QgsCoordinateTransformContext
)


def _find_layer(*keywords):
    """Retorna la primera capa que conté algun keyword al nom."""
    for layer in QgsProject.instance().mapLayers().values():
        name = layer.name().lower()
        if any(kw.lower() in name for kw in keywords):
            return layer
    return None


def _find_all_layers(*keywords):
    """Retorna TOTES les capes que contenen algun keyword al nom."""
    result = []
    for layer in QgsProject.instance().mapLayers().values():
        name = layer.name().lower()
        if any(kw.lower() in name for kw in keywords):
            result.append(layer)
    return result


def _get_field_value(feature, *names):
    fields = [f.name().lower() for f in feature.fields()]
    for name in names:
        for fname in fields:
            if name.lower() in fname:
                try:
                    return str(feature[fname] or "").strip()
                except Exception:  # nosec — error no crític, es descarta intencionadament
                    pass
    return ""


def _area_ha(feature):
    try:
        val = _get_field_value(feature, "areavalue", "area")
        if val:
            return float(val) / 10000.0
    except Exception:  # nosec — error no crític, es descarta intencionadament
        pass
    try:
        return feature.geometry().area() / 10000.0
    except Exception:
        return 0.0


def _expr(field, val):
    return '"' + field + '" = \'' + val + "'"


def _poligon_de_parcella(feat_parcel, layer_zoning):
    if not layer_zoning:
        return ""
    # pointOnSurface(), no centroid(): el centroide d'una parcel·la
    # amb forma allargada o còncava pot caure fora de la pròpia
    # parcel·la, fent que no es trobi cap zona coincident.
    punt = feat_parcel.geometry().pointOnSurface()
    req = QgsFeatureRequest().setFilterRect(punt.boundingBox())
    for z in layer_zoning.getFeatures(req):
        if z.geometry().contains(punt):
            return _get_field_value(z, "label", "zoningid")
    return ""


class SeleccioParcellsDial(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self._layer_parcel = None   # capa activa de parcel·les
        self._layer_zoning = None   # capa activa de zones
        self._layers_parcel = []     # totes les capes de parcel·les disponibles
        self._layers_zoning = []     # totes les capes de zones disponibles
        # Diccionari {fid: QgsFeature} de parcel·les acumulades
        self._parcelles = {}
        self._sync_actiu = False  # evita bucles en sincronitzar seleccio
        self._finca_editant_path = None   # path de la finca que s'esta editant
        self._finca_editant_nom = None   # nom de la finca que s'esta editant
        self.setWindowTitle("Seleccionar parcel\u00b7les cadastrals")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(560)
        self.setMinimumHeight(500)
        self.setModal(False)
        self._build_ui()
        QTimer.singleShot(100, self._init_layers)

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        title = QLabel("Seleccionar parcel\u00b7les cadastrals")
        f = QFont()
        f.setBold(True)
        f.setPointSize(10)
        title.setFont(f)
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Selector de municipi (visible si hi ha mes d'un municipi)
        self._grp_municipi = QGroupBox("Municipi")
        ml = QHBoxLayout(self._grp_municipi)
        ml.addWidget(QLabel("Capa de parcel·les:"))
        self._combo_municipi = QComboBox()
        self._combo_municipi.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._combo_municipi.currentIndexChanged.connect(self._on_municipi_changed)
        ml.addWidget(self._combo_municipi)
        self._grp_municipi.setVisible(False)
        layout.addWidget(self._grp_municipi)

        # Editar finca existent
        grp_editar = QGroupBox("Editar finca existent")
        el = QHBoxLayout(grp_editar)
        el.addWidget(QLabel("Finca:"))
        self._combo_finca_existent = QComboBox()
        self._combo_finca_existent.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        el.addWidget(self._combo_finca_existent)
        self._btn_carregar_finca = QPushButton("Carregar")
        self._btn_carregar_finca.setFixedWidth(80)
        self._btn_carregar_finca.clicked.connect(self._carregar_finca_existent)
        el.addWidget(self._btn_carregar_finca)
        layout.addWidget(grp_editar)

        # Via 1: seleccio al mapa
        grp_mapa = QGroupBox("Selecci\u00f3 al mapa")
        ml = QVBoxLayout(grp_mapa)
        lbl = QLabel(
            "Fes clic a una parcel·la del mapa per afegir-la a la llista. "
            "Torna a clicar-la si la vols eliminar."
        )
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #444;")
        ml.addWidget(lbl)
        layout.addWidget(grp_mapa)

        # Via 2: introduccio manual
        grp_manual = QGroupBox("Afegir per polígon i parcel·la")
        ml2 = QVBoxLayout(grp_manual)
        ml2.setSpacing(4)
        # Fila inputs
        row_inputs = QHBoxLayout()
        row_inputs.addWidget(QLabel("Polígon:"))
        self._edit_poligon = QLineEdit()
        self._edit_poligon.setPlaceholderText("p. ex. 1")
        self._edit_poligon.setFixedWidth(80)
        self._edit_poligon.returnPressed.connect(self._afegir_manual)
        row_inputs.addWidget(self._edit_poligon)
        row_inputs.addWidget(QLabel("Parcel·la:"))
        self._edit_parcella = QLineEdit()
        self._edit_parcella.setPlaceholderText("p. ex. 23")
        self._edit_parcella.setFixedWidth(80)
        self._edit_parcella.returnPressed.connect(self._afegir_manual)
        row_inputs.addWidget(self._edit_parcella)
        self._btn_afegir = QPushButton("Afegir")
        self._btn_afegir.setFixedWidth(70)
        self._btn_afegir.clicked.connect(self._afegir_manual)
        row_inputs.addWidget(self._btn_afegir)
        row_inputs.addStretch()
        ml2.addLayout(row_inputs)
        lbl_x = QLabel("Podeu eliminar una parcel·la de la llista prement la \"X\".")
        lbl_x.setStyleSheet("color: #444;")
        lbl_x.setWordWrap(True)
        ml2.addWidget(lbl_x)
        self._lbl_manual_status = QLabel("")
        self._lbl_manual_status = QLabel("")
        self._lbl_manual_status.setStyleSheet("color: #c00;")
        self._lbl_manual_status.setVisible(False)  # amaga quan buit
        ml2.addWidget(self._lbl_manual_status)
        layout.addWidget(grp_manual)
        grp_taula = QGroupBox("Parcel\u00b7les seleccionades")
        tl = QVBoxLayout(grp_taula)
        self._taula = QTableWidget(0, 5)
        self._taula = QTableWidget(0, 6)
        self._taula.setHorizontalHeaderLabels([
            "Referència cadastral", "Municipi", "Polígon",
            "Parcel·la", "Superfície (ha)", ""
        ])
        self._taula.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._taula.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._taula.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._taula.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._taula.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._taula.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._taula.setColumnWidth(5, 30)
        self._taula.setAlternatingRowColors(True)
        self._taula.setMinimumHeight(150)
        tl.addWidget(self._taula)
        tot_layout = QHBoxLayout()
        layout.addWidget(grp_taula)
        tot_layout = QHBoxLayout()
        tot_layout.addStretch()
        self._lbl_total = QLabel("Superfície total: — ha")
        f2 = QFont()
        f2.setBold(True)
        self._lbl_total.setFont(f2)
        tot_layout.addWidget(self._lbl_total)
        layout.addLayout(tot_layout)

        # Desar com a finca
        grp_finca = QGroupBox("Desar com a finca")
        fl = QGridLayout(grp_finca)
        fl.addWidget(QLabel("Número de finca:"), 0, 0)
        self._spin_finca = QSpinBox()
        self._spin_finca.setMinimum(1)
        self._spin_finca.setMaximum(99)
        self._spin_finca.setValue(1)
        self._spin_finca.setFixedWidth(70)
        fl.addWidget(self._spin_finca, 0, 1)
        self._lbl_nom_finca = QLabel("→  finca1.gpkg")
        self._lbl_nom_finca.setStyleSheet("color: #555;")
        fl.addWidget(self._lbl_nom_finca, 0, 2)
        self._spin_finca.valueChanged.connect(
            lambda v: self._lbl_nom_finca.setText(
                "→  finca" + str(v) + ".gpkg"
            )
        )
        fl.addWidget(QLabel("Nom de la finca:"), 1, 0)
        self._edit_nom_finca = QLineEdit()
        self._edit_nom_finca.setPlaceholderText("p. ex. Can Casals")
        fl.addWidget(self._edit_nom_finca, 1, 1, 1, 2)
        fl.setColumnStretch(2, 1)
        layout.addWidget(grp_finca)
        layout.addWidget(grp_finca)

        # Botons
        btn_layout = QHBoxLayout()
        self._btn_netejar = QPushButton("Netejar tot")
        self._btn_netejar.clicked.connect(self._netejar_tot)
        btn_layout.addWidget(self._btn_netejar)
        btn_layout.addStretch()
        self._btn_desar = QPushButton("Desar finca")
        self._btn_desar.setEnabled(False)
        self._btn_desar.setStyleSheet(
            "QPushButton { background-color: #2e7d32; color: white; "
            "padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self._btn_desar.clicked.connect(self._desar_finca)
        btn_layout.addWidget(self._btn_desar)
        btn_tancar = QPushButton("Tancar")

        self._btn_eliminar_finca = QPushButton("Eliminar finca")
        self._btn_eliminar_finca.setEnabled(False)
        self._btn_eliminar_finca.setStyleSheet(
            "QPushButton { background-color: #c62828; color: white; "
            "padding: 4px 12px; border-radius: 3px; }"
            "QPushButton:disabled { background-color: #aaa; }"
        )
        self._btn_eliminar_finca.clicked.connect(self._eliminar_finca_activa)
        btn_layout.addWidget(self._btn_eliminar_finca)
        btn_tancar.clicked.connect(self.close)
        btn_layout.addWidget(btn_tancar)
        layout.addLayout(btn_layout)

    # ── Inicialitzacio ────────────────────────────────────────────────────────
    def _init_layers(self):
        # Detecta TOTES les capes de parcel·les i zones (una per municipi)
        self._layers_parcel = _find_all_layers(
            "cadastralparcel", "parcel·les cadastrals", "parcelas catastrales"
        )
        self._layers_zoning = _find_all_layers(
            "cadastralzoning", "polígons cadastrals", "poligons cadastrals"
        )
        if not self._layers_parcel:
            QMessageBox.warning(
                self, "Capa no trobada",
                "No s'ha trobat cap capa de parcel·les cadastrals al projecte.\n"
                "Primer importa el cadastre des del botó 'Importar cadastre'."
            )
            self.close()
            return

        # Ordena les capes per nom de municipi (ordre alfabètic) PRIMER
        import unicodedata as _ud_sort

        def _nom_mun_key(lyr):
            src = os.path.basename(lyr.source().split("|")[0])
            nom = (src.replace("CadastralParcel_", "")
                      .replace("CadastralZoning_", "")
                      .replace(".gpkg", "")
                      .replace("_", " "))
            nom = _ud_sort.normalize("NFD", nom.lower())
            return "".join(c for c in nom if _ud_sort.category(c) != "Mn")
        self._layers_parcel = sorted(self._layers_parcel, key=_nom_mun_key)
        self._layers_zoning = sorted(self._layers_zoning, key=_nom_mun_key)

        # Si hi ha mes d'un municipi, mostra el selector (ja ordenat)
        if len(self._layers_parcel) > 1:
            self._grp_municipi.setVisible(True)
            self._combo_municipi.blockSignals(True)
            self._combo_municipi.clear()
            for i, lyr in enumerate(self._layers_parcel):
                src_parc = lyr.source().split("|")[0]
                nom_fitxer = os.path.basename(src_parc)
                nom_mun = nom_fitxer.replace("CadastralParcel_", "").replace(".gpkg", "").replace("_", " ")
                if not nom_mun:
                    root = QgsProject.instance().layerTreeRoot()
                    node = root.findLayer(lyr.id())
                    if node and node.parent():
                        grp = node.parent().name()
                        if grp and grp.lower() not in ("cadastre", ""):
                            nom_mun = grp
                if not nom_mun:
                    nom_mun = "Municipi " + str(i + 1)
                self._combo_municipi.addItem(nom_mun, lyr.id())
            self._combo_municipi.blockSignals(False)

        # Connecta el senyal selectionChanged de TOTES les capes (no nomes l'activa)
        for lyr in self._layers_parcel:
            lyr.selectionChanged.connect(self._on_seleccio_canviada)

        # Activa la primera capa per defecte (sense reconnectar senyals)
        self._layer_parcel = self._layers_parcel[0]
        self._layer_zoning = self._layers_zoning[0] if self._layers_zoning else None
        self.iface.setActiveLayer(self._layer_parcel)
        # Activa l'eina de seleccio per rectangle de QGIS
        self.iface.actionSelectRectangle().trigger()

        self._actualitzar_combo_finques()
        self._suggerir_num_finca()

        # Detecta canvis de capa activa per permetre seleccio en qualsevol municipi
        self.iface.currentLayerChanged.connect(self._on_capa_activa_canviada)

    def _activar_capa_parcel(self, layer_parcel):
        """
        Canvia la capa de parcel·les activa per a la seleccio.
        NO desconnecta/connecta senyals: tots es connecten a _init_layers
        i es mantenen actius fins al tancament.
        """
        self._layer_parcel = layer_parcel

        # Busca la capa de zones del mateix municipi pel nom del fitxer GPKG
        # CadastralParcel_Fogars_De_La_Selva.gpkg <-> CadastralZoning_Fogars_De_La_Selva.gpkg
        src_parc = layer_parcel.source().split("|")[0]
        nom_parc = os.path.basename(src_parc).replace("CadastralParcel_", "").replace(".gpkg", "")
        self._layer_zoning = next(
            (lz for lz in self._layers_zoning
             if nom_parc in os.path.basename(lz.source().split("|")[0])),
            self._layers_zoning[0] if self._layers_zoning else None
        )

        self.iface.setActiveLayer(self._layer_parcel)
        self._sincronitzar_seleccio_qgis()

    def _on_municipi_changed(self, idx):
        """Canvia la capa activa de parcel·les al municipi seleccionat."""
        if idx < 0:
            return
        # Usa el layer_id desat al combo com a userData
        layer_id = self._combo_municipi.itemData(idx)
        if not layer_id:
            return
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer and layer in self._layers_parcel:
            self._activar_capa_parcel(layer)

    def _on_capa_activa_canviada(self, layer):
        """
        Quan l'usuari canvia la capa activa al panell de capes,
        comprova si es una capa de parcel·les i l'activa com a capa de treball.
        Aixo permet seleccionar parcel·les de qualsevol municipi sense usar el selector.
        """
        if not layer:
            return
        for i, lyr in enumerate(self._layers_parcel):
            if lyr.id() == layer.id() and lyr.id() != self._layer_parcel.id():
                # L'usuari ha activat una capa de parcel·les diferent
                self._activar_capa_parcel(lyr)
                # Actualitza el combo de municipi si es visible
                if self._grp_municipi.isVisible():
                    self._combo_municipi.blockSignals(True)
                    self._combo_municipi.setCurrentIndex(i)
                    self._combo_municipi.blockSignals(False)
                break

    # ── Finques existents ─────────────────────────────────────────────────────

    def _actualitzar_combo_finques(self):
        """
        Omple el desplegable amb les finques gpkg al disc (font de veritat).
        Llegeix el camp nom_finca de cada gpkg per mostrar el nom complet.
        """
        self._combo_finca_existent.blockSignals(True)
        self._combo_finca_existent.clear()
        self._combo_finca_existent.addItem("— Selecciona una finca per editar —", None)
        proj_path = QgsProject.instance().absolutePath()
        if proj_path:
            finca_dir = os.path.join(proj_path, "cadastre")
            if os.path.isdir(finca_dir):
                num = 1
                while True:
                    fp = os.path.join(finca_dir, "finca" + str(num) + ".gpkg")
                    if not os.path.exists(fp):
                        break
                    # Llegeix el nom de la finca del gpkg
                    nom_finca = ""
                    try:
                        from osgeo import ogr as _ogr
                        _ds = _ogr.Open(fp, 0)
                        if _ds:
                            _lyr = _ds.GetLayer(0)
                            if _lyr:
                                _feat = _lyr.GetNextFeature()
                                if _feat:
                                    _idx = _lyr.GetLayerDefn().GetFieldIndex("nom_finca")
                                    if _idx >= 0:
                                        v = _feat.GetField(_idx)
                                        if v:
                                            nom_finca = str(v).strip()
                            _ds = None
                    except Exception:  # nosec — error no crític, es descarta intencionadament
                        pass
                    label = "Finca " + str(num)
                    if nom_finca:
                        label += " - " + nom_finca
                    self._combo_finca_existent.addItem(label, fp)
                    num += 1
        self._combo_finca_existent.blockSignals(False)
        self._btn_carregar_finca.setEnabled(
            self._combo_finca_existent.count() > 1
        )

    def _carregar_finca_existent(self):
        """Carrega les parcel·les d'una finca gpkg existent al visualitzador."""
        finca_path = self._combo_finca_existent.currentData()
        if not finca_path or not os.path.exists(finca_path):
            return

        if self._parcelles:
            resp = QMessageBox.question(
                self, "Substituir selecció actual",
                "El visualitzador ja conté parcel·les seleccionades.\n"
                "Vols substituir-les per les de la finca seleccionada?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )
            if resp == QMessageBox.StandardButton.No:
                return

        if not self._layer_parcel:
            return

        # Elimina l'àmbit IOF abans d'editar la finca
        # (la capa àmbit no està bloquejada en aquest moment)
        proj_path = QgsProject.instance().absolutePath()
        if proj_path:
            self._eliminar_ambit_existent(os.path.join(proj_path, "cadastre"))

        # Si hi havia una finca anterior en edicio, la recarrega abans de canviar
        from qgis.PyQt.QtWidgets import QApplication
        import time
        if self._finca_editant_path and self._finca_editant_path != finca_path:
            self._recarregar_finca_editant()

        # Elimina la capa del projecte ABANS de llegir el fitxer
        # per alliberar qualsevol bloqueig (solucio definitiva a Windows)
        finca_path_norm = os.path.normcase(os.path.normpath(os.path.abspath(finca_path)))
        for lid, layer in list(QgsProject.instance().mapLayers().items()):
            src = layer.source().split("|")[0]
            src_norm = os.path.normcase(os.path.normpath(os.path.abspath(src)))
            if src_norm == finca_path_norm:
                QgsProject.instance().removeMapLayer(lid)
        QApplication.processEvents()
        time.sleep(0.3)
        QApplication.processEvents()

        # Buida la seleccio de la finca anterior
        self._parcelles.clear()
        self._actualitzar_taula()

        # Guarda la info de la finca per recarregar-la al tancar si cal
        self._finca_editant_path = finca_path
        self._finca_editant_nom = self._combo_finca_existent.currentText()

        # Llegeix les referencies cadastrals directament amb ogr
        # sense crear cap QgsVectorLayer (evita bloqueig del fitxer a Windows)
        refs = []
        try:
            from osgeo import ogr
            ds = ogr.Open(finca_path, 0)  # 0 = read-only
            if ds is None:
                raise IOError("No s'ha pogut obrir: " + finca_path)
            lyr = ds.GetLayer(0)
            for feat in lyr:
                for field_name in [
                    "nationalCadastralReference", "refcat", "localId", "localid"
                ]:
                    val = feat.GetField(field_name)
                    if val:
                        refs.append(str(val).strip())
                        break
            ds = None  # tanca i allibera immediatament
        except Exception as e:
            QMessageBox.warning(
                self, "Error",
                "No s'ha pogut llegir el fitxer:\n" + finca_path + "\n" + str(e)
            )
            return

        # Per cada referencia, busca la parcel·la a CadastralParcel
        self._parcelles.clear()
        no_trobades = []

        for ref in refs:
            expr = _expr("nationalCadastralReference", ref)
            trobat = False
            # Cerca a TOTES les capes de parcel·les (un per municipi)
            for lyr in self._layers_parcel:
                for parcel_feat in lyr.getFeatures(
                    QgsFeatureRequest().setFilterExpression(expr)
                ):
                    self._parcelles[(lyr.id(), parcel_feat.id())] = (lyr, parcel_feat)
                    trobat = True
                    break
                if trobat:
                    break
            if not trobat:
                no_trobades.append(ref)

        # Sincronitza la seleccio (els senyals ja estan connectats a totes les capes)
        self._sincronitzar_seleccio_qgis()

        self._actualitzar_taula()

        # Actualitza el numero de finca al spinner llegint del nom del fitxer gpkg
        # (font de veritat: el disc, no el nom de la capa)
        nom_fitxer = os.path.basename(finca_path)  # "finca3.gpkg"
        try:
            num_disc = int(nom_fitxer.replace("finca", "").replace(".gpkg", ""))
            self._spin_finca.setValue(num_disc)
        except (ValueError, AttributeError):
            # Fallback: extreu del text del combo
            nom_combo = self._combo_finca_existent.currentText()
            try:
                self._spin_finca.setValue(int(nom_combo.split()[1]))
            except (ValueError, IndexError):
                pass

        # Recupera el nom de la finca del GPKG (primer registre, camp nom_finca)
        nom_finca_recuperat = ""
        try:
            from osgeo import ogr
            ds = ogr.Open(finca_path, 0)
            if ds:
                lyr_ogr = ds.GetLayer(0)
                if lyr_ogr:
                    feat_ogr = lyr_ogr.GetNextFeature()
                    if feat_ogr:
                        idx_nf = lyr_ogr.GetLayerDefn().GetFieldIndex("nom_finca")
                        if idx_nf >= 0:
                            val = feat_ogr.GetField(idx_nf)
                            if val:
                                nom_finca_recuperat = str(val).strip()
                ds = None
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        self._edit_nom_finca.setText(nom_finca_recuperat)

        if no_trobades:
            QMessageBox.warning(
                self, "Parcel·les no trobades",
                str(len(no_trobades)) + " parcel·la(es) de la finca no s'han "
                "pogut localitzar a la capa de cadastre actual:\n" + "\n".join(no_trobades[:5]) + ("\n..." if len(no_trobades) > 5 else "")
            )

    # ── Seleccio al mapa → acumulacio automatica ──────────────────────────────
    def _on_seleccio_canviada(self, selected_ids=None, deselected_ids=None, cleared=False):
        """
        Gestiona els canvis de seleccio al mapa.

        QGIS envia:
        - selected_ids: fids que s'acaben de seleccionar
        - deselected_ids: fids que s'acaben de desseleccionar (pot incloure
          fids que nosaltres haviem posat via _sincronitzar, no compte com a toggle)
        - cleared: True quan QGIS ha fet reset total de la seleccio

        Logica:
        - Nomes els fids de selected_ids son accions de l'usuari -> afegir
        - Un fid de deselected_ids es toggle NOMES si estava a _parcelles
          I l'usuari ha clicat explicitament sobre ell (detected via selected_ids buit)
        """
        if self._sync_actiu:
            return
        if not self._layer_parcel:
            return

        layer_id = self._layer_parcel.id()
        sel_ids = set(selected_ids) if selected_ids else set()
        set(deselected_ids) if deselected_ids else set()

        # Cas 1: l'usuari ha clicat una parcel·la nova (sel_ids no buit)
        if sel_ids:
            req = QgsFeatureRequest().setFilterFids(list(sel_ids))
            for feat in self._layer_parcel.getFeatures(req):
                key = (layer_id, feat.id())
                if key in self._parcelles:
                    # Ja estava -> toggle: elimina
                    self._parcelles.pop(key)
                else:
                    # Nova -> afegeix
                    self._parcelles[key] = (self._layer_parcel, feat)

        # Cas 2: QGIS ha desseleccionat fids que NO provenen de _sincronitzar
        # (sel_ids buit + desel_ids no buit = l'usuari ha fet Escape o clear)
        # En aquest cas NO fem res: mantenim _parcelles intacte
        # perque _sincronitzar restaurara la seleccio visual

        # Restaura la seleccio acumulada
        self._sincronitzar_seleccio_qgis()
        self._actualitzar_taula()

    # ── Afegir manual ─────────────────────────────────────────────────────────
    def _afegir_manual(self):
        self._lbl_manual_status.setText("")
        self._lbl_manual_status.setVisible(False)
        pol_txt = self._edit_poligon.text().strip()
        parc_txt = self._edit_parcella.text().strip()

        if not pol_txt or not parc_txt:
            self._lbl_manual_status.setText(
                "Introdueix el pol\u00edgon i la parcel\u00b7la."
            )
            self._lbl_manual_status.setVisible(True)
            return

        if not self._layer_parcel or not self._layer_zoning:
            self._lbl_manual_status.setText(
                "Calen les capes CadastralParcel i CadastralZoning."
            )
            self._lbl_manual_status.setVisible(True)
            return

        # Pas 1: Troba la geometria del poligon per label (prova variants)
        pol_geom = None
        for variant in [pol_txt, pol_txt.zfill(2), pol_txt.zfill(3)]:
            for feat in self._layer_zoning.getFeatures(
                QgsFeatureRequest().setFilterExpression(_expr("label", variant))
            ):
                pol_geom = feat.geometry()
                break
            if pol_geom is not None:
                break

        if pol_geom is None:
            self._lbl_manual_status.setText(
                "No s'ha trobat el pol\u00edgon " + pol_txt + "."
            )
            self._lbl_manual_status.setVisible(True)
            return

        # Pas 2: Cerca parcelles per label dins bbox del poligon + confirmacio espacial
        candidats = []
        variants_parc = list(dict.fromkeys([
            parc_txt, parc_txt.zfill(2), parc_txt.zfill(3),
            parc_txt.zfill(4), parc_txt.zfill(5)
        ]))
        for variant in variants_parc:
            req = QgsFeatureRequest().setFilterExpression(_expr("label", variant))
            req.setFilterRect(pol_geom.boundingBox())
            for feat in self._layer_parcel.getFeatures(req):
                if pol_geom.contains(feat.geometry().pointOnSurface()):
                    candidats.append(feat)
            if candidats:
                break

        if not candidats:
            self._lbl_manual_status.setText(
                "No s'ha trobat la parcel\u00b7la " + parc_txt + " dins el pol\u00edgon " + pol_txt + "."
            )
            self._lbl_manual_status.setVisible(True)
            return
        # Comprova si la parcel·la ja pertany a una finca desada
        # Usa ogr directament per evitar crear QgsVectorLayer que alteri la llegenda
        proj_path_check = QgsProject.instance().absolutePath()
        if proj_path_check:
            try:
                from osgeo import ogr as _ogr
                import os as _os
                _finca_dir = _os.path.join(proj_path_check, "cadastre")
                _refs = set(_get_field_value(f, "nationalCadastralReference", "localId") for f in candidats)
                _num = 1
                _finca_trobada = 0
                while True:
                    _fp = _os.path.join(_finca_dir, "finca" + str(_num) + ".gpkg")
                    if not _os.path.exists(_fp):
                        break
                    _ds = _ogr.Open(_fp, 0)
                    if _ds:
                        _lyr = _ds.GetLayer(0)
                        if _lyr:
                            for _ff in _lyr:
                                # Busca la referencia cadastral
                                _lyrdef = _lyr.GetLayerDefn()
                                for _camp in ["nationalCadastralReference", "localId", "localid"]:
                                    _idx = _lyrdef.GetFieldIndex(_camp)
                                    if _idx >= 0:
                                        _ref = str(_ff.GetField(_idx) or "").strip()
                                        if _ref in _refs:
                                            _finca_trobada = _num
                                        break
                                if _finca_trobada:
                                    break
                        _ds = None
                    if _finca_trobada:
                        break
                    _num += 1
                    self._lbl_manual_status.setText(
                        "La parcel·la " + parc_txt + " del polígon " + pol_txt + " ja és a la Finca " + str(_finca_trobada) + "."
                    )
                    self._lbl_manual_status.setVisible(True)
                    return
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass

        # Afegeix a la llista interna amb format (layer_id, fid) -> (layer, feat)
        ja_existien = True
        for feat in candidats:
            key = (self._layer_parcel.id(), feat.id())
            if key not in self._parcelles:
                self._parcelles[key] = (self._layer_parcel, feat)
                ja_existien = False

        if ja_existien:
            self._lbl_manual_status.setText(
                "La parcel\u00b7la " + parc_txt + " del pol\u00edgon " + pol_txt + " ja estava afegida."
            )
            self._lbl_manual_status.setVisible(True)
            return

        self._lbl_manual_status.setText("")
        self._lbl_manual_status.setVisible(False)
        self._edit_poligon.clear()
        self._edit_parcella.clear()
        self._edit_poligon.setFocus()

        # Sincronitza la seleccio visual de QGIS amb tota la llista acumulada
        self._sincronitzar_seleccio_qgis()

        # Zoom a la parcel·la afegida
        extent = candidats[0].geometry().boundingBox()
        extent.grow(50)
        self.iface.mapCanvas().setExtent(extent)
        self.iface.mapCanvas().refresh()

        self._actualitzar_taula()

    # ── Actualitzacio de la taula ─────────────────────────────────────────────
    def _actualitzar_taula(self):
        self._taula.setRowCount(0)
        total_ha = 0.0
        for key, (lyr, feat) in list(self._parcelles.items()):
            ref = _get_field_value(
                feat, "nationalcadastralreference", "refcat", "localid"
            )
            parc = _get_field_value(feat, "label")
            # Busca la capa de zones del mateix municipi pel nom del fitxer GPKG
            # CadastralParcel_Fogars_De_La_Selva.gpkg <-> CadastralZoning_Fogars_De_La_Selva.gpkg
            src_parc_key = os.path.basename(lyr.source().split("|")[0])
            nom_mun_key = src_parc_key.replace("CadastralParcel_", "").replace(".gpkg", "")
            zoning_lyr = next(
                (lz for lz in self._layers_zoning
                 if nom_mun_key in os.path.basename(lz.source().split("|")[0])),
                self._layer_zoning
            )
            pol = _poligon_de_parcella(feat, zoning_lyr)
            ha = _area_ha(feat)
            total_ha += ha

            # Format ha: 2 decimals, separador milers=. i decimals=,
            def _fmt_ha(v):
                s = "{:,.2f}".format(v)       # "1,234.56" (format anglosaxó)
                s = s.replace(",", "X").replace(".", ",").replace("X", ".")
                return s                       # "1.234,56"

            row = self._taula.rowCount()
            # Nom del municipi per mostrar
            src_pk = os.path.basename(lyr.source().split("|")[0])
            mun_display = src_pk.replace("CadastralParcel_", "").replace(".gpkg", "").replace("_", " ")

            row = self._taula.rowCount()
            self._taula.insertRow(row)
            self._taula.setItem(row, 0, QTableWidgetItem(ref))
            self._taula.setItem(row, 1, QTableWidgetItem(mun_display))
            item_pol = QTableWidgetItem(pol)
            item_pol.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._taula.setItem(row, 2, item_pol)
            item_parc = QTableWidgetItem(parc)
            item_parc.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._taula.setItem(row, 3, item_parc)
            item_ha = QTableWidgetItem(_fmt_ha(ha))
            item_ha.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._taula.setItem(row, 4, item_ha)

            # Boto eliminar per fila
            btn = QPushButton("\u2715")
            btn.setFixedSize(24, 24)
            btn.setStyleSheet(
                "QPushButton { color: #c00; border: none; font-weight: bold; }"
                "QPushButton:hover { color: #900; }"
            )
            btn.setToolTip("Eliminar aquesta parcel\u00b7la")
            btn.clicked.connect(lambda checked, k=key: self._eliminar_parcella(k))
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.addWidget(btn)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.setContentsMargins(2, 0, 2, 0)
            self._taula.setCellWidget(row, 5, cell)
        if self._parcelles:
            s = "{:,.2f}".format(total_ha)
            s = s.replace(",", "X").replace(".", ",").replace("X", ".")
            self._lbl_total.setText("Superfície total: " + s + " ha")
        else:
            self._lbl_total.setText("Superfície total: — ha")

        # El boto Desar esta actiu si:
        # - hi ha parcel·les seleccionades (cas normal), O
        # - estem editant una finca existent i hem buidat totes les parcel·les
        #   (per permetre eliminar la finca desant-la buida)
        pot_desar = bool(self._parcelles)
        self._btn_desar.setEnabled(pot_desar)
        # Eliminar finca: actiu quan hi ha una finca carregada per editar
        pot_eliminar = bool(self._finca_editant_path)
        self._btn_eliminar_finca.setEnabled(pot_eliminar)

    def _obtenir_nom_municipi(self):
        """
        Extreu el nom del municipi llegint el camp 'municipi' de totes les
        capes 'Municipi cadastral' carregades al projecte, en ordre alfabètic.
        """
        municipis = []
        for lyr in QgsProject.instance().mapLayers().values():
            if "municipi cadastral" in lyr.name().lower():
                idx_m = lyr.fields().lookupField("municipi")
                if idx_m >= 0:
                    for feat in lyr.getFeatures():
                        val = str(feat[idx_m] or "").strip()
                        if val and val not in municipis:
                            municipis.append(val)
                        break
        municipis.sort()
        return ", ".join(municipis) if municipis else ""

    def _afegir_camps_finca(self, gpkg_path, num_finca, nom_finca, nom_municipi):
        """
        Obre el GPKG de la finca, buidar els camps existents i omple:
        - codi_finca: num_finca
        - nom_finca: nom_finca
        - municipi: nom_municipi
        - poligon: label de CadastralZoning
        - parcella: label de CadastralParcel
        Crea els camps si no existeixen.
        """
        from qgis.PyQt.QtCore import QVariant
        from qgis.core import QgsField, QgsFeatureRequest

        if not os.path.exists(gpkg_path):
            return

        lyr = QgsVectorLayer(gpkg_path, "finca_tmp", "ogr")
        if not lyr.isValid():
            return

        prov = lyr.dataProvider()
        camps_actuals = [f.name().lower() for f in lyr.fields()]

        # Defineix els camps en l'ordre correcte: nom_finca, municipi, poligon, parcella, superficie
        camps_nous = []
        for nom_camp, tipus in [
            ("nom_finca", QVariant.String),
            ("municipi", QVariant.String),
            ("poligon", QVariant.String),
            ("parcella", QVariant.String),
            ("superficie", QVariant.Double),
        ]:
            if nom_camp not in camps_actuals:
                if tipus == QVariant.Double:
                    camps_nous.append(QgsField(nom_camp, tipus, "double", 10, 2))
                else:
                    camps_nous.append(QgsField(nom_camp, tipus, "string", 200, 0))

        if camps_nous:
            lyr.startEditing()
            prov.addAttributes(camps_nous)
            lyr.updateFields()
            lyr.commitChanges()

        # Nota: els índexos de camp per a l'escriptura real es calculen
        # més avall (variable _fi), directament amb ogr en brut, no aquí
        # — es va deixar de fer amb l'API de QGIS pel mateix motiu del
        # "del lyr" més avall (alliberar la capa abans que ogr hi escrigui).

        # Construeix mapa de zones per lz: associa cada parcel·la a la seva zona
        # Les claus son els layer_id de les capes de parcel·les originals
        # Fem un mapa directe: (layer_id de parcel·les) -> capa de zones corresponent
        parcel_to_zoning = {}
        for lp in self._layers_parcel:
            src_p = os.path.basename(lp.source().split("|")[0])
            nom_p = src_p.replace("CadastralParcel_", "").replace(".gpkg", "")
            for lz in self._layers_zoning:
                src_z = os.path.basename(lz.source().split("|")[0])
                nom_z = src_z.replace("CadastralZoning_", "").replace(".gpkg", "")
                if nom_p == nom_z:
                    parcel_to_zoning[lp.id()] = lz
                    break

        # Mapa layer_id -> nom municipi llegit de la capa municipi cadastral
        parcel_to_mun = {}
        for lp in self._layers_parcel:
            src_p = os.path.basename(lp.source().split("|")[0])
            nom_p = src_p.replace("CadastralParcel_", "").replace(".gpkg", "")
            mun_trobat = nom_p.replace("_", " ")
            for lm in QgsProject.instance().mapLayers().values():
                if "municipi cadastral" in lm.name().lower():
                    src_lm = os.path.basename(lm.source().split("|")[0])
                    import unicodedata as _ud3
                    k_p = _ud3.normalize("NFD", nom_p)
                    k_p = "".join(c for c in k_p if _ud3.category(c) != "Mn")
                    if k_p.lower() in src_lm.lower():
                        idx_mv2 = lm.fields().lookupField("municipi")
                        if idx_mv2 >= 0:
                            for fm2 in lm.getFeatures():
                                v2 = str(fm2[idx_mv2] or "").strip()
                                if v2:
                                    mun_trobat = v2
                                break
                        break
            parcel_to_mun[lp.id()] = mun_trobat

        # Prepara els valors per cada feature
        # Cal saber a quina capa de parcel·les pertany cada feature del GPKG
        # Ho deduïm de la referència cadastral: els 5 primers digits son el codi INE
        # i les capes de parcel·les s'anomenen CadastralParcel_<NomMunicipi>.gpkg
        # que conté parcel·les del codi INE corresponent
        # Fem un mapa codi_INE -> (layer_id, lz_feat, mun_val)
        ine_to_info = {}
        for lp in self._layers_parcel:
            lz = parcel_to_zoning.get(lp.id())
            mun = parcel_to_mun.get(lp.id(), "")
            # Extreu el codi INE de la primera feature de la capa
            for fp in lp.getFeatures():
                ref_p = _get_field_value(fp, "nationalcadastralreference", "localid", "refcat")
                if ref_p and len(ref_p) >= 5:
                    ine_to_info[ref_p[:5]] = (lp.id(), lz, mun)
                break

        rows_data = []
        for feat in lyr.getFeatures():
            parc_val = _get_field_value(feat, "label")
            ref_val = _get_field_value(feat, "nationalcadastralreference", "localid", "refcat")
            codi_ine_f = ref_val[:5] if ref_val and len(ref_val) >= 5 else ""
            info = ine_to_info.get(codi_ine_f)
            if info:
                _, lz_feat, mun_val = info
            else:
                lz_feat = next(iter(parcel_to_zoning.values()), None)
                mun_val = nom_municipi
            pol_val = ""
            if lz_feat:
                punt = feat.geometry().pointOnSurface()
                req = QgsFeatureRequest().setFilterRect(punt.boundingBox())
                for z in lz_feat.getFeatures(req):
                    if z.geometry().contains(punt):
                        pol_val = _get_field_value(z, "label", "zoningid")
                        break
            area_ha = round(feat.geometry().area() / 10000.0, 2) if feat.geometry() else 0.0
            rows_data.append((feat.id(), nom_finca, mun_val, pol_val, parc_val, area_ha))
        del lyr

        # Escriu els valors directament amb ogr
        try:
            from osgeo import ogr as _ogr_w
            _ds_w = _ogr_w.Open(gpkg_path, 1)
            if _ds_w:
                _lyr_w = _ds_w.GetLayer(0)
                if _lyr_w:
                    _ldef = _lyr_w.GetLayerDefn()
                    _fi = {n: _ldef.GetFieldIndex(n)
                           for n in ["nom_finca", "municipi", "poligon", "parcella", "superficie"]}
                    _lyr_w.StartTransaction()
                    for fid, _nom, _mun, _pol, _parc, _sup in rows_data:
                        _f = _lyr_w.GetFeature(fid)
                        if _f:
                            if _fi["nom_finca"] >= 0:
                                _f.SetField(_fi["nom_finca"], _nom)
                            if _fi["municipi"] >= 0:
                                _f.SetField(_fi["municipi"], _mun)
                            if _fi["poligon"] >= 0:
                                _f.SetField(_fi["poligon"], _pol)
                            if _fi["parcella"] >= 0:
                                _f.SetField(_fi["parcella"], _parc)
                            if _fi["superficie"] >= 0:
                                _f.SetField(_fi["superficie"], float(_sup))
                            _lyr_w.SetFeature(_f)
                    _lyr_w.CommitTransaction()
                _ds_w = None
        except Exception as e_ogr:
            from qgis.core import QgsMessageLog, Qgis
            QgsMessageLog.logMessage(
                "IOF _afegir_camps_finca ogr: " + str(e_ogr),
                "IOFAssistent", level=Qgis.MessageLevel.Warning
            )

    def _afegir_camps_pol_parc(self, gpkg_path):
        """
        Obre el GPKG de la finca i afegeix/omple els camps 'poligon' i 'parcella'
        a partir de les capes CadastralZoning i CadastralParcel.
        - parcella: camp 'label' de CadastralParcel (ja existeix a la feature)
        - poligon:  camp 'label' de la zona (CadastralZoning) que conte la parcella
        """
        from qgis.PyQt.QtCore import QVariant
        from qgis.core import QgsField

        if not os.path.exists(gpkg_path):
            return

        lyr = QgsVectorLayer(gpkg_path, "finca_tmp", "ogr")
        if not lyr.isValid():
            return

        # Afegeix camps si no existeixen
        prov = lyr.dataProvider()
        camps_actuals = [f.name().lower() for f in lyr.fields()]
        nous_camps = []
        if "poligon" not in camps_actuals:
            nous_camps.append(QgsField("poligon", QVariant.String, len=10))
        if "parcella" not in camps_actuals:
            nous_camps.append(QgsField("parcella", QVariant.String, len=10))
        if nous_camps:
            prov.addAttributes(nous_camps)
            lyr.updateFields()

        idx_pol = lyr.fields().lookupField("poligon")
        idx_parc = lyr.fields().lookupField("parcella")
        if idx_pol < 0 and idx_parc < 0:
            del lyr
            return

        # Per cada feature, busca el label de parcel·la i de polígon
        attr_map = {}
        for feat in lyr.getFeatures():
            # Parcel·la: camp 'label' ja a la feature
            parc_val = _get_field_value(feat, "label")

            # Polígon: intersecció espacial amb CadastralZoning
            # Busca la zona correcta per municipi (per un punt garantit
            # dins la parcel·la, no el centroide)
            pol_val = ""
            punt = feat.geometry().pointOnSurface()
            for lz in self._layers_zoning:
                req = QgsFeatureRequest().setFilterRect(punt.boundingBox())
                for z in lz.getFeatures(req):
                    if z.geometry().contains(punt):
                        pol_val = _get_field_value(z, "label", "zoningid")
                        break
                if pol_val:
                    break

            vals = {}
            if idx_pol >= 0:
                vals[idx_pol] = pol_val
            if idx_parc >= 0:
                vals[idx_parc] = parc_val
            attr_map[feat.id()] = vals

        lyr.startEditing()
        prov.changeAttributeValues(attr_map)
        lyr.commitChanges()
        del lyr

    def _eliminar_parcella(self, key):
        """Elimina una parcella del visualitzador per (layer_id, fid)."""
        self._parcelles.pop(key, None)
        self._sincronitzar_seleccio_qgis()
        self._actualitzar_taula()

    def _netejar_tot(self):
        self._parcelles.clear()
        if self._layer_parcel:
            self._layer_parcel.removeSelection()
        self._actualitzar_taula()

    def _sincronitzar_seleccio_qgis(self):
        """
        Manté la seleccio blava de QGIS sincronitzada amb la llista interna,
        a TOTES les capes de parcel·les (un per municipi).
        """
        self._sync_actiu = True
        try:
            for lyr in self._layers_parcel:
                lid = lyr.id()
                fids_capa = [
                    fid for (lid2, fid) in self._parcelles
                    if lid2 == lid
                ]
                lyr.selectByIds(fids_capa)
        finally:
            self._sync_actiu = False

    def _feat_es_de_capa(self, fid, layer):
        """Comprova si un fid pertany a una capa concreta."""
        req = QgsFeatureRequest(fid)
        for _ in layer.getFeatures(req):
            return True
        return False

    # ── Inserir capa finca en ordre ───────────────────────────────────────────
    def _inserir_finca_en_ordre(self, grp, finca_layer, num_finca):
        """
        Insereix la capa de finca al grup mantenint l'ordre correlatiu:
        Finca 1, Finca 2, Finca 3... (les mes baixes primer, mes altes despres).
        """
        # Troba la posicio correcta: despres de totes les finques amb num menor
        pos = 0
        for i, child in enumerate(grp.children()):
            if hasattr(child, 'layer') and child.layer():
                nom = child.layer().name()
                if nom.lower().startswith("finca "):
                    try:
                        # "Finca 3 - Can Casals" -> parts[1] = "3"
                        n = int(nom.split()[1])
                        if n < num_finca:
                            pos = i + 1
                    except (ValueError, IndexError):
                        pass
        grp.insertLayer(pos, finca_layer)

    # ── Num finca ─────────────────────────────────────────────────────────────
    def _suggerir_num_finca(self):
        """
        Suggereix el primer numero de finca lliure.
        Usa les capes del projecte com a font de veritat (no el disc),
        per evitar que fitxers orfes pendents d'esborrar influin el comptador.
        """
        # Recull els numeros de finca que ja existeixen al projecte
        nums_existents = set()
        for layer in QgsProject.instance().mapLayers().values():
            nom = layer.name()
            parts = nom.split()
            if nom.lower().startswith("finca ") and len(parts) >= 2:
                try:
                    nums_existents.add(int(parts[1]))
                except ValueError:
                    pass
        # Primer numero lliure consecutiu
        num = 1
        while num in nums_existents:
            num += 1
        self._spin_finca.setValue(num)
        self._lbl_nom_finca.setText("→  finca" + str(num) + ".gpkg")

    # ── Desar finca ───────────────────────────────────────────────────────────
    def _desar_finca(self):
        from .iof_utils import ensure_project_saved
        proj_path = ensure_project_saved(self)
        if not proj_path:
            return

        num_finca = self._spin_finca.value()
        finca_dir = os.path.join(proj_path, "cadastre")
        os.makedirs(finca_dir, exist_ok=True)
        finca_path = os.path.join(finca_dir, "finca" + str(num_finca) + ".gpkg")

        # Guarda les parelles (layer, fid) ABANS de qualsevol operacio
        fids_a_exportar = list(self._parcelles.keys())

        # Si no hi ha parcel·les, avis i sortida
        if not fids_a_exportar:
            QMessageBox.warning(
                self, "Llista buida",
                "No hi ha parcel·les seleccionades.\n\n"
                "Selecciona parcel·les abans de desar la finca.\n"
                "Si vols eliminar la finca, usa el botó \"Eliminar finca\"."
            )
            return

        # Elimina del projecte qualsevol capa que apunti al fitxer destí
        # Desconnecta currentLayerChanged per evitar que carregar la nova capa
        # finca canvii self._layer_parcel incorrectament
        try:
            self.iface.currentLayerChanged.disconnect(self._on_capa_activa_canviada)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        from qgis.PyQt.QtWidgets import QApplication
        import time

        # Exporta parcel·les de TOTES les capes (multi-municipi)
        import tempfile
        import processing as _proc

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".gpkg", dir=finca_dir)
        os.close(tmp_fd)
        os.remove(tmp_path)

        self._sync_actiu = True
        tmp_parts = []
        for lyr in self._layers_parcel:
            lid = lyr.id()
            fids_capa = [fid for (lid2, fid) in fids_a_exportar if lid2 == lid]
            if not fids_capa:
                continue
            lyr.selectByIds(fids_capa)
            tmp_fd2, tmp_path2 = tempfile.mkstemp(suffix=".gpkg", dir=finca_dir)
            os.close(tmp_fd2)
            os.remove(tmp_path2)
            opts2 = QgsVectorFileWriter.SaveVectorOptions()
            opts2.driverName = "GPKG"
            opts2.fileEncoding = "UTF-8"
            opts2.onlySelectedFeatures = True
            err2, msg2, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
                lyr, tmp_path2, QgsCoordinateTransformContext(), opts2
            )
            lyr.removeSelection()
            if err2 == QgsVectorFileWriter.WriterError.NoError:
                tmp_parts.append(tmp_path2)

        # Guarda el nom de finca abans de netejar la UI
        nom_finca_text = self._edit_nom_finca.text().strip()
        nom_municipi = self._obtenir_nom_municipi()

        # Neteja seleccions i restaura
        self._sync_actiu = False
        # Neteja totes les seleccions visuals
        for lyr in self._layers_parcel:
            lyr.removeSelection()

        # Fusiona tots els fitxers parcials en un de sol
        if len(tmp_parts) == 1:
            os.rename(tmp_parts[0], tmp_path)
            error, msg = QgsVectorFileWriter.WriterError.NoError, ""
        elif len(tmp_parts) > 1:
            lyrs_tmp = [QgsVectorLayer(p, "p_" + str(i), "ogr")
                        for i, p in enumerate(tmp_parts)]
            res_m = _proc.run(
                "native:mergevectorlayers",
                {"LAYERS": lyrs_tmp, "CRS": None, "OUTPUT": tmp_path}
            )
            for p in tmp_parts:
                try:
                    os.remove(p)
                except Exception:  # nosec — error no crític, es descarta intencionadament
                    pass
            error = (QgsVectorFileWriter.WriterError.NoError
                     if res_m and os.path.exists(tmp_path)
                     else QgsVectorFileWriter.WriterError.ErrCreateDataSource)
            msg = "" if error == QgsVectorFileWriter.WriterError.NoError else "Error en fusionar"
        else:
            error, msg = QgsVectorFileWriter.WriterError.ErrCreateDataSource, "Cap parcel·la exportada"

        if error == QgsVectorFileWriter.WriterError.NoError:
            # Substitueix el fitxer original pel temporal
            try:
                # Intenta esborrar l'original (amb reintents per Windows)
                esborrat = False
                for intent in range(10):
                    try:
                        if os.path.exists(finca_path):
                            os.remove(finca_path)
                            for ext in ["-wal", "-shm", ".gpkg-journal"]:
                                aux = finca_path + ext
                                if os.path.exists(aux):
                                    os.remove(aux)
                        esborrat = True
                        break
                    except OSError:
                        # Força la neteja del cache de connexions GDAL
                        try:
                            from osgeo import gdal
                            gdal.GetDriverByName("GPKG")
                        except Exception:  # nosec — error no crític, es descarta intencionadament
                            pass
                        QApplication.processEvents()
                        time.sleep(0.3)
                if not esborrat:
                    # No s'ha pogut esborrar l'original despres de 10 intents
                    os.remove(tmp_path)
                    QMessageBox.critical(
                        self, "Error en desar",
                        "El fitxer 'finca" + str(num_finca) + ".gpkg' est\u00e0 "
                        "bloquejat per QGIS.\n\nTanca la capa 'Finca " + str(num_finca) + "' del panell de capes i torna a desar."
                    )
                    return
                # Reanomena el temporal al nom definitiu
                os.rename(tmp_path, finca_path)
            except Exception as e:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:  # nosec — error no crític, es descarta intencionadament
                        pass
                QMessageBox.critical(
                    self, "Error en desar",
                    "No s'ha pogut substituir el fitxer:\n" + str(e)
                )
                return

        if error != QgsVectorFileWriter.WriterError.NoError:
            QMessageBox.critical(
                self, "Error en desar",
                "No s'ha pogut desar la finca:\n" + msg
            )
            return

        # Afegeix/omple camps nom_finca, poligon, parcella al fitxer final
        self._afegir_camps_finca(finca_path, num_finca, nom_finca_text, nom_municipi)

        # Carrega la nova capa al grup "Cadastre"
        layer_name = "Finca " + str(num_finca)
        if nom_finca_text:
            layer_name = layer_name + " - " + nom_finca_text
        finca_layer = QgsVectorLayer(finca_path, layer_name, "ogr")
        if finca_layer.isValid():
            sym = finca_layer.renderer().symbol()
            sym.setColor(QColor(200, 0, 0, 0))
            sym.symbolLayer(0).setStrokeColor(QColor(200, 0, 0))
            sym.symbolLayer(0).setStrokeWidth(0.8)
            root = QgsProject.instance().layerTreeRoot()
            grp = root.findGroup("Cadastre")
            if grp is None:
                grp = root.insertGroup(0, "Cadastre")
            QgsProject.instance().addMapLayer(finca_layer, False)
            self._inserir_finca_en_ordre(grp, finca_layer, num_finca)

        # Reconnecta currentLayerChanged
        self.iface.currentLayerChanged.connect(self._on_capa_activa_canviada)

        # Neteja el visualitzador i la seleccio de totes les capes
        self._parcelles.clear()
        self._sync_actiu = True
        for lyr in self._layers_parcel:
            lyr.removeSelection()
        self._sync_actiu = False
        self._actualitzar_taula()
        self._actualitzar_combo_finques()
        self._suggerir_num_finca()
        # Buida el camp nom de finca per a la seguent
        self._edit_nom_finca.clear()
        self._finca_editant_path = None
        # Restaura la capa de parcel·les activa
        if self._layer_parcel and self._layer_parcel in self._layers_parcel:
            self.iface.setActiveLayer(self._layer_parcel)

        # Neteja fitxers temporals de la carpeta cadastre
        from .iof_utils import netejar_carpeta_cadastre
        netejar_carpeta_cadastre(finca_dir)

        # Elimina l'àmbit IOF existent (cal regenerar-lo amb les finques noves)
        ambit_eliminat = self._eliminar_ambit_existent(finca_dir)
        ambit_existeix = os.path.exists(os.path.join(finca_dir, "ambitIOF.gpkg"))

        missatge = (
            "La finca " + str(num_finca) + " s'ha desat correctament.\n\n"
            "Fitxer: " + finca_path + "\n"
            "Capa '" + layer_name + "' afegida al grup 'Cadastre'."
        )
        if ambit_eliminat:
            missatge += (
                "\n\nL'àmbit IOF s'ha eliminat. "
                "Torna a generar-lo des de 'Crear àmbit IOF'."
            )
        elif ambit_existeix:
            missatge += (
                "\n\nAvís: no s'ha pogut eliminar l'àmbit IOF existent. "
                "Elimina manualment la capa 'Àmbit IOF' del panell de capes "
                "i després regenera l'àmbit."
            )
        QMessageBox.information(self, "Finca desada", missatge)

    def _recarregar_finca_editant(self):
        """Recarrega la finca que estava en edicio al projecte."""
        if not self._finca_editant_path or not os.path.exists(self._finca_editant_path):
            return
        path_norm = os.path.normcase(os.path.normpath(os.path.abspath(self._finca_editant_path)))
        # Comprova si ja esta carregada
        for layer in QgsProject.instance().mapLayers().values():
            src_norm = os.path.normcase(os.path.normpath(os.path.abspath(
                layer.source().split("|")[0]
            )))
            if src_norm == path_norm:
                return  # ja esta carregada
        # Carrega la capa amb estil vermell
        nom = self._finca_editant_nom or os.path.splitext(
            os.path.basename(self._finca_editant_path))[0]
        finca_layer = QgsVectorLayer(self._finca_editant_path, nom, "ogr")
        if finca_layer.isValid():
            from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
            sym = QgsFillSymbol.createSimple({
                "color": "0,0,0,0",
                "outline_color": "#cc0000",
                "outline_width": "0.8",
                "outline_style": "solid",
            })
            finca_layer.setRenderer(QgsSingleSymbolRenderer(sym))
            root = QgsProject.instance().layerTreeRoot()
            grp = root.findGroup("Cadastre")
            if grp is None:
                grp = root.insertGroup(0, "Cadastre")
            QgsProject.instance().addMapLayer(finca_layer, False)
            try:
                nf = int(nom.split()[1])
            except (ValueError, IndexError):
                nf = 999
            self._inserir_finca_en_ordre(grp, finca_layer, nf)

    def _eliminar_finca_activa(self):
        """Elimina la finca que esta carregada per editar."""
        if not self._finca_editant_path:
            return
        from .iof_utils import ensure_project_saved
        proj_path = ensure_project_saved(self)
        if not proj_path:
            return

        # Extreu num_finca del nom del fitxer
        nom_fitxer = os.path.basename(self._finca_editant_path)
        try:
            num_finca = int(nom_fitxer.replace("finca", "").replace(".gpkg", ""))
        except ValueError:
            return

        resp = QMessageBox.question(
            self, "Eliminar finca",
            "Segur que vols eliminar la Finca " + str(num_finca) + "?\n\n"
            "Aquesta accio no es pot desfer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if resp == QMessageBox.StandardButton.No:
            return

        self._eliminar_finca(self._finca_editant_path, num_finca, proj_path)

    def _eliminar_finca(self, finca_path, num_finca, proj_path):
        """Elimina la capa i el fitxer d'una finca sense parcel·les."""
        from qgis.PyQt.QtWidgets import QApplication
        import time
        # Elimina la capa del projecte
        path_norm = os.path.normcase(os.path.normpath(os.path.abspath(finca_path)))
        for lid, layer in list(QgsProject.instance().mapLayers().items()):
            src = layer.source().split("|")[0]
            if os.path.normcase(os.path.normpath(os.path.abspath(src))) == path_norm:
                QgsProject.instance().removeMapLayer(lid)
        QApplication.processEvents()
        time.sleep(0.3)
        QApplication.processEvents()
        # Esborra el fitxer
        for intent in range(10):
            try:
                if os.path.exists(finca_path):
                    os.remove(finca_path)
                    for ext in ["-wal", "-shm", ".gpkg-journal"]:
                        aux = finca_path + ext
                        if os.path.exists(aux):
                            os.remove(aux)
                break
            except OSError:
                QApplication.processEvents()
                time.sleep(0.3)
        # Reordena les finques superiors (finca N+1 -> finca N, etc.)
        from qgis.PyQt.QtWidgets import QApplication
        finca_dir = os.path.join(proj_path, "cadastre")
        n = num_finca + 1
        while True:
            fp_actual = os.path.join(finca_dir, "finca" + str(n) + ".gpkg")
            if not os.path.exists(fp_actual):
                break
            fp_nou = os.path.join(finca_dir, "finca" + str(n - 1) + ".gpkg")

            nou_num = str(n - 1)

            # Pas 1: busca la capa per nom (finca N) i guarda info, despres elimina
            nom_finca_part = ""
            grp_name = "Cadastre"
            pos = 0
            renderer_clone = None
            for lid, layer in list(QgsProject.instance().mapLayers().items()):
                lnom = layer.name()
                parts_nom = lnom.split()
                if lnom.lower().startswith("finca ") and len(parts_nom) >= 2 and parts_nom[1] == str(n):
                    parts = lnom.split(" - ", 1)
                    nom_finca_part = parts[1] if len(parts) > 1 else ""
                    # Clona el renderer per reutilitzar-lo
                    if layer.renderer():
                        renderer_clone = layer.renderer().clone()
                    root = QgsProject.instance().layerTreeRoot()
                    node = root.findLayer(lid)
                    if node and node.parent():
                        grp_name = node.parent().name()
                        children = list(node.parent().children())
                        pos = children.index(node)
                    QgsProject.instance().removeMapLayer(lid)
                    QApplication.processEvents()
                    time.sleep(0.5)
                    QApplication.processEvents()
                    break

            # Pas 2: copia el fitxer al nou nom (evita bloqueig Windows)
            # i marca l'original per esborrar despres
            import shutil
            if os.path.exists(fp_actual):
                try:
                    shutil.copy2(fp_actual, fp_nou)
                except Exception:  # nosec — error no crític, es descarta intencionadament
                    pass

            # Pas 2b: intenta esborrar l'original; si falla, registra per esborrar despres
            if os.path.exists(fp_actual) and os.path.exists(fp_nou):
                try:
                    os.remove(fp_actual)
                except OSError:
                    if not hasattr(self, '_fitxers_a_esborrar'):
                        self._fitxers_a_esborrar = []
                    self._fitxers_a_esborrar.append(fp_actual)

            # Pas 3: carrega la nova capa
            if os.path.exists(fp_nou):
                nou_nom = "Finca " + nou_num + (" - " + nom_finca_part if nom_finca_part else "")
                nova_layer = QgsVectorLayer(fp_nou, nou_nom, "ogr")
                if nova_layer.isValid():
                    # Reutilitza el renderer de la capa original
                    if renderer_clone:
                        nova_layer.setRenderer(renderer_clone)
                    else:
                        from .iof_estil_cadastre import _llegir_colors_finca
                        colors = _llegir_colors_finca()
                        nf = int(nou_num)
                        idx_c = nf if nf in colors else ((nf - 1) % len(colors)) + 1 if colors else 1
                        r, g, b = colors.get(idx_c, (220, 220, 180))
                        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
                        sym = QgsFillSymbol.createSimple({
                            "color": "{},{},{},180".format(r, g, b),
                            "outline_style": "no", "outline_width": "0",
                        })
                        nova_layer.setRenderer(QgsSingleSymbolRenderer(sym))
                    QgsProject.instance().addMapLayer(nova_layer, False)
                    root = QgsProject.instance().layerTreeRoot()
                    grp = root.findGroup(grp_name) or root.findGroup("Cadastre")
                    if grp:
                        grp.insertLayer(pos, nova_layer)
                    else:
                        root.addLayer(nova_layer)
            n += 1

        # Neteja el visualitzador
        # Elimina els fitxers originals que han quedat bloquejats
        for fp_pendent in getattr(self, '_fitxers_a_esborrar', []):
            for _ in range(5):
                try:
                    if os.path.exists(fp_pendent):
                        os.remove(fp_pendent)
                    break
                except OSError:
                    pass
        self._fitxers_a_esborrar = []

        self._finca_editant_path = None
        self._parcelles.clear()
        self._edit_nom_finca.clear()
        self._actualitzar_taula()
        self._actualitzar_combo_finques()
        self._suggerir_num_finca()
        # Elimina l'ambit IOF
        self._eliminar_ambit_existent(finca_dir)
        QMessageBox.information(
            self, "Finca eliminada",
            "La finca " + str(num_finca) + " s'ha eliminat correctament." + ("\n\nLes finques superiors s'han reordenat." if n > num_finca + 1 else "")
        )

    def _eliminar_ambit_existent(self, finca_dir):
        """Elimina ambitIOF.gpkg (fitxer i capa) perquè cal regenerar-lo."""
        ambit_path = os.path.join(finca_dir, "ambitIOF.gpkg")
        if not os.path.exists(ambit_path):
            return False
        from qgis.PyQt.QtWidgets import QApplication
        import time
        # Elimina la capa del projecte
        ambit_norm = os.path.normcase(os.path.normpath(os.path.abspath(ambit_path)))
        for lid, layer in list(QgsProject.instance().mapLayers().items()):
            src = layer.source().split("|")[0]
            src_norm = os.path.normcase(os.path.normpath(os.path.abspath(src)))
            if src_norm == ambit_norm:
                QgsProject.instance().removeMapLayer(lid)
        QApplication.processEvents()
        time.sleep(0.3)
        QApplication.processEvents()
        # Esborra el fitxer
        for intent in range(10):
            try:
                os.remove(ambit_path)
                for ext in ["-wal", "-shm", ".gpkg-journal"]:
                    aux = ambit_path + ext
                    if os.path.exists(aux):
                        os.remove(aux)
                return True
            except OSError:
                QApplication.processEvents()
                time.sleep(0.3)
        return False

    # ── Tancament ─────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        # Elimina del projecte les capes que apunten als fitxers pendents d'esborrar
        # (necessari per alliberar el bloqueig Windows abans d'esborrar)
        import time as _t_close
        for fp_pendent in getattr(self, '_fitxers_a_esborrar', []):
            if not fp_pendent:
                continue
            path_norm = os.path.normcase(os.path.normpath(os.path.abspath(fp_pendent)))
            for lid, layer in list(QgsProject.instance().mapLayers().items()):
                src = os.path.normcase(os.path.normpath(os.path.abspath(
                    layer.source().split("|")[0]
                )))
                if src == path_norm:
                    QgsProject.instance().removeMapLayer(lid)
            from qgis.PyQt.QtWidgets import QApplication as _QAc
            _QAc.processEvents()
            _t_close.sleep(0.3)
            # Ara intenta esborrar
            for _ in range(5):
                try:
                    if os.path.exists(fp_pendent):
                        os.remove(fp_pendent)
                    break
                except OSError:
                    _QAc.processEvents()
                    _t_close.sleep(0.3)
        self._fitxers_a_esborrar = []

        # Elimina GPKGs de finca orfes (sense capa al projecte)
        proj_path = QgsProject.instance().absolutePath()
        if proj_path:
            finca_dir = os.path.join(proj_path, "cadastre")
            if os.path.isdir(finca_dir):
                # Obte els paths de totes les capes de finca al projecte
                paths_projecte = set()
                for layer in QgsProject.instance().mapLayers().values():
                    nom = layer.name().lower()
                    if nom.startswith("finca "):
                        src = os.path.normcase(os.path.normpath(os.path.abspath(
                            layer.source().split("|")[0]
                        )))
                        paths_projecte.add(src)
                # Esborra els GPKGs de finca que no estan al projecte
                import re as _re_close
                for f in os.listdir(finca_dir):
                    if _re_close.match(r'^finca\d+\.gpkg$', f):
                        fp = os.path.join(finca_dir, f)
                        fp_norm = os.path.normcase(os.path.normpath(os.path.abspath(fp)))
                        if fp_norm not in paths_projecte:
                            try:
                                os.remove(fp)
                            except OSError:
                                pass

        # Desconnecta el detector de canvi de capa activa
        try:
            self.iface.currentLayerChanged.disconnect(self._on_capa_activa_canviada)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass

        # Desconnecta TOTES les capes i neteja seleccions
        self._sync_actiu = True
        for lyr in self._layers_parcel:
            try:
                lyr.selectionChanged.disconnect(self._on_seleccio_canviada)
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass
            lyr.removeSelection()
            lyr.setSubsetString("")
        self._sync_actiu = False

        # Si hi havia una finca en edicio, la recarrega al projecte
        if self._finca_editant_path and os.path.exists(self._finca_editant_path):
            # Comprova si ja esta carregada (per si s'ha desat)
            path_norm = os.path.normcase(os.path.normpath(
                os.path.abspath(self._finca_editant_path)
            ))
            ja_carregada = any(
                os.path.normcase(os.path.normpath(os.path.abspath(
                    lyr.source().split("|")[0]
                ))) == path_norm
                for lyr in QgsProject.instance().mapLayers().values()
            )
            if not ja_carregada:
                nom = self._finca_editant_nom or os.path.splitext(
                    os.path.basename(self._finca_editant_path))[0]
                finca_layer = QgsVectorLayer(
                    self._finca_editant_path, nom, "ogr"
                )
                if finca_layer.isValid():
                    # Aplica l'estil: contorn vermell gruixut sense farciment
                    from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
                    sym = QgsFillSymbol.createSimple({
                        "color": "0,0,0,0",
                        "outline_color": "#cc0000",
                        "outline_width": "0.8",
                        "outline_style": "solid",
                    })
                    finca_layer.setRenderer(QgsSingleSymbolRenderer(sym))
                    root = QgsProject.instance().layerTreeRoot()
                    grp = root.findGroup("Cadastre")
                    if grp is None:
                        grp = root.insertGroup(0, "Cadastre")
                    QgsProject.instance().addMapLayer(finca_layer, False)
                    # Extreu el numero de finca del nom per inserir en ordre
                    try:
                        # "Finca 3 - Can Casals" -> parts[1] = "3"
                        nf = int(nom.split()[1])
                    except (ValueError, IndexError):
                        nf = 999
                    self._inserir_finca_en_ordre(grp, finca_layer, nf)

        super().closeEvent(event)

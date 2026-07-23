# -*- coding: utf-8 -*-
"""
IOF Assistent — Digitalitzar límits de la capa IOF_Finques.

Tres opcions:
  A) Carregar l'Ambit IOF existent (ambitIOF.gpkg) directament.
  B) Importar un fitxer vectorial existent (SHP, GPKG, GeoJSON, etc.)
     i copiar-ne els polígons a IOF_Finques.
  C) Activar el mode edició de IOF_Finques perquè l'usuari digitalitzi
     manualment amb les eines natives de QGIS.
"""

import os
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QMessageBox
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsWkbTypes,
    QgsCoordinateTransform, QgsMessageLog, Qgis
)

LAYER_FINQUES = "IOF_Finques"

VECTOR_FILTER = (
    "Fitxers vectorials (*.shp *.gpkg *.geojson *.json *.kml *.tab *.gml);;"
    "Shapefile (*.shp);;"
    "GeoPackage (*.gpkg);;"
    "GeoJSON (*.geojson *.json);;"
    "Tots els fitxers (*.*)"
)


def _log(msg):
    QgsMessageLog.logMessage(str(msg), "IOF Assistent", Qgis.MessageLevel.Info)


def _get_finques_layer():
    for lyr in QgsProject.instance().mapLayers().values():
        if (isinstance(lyr, QgsVectorLayer) and lyr.name() == LAYER_FINQUES and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
            return lyr
    return None


class LimitsDialog(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self._layer_finques = None
        self._form_config_backup = None
        self._label_backup = None
        self._editing_active = False   # True quan l'usuari és en mode edició manual
        # True si _check_layer() no ha trobat la capa: qui crea el
        # diàleg (iof_exporter.py) ha de comprovar-ho i no cridar
        # .show() en aquest cas.
        self._cancelled = False

        self.setWindowTitle("IOF Assistent — Digitalitzar límits")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setModal(False)
        self.setMinimumWidth(440)

        self._build_ui()
        self._check_layer()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Títol
        lbl_title = QLabel(
            "<b>Digitalitzar límits de la capa IOF_Finques</b>"
        )
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet(
            "padding:8px; background:#e3f2fd; border-radius:4px; font-weight:bold;"
        )
        layout.addWidget(lbl_title)

        lbl_desc = QLabel("Tria com vols introduir els límits de les finques:")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color:#555; padding:2px 4px;")
        layout.addWidget(lbl_desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#ddd;")
        layout.addWidget(sep)

        # ---- Opció A — Carregar àmbit IOF ----
        self._grp_a = QFrame()
        self._grp_a.setStyleSheet(
            "QFrame { border:1px solid #ffe082; border-radius:6px; "
            "background:#fffde7; padding:4px; }"
        )
        layout_a = QVBoxLayout(self._grp_a)
        layout_a.setSpacing(6)

        lbl_a_title = QLabel("<b>A) Carregar l\'\u00e0mbit de l\'IOF</b>")
        lbl_a_desc = QLabel(
            "Copia la geometria de l\'\u00e0mbit de l\'IOF (ambitIOF.gpkg) "
            "directament a la capa IOF_Finques. "
            "\u00c9s la manera m\u00e9s r\u00e0pida si l\'\u00e0mbit ja est\u00e0 generat."
        )
        lbl_a_desc.setWordWrap(True)
        lbl_a_desc.setStyleSheet("color:#444; font-size:12px;")

        self._btn_ambit = QPushButton("Carregar \u00e0mbit IOF \u2192 IOF_Finques")
        self._btn_ambit.setStyleSheet(
            "background:#f9a825; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_ambit.clicked.connect(self._on_carregar_ambit)

        layout_a.addWidget(lbl_a_title)
        layout_a.addWidget(lbl_a_desc)
        layout_a.addWidget(self._btn_ambit)
        layout.addWidget(self._grp_a)

        sep_ab = QFrame()
        sep_ab.setFrameShape(QFrame.Shape.HLine)
        sep_ab.setStyleSheet("color:#ddd;")
        layout.addWidget(sep_ab)
        self._sep_ab = sep_ab

        # ---- Opció B — Importar fitxer ----
        self._grp_b = QFrame()
        self._grp_b.setStyleSheet(
            "QFrame { border:1px solid #bbdefb; border-radius:6px; "
            "background:#f5faff; padding:4px; }"
        )
        layout_b = QVBoxLayout(self._grp_b)
        layout_b.setSpacing(6)

        lbl_b_title = QLabel("<b>B) Importar des d\'un fitxer existent</b>")
        lbl_b_desc = QLabel(
            "Obre un fitxer SHP, GPKG, GeoJSON o similar i copia els seus "
            "pol\u00edgons a la capa IOF_Finques. La reprojecci\u00f3 es fa "
            "autom\u00e0ticament si cal."
        )
        lbl_b_desc.setWordWrap(True)
        lbl_b_desc.setStyleSheet("color:#444; font-size:12px;")

        self._btn_import = QPushButton("Seleccionar fitxer i importar\u2026")
        self._btn_import.setStyleSheet(
            "background:#1565c0; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_import.clicked.connect(self._on_import)

        layout_b.addWidget(lbl_b_title)
        layout_b.addWidget(lbl_b_desc)
        layout_b.addWidget(self._btn_import)
        layout.addWidget(self._grp_b)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#ddd;")
        layout.addWidget(sep2)
        self._sep2 = sep2

        # ---- Opció C — Mode edició manual ----
        self._grp_c = QFrame()
        self._grp_c.setStyleSheet(
            "QFrame { border:1px solid #c8e6c9; border-radius:6px; "
            "background:#f5fff5; padding:4px; }"
        )
        layout_c = QVBoxLayout(self._grp_c)
        layout_c.setSpacing(6)

        lbl_c_title = QLabel("<b>C) Digitalitzar manualment</b>")
        lbl_c_desc = QLabel(
            "Activa el mode edici\u00f3 de la capa IOF_Finques i usa les eines "
            "natives de QGIS per dibuixar els pol\u00edgons de finca."
        )
        lbl_c_desc.setWordWrap(True)
        lbl_c_desc.setStyleSheet("color:#444; font-size:12px;")

        self._btn_edit = QPushButton("Activar mode edici\u00f3")
        self._btn_edit.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_edit.clicked.connect(self._on_edit)

        layout_c.addWidget(lbl_c_title)
        layout_c.addWidget(lbl_c_desc)
        layout_c.addWidget(self._btn_edit)
        layout.addWidget(self._grp_c)

        # ---- Zona d'edició activa (oculta inicialment) ----
        self._grp_editing = QFrame()
        self._grp_editing.setStyleSheet(
            "QFrame { border:2px solid #f9a825; border-radius:6px; "
            "background:#fffde7; padding:6px; }"
        )
        layout_ed = QVBoxLayout(self._grp_editing)
        layout_ed.setSpacing(8)

        lbl_ed = QLabel(
            "<b>✏ Mode edició actiu</b><br>"
            "Dibuixa nous polígons al mapa amb les eines de QGIS "
            "(«Afegir element»).<br>"
            "També pots seleccionar-ne un i eliminar-lo (tecla Supr, o "
            "«Eliminar elements seleccionats»).<br>"
            "Quan acabis, desa o descarta els canvis:"
        )
        lbl_ed.setWordWrap(True)
        lbl_ed.setStyleSheet("color:#5d4037;")
        layout_ed.addWidget(lbl_ed)

        btn_row = QHBoxLayout()
        self._btn_save_edit = QPushButton("Desar i tancar edició")
        self._btn_save_edit.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_save_edit.clicked.connect(self._on_save_edit)

        self._btn_discard_edit = QPushButton("Descartar canvis")
        self._btn_discard_edit.setStyleSheet(
            "background:#b71c1c; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_discard_edit.clicked.connect(self._on_discard_edit)

        btn_row.addWidget(self._btn_save_edit)
        btn_row.addWidget(self._btn_discard_edit)
        layout_ed.addLayout(btn_row)
        layout.addWidget(self._grp_editing)
        self._grp_editing.hide()

        # ---- Estat ----
        self._lbl_status = QLabel()
        self._lbl_status.setWordWrap(True)
        self._lbl_status.setStyleSheet(
            "padding:6px; color:#333; font-style:italic;"
        )
        self._lbl_status.hide()
        layout.addWidget(self._lbl_status)

        # ---- Botó tancar ----
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet("color:#ddd;")
        layout.addWidget(sep3)

        btn_close = QPushButton("Tancar")
        btn_close.setStyleSheet("padding:6px;")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    # ------------------------------------------------------------------
    # Verificació capa
    # ------------------------------------------------------------------

    def _check_layer(self):
        self._layer_finques = _get_finques_layer()
        if self._layer_finques is None:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(self, LAYER_FINQUES)
            self._cancelled = True

    # ------------------------------------------------------------------
    # Opcio A: carregar ambit IOF
    # ------------------------------------------------------------------

    def _crear_capa_finques(self, proj_path):
        """Crea la capa IOF_Finques si no existeix al projecte."""
        from qgis.core import (
            QgsVectorLayer, QgsFields, QgsField,
            QgsVectorFileWriter, QgsCoordinateTransformContext,
            QgsCoordinateReferenceSystem
        )
        from qgis.PyQt.QtCore import QVariant

        # Intenta agafar el CRS del ambitIOF
        ambit_path = os.path.join(proj_path, "cadastre", "ambitIOF.gpkg")
        ambit_tmp = QgsVectorLayer(ambit_path, "tmp", "ogr")
        crs = ambit_tmp.crs() if ambit_tmp.isValid() else QgsCoordinateReferenceSystem("EPSG:25831")

        # Crea capa de memoria amb els camps d'IOF_Finques
        fields = QgsFields()
        fields.append(QgsField("codi_finca", QVariant.Int, "int", 10, 0))
        fields.append(QgsField("nom_finca", QVariant.String, "string", 200, 0))
        fields.append(QgsField("municipi", QVariant.String, "string", 150, 0))
        fields.append(QgsField("comarca", QVariant.String, "string", 100, 0))
        fields.append(QgsField("superficie", QVariant.Double, "double", 10, 2))

        mem = QgsVectorLayer(
            "MultiPolygon?crs=" + crs.authid(), "IOF_Finques", "memory"
        )
        mem.dataProvider().addAttributes(fields.toList())
        mem.updateFields()

        # Desa com a GPKG al directori del projecte
        gpkg_path = os.path.join(proj_path, "IOF_Finques.gpkg")
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.fileEncoding = "UTF-8"
        opts.layerName = "IOF_Finques"
        error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
            mem, gpkg_path, QgsCoordinateTransformContext(), opts
        )
        if error != QgsVectorFileWriter.WriterError.NoError:
            return None

        # Carrega al projecte
        layer = QgsVectorLayer(gpkg_path + "|layername=IOF_Finques",
                               "IOF_Finques", "ogr")
        if not layer.isValid():
            return None

        QgsProject.instance().addMapLayer(layer)
        self._btn_ambit.setEnabled(True)
        self._btn_import.setEnabled(True)
        self._btn_edit.setEnabled(True)
        return layer

    def _on_carregar_ambit(self):
        """Copia la geometria de ambitIOF.gpkg a la capa IOF_Finques."""
        proj_path = QgsProject.instance().absolutePath()
        if not proj_path:
            from .iof_utils import ensure_project_saved
            proj_path = ensure_project_saved(self)
            if not proj_path:
                return

        ambit_path = os.path.join(proj_path, "cadastre", "ambitIOF.gpkg")
        if not os.path.exists(ambit_path):
            QMessageBox.warning(
                self, "\u00c0mbit IOF no trobat",
                "No s'ha trobat el fitxer ambitIOF.gpkg.\n\n"
                "Primer genera l'\u00e0mbit de l'IOF des del men\u00fa Cadastre."
            )
            return

        # Si IOF_Finques no existeix, la creem
        lf = self._layer_finques
        if lf is None:
            lf = self._crear_capa_finques(proj_path)
            if lf is None:
                QMessageBox.critical(
                    self, "Error",
                    "No s'ha pogut crear la capa IOF_Finques."
                )
                return
            self._layer_finques = lf

        if lf.featureCount() > 0:
            resp = QMessageBox.question(
                self, "Capa no buida",
                "La capa IOF_Finques ja cont\u00e9 pol\u00edgons.\n\n"
                "Vols substituir-los per l'\u00e0mbit de l'IOF?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )
            if resp == QMessageBox.StandardButton.No:
                return

        # Llegeix cada fincaN.gpkg i crea una feature per finca
        finca_dir = os.path.join(proj_path, "cadastre")

        prov = lf.dataProvider()
        dst_crs = lf.crs()

        # Elimina existents
        if lf.featureCount() > 0:
            fids = [f.id() for f in lf.getFeatures()]
            prov.deleteFeatures(fids)

        new_feats = []
        num = 1
        while True:
            fp = os.path.join(finca_dir, "finca" + str(num) + ".gpkg")
            if not os.path.exists(fp):
                break

            finca_lyr = QgsVectorLayer(fp, "f_tmp", "ogr")
            if not finca_lyr.isValid():
                num += 1
                continue

            # Llegeix camps de totes les features (municipi pot ser múltiple)
            codi_finca = num
            nom_finca = ""
            comarca = ""
            municipis_set = []  # llista ordenada sense duplicats

            idx_nom = finca_lyr.fields().lookupField("nom_finca")
            idx_mun = finca_lyr.fields().lookupField("municipi")
            idx_com = finca_lyr.fields().lookupField("comarca")

            primera = True
            for f in finca_lyr.getFeatures():
                if primera:
                    if idx_nom >= 0:
                        nom_finca = str(f[idx_nom] or "").strip()
                    if idx_com >= 0:
                        comarca = str(f[idx_com] or "").strip()
                    primera = False
                if idx_mun >= 0:
                    m = str(f[idx_mun] or "").strip()
                    if m and m not in municipis_set:
                        municipis_set.append(m)

            municipis_set.sort()
            municipi = ", ".join(municipis_set)

            # Dedueix la comarca a partir dels municipis
            if not comarca and municipis_set:
                try:
                    from .municipis_catalunya import COMARQUES_MUNICIPIS
                    import unicodedata as _udc

                    def _norm(s):
                        s = _udc.normalize("NFD", s.lower())
                        return "".join(c for c in s if _udc.category(c) != "Mn")
                    # Mapa invers: nom_municipi_normalitzat -> comarca
                    mun_a_comarca = {}
                    for com, muns in COMARQUES_MUNICIPIS.items():
                        for m in muns:
                            mun_a_comarca[_norm(m)] = com
                    # Busca la comarca per cada municipi de la finca
                    comarques_finca = []
                    for m in municipis_set:
                        com = mun_a_comarca.get(_norm(m), "")
                        if com and com not in comarques_finca:
                            comarques_finca.append(com)
                    comarques_finca.sort()
                    comarca = ", ".join(comarques_finca)
                except Exception:  # nosec — error no crític, es descarta intencionadament
                    pass

            # Fusiona totes les parcel·les de la finca i aplica morphological closing
            # per eliminar línies internes entre parcel·les adjacents
            from qgis.core import QgsGeometry
            geoms = [f.geometry() for f in finca_lyr.getFeatures()
                     if f.geometry() and not f.geometry().isEmpty()]
            if not geoms:
                del finca_lyr
                num += 1
                continue

            geom = QgsGeometry.unaryUnion(geoms)
            # Morphological closing: elimina les línies internes entre parcel·les
            if geom and not geom.isEmpty():
                geom = geom.buffer(0.05, 5)
                geom = geom.buffer(-0.05, 5)

            # El closing anterior pot desplaçar lleugerament els anells
            # interiors (exclusions legítimes) respecte al nou contorn
            # exterior recalculat, produint "Hole lies outside shell" —
            # sobretot amb finques que tenen exclusions properes a la vora.
            # Es corregeix aquí, igual que ja es fa a
            # _crear_municipi_cadastral() amb native:fixgeometries.
            if geom and not geom.isEmpty() and not geom.isGeosValid():
                fixed = geom.makeValid()
                if fixed and not fixed.isEmpty():
                    _log(
                        f"finca{num}: geometria no vàlida després del "
                        f"morphological closing — corregida amb makeValid()"
                    )
                    geom = fixed
                else:
                    _log(
                        f"finca{num}: ERROR — geometria no vàlida i "
                        f"makeValid() no l'ha pogut arreglar"
                    )

            # Converteix sempre a multipart: si makeValid() ha produït un
            # MultiPolygon de debò (cas del forat que surt del contorn),
            # es manté tal qual; si la finca és un polígon normal, es
            # converteix a MultiPolygon d'una sola part sense alterar-ne
            # la forma. Necessari perquè IOF_Finques ara és MultiPolygon.
            if geom and not geom.isEmpty():
                geom.convertToMultiType()

            # Reproj si cal
            src_crs = finca_lyr.crs()
            if src_crs != dst_crs:
                from qgis.core import QgsCoordinateTransform
                tr = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
                geom.transform(tr)

            area_ha = round(geom.area() / 10000.0, 2)
            del finca_lyr

            new_feat = QgsFeature(lf.fields())
            new_feat.setGeometry(geom)
            fields_lower = {f.name().lower(): f.name() for f in lf.fields()}
            if "codi_finca" in fields_lower:
                new_feat[fields_lower["codi_finca"]] = codi_finca
            if "nom_finca" in fields_lower:
                new_feat[fields_lower["nom_finca"]] = nom_finca
            if "municipi" in fields_lower:
                new_feat[fields_lower["municipi"]] = municipi
            if "comarca" in fields_lower:
                new_feat[fields_lower["comarca"]] = comarca
            if "superficie" in fields_lower:
                new_feat[fields_lower["superficie"]] = area_ha
            new_feats.append(new_feat)
            num += 1

        ok, added = prov.addFeatures(new_feats)
        count = len(added) if added else 0

        lf.updateExtents()
        lf.triggerRepaint()
        self.iface.mapCanvas().refresh()
        self.iface.setActiveLayer(lf)
        self.iface.zoomToActiveLayer()

        if ok and count > 0:
            plural = "s" if count != 1 else ""
            self._show_status(
                "\u2714 L'\u00e0mbit de l'IOF s'ha carregat correctament "
                "a IOF_Finques (" + str(count) + " pol\u00edgon" + plural + ")."
            )
        else:
            QMessageBox.critical(
                self, "Error",
                "No s'han pogut afegir les geometries a IOF_Finques.\n\n"
                "Comprova que la capa sigui editable."
            )

    # ------------------------------------------------------------------
    # Opcio B: importar fitxer
    # ------------------------------------------------------------------

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecciona el fitxer amb els límits de finca",
            "",
            VECTOR_FILTER
        )
        if not path:
            return

        _log(f"Importar fitxer: {path}")

        src_layer = QgsVectorLayer(path, "import_temp", "ogr")
        if not src_layer.isValid():
            QMessageBox.critical(
                self, "Error",
                f"No s'ha pogut llegir el fitxer:\n{path}\n\n"
                "Comprova que el format sigui compatible."
            )
            return

        if QgsWkbTypes.geometryType(src_layer.wkbType()) != QgsWkbTypes.GeometryType.PolygonGeometry:
            QMessageBox.warning(
                self, "Tipus incorrecte",
                "El fitxer seleccionat no conté polígons.\n\n"
                "La capa IOF_Finques requereix geometries de tipus polígon."
            )
            return

        if src_layer.featureCount() == 0:
            QMessageBox.warning(
                self, "Fitxer buit",
                "El fitxer seleccionat no conté cap objecte."
            )
            return

        # Confirmar si la capa de destí ja té dades
        lf = self._layer_finques
        if lf.featureCount() > 0:
            n = lf.featureCount()
            msg = QMessageBox(self)
            msg.setWindowTitle("Capa no buida")
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setText(
                f"La capa «{LAYER_FINQUES}» ja conté "
                f"{n} polígon{'s' if n != 1 else ''}.\n\n"
                "Què vols fer amb els polígons existents?"
            )
            btn_sub = msg.addButton("Substituir", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Afegir", QMessageBox.ButtonRole.AcceptRole)
            btn_cancel = msg.addButton("Cancel·lar", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_cancel)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == btn_cancel:
                return
            eliminar_existents = (clicked == btn_sub)
        else:
            eliminar_existents = False

        # Transformació de coordenades si cal
        src_crs = src_layer.crs()
        dst_crs = lf.crs()
        transform = None
        if src_crs != dst_crs:
            transform = QgsCoordinateTransform(
                src_crs, dst_crs, QgsProject.instance()
            )
            _log(f"Reprojectant de {src_crs.authid()} a {dst_crs.authid()}")

        # Copiar les geometries
        lf.startEditing()

        if eliminar_existents:
            for fid in [f.id() for f in lf.getFeatures()]:
                lf.deleteFeature(fid)

        count = 0
        errors = 0

        for feat in src_layer.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            if transform:
                geom.transform(transform)
            new_feat = QgsFeature(lf.fields())
            new_feat.setGeometry(geom)
            if lf.addFeature(new_feat):
                count += 1
            else:
                errors += 1

        if errors == 0:
            lf.commitChanges()
            self.iface.mapCanvas().refresh()
            reproj_note = (
                f"\n(Reprojectat de {src_crs.authid()} a {dst_crs.authid()})" if transform else ""
            )
            self._show_status(
                f"✔ S'han importat {count} polígon{'s' if count != 1 else ''} "
                f"de «{os.path.basename(path)}» a «{LAYER_FINQUES}»." + reproj_note
            )
            self.iface.setActiveLayer(lf)
            self.iface.zoomToActiveLayer()
        else:
            lf.rollBack()
            QMessageBox.critical(
                self, "Error d'importació",
                f"S'han produït {errors} errors durant la importació.\n"
                "No s'han desat canvis."
            )

    # ------------------------------------------------------------------
    # Etiquetes temporals durant la digitalització
    # ------------------------------------------------------------------

    def _activate_temp_labels(self, layer):
        """
        Activa etiquetes temporals a IOF_Finques que mostren el número
        de finca i la superfície mentre es digitalitza manualment.
        Es desactiven en desar o descartar.
        """
        from qgis.core import (
            QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
            QgsVectorLayerSimpleLabeling
        )
        from qgis.PyQt.QtGui import QFont, QColor

        fields = layer.fields().names()
        has_codi = "codi_finca" in fields
        has_sup = "superficie" in fields

        if has_codi and has_sup:
            expr = (
                'CASE '
                'WHEN "codi_finca" IS NOT NULL AND "superficie" IS NOT NULL '
                'THEN \'Finca \' || to_string("codi_finca") || \'\\n\' || '
                '     format_number("superficie", 2) || \' ha\' '
                'WHEN "codi_finca" IS NOT NULL '
                'THEN \'Finca \' || to_string("codi_finca") '
                'WHEN "superficie" IS NOT NULL '
                'THEN format_number("superficie", 2) || \' ha\' '
                'ELSE NULL END'
            )
        elif has_codi:
            expr = (
                'CASE WHEN "codi_finca" IS NOT NULL '
                'THEN \'Finca \' || to_string("codi_finca") '
                'ELSE NULL END'
            )
        else:
            expr = (
                'CASE WHEN "superficie" IS NOT NULL '
                'THEN format_number("superficie", 2) || \' ha\' '
                'ELSE NULL END'
            )
        pal = QgsPalLayerSettings()
        pal.isExpression = True
        pal.fieldName = expr
        pal.placement = QgsPalLayerSettings.Placement.OverPoint

        fmt = QgsTextFormat()
        font = QFont("Calibri", 9)
        font.setBold(True)
        fmt.setFont(font)
        fmt.setSize(9)
        fmt.setColor(QColor(80, 0, 80))
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(1)
        buf.setColor(QColor(255, 255, 255))
        fmt.setBuffer(buf)
        pal.setFormat(fmt)

        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)
        layer.triggerRepaint()

    def _remove_temp_labels(self, layer):
        """Desactiva les etiquetes temporals."""
        if not layer:
            return
        layer.setLabelsEnabled(False)
        layer.triggerRepaint()

    # ------------------------------------------------------------------
    # Opció B: mode edició manual
    # ------------------------------------------------------------------

    def _on_edit(self):
        lf = self._layer_finques

        # Si la capa ja té polígons, preguntar què fer amb els existents
        eliminar_existents = False
        if lf.featureCount() > 0:
            n = lf.featureCount()
            msg = QMessageBox(self)
            msg.setWindowTitle("Capa no buida")
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setText(
                f"La capa «IOF_Finques» ja conté "
                f"{n} polígon{'s' if n != 1 else ''}.\n\n"
                "Què vols fer amb els polígons existents "
                "mentre digitalitzes?"
            )
            btn_sub = msg.addButton("Eliminar i tornar a dibuixar", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Mantenir i editar", QMessageBox.ButtonRole.AcceptRole)
            btn_cancel = msg.addButton("Cancel·lar", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_cancel)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == btn_cancel:
                return
            eliminar_existents = (clicked == btn_sub)

        self.iface.setActiveLayer(lf)

        # Suprimir el formulari d'atributs automàtic de QGIS
        from qgis.core import QgsEditFormConfig
        self._form_config_backup = lf.editFormConfig()
        cfg = lf.editFormConfig()
        cfg.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
        lf.setEditFormConfig(cfg)

        if not lf.isEditable():
            lf.startEditing()

        if eliminar_existents:
            for fid in [f.id() for f in lf.getFeatures()]:
                lf.deleteFeature(fid)
            lf.commitChanges()
            lf.startEditing()

        # QGIS pot reutilitzar els valors de l'últim element digitalitzat
        # per als següents quan el formulari d'atributs està suprimit
        # (comportament del propi QGIS, no d'aquest complement). Com que
        # nom/comarca/municipi no s'han d'heretar mai entre finques, es
        # netegen explícitament a cada polígon nou.
        try:
            lf.featureAdded.disconnect(self._on_finca_added)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        lf.featureAdded.connect(self._on_finca_added, Qt.ConnectionType.UniqueConnection)

        self.iface.actionAddFeature().trigger()

        # Activar etiquetes temporals
        self._activate_temp_labels(lf)

        # Canviar la UI al mode edició actiu
        self._set_editing_mode(True)

    def _on_finca_added(self, fid):
        """
        Neteja nom/comarca/municipi d'una finca acabada de digitalitzar,
        perquè mai s'heretin els valors de la finca anterior encara que
        QGIS els reutilitzi per defecte amb el formulari suprimit.
        """
        lf = self._layer_finques
        if not lf:
            return
        fields = lf.fields().names()
        for camp in ("nom_finca", "comarca", "municipi"):
            if camp in fields:
                lf.changeAttributeValue(fid, lf.fields().indexOf(camp), None)

    def _on_save_edit(self):
        """Desa els canvis pendents i surt del mode edició."""
        lf = self._layer_finques
        try:
            if lf:
                lf.featureAdded.disconnect(self._on_finca_added)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        if lf and lf.isEditable():
            if not lf.commitChanges():
                errs = "; ".join(lf.commitErrors())
                QMessageBox.critical(
                    self, "Error desant",
                    f"No s'han pogut desar els canvis:\n{errs}"
                )
                return
        self.iface.mapCanvas().refresh()
        self._restore_form_config()
        self._remove_temp_labels(lf)
        self._set_editing_mode(False)
        n = lf.featureCount() if lf else 0
        self._show_status(
            f"✔ Canvis desats. La capa «IOF_Finques» conté "
            f"{n} polígon{'s' if n != 1 else ''}."
        )

    def _on_discard_edit(self):
        """Descarta tots els canvis no desats i surt del mode edició."""
        lf = self._layer_finques
        try:
            if lf:
                lf.featureAdded.disconnect(self._on_finca_added)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        if lf and lf.isEditable():
            reply = QMessageBox.question(
                self,
                "Descartar canvis",
                "Estàs segur que vols descartar tots els canvis no desats?\n\n"
                "Els polígons dibuixats en aquesta sessió es perdran.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
            lf.rollBack()
        self.iface.mapCanvas().refresh()
        self._restore_form_config()
        self._remove_temp_labels(lf)
        self._set_editing_mode(False)
        self._show_status("Canvis descartats.")

    def _set_editing_mode(self, active):
        """Mostra o amaga els grups A/B/C i la zona d'edici\u00f3 activa."""
        self._editing_active = active
        self._grp_a.setVisible(not active)
        self._sep_ab.setVisible(not active)
        self._grp_b.setVisible(not active)
        self._sep2.setVisible(not active)
        self._grp_c.setVisible(not active)
        self._grp_editing.setVisible(active)
        self.adjustSize()

    # ------------------------------------------------------------------
    # Gestió del formulari d'atributs i tancament
    # ------------------------------------------------------------------

    def _restore_form_config(self):
        """Restaura la configuració del formulari d'atributs original."""
        if self._layer_finques is not None and self._form_config_backup is not None:
            self._layer_finques.setEditFormConfig(self._form_config_backup)
            self._form_config_backup = None

    def closeEvent(self, event):
        # Si es tanca amb edició activa, preguntar
        lf = self._layer_finques
        if self._editing_active and lf and lf.isEditable():
            msg = QMessageBox(self)
            msg.setWindowTitle("Edició activa")
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setText(
                "Hi ha canvis no desats a «IOF_Finques».\n\n"
                "Què vols fer abans de tancar?"
            )
            btn_save = msg.addButton("Desar i tancar", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Descartar i tancar", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg.addButton("Cancel·lar", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_cancel)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == btn_cancel:
                event.ignore()
                return
            if clicked == btn_save:
                if not lf.commitChanges():
                    errs = "; ".join(lf.commitErrors())
                    QMessageBox.critical(
                        self, "Error desant",
                        f"No s'han pogut desar els canvis:\n{errs}"
                    )
                    event.ignore()
                    return
            else:  # Descartar
                lf.rollBack()

        self._restore_form_config()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Estat
    # ------------------------------------------------------------------

    def _show_status(self, msg, error=False):
        self._lbl_status.setText(msg)
        color = "#b71c1c" if error else "#1b5e20"
        self._lbl_status.setStyleSheet(
            f"padding:8px; color:{color}; font-style:normal; "
            "border:1px solid #ddd; border-radius:4px; background:#fafafa;"
        )
        self._lbl_status.show()
        self.adjustSize()

# -*- coding: utf-8 -*-
"""
IOF Assistent — Assistent per digitalitzar unitats de vegetació.

Flux per a cada polígon de IOF_Finques (excloent els polígons interiors):
  1. Ressaltar el polígon al mapa.
  2. Preguntar si forma una única unitat de vegetació.
     - Sí → copiar el polígon a IOF_Unitats_Actuacio/IOF_Rodals i continuar.
     - No → activar l'eina de partició (o polígon tancat) per dividir-lo.
  3. Passar al polígon següent fins que no n'hi hagi cap més.
"""

from .iof_utils import (
    get_layer as _get_layer_util,
    geom_sense_forats as _geom_sense_forats,
    find_interior_polygons as _find_exclusions,
    activar_snapping_totes_capes as _activar_snapping_totes_capes,
    restaurar_snapping as _restaurar_snapping,
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
    QgsWkbTypes, QgsMessageLog, Qgis,
    QgsPointXY, QgsPointLocator
)
from qgis.gui import QgsRubberBand, QgsMapTool, QgsSnapIndicator


def _log(msg):
    QgsMessageLog.logMessage(str(msg), "IOF Assistent", Qgis.MessageLevel.Info)


LAYER_FINQUES = "IOF_Finques"
LAYERS_UNITATS = ["IOF_Unitats_Actuacio", "IOF_Rodals"]


def _get_layer(names):
    return _get_layer_util(names)


class IOFSplitTool(QgsMapTool):
    """
    Eina de mapa pròpia per dividir polígons amb una polilínia.
    L'usuari fa clics per definir la línia de tall i clic dret per executar.
    Usa QgsGeometry.splitGeometry() directament, sense dependre de
    cap acció interna de QGIS.
    """

    def __init__(self, canvas, layer, on_split_done=None):
        super().__init__(canvas)
        self._canvas = canvas
        self._layer = layer
        self._points = []       # punts en CRS de la capa
        self._on_done = on_split_done
        self._rubber = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self._rubber.setColor(QColor(255, 255, 0, 200))
        self._rubber.setWidth(2)

        # Indicador visual de snap (el quadradet/rombe lila que mostra QGIS
        # quan l'eina nativa de digitalització s'enganxa a un vèrtex/segment).
        # La nostra eina pròpia no el dibuixava mai, per això no es veia
        # cap confirmació visual encara que el snap funcionés internament.
        self._snap_indicator = QgsSnapIndicator(canvas)

        # Transformació canvas → capa
        from qgis.core import QgsCoordinateTransform
        self._transform = QgsCoordinateTransform(
            canvas.mapSettings().destinationCrs(),
            layer.crs(),
            QgsProject.instance()
        )

        # Cerca de snap pròpia (QgsPointLocator), independent de la
        # configuració de QgsSnappingConfig del projecte: es construeix
        # un localitzador per cada capa vectorial visible i es busca el
        # vèrtex/segment més proper dins la tolerància en píxels. Així
        # el tall de polígons s'enganxa igual que l'eina nativa encara
        # que canviï l'API de snapping entre versions de QGIS.
        self._locators = []
        for lyr in QgsProject.instance().mapLayers().values():
            if not isinstance(lyr, QgsVectorLayer):
                continue
            try:
                root = QgsProject.instance().layerTreeRoot()
                node = root.findLayer(lyr.id())
                if node is not None and not node.isVisible():
                    continue
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass
            try:
                self._locators.append(QgsPointLocator(lyr, canvas.mapSettings().destinationCrs()))
            except Exception as e:
                _log(f"IOFSplitTool: no s'ha pogut indexar {lyr.name()} per snap: {e}")
        _log(f"IOFSplitTool: {len(self._locators)} capa(es) indexada(es) per al snap propi: "
             f"{[loc.layer().name() for loc in self._locators]}")

    def _snap_propi(self, canvas_pt, tolerance_px=12):
        """Cerca manual del vèrtex/segment més proper dins totes les capes indexades.
        Retorna el QgsPointLocator.Match trobat (o None si no n'hi ha cap)."""
        try:
            tol_map_units = self._canvas.mapUnitsPerPixel() * tolerance_px
        except Exception:
            tol_map_units = 1.0

        best_match = None
        best_dist = None
        for loc in self._locators:
            try:
                m = loc.nearestVertex(canvas_pt, tol_map_units)
                if not m.isValid():
                    m = loc.nearestEdge(canvas_pt, tol_map_units)
                if m.isValid():
                    d = m.point().distance(canvas_pt)
                    if best_dist is None or d < best_dist:
                        best_dist = d
                        best_match = m
            except Exception:  # nosec — error no crític, es descarta intencionadament
                continue
        return best_match

    def _to_layer_crs(self, canvas_pt):
        """Converteix un punt del canvas al CRS de la capa."""
        try:
            return self._transform.transform(QgsPointXY(canvas_pt))
        except Exception:
            return QgsPointXY(canvas_pt)

    def _snapped_point(self, pos):
        """Retorna el punt amb snap aplicat (en CRS del canvas) i el converteix al CRS de la capa.
        També actualitza l'indicador visual de snap (quadradet/rombe lila)."""
        snapper = self._canvas.snappingUtils()
        match = snapper.snapToMap(pos)
        if match.isValid():
            canvas_pt = match.point()
            self._snap_indicator.setMatch(match)
            try:
                _log(f"IOFSplitTool snap: projecte OK, tipus={match.type()}, "
                     f"capa={match.layer().name() if match.layer() else '—'}, punt=({canvas_pt.x():.2f},{canvas_pt.y():.2f})")
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass
        else:
            canvas_pt = self.toMapCoordinates(pos)
            # Reforç: si el snap del projecte no ha trobat res, prova la
            # cerca pròpia amb QgsPointLocator (vegeu __init__/_snap_propi).
            propi_match = self._snap_propi(canvas_pt)
            if propi_match is not None:
                canvas_pt = propi_match.point()
                self._snap_indicator.setMatch(propi_match)
            else:
                self._snap_indicator.setMatch(QgsPointLocator.Match())
        return self._to_layer_crs(canvas_pt), canvas_pt

    def canvasPressEvent(self, event):
        from qgis.PyQt.QtCore import Qt
        if event.button() == Qt.MouseButton.RightButton:
            if len(self._points) >= 2:
                self._execute_split()
            self._reset()
        elif event.button() == Qt.MouseButton.LeftButton:
            layer_pt, canvas_pt = self._snapped_point(event.pos())
            self._points.append(layer_pt)
            self._rubber.addPoint(canvas_pt)

    def canvasMoveEvent(self, event):
        # Actualitza sempre l'indicador de snap (fins i tot abans del primer
        # clic), igual que fa l'eina nativa de QGIS.
        _, canvas_pt = self._snapped_point(event.pos())
        if not self._points:
            return
        if self._rubber.numberOfVertices() > len(self._points):
            self._rubber.removeLastPoint()
        self._rubber.addPoint(canvas_pt)

    def keyPressEvent(self, event):
        from qgis.PyQt.QtCore import Qt
        if event.key() == Qt.Key.Key_Escape:
            self._reset()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if len(self._points) >= 2:
                self._execute_split()
            self._reset()
        elif event.key() == Qt.Key.Key_Backspace and self._points:
            self._points.pop()
            self._rubber.removeLastPoint()
            self._rubber.removeLastPoint()

    def _extend_split_line(self, pts, extend_factor=0.05, min_extend=2.0):
        """Allarga la línia de tall una mica pels dos extrems.

        splitGeometry() només divideix si la línia travessa el polígon de
        banda a banda. Quan els punts inicial/final s'enganxen exactament a
        vèrtexs del propi contorn, la línia "toca" la vora però no la creua i
        el tall falla (result_code=1). Prolongant els segments extrems cap a
        fora es garanteix que la línia surti del polígon pels dos costats.
        """
        if len(pts) < 2:
            return list(pts)

        out = [QgsPointXY(p) for p in pts]

        # Extrem inicial: prolonga en direcció contrària al segon punt.
        p0, p1 = out[0], out[1]
        dx, dy = p0.x() - p1.x(), p0.y() - p1.y()
        d = (dx * dx + dy * dy) ** 0.5
        if d > 0:
            ext = max(d * extend_factor, min_extend)
            out[0] = QgsPointXY(p0.x() + dx / d * ext, p0.y() + dy / d * ext)

        # Extrem final: prolonga en direcció contrària al penúltim punt.
        pn, pm = out[-1], out[-2]
        dx, dy = pn.x() - pm.x(), pn.y() - pm.y()
        d = (dx * dx + dy * dy) ** 0.5
        if d > 0:
            ext = max(d * extend_factor, min_extend)
            out[-1] = QgsPointXY(pn.x() + dx / d * ext, pn.y() + dy / d * ext)

        return out

    def _execute_split(self):
        """Executa splitGeometry sobre tots els polígons de la capa."""
        layer = self._layer
        if not layer or not layer.isEditable():
            _log("IOFSplitTool: capa no editable")
            return

        # Neteja qualsevol selecció: si la capa té entitats seleccionades,
        # l'eina de tall de QGIS només actua sobre aquelles i avisa
        # "No features were split ... clear the selection".
        try:
            if layer.selectedFeatureCount():
                layer.removeSelection()
                _log("IOFSplitTool: selecció de la capa netejada abans del tall")
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass

        split_line = self._extend_split_line(self._points)
        _log(f"IOFSplitTool: executant split amb {len(split_line)} punts, CRS capa={layer.crs().authid()}")
        _log(f"IOFSplitTool: primer punt = ({split_line[0].x():.1f}, {split_line[0].y():.1f})")

        n_split = 0
        for feat in list(layer.getFeatures()):
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue

            # Geometries invàlides (autointerseccions, sovint heretades del
            # cadastre) fan que splitGeometry() torni InvalidBaseGeometry
            # sense ni intentar el tall. Es corregeix abans d'operar-hi.
            if not geom.isGeosValid():
                fixed = geom.makeValid()
                if fixed and not fixed.isEmpty():
                    _log(f"IOFSplitTool: fid={feat.id()} geometria no vàlida "
                         f"— corregida amb makeValid() abans de tallar")
                    geom = fixed
                else:
                    _log(f"IOFSplitTool: fid={feat.id()} geometria no vàlida "
                         f"i no s'ha pogut corregir — s'omet")
                    continue

            bb = geom.boundingBox()
            _log(f"IOFSplitTool: fid={feat.id()} bbox=({bb.xMinimum():.0f},{bb.yMinimum():.0f},{bb.xMaximum():.0f},{bb.yMaximum():.0f})")

            result = geom.splitGeometry(split_line, False)
            if result[0] == 0 and result[1]:
                layer.changeGeometry(feat.id(), geom)
                fid_idx = layer.fields().indexFromName("fid")
                for new_geom in result[1]:
                    new_feat = QgsFeature(layer.fields())
                    new_feat.setGeometry(new_geom)
                    new_feat.setAttributes(feat.attributes())
                    # En un GeoPackage, "fid" sovint apareix com a camp
                    # normal dins de layer.fields(). setAttributes() de
                    # dalt copia també el fid de l'entitat original cap a
                    # totes les parts noves; QGIS ho respecta en desar, i
                    # com que totes competeixen pel mateix fid, el
                    # GeoPackage rebutja la inserció amb
                    # "UNIQUE constraint failed". Es buida explícitament
                    # perquè el proveïdor n'assigni un de nou i únic
                    # (bug conegut de QGIS+GPKG en dividir entitats).
                    if fid_idx >= 0:
                        new_feat.setAttribute(fid_idx, None)
                    layer.addFeature(new_feat)
                n_split += 1
                _log(f"IOFSplitTool: split OK fid={feat.id()}, {len(result[1])} parts noves")
            else:
                # Des de QGIS ~3.30, splitGeometry() retorna l'enum
                # Qgis.GeometryOperationResult, on els valors "sense èxit"
                # comencen a 1000 (NothingHappened=1000,
                # InvalidBaseGeometry=1001, GeometryEngineError=1005...),
                # NO els codis vells 1/2 de QGIS 3.4. Es registra el nom
                # real perquè el log sigui diagnosticable.
                code = result[0]
                code_name = getattr(code, "name", str(code))
                _log(f"IOFSplitTool: fid={feat.id()} result_code={int(code)} ({code_name})")

        if n_split == 0:
            _log("IOFSplitTool: cap polígon dividit")
        else:
            layer.triggerRepaint()
            if self._on_done:
                self._on_done()

    def _reset(self):
        self._points = []
        self._rubber.reset(QgsWkbTypes.GeometryType.LineGeometry)

    def deactivate(self):
        self._reset()
        self._rubber.hide()
        self._snap_indicator.setMatch(QgsPointLocator.Match())
        super().deactivate()


class UnitatsWizard(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self._layer_finques = None
        self._layer_unitats = None
        self._finques = []
        self._current = 0
        self._rubber_band = None
        self._split_tool = None
        self._draw_mode = 'split'
        self._cancelled = False

        # Botons permanents
        self._btn_unic = None
        self._btn_multi = None
        self._btn_done = None
        self._btn_switch = None

        self.setWindowTitle("IOF Assistent — Digitalitzar unitats de vegetació")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(420)
        self._build_ui()

        if self._check_layers():
            from .iof_utils import dimmar_altres_capes_iof
            dimmar_altres_capes_iof(self._layer_unitats)
            self._load_finques()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self._lbl_title = QLabel()
        self._lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_title.setWordWrap(True)
        self._lbl_title.setStyleSheet(
            "padding:8px; background:#e3f2fd; border-radius:4px; font-weight:bold;"
        )
        layout.addWidget(self._lbl_title)

        self._lbl_info = QLabel()
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet("padding:6px; color:#333;")
        layout.addWidget(self._lbl_info)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#ccc;")
        layout.addWidget(sep)

        self._btn_unic = QPushButton()
        self._btn_unic.setStyleSheet(
            "background:#1565c0; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_unic.clicked.connect(self._on_btn_unic)
        self._btn_unic.hide()
        layout.addWidget(self._btn_unic)

        self._btn_multi = QPushButton()
        self._btn_multi.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_multi.clicked.connect(self._on_btn_multi)
        self._btn_multi.hide()
        layout.addWidget(self._btn_multi)

        self._btn_done = QPushButton()
        self._btn_done.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:8px;"
        )
        self._btn_done.clicked.connect(self._on_btn_done)
        self._btn_done.hide()
        layout.addWidget(self._btn_done)

        self._btn_switch = QPushButton()
        self._btn_switch.setStyleSheet(
            "background:#e65100; color:white; font-weight:bold; padding:7px;"
        )
        self._btn_switch.clicked.connect(self._on_btn_switch)
        self._btn_switch.hide()
        layout.addWidget(self._btn_switch)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color:#ccc;")
        layout.addWidget(sep2)

        btn_close = QPushButton("Tancar assistent")
        btn_close.setStyleSheet("padding:5px; color:#555;")
        btn_close.clicked.connect(self._close_wizard)
        layout.addWidget(btn_close)

    # ------------------------------------------------------------------
    # Verificació i càrrega
    # ------------------------------------------------------------------

    def _check_layers(self):
        self._layer_finques = _get_layer(LAYER_FINQUES)
        self._layer_unitats = _get_layer(LAYERS_UNITATS)

        if self._layer_finques is None:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(self, LAYER_FINQUES)
            self._cancelled = True
            return False
        if self._layer_unitats is None:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(self, "IOF_Rodals / IOF_Unitats_Actuacio")
            self._cancelled = True
            return False
        if self._layer_finques.featureCount() == 0:
            self._lbl_title.setText("Error")
            self._lbl_info.setText(
                "La capa de finques no conté cap polígon.\n"
                "Digitalitza les finques primer."
            )
            return False
        return True

    def _units_for_finca(self, finca_feat):
        """
        Retorna la llista de features d'unitats que pertanyen a la finca donada.
        Criteri: el centroide de la unitat cau dins de la geometria de la finca
        (tolerància: bbox expandit 1 m per cobrir vèrtexs exactament al límit).
        """
        if not self._layer_unitats:
            return []
        finca_geom = finca_feat.geometry()
        if not finca_geom or finca_geom.isEmpty():
            return []
        result = []
        for u in self._layer_unitats.getFeatures():
            g = u.geometry()
            if not g or g.isEmpty():
                continue
            centroide = g.centroid()
            if finca_geom.contains(centroide):
                result.append(u)
        return result

    def _finca_is_complete(self, finca_feat):
        """
        Retorna True si la finca ja té unitats que cobreixen tota la
        seva geometria (àrea de la unió ≥ 99% de l'àrea de la finca).
        """
        units = self._units_for_finca(finca_feat)
        if not units:
            return False
        finca_area = finca_feat.geometry().area()
        if finca_area <= 0:
            return True
        union = units[0].geometry()
        for u in units[1:]:
            union = union.combine(u.geometry())
        covered = union.intersection(finca_feat.geometry()).area()
        return (covered / finca_area) >= 0.99

    def _find_resume_index(self):
        """
        Troba l'índex de la primera finca que no té unitats completes.
        Si totes estan completes, retorna l'última (per mostrar la pantalla done).
        """
        for i, finca in enumerate(self._finques):
            if not self._finca_is_complete(finca):
                return i
        return len(self._finques) - 1

    def _load_finques(self):
        """Carrega els polígons de finca excloent els polígons interiors."""
        all_feats = list(self._layer_finques.getFeatures())
        exclusion_ids = _find_exclusions(all_feats)
        self._finques = [f for f in all_feats if f.id() not in exclusion_ids]

        n_excl = len(exclusion_ids)
        _log(f"Finques: {len(self._finques)} vàlides, {n_excl} excloses (id={exclusion_ids})")

        if not self._finques:
            self._lbl_title.setText("Error")
            self._lbl_info.setText(
                "No hi ha polígons de finca vàlids per editar.\n"
                "Tots els polígons han estat identificats com a àrees excloses."
            )
            return

        # Si ja hi ha unitats digitalitzades, preguntar si continuar o reiniciar
        if self._layer_unitats and self._layer_unitats.featureCount() > 0:
            n_unitats = self._layer_unitats.featureCount()
            msg = QMessageBox(self)
            msg.setWindowTitle("Unitats existents")
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setText(
                f"La capa d'unitats ja conté {n_unitats} "
                f"polígon{'s' if n_unitats != 1 else ''}.\n\n"
                "Vols continuar des d'on ho vas deixar "
                "o eliminar-ho tot i començar de nou?"
            )
            btn_cont = msg.addButton("Continuar", QMessageBox.ButtonRole.AcceptRole)
            btn_new = msg.addButton("Eliminar i reiniciar", QMessageBox.ButtonRole.DestructiveRole)
            btn_can = msg.addButton("Cancel·lar", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_cont)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == btn_can:
                # self.close() aquí no evita que es mostri: el diàleg
                # encara no s'ha ensenyat (això passa dins __init__,
                # abans que qui l'ha creat cridi .show()). Es marca
                # explícitament perquè qui l'ha creat (run_unitats a
                # iof_exporter.py) comprovi aquest flag i no en cridi
                # .show() si l'usuari ha cancel·lat.
                self._cancelled = True
                self.close()
                return
            if clicked == btn_new:
                # Eliminar totes les unitats existents
                lyr = self._layer_unitats
                lyr.startEditing()
                for fid in [f.id() for f in lyr.getFeatures()]:
                    lyr.deleteFeature(fid)
                lyr.commitChanges()
            # Si clicked == btn_cont, continuem amb la detecció

        # Sempre comencem des del primer polígon;
        # _show_step_finca preguntarà per cada finca que ja tingui unitats
        self._current = 0
        self._show_step_finca()

    # ------------------------------------------------------------------
    # Pas principal: un polígon de finca
    # ------------------------------------------------------------------

    def _show_step_finca(self):
        """Mostra el diàleg per al polígon de finca actual."""
        feat = self._finques[self._current]
        total = len(self._finques)
        idx = self._current + 1
        is_last = (idx == total)

        # Ressaltar el polígon al mapa (sense zoom)
        self._highlight(feat.geometry())

        codi = feat["codi_finca"] or f"#{feat.id()}"

        units = self._units_for_finca(feat)

        if units:
            # --- Polígon ja dividit: diàleg de represa ---
            msg = QMessageBox(self)
            msg.setWindowTitle(f"Finca {codi} — ja digitalitzada")
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setText(
                f"La finca {codi} ja té {len(units)} unitat"
                f"{'s' if len(units) != 1 else ''} definida"
                f"{'des' if len(units) != 1 else ''}.\n\n"
                "Què vols fer?"
            )
            msg.addButton("Reprendre la digitalització", QMessageBox.ButtonRole.AcceptRole)
            btn_unica = msg.addButton("Convertir en una única unitat", QMessageBox.ButtonRole.AcceptRole)
            btn_ok = msg.addButton(
                "És correcte. Passar al següent." if not is_last else "És correcte.",
                QMessageBox.ButtonRole.AcceptRole
            )
            btn_cancel = msg.addButton("Cancel·lar", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_ok)
            msg.exec()
            clicked = msg.clickedButton()

            if clicked == btn_cancel:
                # Tanca l'assistent sencer (amb la mateixa neteja i
                # confirmació de canvis pendents que "Tancar assistent"),
                # no només aquest pas.
                self._close_wizard()
                return
            if clicked == btn_unica:
                self._delete_units_for_finca(feat)
                self._copy_finca_as_unit()
                self._finish_current_finca()
                return
            if clicked == btn_ok:
                self._finish_current_finca()
                return
            # btn_rep: activar mode split sense copiar
            self._setup_snapping()
            self._suppress_attribute_form(True)
            if not self._layer_unitats.isEditable():
                self._layer_unitats.startEditing()
            self.iface.setActiveLayer(self._layer_unitats)
            self._layer_unitats.featureAdded.connect(self._on_feature_added)
            self._draw_mode = 'split'
            self._trigger_split_tool()
            self._apply_digitizing_style()
            self._clear_highlight()
            self._show_step_split()
            return

        # --- Polígon sense unitats: diàleg inicial ---
        self._lbl_title.setText(f"Polígon {idx} de {total} — Finca {codi}")
        self._lbl_info.setText(
            f"El polígon ressaltat al mapa correspon a la finca {codi}.\n\n"
            "Aquest polígon forma una única unitat de vegetació, "
            "o cal dividir-lo en diverses unitats?"
        )
        self._btn_unic.setText("És una única unitat de vegetació")
        self._btn_multi.setText("Cal dividir en diverses unitats")
        self._btn_unic.show()
        self._btn_multi.show()
        self._btn_done.hide()
        self._btn_switch.hide()
        self.adjustSize()
    # ------------------------------------------------------------------
    # Callbacks dels botons
    # ------------------------------------------------------------------

    def _on_btn_unic(self):
        _log("Botó 'única unitat' premut")
        try:
            self._copy_finca_as_unit()
            self._next_finca()
        except Exception as e:
            _log(f"ERROR _on_btn_unic: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def _on_btn_multi(self):
        _log("Botó 'diverses unitats' premut")
        try:
            self._start_digitizing()
        except Exception as e:
            _log(f"ERROR _on_btn_multi: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def _on_btn_done(self):
        _log("Botó 'he acabat' premut")
        try:
            self._finish_current_finca()
        except Exception as e:
            _log(f"ERROR _on_btn_done: {e}")
            QMessageBox.critical(self, "Error", str(e))

    def _on_btn_switch(self):
        _log(f"Switch mode: {self._draw_mode}")
        try:
            if self._draw_mode == 'split':
                self._draw_mode = 'polygon'
                self.iface.setActiveLayer(self._layer_unitats)
                self.iface.actionAddFeature().trigger()
            else:
                self._draw_mode = 'split'
                self.iface.setActiveLayer(self._layer_unitats)
                self._trigger_split_tool()
            self._update_split_panel()
            self.adjustSize()
        except Exception as e:
            _log(f"ERROR _on_btn_switch: {e}")

    # ------------------------------------------------------------------
    # Opció A: copiar el polígon sencer com a unitat única
    # ------------------------------------------------------------------

    def _delete_units_for_finca(self, finca_feat):
        """Elimina totes les unitats que corresponen a la finca donada."""
        units = self._units_for_finca(finca_feat)
        if not units:
            return
        lu = self._layer_unitats
        lu.startEditing()
        for u in units:
            lu.deleteFeature(u.id())
        lu.commitChanges()

    def _copy_finca_as_unit(self):
        feat = self._finques[self._current]
        geom = QgsGeometry(feat.geometry())
        lu = self._layer_unitats
        # Copiar la geometria tal com és (amb els forats si en té).
        # QGIS calcula area() descomptant els forats automàticament.
        #
        # Les geometries de finca (sovint importades del cadastre) poden
        # arribar amb autointerseccions o altres invalideses que fan
        # fallar més endavant splitGeometry() i difference() sense avís
        # clar. Es valida i, si cal, es corregeix aquí — a l'origen —
        # perquè tota la resta del flux (tall, resta de polígons) treballi
        # sempre amb geometria neta.
        if not geom.isGeosValid():
            fixed = geom.makeValid()
            if fixed and not fixed.isEmpty():
                _log(f"_copy_finca_as_unit: geometria de finca fid={feat.id()} "
                     f"no vàlida — corregida amb makeValid()")
                geom = fixed
            else:
                _log(f"_copy_finca_as_unit: ERROR — geometria de finca fid={feat.id()} "
                     f"no vàlida i makeValid() no l'ha pogut arreglar")
        lu.startEditing()
        nf = QgsFeature(lu.fields())
        nf.setGeometry(geom)
        lu.addFeature(nf)
        lu.commitChanges()
        # Eliminar polígons d'exclusió que puguin haver quedat a la capa
        self._remove_exclusions_from_unitats()

    def _remove_exclusions_from_unitats(self):
        """
        Elimina de la capa d'unitats els polígons que corresponen a
        exclusions de IOF_Finques (polígons interiors/forats).
        Els identifica comparant àrea i bounding box.
        """
        lu = self._layer_unitats
        lf = self._layer_finques

        # Obtenir signatures de les exclusions de IOF_Finques
        all_finques = list(lf.getFeatures())
        excl_ids_f = _find_exclusions(all_finques)
        if not excl_ids_f:
            # Buscar anells interiors als polígons de IOF_Finques
            from qgis.core import QgsGeometry as QG
            excl_signatures = []
            for f in all_finques:
                g = f.geometry()
                if not g or g.isEmpty():
                    continue
                parts = g.asMultiPolygon() if g.isMultipart() else [g.asPolygon()]
                for part in parts:
                    for ring in part[1:]:
                        hole = QG.fromPolygonXY([ring])
                        if hole and not hole.isEmpty():
                            excl_signatures.append({
                                'area': round(hole.area(), 1),
                                'bbox': hole.boundingBox(),
                            })
        else:
            excl_signatures = []
            for f in all_finques:
                if f.id() not in excl_ids_f:
                    continue
                g = f.geometry()
                if g and not g.isEmpty():
                    excl_signatures.append({
                        'area': round(g.area(), 1),
                        'bbox': g.boundingBox(),
                    })

        if not excl_signatures:
            return

        # Trobar i eliminar polígons d'unitats que coincideixen amb exclusions
        to_delete = []
        for u_feat in lu.getFeatures():
            g = u_feat.geometry()
            if not g or g.isEmpty():
                continue
            area_u = round(g.area(), 1)
            bbox_u = g.boundingBox()
            for sig in excl_signatures:
                sig_match = all([
                    area_u == sig['area'],
                    abs(bbox_u.xMinimum() - sig['bbox'].xMinimum()) < 0.1,
                    abs(bbox_u.yMinimum() - sig['bbox'].yMinimum()) < 0.1,
                    abs(bbox_u.xMaximum() - sig['bbox'].xMaximum()) < 0.1,
                    abs(bbox_u.yMaximum() - sig['bbox'].yMaximum()) < 0.1,
                ])
                if sig_match:
                    to_delete.append(u_feat.id())
                    break

        if to_delete:
            lu.startEditing()
            lu.deleteFeatures(to_delete)
            lu.commitChanges()
            _log(f"Eliminats {len(to_delete)} polígons d'exclusió de {lu.name()}")

    # ------------------------------------------------------------------
    # Opció B: dividir en diverses unitats (eina de partició)
    # ------------------------------------------------------------------

    def _start_digitizing(self):
        """Copia el polígon de finca a la capa d'unitats i activa l'eina de partició."""
        self._copy_finca_as_unit()
        self._setup_snapping()
        self._suppress_attribute_form(True)
        self._layer_unitats.startEditing()
        self.iface.setActiveLayer(self._layer_unitats)
        self._layer_unitats.featureAdded.connect(self._on_feature_added)
        self._draw_mode = 'split'
        self._trigger_split_tool()
        # Aplicar estil i netejar ressaltat DESPRÉS d'activar l'eina
        self._apply_digitizing_style()
        self._clear_highlight()
        self._show_step_split()

    def _on_feature_added(self, fid):
        """
        Quan s'afegeix un polígon nou en mode 'polygon' (polígon tancat),
        resta la seva geometria del polígon gran que el conté,
        de manera que no se solapen.
        """
        if self._draw_mode != 'polygon':
            return

        lu = self._layer_unitats

        # Obtenir la geometria del polígon nou (pot tenir fid negatiu mentre no es desa)
        new_feat = lu.getFeature(fid)
        if not new_feat or not new_feat.isValid():
            return
        new_geom = new_feat.geometry()
        if not new_geom or new_geom.isEmpty():
            return

        # Trobar el polígon gran que conté el nou (el que té més àrea i el seu bbox inclou el nou)
        bb_new = new_geom.boundingBox()
        area_new = new_geom.area()
        container_fid = None
        container_geom = None

        for feat in lu.getFeatures():
            if feat.id() == fid:
                continue
            g = feat.geometry()
            if not g or g.isEmpty():
                continue
            if g.area() <= area_new:
                continue
            bb = g.boundingBox()
            # El nou polígon cau dins del gran?
            conte_nou = all([
                bb_new.xMinimum() >= bb.xMinimum(),
                bb_new.yMinimum() >= bb.yMinimum(),
                bb_new.xMaximum() <= bb.xMaximum(),
                bb_new.yMaximum() <= bb.yMaximum(),
            ])
            if conte_nou:
                container_fid = feat.id()
                container_geom = g
                break

        if container_fid is None:
            return  # No hi ha cap contenidor — polígon independent, no fer res

        # Geometria invàlida al contenidor (mateixa causa que a
        # IOFSplitTool) fa que difference() torni buida sense cap error
        # explícit. Es corregeix abans de restar.
        if not container_geom.isGeosValid():
            fixed = container_geom.makeValid()
            if fixed and not fixed.isEmpty():
                _log(f"_on_feature_added: geometria contenidora fid={container_fid} "
                     f"no vàlida — corregida amb makeValid()")
                container_geom = fixed

        # Restar la geometria nova del polígon gran
        new_container_geom = container_geom.difference(new_geom)
        if new_container_geom and not new_container_geom.isEmpty():
            lu.changeGeometry(container_fid, new_container_geom)
            _log(f"Geometria restada: fid_container={container_fid} fid_nou={fid}")
        else:
            _log(f"ERROR: difference retorna buit — fid_container={container_fid} "
                 f"(geometria contenidora encara invàlida després de makeValid()?)")

    def _disconnect_feature_added(self):
        """Desconnecta el signal featureAdded si estava connectat."""
        try:
            self._layer_unitats.featureAdded.disconnect(self._on_feature_added)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass

    def _setup_snapping(self):
        _activar_snapping_totes_capes(self.iface)

    def _trigger_split_tool(self):
        """Activa l'eina de divisió pròpia IOFSplitTool."""
        self._split_tool = IOFSplitTool(
            self.iface.mapCanvas(),
            self._layer_unitats,
            on_split_done=None  # el wizard no necessita callback aquí
        )
        self.iface.mapCanvas().setMapTool(self._split_tool)
        _log("IOFSplitTool activada")

    def _apply_digitizing_style(self):
        """Farciment transparent + contorn del color propi de la capa
        (paleta compartida a iof_utils._COLORS_DIMMAT_IOF) durant la
        digitalització."""
        from qgis.core import QgsFillSymbol, QgsSingleSymbolRenderer
        from .iof_utils import _COLORS_DIMMAT_IOF
        r, g, b = _COLORS_DIMMAT_IOF.get(self._layer_unitats.name(), (0, 150, 60))
        self._renderer_backup = self._layer_unitats.renderer().clone()
        sym = QgsFillSymbol.createSimple({
            'color': '0,0,0,0',
            'outline_color': f'{r},{g},{b},255',
            'outline_width': '0.6',
            'outline_style': 'solid',
        })
        self._layer_unitats.setRenderer(QgsSingleSymbolRenderer(sym))
        self._layer_unitats.triggerRepaint()

    def _restore_digitizing_style(self):
        """Restaura el renderer anterior a la digitalització."""
        if hasattr(self, '_renderer_backup') and self._renderer_backup:
            self._layer_unitats.setRenderer(self._renderer_backup)
            self._renderer_backup = None
            self._layer_unitats.triggerRepaint()

    def _show_step_split(self):
        feat = self._finques[self._current]
        codi = feat["codi_finca"] or f"#{feat.id()}"
        total = len(self._finques)
        idx = self._current + 1

        self._lbl_title.setText(
            f"Dividint polígon {idx}/{total} — Finca {codi}"
        )
        self._draw_mode = 'split'
        self._update_split_panel()

        self._btn_unic.hide()
        self._btn_multi.hide()
        self._btn_done.setText("He acabat de dividir aquest polígon ✔")
        self._btn_done.show()
        self._btn_switch.show()
        self.adjustSize()

    def _update_split_panel(self):
        if self._draw_mode == 'split':
            self._lbl_info.setText(
                "<b>Mode: Polilínia divisòria</b><br><br>"
                "1. Fes clic per iniciar la línia de tall.<br>"
                "2. Afegeix vèrtexs intermedis si cal.<br>"
                "3. Fes <b>clic dret</b> per executar la partició.<br><br>"
                "<i>La línia no cal que toqui el límit del polígon: "
                "QGIS el calcula automàticament.</i><br><br>"
                "<i>Botó taronja per canviar a mode polígon tancat.</i>"
            )
            self._btn_switch.setText("Canviar a: Polígon tancat →")
        else:
            self._lbl_info.setText(
                "<b>Mode: Polígon tancat</b><br><br>"
                "1. Dibuixa el polígon complet fent clic als vèrtexs.<br>"
                "2. Fes <b>clic dret</b> o prem <b>Enter</b> per tancar.<br><br>"
                "<i>El polígon nou es restarà automàticament del polígon gran.</i><br><br>"
                "<i>Si el resultat no és correcte, prem <b>Ctrl+Z</b> per desfer.</i><br><br>"
                "<i>Botó taronja per tornar a mode polilínia divisòria.</i>"
            )
            self._btn_switch.setText("← Tornar a: Polilínia divisòria")

    # ------------------------------------------------------------------
    # Finalitzar edició del polígon actual i passar al següent
    # ------------------------------------------------------------------

    def _suppress_attribute_form(self, suppress):
        """Activa o desactiva el diàleg d'atributs automàtic de la capa d'unitats."""
        from qgis.core import QgsEditFormConfig
        config = self._layer_unitats.editFormConfig()
        if suppress:
            config.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOn)
        else:
            config.setSuppress(QgsEditFormConfig.FeatureFormSuppress.SuppressOff)
        self._layer_unitats.setEditFormConfig(config)

    def _finish_current_finca(self):
        """Desa els canvis del polígon actual i passa al següent."""
        self._disconnect_feature_added()
        self._restore_digitizing_style()
        self._restore_snapping()
        self._suppress_attribute_form(False)
        self.iface.actionSelect().trigger()
        if self._layer_unitats.isEditable():
            self._layer_unitats.commitChanges()
        self.iface.mapCanvas().refresh()
        self._next_finca()

    def _next_finca(self):
        """Passa al polígon de finca següent o finalitza."""
        self._current += 1
        if self._current < len(self._finques):
            self._show_step_finca()
        else:
            self._show_done()

    def _show_done(self):
        self._clear_highlight()
        n = self._layer_unitats.featureCount()
        self._btn_unic.hide()
        self._btn_multi.hide()
        self._btn_done.hide()
        self._btn_switch.hide()
        self._lbl_title.setText("Digitalització completada ✔")
        self._lbl_info.setText(
            f"La capa «{self._layer_unitats.name()}» conté ara "
            f"{n} unitat{'s' if n != 1 else ''} de vegetació.\n\n"
            "Recorda completar els camps de cada unitat "
            "des de la taula d'atributs."
        )
        self.adjustSize()

    # ------------------------------------------------------------------
    # Rubber band (ressaltat del polígon actiu)
    # ------------------------------------------------------------------

    def _highlight(self, geom):
        canvas = self.iface.mapCanvas()
        if self._rubber_band is None:
            self._rubber_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)
        self._rubber_band.setColor(QColor(255, 220, 0, 220))
        self._rubber_band.setFillColor(QColor(255, 235, 0, 60))
        self._rubber_band.setWidth(4)
        self._rubber_band.setToGeometry(
            _geom_sense_forats(geom), self._layer_finques
        )
        self._rubber_band.show()

    def _clear_highlight(self):
        if self._rubber_band is not None:
            self._rubber_band.hide()
            self._rubber_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self._rubber_band = None
        if self._layer_finques:
            self._layer_finques.removeSelection()
        self.iface.mapCanvas().refresh()

    # ------------------------------------------------------------------
    # Snapping i tancament
    # ------------------------------------------------------------------

    def _restore_snapping(self):
        _restaurar_snapping(self.iface)

    def _close_wizard(self):
        self._disconnect_feature_added()
        self._clear_highlight()
        self._restore_digitizing_style()
        self._restore_snapping()
        self.iface.actionSelect().trigger()
        self.close()

    def _confirm_close_with_edits(self):
        """
        Si la capa d'unitats té edició activa, pregunta a l'usuari
        si vol desar o descartar els canvis abans de tancar.
        Retorna True si es pot tancar, False si l'usuari cancel·la.
        """
        lyr = self._layer_unitats
        if not lyr or not lyr.isEditable():
            return True

        from qgis.PyQt.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Edició activa")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText(
            "Hi ha canvis no desats a la capa d'unitats.\n\n"
            "Què vols fer abans de tancar?"
        )
        btn_save = msg.addButton("Desar i tancar", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Descartar i tancar", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton("Cancel·lar", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_cancel)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_cancel:
            return False
        if clicked == btn_save:
            if not lyr.commitChanges():
                errs = "; ".join(lyr.commitErrors())
                QMessageBox.critical(
                    self, "Error desant",
                    f"No s'han pogut desar els canvis:\n{errs}"
                )
                return False
        else:  # Descartar
            lyr.rollBack()
        self.iface.mapCanvas().refresh()
        return True

    def closeEvent(self, event):
        if not self._confirm_close_with_edits():
            event.ignore()
            return
        # Avisar si tanquem sense haver acabat totes les finques
        total = len(self._finques)
        if total > 1 and 0 < self._current < total:
            pendents = total - self._current
            reply = QMessageBox.question(
                self,
                "Digitalització incompleta",
                f"Encara queden {pendents} finca{'s' if pendents != 1 else ''} "
                f"per digitalitzar ({self._current} de {total} completades).\n\n"
                "Estàs segur que vols tancar l'assistent?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        self._disconnect_feature_added()
        self._clear_highlight()
        self._restore_digitizing_style()
        self._restore_snapping()
        from .iof_utils import restaurar_opacitat_capes_iof
        restaurar_opacitat_capes_iof()
        super().closeEvent(event)

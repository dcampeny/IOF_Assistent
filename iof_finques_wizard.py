# -*- coding: utf-8 -*-
"""
IOF Assistent — Assistent per omplir les dades de la capa IOF_Finques.

Per a cada polígon de la capa demana:
  - Codi de finca (numèric, autoincremental des d'1)
  - Comarca (desplegable)
  - Municipi (desplegable dinàmic segons comarca)
  - Superfície (calculada automàticament en ha amb 2 decimals, no editable)
"""

from qgis.PyQt.QtCore import QObject, QEvent
from .iof_utils import (
    geom_sense_forats as _geom_sense_forats,
    find_interior_polygons,
)
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel,
    QSpinBox, QComboBox, QLineEdit, QGroupBox,
    QMessageBox, QProgressBar, QFrame
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes
)
from qgis.gui import QgsRubberBand
from qgis.PyQt.QtGui import QColor


from .municipis_catalunya import COMARQUES_MUNICIPIS

# Ordre alfabètic de comarques
COMARQUES = sorted(COMARQUES_MUNICIPIS.keys())

# Nom estàndard de la capa de finques
LAYER_NAME = "IOF_Finques"


class _ComboBlocker(QObject):
    """Instal·lat com a eventFilter en un QComboBox per bloquejar el desplegament."""

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                            QEvent.Type.MouseButtonDblClick, QEvent.Type.KeyPress,
                            QEvent.Type.Wheel, QEvent.Type.FocusIn):
            return True  # bloqueja l'event
        return False


class FinquesWizard(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("IOF Assistent — Dades de finques")
        self.setMinimumWidth(500)
        self.setWindowFlags(
            (self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint) | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )

        self._layer = None
        self._features = []   # llista de QgsFeature (finques reals)
        self._current = 0    # índex del polígon actual
        self._exclusions = []  # polígons interiors (àrees excloses, sense dades)
        # True si _load_layer() no ha trobat la capa (o l'usuari ha
        # cancel·lat): qui crea el diàleg (iof_exporter.py) ha de
        # comprovar-ho i no cridar .show() en aquest cas.
        self._cancelled = False

        # Rubber band per il·luminar el polígon actiu
        self._rubber_band = None

        # Memòria de la darrera selecció
        self._loading = False  # True durant _show_feature per evitar _mark_changed
        self._combo_blocker = _ComboBlocker()
        self._read_only = False  # True si les dades venen de l'ambit IOF
        self._last_codi = 0   # darrer codi de finca desat (0 = cap; és l'únic camp que s'hereta a la finca següent)

        self._build_ui()
        self._load_layer()
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(12)

        # Títol
        title = QLabel(
            "<b>Assistent per omplir les dades de finques</b><br>"
            "<small>Omple les dades per a cada polígon de la capa "
            f"<i>{LAYER_NAME}</i>.</small>"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "padding:8px; background:#e8f4e8; border-radius:4px;"
        )
        main.addWidget(title)

        # Indicador de polígon actual
        self._lbl_progress = QLabel()
        self._lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_progress.setStyleSheet("color:#555; font-size:12px;")
        main.addWidget(self._lbl_progress)

        # Formulari
        # Avís mode només lectura (ocult per defecte)
        self._lbl_read_only = QLabel(
            "🔒 Dades carregades des de l'àmbit IOF — només lectura."
        )
        self._lbl_read_only.setStyleSheet(
            "background:#fff3cd; color:#856404; padding:6px; "
            "border:1px solid #ffc107; border-radius:4px;"
        )
        self._lbl_read_only.setWordWrap(True)
        self._lbl_read_only.setVisible(False)
        main.addWidget(self._lbl_read_only)

        form_group = QGroupBox("Dades de la finca")
        form = QGridLayout(form_group)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        # Codi de finca
        lbl_codi = QLabel("Codi de finca *:")
        lbl_codi.setToolTip("Número identificador de la finca (enter positiu)")
        self._spin_codi = QSpinBox()
        self._spin_codi.setMinimum(1)
        self._spin_codi.setMaximum(9999)
        self._spin_codi.setFixedWidth(90)
        form.addWidget(lbl_codi, 0, 0)
        form.addWidget(self._spin_codi, 0, 1, Qt.AlignmentFlag.AlignLeft)

        # Nom de la finca
        lbl_nom = QLabel("Nom de la finca:")
        self._edit_nom = QLineEdit()
        self._edit_nom.setPlaceholderText("ex: Can Pujol, Mas del Bosc...")
        form.addWidget(lbl_nom, 1, 0)
        form.addWidget(self._edit_nom, 1, 1)
        self._edit_nom.textChanged.connect(lambda _: self._mark_changed())

        # Comarca (per afegir municipis)
        lbl_comarca = QLabel("Comarca:")
        self._combo_comarca = QComboBox()
        self._combo_comarca.addItem("(selecciona comarca...)", None)
        for c in COMARQUES:
            self._combo_comarca.addItem(c, c)
        self._combo_comarca.currentIndexChanged.connect(self._on_comarca_changed)
        form.addWidget(lbl_comarca, 2, 0)
        form.addWidget(self._combo_comarca, 2, 1)

        # Municipi (selector + botó afegir)
        lbl_municipi = QLabel("Municipi:")
        self._combo_municipi = QComboBox()
        self._combo_municipi.addItem("(selecciona primer la comarca)", None)
        self._combo_municipi.setEnabled(False)
        from qgis.PyQt.QtWidgets import QPushButton, QHBoxLayout, QWidget, QListWidget
        row_mun = QHBoxLayout()
        row_mun.setSpacing(4)
        row_mun.addWidget(self._combo_municipi)
        btn_add_mun = QPushButton("+")
        btn_add_mun.setFixedWidth(28)
        btn_add_mun.setToolTip("Afegir municipi a la llista")
        btn_add_mun.clicked.connect(self._afegir_municipi)
        row_mun.addWidget(btn_add_mun)
        w_mun = QWidget()
        w_mun.setLayout(row_mun)
        form.addWidget(lbl_municipi, 3, 0)
        form.addWidget(w_mun, 3, 1)

        # Llista de municipis seleccionats (+ botó eliminar visible, ja
        # que el doble clic i la tecla Supr no eren prou intuïtius)
        lbl_muns = QLabel("Municipis *:")
        self._list_municipis = QListWidget()
        self._list_municipis.setMinimumHeight(60)
        self._list_municipis.setMaximumHeight(90)
        self._list_municipis.setToolTip("Selecciona un municipi i prem Supr, fes doble clic, o usa el botó «−» per eliminar-lo")
        # Tecla Supr per eliminar
        self._list_municipis.keyPressEvent = self._list_municipis_key_press
        self._list_municipis.itemDoubleClicked.connect(self._eliminar_municipi_llista)
        self._list_municipis.model().rowsInserted.connect(lambda *a: self._mark_changed())
        self._list_municipis.model().rowsRemoved.connect(lambda *a: self._mark_changed())

        btn_del_mun = QPushButton("−")
        btn_del_mun.setFixedWidth(28)
        btn_del_mun.setToolTip("Eliminar el municipi seleccionat de la llista")
        btn_del_mun.clicked.connect(self._eliminar_municipi_seleccionat)
        row_llista = QHBoxLayout()
        row_llista.setSpacing(4)
        row_llista.addWidget(self._list_municipis)
        row_llista.addWidget(btn_del_mun, alignment=Qt.AlignmentFlag.AlignTop)
        w_llista = QWidget()
        w_llista.setLayout(row_llista)

        form.addWidget(lbl_muns, 4, 0)
        form.addWidget(w_llista, 4, 1)

        # Superfície (només lectura)
        lbl_sup = QLabel("Superfície (ha):")
        self._lbl_sup_val = QLabel("—")
        self._lbl_sup_val.setStyleSheet(
            "font-weight:bold; color:#1a237e; font-size:13px;"
        )
        form.addWidget(lbl_sup, 5, 0)
        form.addWidget(self._lbl_sup_val, 5, 1)

        form.setColumnStretch(1, 1)
        main.addWidget(form_group)

        # Línia separadora
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#ddd;")
        main.addWidget(sep)

        # Barra de progrés
        self._progress = QProgressBar()
        self._progress.setValue(0)
        main.addWidget(self._progress)

        # Botons de navegació i acció
        nav_layout = QHBoxLayout()

        self._btn_prev = QPushButton("◄ Anterior")
        self._btn_prev.setEnabled(False)
        self._btn_prev.clicked.connect(self._go_prev)

        self._btn_save = QPushButton("Desar")
        self._btn_save.setEnabled(False)
        self._btn_save.setStyleSheet(
            "QPushButton { background:#e65100; color:white; font-weight:bold; padding:6px 14px; }"
            "QPushButton:disabled { background:#aaa; }"
        )
        self._btn_save.clicked.connect(self._save_and_stay)

        self._btn_next = QPushButton("Següent ►")
        self._btn_next.setToolTip("Passa al següent polígon (desa automàticament si hi ha canvis)")
        self._btn_next.setStyleSheet(
            "background:#1565c0; color:white; font-weight:bold; padding:6px 14px;"
        )
        self._btn_next.clicked.connect(self._go_next)

        self._btn_finish = QPushButton("✔ Finalitzar")
        self._btn_finish.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:6px 14px;"
        )
        self._btn_finish.setVisible(False)
        self._btn_finish.clicked.connect(self._finish)

        btn_cancel = QPushButton("Cancel·lar")
        btn_cancel.clicked.connect(self.reject)

        nav_layout.addWidget(self._btn_prev)
        nav_layout.addStretch()
        nav_layout.addWidget(btn_cancel)
        nav_layout.addWidget(self._btn_save)
        nav_layout.addWidget(self._btn_next)
        nav_layout.addWidget(self._btn_finish)
        main.addLayout(nav_layout)
        main.addLayout(nav_layout)

    # ------------------------------------------------------------------
    # Lògica de càrrega
    # ------------------------------------------------------------------

    def _load_layer(self):
        """Cerca la capa IOF_Finques al projecte i carrega els polígons."""
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == LAYER_NAME and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                self._layer = lyr
                break

        if self._layer is None:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(self, LAYER_NAME, accio="omplir les dades")
            self._cancelled = True
            self.reject()
            return

        all_feats = list(self._layer.getFeatures())

        if not all_feats:
            QMessageBox.information(
                self,
                "Capa buida",
                f"La capa «{LAYER_NAME}» no conté cap polígon.\n\n"
                "Digitalitza primer les finques i torna a obrir l'assistent."
            )
            self._cancelled = True
            self.reject()
            return

        # Classificar polígons: els que estan completament dins d'un altre
        # són exclusions (àrees excloses de la finca) i no reben dades.
        exclusion_ids = find_interior_polygons(all_feats)

        from qgis.core import QgsMessageLog, Qgis
        QgsMessageLog.logMessage(
            f"Finques: {len(all_feats)} polígons, "
            f"{len(exclusion_ids)} exclusions (id={exclusion_ids})",
            "IOF Assistent", Qgis.MessageLevel.Info
        )

        self._features = [f for f in all_feats if f.id() not in exclusion_ids]
        self._exclusions = [f for f in all_feats if f.id() in exclusion_ids]

        # Buidar les dades dels polígons d'exclusió (sense finca, municipi ni superfície)
        if self._exclusions:
            self._clear_exclusion_data(self._exclusions)

        # Detecta si les dades venen de l'àmbit IOF (tots els camps omplerts)
        camps = ["codi_finca", "nom_finca", "municipi", "comarca", "superficie"]
        fields_names = self._layer.fields().names()
        self._read_only = self._features and all(
            all(
                str(feat[camp] or "").strip() not in ("", "NULL")
                for camp in camps if camp in fields_names
            )
            for feat in self._features
        )

        if self._read_only:
            self._set_read_only_mode(True)

        self._show_feature(0)

    def _clear_exclusion_data(self, exclusions):
        """
        Buida els camps de dades dels polígons d'exclusió:
        codi_finca, municipi i superficie queden a NULL.
        """
        self._layer.startEditing()
        fields = self._layer.fields().names()
        for feat in exclusions:
            fid = feat.id()
            for camp in ["codi_finca", "municipi", "superficie"]:
                if camp in fields:
                    self._layer.changeAttributeValue(
                        fid,
                        self._layer.fields().indexOf(camp),
                        None
                    )
        if not self._layer.commitChanges():
            self._layer.rollBack()

    # ------------------------------------------------------------------
    # Navegació entre polígons
    # ------------------------------------------------------------------

    def _show_feature(self, idx):
        """Mostra les dades del polígon a la posició idx."""
        self._current = idx
        feat = self._features[idx]
        total = len(self._features)

        # Bloqueja senyals durant la càrrega per evitar activar _mark_changed
        self._loading = True
        self._edit_nom.blockSignals(True)
        self._combo_comarca.blockSignals(True)
        self._combo_municipi.blockSignals(True)

        # Progrés
        self._lbl_progress.setText(
            f"Polígon {idx + 1} de {total}"
        )
        self._progress.setMaximum(total)
        self._progress.setValue(idx + 1)

        # Codi de finca:
        # - Si el polígon té valor desat → mostrar-lo
        # - Si no → mantenir el darrer codi (l'usuari el canviarà si cal)
        codi_val = feat["codi_finca"]
        try:
            codi_int = int(codi_val) if codi_val and codi_val == codi_val else 0
        except (TypeError, ValueError):
            codi_int = 0

        if codi_int > 0:
            self._spin_codi.setValue(codi_int)
        else:
            # _last_codi = 0 el primer cop → proposa 1; després manté el valor anterior
            self._spin_codi.setValue(max(1, self._last_codi))

        # Nom de la finca: NO s'hereta de la finca anterior, sempre en blanc
        # si el polígon no en té un de desat.
        nom_val = ""
        if "nom_finca" in feat.fields().names():
            v = feat["nom_finca"]
            if v and v == v:
                nom_val = str(v).strip()
        self._edit_nom.setText(nom_val)

        # Comarca i municipi: NO s'hereten de la finca anterior, sempre en
        # blanc si el polígon no en té un de desat (només el codi de finca
        # es manté d'una finca a la següent).
        municipi_val = ""
        if "municipi" in feat.fields().names():
            v = feat["municipi"]
            if v and v == v:
                municipi_val = str(v).strip()

        if municipi_val:
            # El polígon ja té municipi desat: restaurar-lo
            self._restore_municipi(municipi_val)
        else:
            # Polígon nou sense dades: deixar en blanc
            self._restore_municipi("")

        # Superfície calculada
        geom = feat.geometry()
        if geom and not geom.isEmpty():
            area_ha = round(geom.area() / 10000, 2)
            s = "{:,.2f}".format(area_ha).replace(",", "X").replace(".", "·").replace("X", ".")
            s = s.replace("·", ",")
            self._lbl_sup_val.setText(s + " ha")
        else:
            self._lbl_sup_val.setText("(sense geometria)")

        # Desbloqueja senyals i desactiva Desar (no hi ha canvis nous)
        self._loading = False
        self._edit_nom.blockSignals(False)
        self._combo_comarca.blockSignals(False)
        self._combo_municipi.blockSignals(False)
        self._reset_changed()

        # Ressaltar el polígon actiu al mapa
        self._highlight_feature(feat)

        # Botons de navegació
        self._btn_prev.setEnabled(idx > 0)
        is_last = (idx == total - 1)
        self._btn_next.setVisible(not is_last)
        self._btn_finish.setVisible(is_last)

    def _set_read_only_mode(self, read_only):
        """Activa/desactiva el mode només lectura del formulari."""
        from qgis.PyQt.QtWidgets import QAbstractItemView
        self._spin_codi.setReadOnly(read_only)
        self._spin_codi.setEnabled(not read_only)
        self._edit_nom.setReadOnly(read_only)
        self._edit_nom.setStyleSheet(
            "background:#f0f0f0; color:#555;" if read_only else ""
        )
        # Bloqueja comarca i municipi completament
        self._combo_comarca.setEnabled(not read_only)
        self._combo_comarca.setEditable(False)
        self._combo_municipi.setEditable(False)
        self._combo_comarca.setEditable(False)
        from qgis.PyQt.QtCore import Qt
        estil_ro = "background:#f0f0f0; color:#555;"
        if read_only:
            self._combo_municipi.installEventFilter(self._combo_blocker)
            self._combo_comarca.installEventFilter(self._combo_blocker)
            self._combo_municipi.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._combo_comarca.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._combo_municipi.setStyleSheet(estil_ro)
            self._combo_comarca.setStyleSheet(estil_ro)
        else:
            self._combo_municipi.removeEventFilter(self._combo_blocker)
            self._combo_comarca.removeEventFilter(self._combo_blocker)
            self._combo_municipi.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self._combo_comarca.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self._combo_municipi.setEnabled(True)
            self._combo_comarca.setEnabled(True)
            self._combo_municipi.setStyleSheet("")
            self._combo_comarca.setStyleSheet("")
        # Boto afegir municipi
        from qgis.PyQt.QtWidgets import QPushButton
        for child in self._combo_municipi.parent().findChildren(QPushButton):
            child.setEnabled(not read_only)
        # Llista de municipis
        self._list_municipis.setEnabled(not read_only)
        if read_only:
            self._list_municipis.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        else:
            self._list_municipis.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._btn_save.setVisible(not read_only)
        self._lbl_read_only.setVisible(read_only)

    def _mark_changed(self):
        """Activa el boto Desar quan es fa algun canvi."""
        if getattr(self, '_loading', False):
            return
        if hasattr(self, '_btn_save'):
            self._btn_save.setEnabled(True)

    def _reset_changed(self):
        """Desactiva el boto Desar."""
        if hasattr(self, '_btn_save'):
            self._btn_save.setEnabled(False)

    def _save_and_stay(self):
        """Desa els canvis sense passar al seguent poligon."""
        if not self._validate():
            return
        self._save_current()
        self._reset_changed()

    def _list_municipis_key_press(self, event):
        """Gestiona tecles a la llista de municipis."""
        from qgis.PyQt.QtCore import Qt
        from qgis.PyQt.QtWidgets import QListWidget
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._eliminar_municipi_seleccionat()
        else:
            QListWidget.keyPressEvent(self._list_municipis, event)

    def _eliminar_municipi_seleccionat(self):
        """Elimina el municipi seleccionat a la llista (tecla Supr)."""
        row = self._list_municipis.currentRow()
        if row >= 0:
            self._list_municipis.takeItem(row)
            self._mark_changed()

    def _eliminar_municipi_llista(self, item):
        """Elimina un municipi de la llista amb doble clic."""
        row = self._list_municipis.row(item)
        if row >= 0:
            self._list_municipis.takeItem(row)
            self._mark_changed()

    def _afegir_municipi(self):
        """Afegeix el municipi seleccionat a la llista."""
        mun = self._combo_municipi.currentData()
        if not mun:
            return
        # Comprova si ja existeix a la llista (compara normalitzat)
        mun_lower = mun.lower().strip()
        for i in range(self._list_municipis.count()):
            if self._list_municipis.item(i).data(32).lower().strip() == mun_lower:
                return
        from qgis.PyQt.QtWidgets import QListWidgetItem
        item = QListWidgetItem(mun)
        item.setData(32, mun)  # Qt.UserRole = 32
        self._list_municipis.addItem(item)

    def _get_municipis_seleccionats(self):
        """Retorna els municipis de la llista com a string separat per comes."""
        muns = [self._list_municipis.item(i).data(32)
                for i in range(self._list_municipis.count())]
        return ", ".join(muns)

    def _restore_municipi(self, municipi_str, keep_comarca=False):
        """
        Selecciona comarca i municipi als desplegables.
        Si el municipi_str conté múltiples municipis (separats per coma),
        busca la comarca del primer i selecciona el primer municipi.

        Si `keep_comarca` és True, NO es toca la comarca ja seleccionada
        al combo (es fa servir des de _restore_comarca_only(), per no
        sobreescriure una comarca ja fixada amb la que es dedueix del
        municipi de la finca anterior).
        """
        if not municipi_str:
            if not keep_comarca:
                self._combo_comarca.setCurrentIndex(0)
            self._populate_municipis(
                self._combo_comarca.currentData() if keep_comarca else None
            )
            # BUG corregit: aquest "return" precoç no arribava mai a
            # netejar self._list_municipis (només ho feia la resta de la
            # funció, més avall). Com que aquesta és exactament la
            # branca que es crida per a un polígon nou sense municipi
            # desat, la llista es quedava amb el contingut de la finca
            # anterior mostrada — semblava una herència de dades, però
            # les dades reals ja estaven correctament buides; només la
            # interfície no s'actualitzava.
            self._list_municipis.clear()
            return

        # Agafa el primer municipi si n'hi ha més d'un
        primer_municipi = municipi_str.split(",")[0].strip()

        if keep_comarca:
            comarca_trobada = self._combo_comarca.currentData()
        else:
            # Busca la comarca del primer municipi
            comarca_trobada = None
            for comarca, munis in COMARQUES_MUNICIPIS.items():
                if primer_municipi in munis:
                    comarca_trobada = comarca
                    break

            # Si no troba el municipi exacte, prova normalitzant accents
            if not comarca_trobada:
                import unicodedata as _udn

                def _norm(s):
                    s = _udn.normalize("NFD", s.lower())
                    return "".join(c for c in s if _udn.category(c) != "Mn")
                primer_norm = _norm(primer_municipi)
                for comarca, munis in COMARQUES_MUNICIPIS.items():
                    for m in munis:
                        if _norm(m) == primer_norm:
                            comarca_trobada = comarca
                            primer_municipi = m  # usa el nom exacte de la llista
                            break
                    if comarca_trobada:
                        break

            self._combo_comarca.blockSignals(True)
            if comarca_trobada:
                idx = self._combo_comarca.findData(comarca_trobada)
                self._combo_comarca.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                self._combo_comarca.setCurrentIndex(0)
            self._combo_comarca.blockSignals(False)

        self._populate_municipis(comarca_trobada)

        # Selecciona el primer municipi al combo
        idx = self._combo_municipi.findData(primer_municipi)
        if idx >= 0:
            self._combo_municipi.setCurrentIndex(idx)

        # Omple la llista amb tots els municipis normalitzats
        from qgis.PyQt.QtWidgets import QListWidgetItem
        import unicodedata as _udn2

        def _norm2(s):
            s = _udn2.normalize("NFD", s.lower())
            return "".join(c for c in s if _udn2.category(c) != "Mn")
        # Mapa invers normalitzat
        mun_normalitzat = {}
        for _com, _muns in COMARQUES_MUNICIPIS.items():
            for _m in _muns:
                mun_normalitzat[_norm2(_m)] = _m

        self._list_municipis.clear()
        for m in [m.strip() for m in municipi_str.split(",") if m.strip()]:
            # Usa el nom correcte de la llista si existeix
            nom_correcte = mun_normalitzat.get(_norm2(m), m)
            item = QListWidgetItem(nom_correcte)
            item.setData(32, nom_correcte)
            self._list_municipis.addItem(item)

    def _restore_comarca_only(self, comarca_str, municipi_str=None):
        """
        Selecciona la comarca (amb prioritat sobre qualsevol deducció a
        partir del municipi anterior) i, si els municipis indicats
        pertanyen a aquesta comarca, els selecciona també.

        Si l'usuari ha canviat de comarca respecte a la finca anterior
        sense triar encara un municipi nou, els municipis heretats ja
        no pertanyen a la comarca actual: es descarten en lloc de
        forçar la comarca antiga de nou (bug reportat: en canviar de
        comarca, la finca següent recuperava la comarca antiga perquè
        _restore_municipi() la tornava a deduir del municipi heretat).
        """
        self._combo_comarca.blockSignals(True)
        idx = self._combo_comarca.findData(comarca_str)
        self._combo_comarca.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo_comarca.blockSignals(False)

        self._populate_municipis(comarca_str)

        if not municipi_str:
            return

        munis_de_la_comarca = set(COMARQUES_MUNICIPIS.get(comarca_str, []))

        import unicodedata as _udn3

        def _norm3(s):
            s = _udn3.normalize("NFD", s.lower())
            return "".join(c for c in s if _udn3.category(c) != "Mn")
        munis_norm = {_norm3(m) for m in munis_de_la_comarca}

        municipis_valids = [
            m.strip() for m in municipi_str.split(",")
            if m.strip() and _norm3(m.strip()) in munis_norm
        ]
        if municipis_valids:
            self._restore_municipi(", ".join(municipis_valids), keep_comarca=True)

    def _highlight_feature(self, feat):
        """Il·lumina el polígon actiu amb un rubber band groc i centra el mapa."""
        canvas = self.iface.mapCanvas()

        # Reutilitzar el rubber band existent o crear-ne un de nou
        if self._rubber_band is None:
            self._rubber_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.PolygonGeometry)

        self._rubber_band.setColor(QColor(255, 220, 0, 220))      # groc viu, semitransparent
        self._rubber_band.setFillColor(QColor(255, 235, 0, 60))   # groc molt transparent
        self._rubber_band.setWidth(4)

        geom = feat.geometry()
        if geom and not geom.isEmpty():
            self._rubber_band.setToGeometry(
                _geom_sense_forats(geom), self._layer
            )
            self._rubber_band.show()
            geom.boundingBox()
            canvas.refresh()

        # Selecció nativa per complementar la visualització
        self._layer.selectByIds([feat.id()])

    # ------------------------------------------------------------------
    # Desplegables dinàmics
    # ------------------------------------------------------------------

    def _on_comarca_changed(self, _):
        comarca = self._combo_comarca.currentData()
        self._populate_municipis(comarca)

    def _populate_municipis(self, comarca):
        self._combo_municipi.clear()
        if not comarca:
            self._combo_municipi.addItem("(selecciona primer la comarca)", None)
            self._combo_municipi.setEnabled(False)
            return
        self._combo_municipi.setEnabled(True)
        self._combo_municipi.addItem("(selecciona municipi...)", None)
        for m in sorted(COMARQUES_MUNICIPIS.get(comarca, [])):
            self._combo_municipi.addItem(m, m)

    # ------------------------------------------------------------------
    # Validació i desament
    # ------------------------------------------------------------------

    def _validate(self):
        """Retorna True si el formulari és vàlid."""
        if self._list_municipis.count() == 0:
            QMessageBox.warning(self, "Camp obligatori",
                                "Afegeix almenys un municipi a la llista.\n"
                                "Selecciona comarca i municipi i prem el botó " + ".")
            return False
        return True

    def _save_current(self):
        """Desa els valors del formulari a la feature actual i actualitza la memòria."""
        feat = self._features[self._current]
        geom = feat.geometry()
        area_ha = round(geom.area() / 10000, 2) if geom and not geom.isEmpty() else 0.0

        # Guardar el codi actual com a memòria per a la finca següent
        # (únic camp que s'hereta; nom/comarca/municipi sempre comencen buits)
        self._last_codi = self._spin_codi.value()

        self._layer.startEditing()
        fid = feat.id()
        self._layer.changeAttributeValue(
            fid,
            self._layer.fields().indexOf("codi_finca"),
            self._spin_codi.value()
        )
        if self._layer.fields().indexOf("nom_finca") >= 0:
            self._layer.changeAttributeValue(
                fid,
                self._layer.fields().indexOf("nom_finca"),
                self._edit_nom.text().strip() or None
            )
        if self._layer.fields().indexOf("comarca") >= 0:
            self._layer.changeAttributeValue(
                fid,
                self._layer.fields().indexOf("comarca"),
                self._combo_comarca.currentData() or None
            )
        self._layer.changeAttributeValue(
            fid,
            self._layer.fields().indexOf("municipi"),
            self._get_municipis_seleccionats() or ""
        )
        self._layer.changeAttributeValue(
            fid,
            self._layer.fields().indexOf("superficie"),
            area_ha
        )
        if not self._layer.commitChanges():
            errs = "; ".join(self._layer.commitErrors())
            self._layer.rollBack()
            QMessageBox.critical(
                self, "Error desant",
                f"No s'han pogut desar les dades de la finca:\n{errs}"
            )
        else:
            try:
                from .iof_format_dialog import _apply_preview_labels
                _apply_preview_labels(
                    self._layer,
                    'CASE '
                    'WHEN "codi_finca" IS NOT NULL AND "superficie" IS NOT NULL '
                    "THEN 'Finca ' || to_string(\"codi_finca\") || '\\n' || "
                    'format_number("superficie", 2) || \' ha\' '
                    'WHEN "codi_finca" IS NOT NULL '
                    "THEN 'Finca ' || to_string(\"codi_finca\") "
                    'WHEN "superficie" IS NOT NULL '
                    'THEN format_number("superficie", 2) || \' ha\' '
                    'ELSE NULL END',
                    'superficie'
                )
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass

    # ------------------------------------------------------------------
    # Accions dels botons
    # ------------------------------------------------------------------

    def _go_prev(self):
        if self._current > 0:
            self._show_feature(self._current - 1)

    def _go_next(self):
        if self._btn_save.isEnabled():
            # Hi ha canvis pendents: desa automaticament abans de passar
            if not self._validate():
                return
            self._save_current()
            self._reset_changed()
        # Sense canvis o despres de desar: passa al seguent
        if self._current < len(self._features) - 1:
            self._show_feature(self._current + 1)

    def _clear_highlight(self):
        """Oculta el rubber band i deselecciona tots els polígons de la capa."""
        if self._rubber_band is not None:
            self._rubber_band.hide()
            # Eliminar-lo completament del canvas per no deixar residus
            self._rubber_band.reset(QgsWkbTypes.GeometryType.PolygonGeometry)
            self._rubber_band = None
        if self._layer:
            self._layer.removeSelection()
        self.iface.mapCanvas().refresh()

    def _finish(self):
        # En mode nomes lectura: tanca sense desar ni mostrar avis
        if getattr(self, '_read_only', False):
            self._clear_highlight()
            self.accept()
            return
        if not self._validate():
            return
        self._save_current()
        self._clear_highlight()
        n_finques = len(self._features)
        n_exclusions = len(self._exclusions)
        msg = (
            f"S'han desat les dades de {n_finques} "
            f"{'finques' if n_finques != 1 else 'finca'}."
        )
        if n_exclusions > 0:
            msg += (
                f"\n\n{n_exclusions} polígon"
                f"{'s' if n_exclusions != 1 else ''} interior"
                f"{'s' if n_exclusions != 1 else ''} "
                f"{'han estat identificats' if n_exclusions != 1 else 'ha estat identificat'} "
                f"com a àrea{'es' if n_exclusions != 1 else ''} exclosa"
                f"{'es' if n_exclusions != 1 else ''} i s'han deixat sense dades "
                f"(sense codi de finca, municipi ni superfície)."
            )
        msg += (
            "\n\nPots revisar i editar les dades directament des de la "
            "taula d'atributs de la capa si ho necessites."
        )
        QMessageBox.information(self, "Assistent completat", msg)
        self.accept()

    def reject(self):
        self._clear_highlight()
        super().reject()

    def closeEvent(self, event):
        self._clear_highlight()
        super().closeEvent(event)

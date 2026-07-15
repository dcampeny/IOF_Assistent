# -*- coding: utf-8 -*-
"""
IOF Assistent — Omplir camps de IOF_Camins.

Per a cada camí demana:
  - Tipus de vial (PR, PM, SC, DB)
  - Estat (E=Existent, P=Projectat)

El codi s'assigna automàticament (tipus + número seqüencial + estat)
i la longitud es calcula automàticament de la geometria.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton,
    QGroupBox, QMessageBox, QProgressBar, QFrame
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes
)
from qgis.gui import QgsRubberBand

LAYER_CAMINS = "IOF_Camins"

TIPUS_VIAL = [
    ("PR", "PR — Camí principal"),
    ("PM", "PM — Camí primari"),
    ("SC", "SC — Camí secundari"),
    ("DB", "DB — Camí de desembosc"),
]

ESTATS = [
    ("E", "E — Existent"),
    ("P", "P — Projectat"),
]


def _get_layer():
    for lyr in QgsProject.instance().mapLayers().values():
        if (isinstance(lyr, QgsVectorLayer) and lyr.name() == LAYER_CAMINS and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.LineGeometry):
            return lyr
    return None


def _build_used_nums(layer):
    """
    Escaneja la capa i retorna un dict {(tipus, estat): set(números)}
    amb tots els números seqüencials ja usats per cada combinació tipus+estat.
    Existent (E) i Projectat (P) són independents i comencen des de l'1.
    """
    used = {}
    for feat in layer.getFeatures():
        codi = feat["codi_cami"]
        if not codi or not isinstance(codi, str):
            continue
        for tipus in ("PR", "PM", "SC", "DB"):
            if codi.startswith(tipus):
                estat = codi[-1] if codi[-1] in ("E", "P") else "E"
                try:
                    num = int(codi[len(tipus):len(tipus) + 2])
                    used.setdefault((tipus, estat), set()).add(num)
                except (ValueError, IndexError):
                    pass
                break
    return used


def _genera_codi(layer, tipus, estat, used_by_tipus=None):
    """
    Genera el codi del camí: tipus + número seqüencial de 2 dígits + estat.
    Existent (E) i Projectat (P) tenen numeració independent des de l'1:
    PR01E, PR02E... i PR01P, PR02P... per separat.
    """
    if used_by_tipus is None:
        used_by_tipus = _build_used_nums(layer)
    existing = used_by_tipus.get((tipus, estat), set())

    n = 1
    while n in existing:
        n += 1
    used_by_tipus.setdefault((tipus, estat), set()).add(n)

    return f"{tipus}{n:02d}{estat}"


class CaminsWizard(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self._layer = None
        self._features = []
        self._current = 0
        self._rubber_band = None
        self._finca_union = False  # cache de la unió de finques (False = no calculat)
        self._used_nums = None   # cache {tipus: set(números)} de codis usats
        # True si _load_layer() no ha trobat la capa: qui crea el
        # diàleg (iof_exporter.py) ha de comprovar-ho i no cridar
        # .show() en aquest cas.
        self._cancelled = False

        self.setWindowTitle("IOF Assistent — Omplir camps de camins")
        self.setWindowFlags(
            (self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint) | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(440)

        self._build_ui()
        self._load_layer()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setSpacing(10)

        title = QLabel("<b>Omplir camps de la capa IOF_Camins</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "padding:8px; background:#fff3e0; border-radius:4px; font-weight:bold;"
        )
        main.addWidget(title)

        self._lbl_progress = QLabel()
        self._lbl_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_progress.setStyleSheet("color:#555; font-size:12px;")
        main.addWidget(self._lbl_progress)

        # Formulari
        form_group = QGroupBox("Dades del camí")
        form = QGridLayout(form_group)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        # Tipus de vial
        lbl_tipus = QLabel("Tipus de vial *:")
        self._combo_tipus = QComboBox()
        for codi, desc in TIPUS_VIAL:
            nom = desc.split(' — ')[1]  # Només el nom, sense el codi
            self._combo_tipus.addItem(nom, codi)
        self._combo_tipus.currentIndexChanged.connect(self._update_codi_preview)
        form.addWidget(lbl_tipus, 0, 0)
        form.addWidget(self._combo_tipus, 0, 1)

        # Estat
        lbl_estat = QLabel("Estat *:")
        self._combo_estat = QComboBox()
        for codi, desc in ESTATS:
            nom = desc.split(' — ')[1]  # Només el nom, sense el codi
            self._combo_estat.addItem(nom, codi)
        self._combo_estat.currentIndexChanged.connect(self._update_codi_preview)
        form.addWidget(lbl_estat, 1, 0)
        form.addWidget(self._combo_estat, 1, 1)

        # Codi (calculat automàticament)
        lbl_codi = QLabel("Codi assignat:")
        self._lbl_codi_val = QLabel("—")
        self._lbl_codi_val.setStyleSheet(
            "font-weight:bold; color:#1a237e; font-size:13px;"
        )
        form.addWidget(lbl_codi, 2, 0)
        form.addWidget(self._lbl_codi_val, 2, 1)

        # Longitud (calculada automàticament)
        lbl_long = QLabel("Longitud total (m):")
        self._lbl_long_val = QLabel("—")
        self._lbl_long_val.setStyleSheet(
            "font-weight:bold; color:#2e7d32; font-size:13px;"
        )
        form.addWidget(lbl_long, 3, 0)
        form.addWidget(self._lbl_long_val, 3, 1)

        lbl_long_iof = QLabel("Longitud dins IOF (m):")
        self._lbl_long_iof_val = QLabel("—")
        self._lbl_long_iof_val.setStyleSheet(
            "font-weight:bold; color:#1565c0; font-size:13px;"
        )
        form.addWidget(lbl_long_iof, 4, 0)
        form.addWidget(self._lbl_long_iof_val, 4, 1)

        main.addWidget(form_group)

        # Barra de progrés
        self._progress = QProgressBar()
        main.addWidget(self._progress)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#ddd;")
        main.addWidget(sep)

        # Botons
        nav = QHBoxLayout()
        self._btn_prev = QPushButton("◀ Anterior")
        self._btn_prev.setEnabled(False)
        self._btn_prev.clicked.connect(self._go_prev)

        self._btn_next = QPushButton("Desar i continuar ▶")
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

        nav.addWidget(self._btn_prev)
        nav.addStretch()
        nav.addWidget(btn_cancel)
        nav.addWidget(self._btn_next)
        nav.addWidget(self._btn_finish)
        main.addLayout(nav)

    # ------------------------------------------------------------------
    # Càrrega
    # ------------------------------------------------------------------

    def _load_layer(self):
        self._layer = _get_layer()
        if self._layer is None:
            from .iof_utils import avisa_capa_no_trobada
            avisa_capa_no_trobada(self, LAYER_CAMINS, accio="omplir les dades")
            self._cancelled = True
            self.reject()
            return

        self._features = list(self._layer.getFeatures())
        if not self._features:
            QMessageBox.information(
                self, "Capa buida",
                f"La capa «{LAYER_CAMINS}» no conté cap camí.\n"
                "Digitalitza els camins primer."
            )
            self._cancelled = True
            self.reject()
            return

        # Renumerar des de zero: buidar codis existents perquè
        # _genera_codi assigni correlativament des de l'1
        self._used_nums = {}
        idx_codi = self._layer.fields().indexOf("codi_cami")
        if idx_codi >= 0:
            self._layer.startEditing()
            for feat in self._features:
                self._layer.changeAttributeValue(feat.id(), idx_codi, None)
            self._layer.commitChanges()
            # Recarregar features amb codis buits
            self._features = list(self._layer.getFeatures())

        self._show_feature(0)

    # ------------------------------------------------------------------
    # Mostrar feature
    # ------------------------------------------------------------------

    def _show_feature(self, idx):
        self._current = idx
        feat = self._features[idx]
        total = len(self._features)

        self._lbl_progress.setText(f"Camí {idx + 1} de {total}")
        self._progress.setMaximum(total)
        self._progress.setValue(idx + 1)

        # Ressaltar al mapa
        self._highlight(feat.geometry())

        # Restaurar valors existents si ja s'han omplert
        tipus_val = feat["tipus_vial"]
        if tipus_val and tipus_val == tipus_val:
            idx_t = self._combo_tipus.findData(str(tipus_val).strip())
            if idx_t >= 0:
                self._combo_tipus.setCurrentIndex(idx_t)

        estat_val = feat["estat"]
        if estat_val and estat_val == estat_val:
            idx_e = self._combo_estat.findData(str(estat_val).strip())
            if idx_e >= 0:
                self._combo_estat.setCurrentIndex(idx_e)

        # Calcular longituds
        geom = feat.geometry()
        long_total = round(geom.length(), 2) if geom and not geom.isEmpty() else 0.0
        self._lbl_long_val.setText(f"{long_total:.2f} m")

        # Longitud dins de IOF_Finques
        long_iof = self._calc_longitud_dins_finca(geom)
        self._lbl_long_iof_val.setText(f"{long_iof:.2f} m")
        self._long_iof = long_iof

        self._update_codi_preview()

        # Navegació
        self._btn_prev.setEnabled(idx > 0)
        is_last = (idx == total - 1)
        self._btn_next.setVisible(not is_last)
        self._btn_finish.setVisible(is_last)

    def _get_finca_union(self):
        """
        Retorna la unió de tots els polígons de IOF_Finques, calculada
        una sola vegada i cachejada (la geometria no canvia durant la sessió
        de l'assistent). Retorna None si no hi ha finques.
        """
        if self._finca_union is not False:
            return self._finca_union

        lyr_finques = None
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Finques" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                lyr_finques = lyr
                break

        if lyr_finques is None or lyr_finques.featureCount() == 0:
            self._finca_union = None
            return None

        poligs = [f.geometry() for f in lyr_finques.getFeatures()
                  if f.geometry() and not f.geometry().isEmpty()]
        if not poligs:
            self._finca_union = None
            return None

        finca_union = poligs[0]
        for p in poligs[1:]:
            finca_union = finca_union.combine(p)
        self._finca_union = finca_union
        return finca_union

    def _calc_longitud_dins_finca(self, geom):
        """
        Calcula la longitud del camí que cau dins del polígon de IOF_Finques.
        Usa la unió (cachejada) de tots els polígons de la finca com a màscara.
        """
        if not geom or geom.isEmpty():
            return 0.0

        finca_union = self._get_finca_union()
        if finca_union is None:
            return 0.0

        # Intersecar el camí amb la finca
        try:
            inter = geom.intersection(finca_union)
            if inter and not inter.isEmpty():
                return round(inter.length(), 2)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        return 0.0

    def _update_codi_preview(self):
        """Actualitza la previsualització del codi generat (sense consumir números)."""
        if not self._layer:
            return
        tipus = self._combo_tipus.currentData()
        estat = self._combo_estat.currentData()
        if tipus and estat:
            if self._used_nums is None:
                self._used_nums = _build_used_nums(self._layer)
            # Previsualitzar sense modificar _used_nums
            import copy
            used_temp = copy.deepcopy(self._used_nums)
            codi = _genera_codi(self._layer, tipus, estat, used_temp)
            self._lbl_codi_val.setText(codi)
        else:
            self._lbl_codi_val.setText("—")

    # ------------------------------------------------------------------
    # Desar i navegar
    # ------------------------------------------------------------------

    def _save_current(self):
        feat = self._features[self._current]
        fid = feat.id()
        tipus = self._combo_tipus.currentData()
        estat = self._combo_estat.currentData()
        if self._used_nums is None:
            self._used_nums = _build_used_nums(self._layer)
        codi = _genera_codi(self._layer, tipus, estat, self._used_nums)
        geom = feat.geometry()
        long_m = getattr(self, '_long_iof',
                         round(geom.length(), 2) if geom and not geom.isEmpty() else 0.0)

        fields = self._layer.fields().names()

        def cv(camp, val):
            if camp in fields:
                self._layer.changeAttributeValue(
                    fid, self._layer.fields().indexOf(camp), val
                )

        self._layer.startEditing()
        cv("codi_cami", codi)
        cv("tipus_vial", tipus)
        cv("estat", estat)
        cv("longitud", long_m)
        if not self._layer.commitChanges():
            errs = "; ".join(self._layer.commitErrors())
            self._layer.rollBack()
            QMessageBox.critical(
                self, "Error desant",
                f"No s'han pogut desar les dades del camí:\n{errs}"
            )
        else:
            # _genera_codi ja ha actualitzat _used_nums a la línia de dalt
            try:
                from .iof_format_dialog import _apply_preview_labels
                _apply_preview_labels(
                    self._layer,
                    'COALESCE("codi_cami", \'\') || \'\\n\' ||'
                    ' format_number("longitud", 2) || \' m\'',
                    'codi_cami'
                )
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass

    def _go_prev(self):
        if self._current > 0:
            self._show_feature(self._current - 1)

    def _go_next(self):
        self._save_current()
        if self._current < len(self._features) - 1:
            self._show_feature(self._current + 1)

    def _finish(self):
        self._save_current()
        self._clear_highlight()
        n = len(self._features)
        QMessageBox.information(
            self, "Completat",
            f"S'han desat les dades de {n} camí{'ns' if n != 1 else ''}."
        )
        self.accept()

    # ------------------------------------------------------------------
    # Rubber band
    # ------------------------------------------------------------------

    def _highlight(self, geom):
        canvas = self.iface.mapCanvas()
        if self._rubber_band is None:
            self._rubber_band = QgsRubberBand(canvas, QgsWkbTypes.GeometryType.LineGeometry)
        self._rubber_band.setColor(QColor(255, 165, 0, 220))
        self._rubber_band.setWidth(4)
        if geom and not geom.isEmpty():
            self._rubber_band.setToGeometry(geom, self._layer)
            self._rubber_band.show()
            geom.boundingBox()
            canvas.refresh()

    def _clear_highlight(self):
        if self._rubber_band is not None:
            self._rubber_band.hide()
            self._rubber_band.reset(QgsWkbTypes.GeometryType.LineGeometry)
            self._rubber_band = None
        if self._layer:
            self._layer.removeSelection()
        self.iface.mapCanvas().refresh()

    def reject(self):
        self._clear_highlight()
        super().reject()

    def closeEvent(self, event):
        self._clear_highlight()
        super().closeEvent(event)

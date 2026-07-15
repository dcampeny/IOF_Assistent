# -*- coding: utf-8 -*-
"""
IOF Assistent — Omplir camps de IOF_Infraestructures_PI.

Per a cada infraestructura demana:
  - Tipus (LD = Obertura de línia de defensa)
  - Estat (E = Existent, P = Projectat)

El codi s'assigna automàticament (tipus + número seqüencial + estat)
i la superfície es calcula automàticament de la geometria.
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

LAYER_INFRA = "IOF_Infraestructures_PI"

TIPUS_INFRA = [
    ("LD", "LD — Obertura de línia de defensa"),
]

ESTATS = [
    ("E", "E — Existent"),
    ("P", "P — Projectat"),
]


def _get_layer():
    for lyr in QgsProject.instance().mapLayers().values():
        if (isinstance(lyr, QgsVectorLayer) and lyr.name() == LAYER_INFRA and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
            return lyr
    return None


def _build_used_nums(layer):
    used = {}
    for feat in layer.getFeatures():
        codi = feat["codi_infra"]
        if not codi or not isinstance(codi, str):
            continue
        for tipus in ("LD",):
            if codi.startswith(tipus):
                try:
                    num = int(codi[len(tipus):len(tipus) + 2])
                    used.setdefault(tipus, set()).add(num)
                except (ValueError, IndexError):
                    pass
                break
    return used


def _genera_codi(layer, tipus, estat, used_by_tipus=None):
    if used_by_tipus is None:
        used_by_tipus = _build_used_nums(layer)
    used = used_by_tipus.get(tipus, set())
    num = 1
    while num in used:
        num += 1
    used_by_tipus.setdefault(tipus, set()).add(num)
    return f"{tipus}{num:02d}{estat}"


class InfraWizard(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self._layer = None
        self._features = []
        self._current = 0
        self._highlight = None
        self._used_nums = {}

        self.setWindowTitle("IOF Assistent — Omplir camps d'infraestructures PI")
        self.setMinimumWidth(440)
        self._build_ui()
        self._load_layer()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        lbl_title = QLabel(
            "<b>Omplir camps — Infraestructures de prevenció d'incendis</b>"
        )
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet(
            "padding:8px; background:#fce4ec; border-radius:4px;"
        )
        layout.addWidget(lbl_title)

        # Barra de progrés
        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setFormat("%v / %m infraestructures")
        layout.addWidget(self._progress)

        # Formulari
        form_group = QGroupBox("Dades de la infraestructura")
        form = QGridLayout(form_group)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)

        # Tipus
        form.addWidget(QLabel("Tipus *:"), 0, 0)
        self._combo_tipus = QComboBox()
        for val, desc in TIPUS_INFRA:
            self._combo_tipus.addItem(desc, val)
        self._combo_tipus.setMinimumWidth(260)
        form.addWidget(self._combo_tipus, 0, 1, 1, 3)

        # Estat
        form.addWidget(QLabel("Estat *:"), 1, 0)
        self._combo_estat = QComboBox()
        for val, desc in ESTATS:
            self._combo_estat.addItem(desc, val)
        form.addWidget(self._combo_estat, 1, 1, Qt.AlignmentFlag.AlignLeft)

        # Codi (generat automàticament)
        form.addWidget(QLabel("Codi generat:"), 2, 0)
        self._lbl_codi = QLabel("—")
        self._lbl_codi.setStyleSheet("font-weight:bold; color:#880e4f;")
        form.addWidget(self._lbl_codi, 2, 1, 1, 3)

        # Superfície calculada
        form.addWidget(QLabel("Superfície (ha):"), 3, 0)
        self._lbl_sup = QLabel("—")
        self._lbl_sup.setStyleSheet("font-weight:bold;")
        form.addWidget(self._lbl_sup, 3, 1, Qt.AlignmentFlag.AlignLeft)

        self._combo_tipus.currentIndexChanged.connect(self._update_codi_preview)
        self._combo_estat.currentIndexChanged.connect(self._update_codi_preview)

        layout.addWidget(form_group)

        # Resum últim desat
        self._lbl_resum = QLabel("")
        self._lbl_resum.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_resum.setStyleSheet("color:#2e7d32; font-style:italic;")
        layout.addWidget(self._lbl_resum)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Botons
        btn_row = QHBoxLayout()
        self._btn_prev = QPushButton("◀  Anterior")
        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_prev.setEnabled(False)
        btn_row.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Desar i continuar  ▶")
        self._btn_next.setStyleSheet(
            "background:#880e4f; color:white; font-weight:bold; padding:6px 16px;"
        )
        self._btn_next.clicked.connect(self._go_next)
        btn_row.addWidget(self._btn_next)
        layout.addLayout(btn_row)

        btn_finish = QPushButton("✔  Finalitzar")
        btn_finish.setStyleSheet(
            "background:#2e7d32; color:white; font-weight:bold; padding:6px 16px;"
        )
        btn_finish.clicked.connect(self._finish)
        layout.addWidget(btn_finish)

        btn_cancel = QPushButton("Cancel·lar")
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)

    # ------------------------------------------------------------------
    # Càrrega de capa
    # ------------------------------------------------------------------

    def _load_layer(self):
        self._layer = _get_layer()
        if self._layer is None:
            QMessageBox.warning(
                self, "Capa no trobada",
                f"No s'ha trobat la capa «{LAYER_INFRA}» al projecte.\n\n"
                "Crea primer les capes IOF des de «Crear capes IOF»."
            )
            self.reject()
            return

        feats = list(self._layer.getFeatures())
        if not feats:
            QMessageBox.information(
                self, "Sense infraestructures",
                "La capa no conté cap infraestructura.\n"
                "Digitalitza primer les infraestructures."
            )
            self.reject()
            return

        # Ordenar per àrea descendent (les més grans primer)
        feats.sort(key=lambda f: f.geometry().area() if f.geometry() else 0,
                   reverse=True)
        self._features = feats
        self._used_nums = _build_used_nums(self._layer)

        self._progress.setMaximum(len(feats))
        self._show_feature(0)

    # ------------------------------------------------------------------
    # Navegació
    # ------------------------------------------------------------------

    def _show_feature(self, idx):
        self._current = idx
        feat = self._features[idx]

        # Superfície
        area_ha = feat.geometry().area() / 10000 if feat.geometry() else 0.0
        self._lbl_sup.setText(f"{area_ha:.2f} ha")

        # Valors desats
        fields = self._layer.fields().names()
        codi_val = feat["codi_infra"] if "codi_infra" in fields else None
        if codi_val and str(codi_val).strip() and str(codi_val) != "NULL":
            # Recuperar tipus i estat del codi desat
            codi_str = str(codi_val).strip()
            for i, (val, _) in enumerate(TIPUS_INFRA):
                if codi_str.startswith(val):
                    self._combo_tipus.setCurrentIndex(i)
                    estat = codi_str[-1] if codi_str[-1] in ("E", "P") else "E"
                    for j, (ev, _) in enumerate(ESTATS):
                        if ev == estat:
                            self._combo_estat.setCurrentIndex(j)
                            break
                    break
        else:
            self._combo_tipus.setCurrentIndex(0)
            self._combo_estat.setCurrentIndex(0)

        self._update_codi_preview()
        self._highlight_feature(feat)

        # Progrés i botons
        self._progress.setValue(idx + 1)
        self._btn_prev.setEnabled(idx > 0)
        is_last = (idx >= len(self._features) - 1)
        self._btn_next.setText(
            "Desar i continuar  ▶" if not is_last else "Desar  ✔"
        )
        self._lbl_resum.setText("")

    def _update_codi_preview(self):
        tipus = self._combo_tipus.currentData()
        estat = self._combo_estat.currentData()
        # Mostrar previsualització sense consumir el número
        used = self._used_nums.get(tipus, set())
        num = 1
        while num in used:
            num += 1
        self._lbl_codi.setText(f"{tipus}{num:02d}{estat}  (provisional)")

    def _go_next(self):
        if not self._save_current():
            return
        if self._current < len(self._features) - 1:
            self._show_feature(self._current + 1)
        else:
            self._finish()

    def _go_prev(self):
        if self._current > 0:
            self._show_feature(self._current - 1)

    # ------------------------------------------------------------------
    # Desament
    # ------------------------------------------------------------------

    def _save_current(self):
        feat = self._features[self._current]
        lyr = self._layer
        fields = lyr.fields().names()

        tipus = self._combo_tipus.currentData()
        estat = self._combo_estat.currentData()

        # Comprovar si ja té codi (no sobreescriure número)
        codi_existent = feat["codi_infra"] if "codi_infra" in fields else None
        if codi_existent and str(codi_existent).strip() and \
                str(codi_existent) != "NULL":
            codi = str(codi_existent).strip()
            # Actualitzar estat si ha canviat
            codi = codi[:-1] + estat
        else:
            codi = _genera_codi(lyr, tipus, estat, self._used_nums)

        area_ha = feat.geometry().area() / 10000 if feat.geometry() else 0.0

        def cv(field, val):
            if field in fields:
                lyr.changeAttributeValue(
                    feat.id(), lyr.fields().indexOf(field), val)

        lyr.startEditing()
        cv("codi_infra", codi)
        cv("sup_infra", round(area_ha, 2))

        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error", f"No s'ha pogut desar:\n{errs}")
            return False

        self._lbl_resum.setText(f"✔  {codi}  ({area_ha:.2f} ha) — desat")
        self._lbl_codi.setText(codi)
        return True

    # ------------------------------------------------------------------
    # Finalitzar
    # ------------------------------------------------------------------

    def _finish(self):
        self._clear_highlight()
        n = len(self._features)
        QMessageBox.information(
            self, "Fet",
            f"S'han processat {n} infraestructura{'es' if n != 1 else ''}."
        )
        self.accept()

    # ------------------------------------------------------------------
    # Ressaltat
    # ------------------------------------------------------------------

    def _highlight_feature(self, feat):
        self._clear_highlight()
        if not feat.geometry():
            return
        canvas = self.iface.mapCanvas()
        rb = QgsRubberBand(canvas)
        rb.setColor(QColor(220, 20, 60, 180))
        rb.setWidth(3)
        rb.setToGeometry(feat.geometry(), self._layer)
        self._highlight = rb
        canvas.refresh()

    def _clear_highlight(self):
        if self._highlight:
            self.iface.mapCanvas().scene().removeItem(self._highlight)
            self._highlight = None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def reject(self):
        self._clear_highlight()
        super().reject()

    def closeEvent(self, event):
        self._clear_highlight()
        super().closeEvent(event)

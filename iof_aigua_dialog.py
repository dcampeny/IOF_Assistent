# -*- coding: utf-8 -*-
"""
iof_aigua_dialog.py — Digitalitzar punts d'aigua.

Hereta de IOFBasePointDialog i sobreescriu únicament
la lògica específica dels punts d'aigua:
  - Atributs: codi_pa (autocorrellatiu), estat (E/P)
  - La modificació recalcula el codi segons el nou estat
"""

from qgis.PyQt.QtWidgets import (
    QGroupBox, QGridLayout, QLabel, QComboBox, QLineEdit, QMessageBox,
)

from .iof_base_point_dialog import IOFBasePointDialog

ESTAT_OPCIONS = [
    ("E", "E — Existent"),
    ("P", "P — Projectat"),
]


class AiguaDialog(IOFBasePointDialog):

    LAYER_NAME = "IOF_Punts_Aigua"

    def _dialog_title(self):
        return "Digitalitzar punts d'aigua"

    def _heading_text(self):
        return "Digitalitzar punts d'aigua"

    def _info_color(self):
        return "#e1f5fe"

    def _info_border_color(self):
        return "#81d4fa"

    def _accent_color(self):
        return "#0277bd"

    def _counter_text(self, n):
        return f"Punts d'aigua afegits: {n}"

    def _feature_display_name(self, feat):
        return str(feat["codi_pa"] or feat.id())

    def _build_attr_group(self):
        grp = QGroupBox("Atributs del punt d'aigua")
        lay = QGridLayout(grp)

        lay.addWidget(QLabel("Codi PA:"), 0, 0)
        self._edit_codi = QLineEdit()
        self._edit_codi.setReadOnly(True)
        self._edit_codi.setStyleSheet("background:#f0f0f0; color:#555;")
        self._edit_codi.setToolTip(
            "Codi correlatiu generat automàticament.\n"
            "Format: PA01E (existent) o PA01P (projectat)."
        )
        lay.addWidget(self._edit_codi, 0, 1)

        lay.addWidget(QLabel("Estat:"), 1, 0)
        self._combo_estat = QComboBox()
        for val, desc in ESTAT_OPCIONS:
            self._combo_estat.addItem(desc, val)
        self._combo_estat.setMinimumWidth(200)
        self._combo_estat.setToolTip(
            "E = Existent (la infraestructura ja existeix al terreny).\n"
            "P = Projectat (prevista per al pla d'actuació)."
        )
        self._combo_estat.currentIndexChanged.connect(self._on_estat_changed)
        lay.addWidget(self._combo_estat, 1, 1)

        return grp

    def _next_codi(self):
        if not self._layer:
            return "PA01E"
        idx = self._layer.fields().indexOf("codi_pa")
        used = set()
        for feat in self._layer.getFeatures():
            val = feat.attribute(idx)
            if val:
                used.add(str(val))
        estat = self._combo_estat.currentData() or "E"
        n = 1
        while True:
            codi = f"PA{n:02d}{estat}"
            if codi not in used:
                return codi
            n += 1

    def _update_codi(self):
        self._edit_codi.setText(self._next_codi())

    def _on_estat_changed(self, index):
        self._update_codi()

    def _post_load_layer(self):
        self._update_codi()

    def _apply_attrs(self, fid, x, y):
        lyr = self._layer
        codi = self._edit_codi.text().strip()
        estat = self._combo_estat.currentData() or "E"
        fields = lyr.fields().names()
        if "codi_pa" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("codi_pa"), codi)
        if "estat" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("estat"), estat)
        if "coord_x" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("coord_x"), round(x, 2))
        if "coord_y" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("coord_y"), round(y, 2))

    def _apply_attrs_new(self, feat, x, y):
        codi = self._edit_codi.text().strip()
        estat = self._combo_estat.currentData() or "E"
        fields = feat.fields().names()
        if "codi_pa" in fields:
            feat.setAttribute("codi_pa", codi)
        if "estat" in fields:
            feat.setAttribute("estat", estat)
        if "coord_x" in fields:
            feat.setAttribute("coord_x", round(x, 2))
        if "coord_y" in fields:
            feat.setAttribute("coord_y", round(y, 2))

    def _reset_attr_fields(self):
        self._update_codi()

    def _load_attrs_for_mod(self, feat):
        codi = feat["codi_pa"] or ""
        estat = feat["estat"] or "E"
        self._edit_codi.setText(str(codi))
        for i in range(self._combo_estat.count()):
            if self._combo_estat.itemData(i) == estat:
                self._combo_estat.setCurrentIndex(i)
                break

    def _save_attrs_for_mod(self, fid):
        lyr = self._layer
        codi = self._edit_codi.text().strip()
        estat = self._combo_estat.currentData() or "E"
        base = codi[:-1] if codi and codi[-1] in ("E", "P") else codi
        codi_nou = base + estat
        fields = lyr.fields().names()
        lyr.startEditing()
        if "codi_pa" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("codi_pa"), codi_nou)
        if "estat" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("estat"), estat)
        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"No s'ha pogut desar:\n{errs}")
            return False
        return True

    # Sobreescrivim _on_confirmar_elim per afegir la renumeració
    # (mateix patró que InventariDialog._on_confirmar_elim(), adaptat
    # al codi PA + número + estat, amb numeració independent per estat)
    def _on_confirmar_elim(self):
        lyr = self._layer
        selected = lyr.selectedFeatures()
        if not selected:
            QMessageBox.information(
                self, "Cap punt seleccionat",
                "Selecciona primer un punt d'aigua al mapa."
            )
            return
        if len(selected) > 1:
            QMessageBox.warning(
                self, "Selecció múltiple",
                "Selecciona només un punt a la vegada."
            )
            return
        feat = selected[0]
        codi = feat["codi_pa"] or "?"
        reply = QMessageBox.question(
            self, "Confirmar eliminació",
            f"Vols eliminar el punt d'aigua «{codi}»?\n\n"
            "La resta de punts del mateix estat (Existent/Projectat) es "
            "renumeraran automàticament.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        lyr.startEditing()
        lyr.deleteFeature(feat.id())
        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error", f"No s'ha pogut eliminar:\n{errs}")
            return
        lyr.removeSelection()
        self._renumerar()
        self._count = self._layer.featureCount()
        self._lbl_comptador.setText(self._counter_text(self._count))
        self.iface.mapCanvas().refresh()
        self._on_cancel_elim()

    def _renumerar(self):
        """Renumera tots els punts d'aigua agrupant-los per estat
        (Existent/Projectat) — cadascun amb numeració independent des
        de l'1, igual que ja fa _next_codi() en crear-ne un de nou."""
        lyr = self._layer
        if not lyr:
            return
        idx = lyr.fields().indexOf("codi_pa")
        if idx < 0:
            return

        grups = {}
        for feat in lyr.getFeatures():
            codi = feat["codi_pa"]
            if not codi or not isinstance(codi, str) or not codi.startswith("PA"):
                continue
            estat = codi[-1] if codi[-1] in ("E", "P") else "E"
            try:
                num = int(codi[2:4])
            except (ValueError, IndexError):
                num = 9999
            grups.setdefault(estat, []).append((num, feat))

        lyr.startEditing()
        for estat, llista in grups.items():
            llista.sort(key=lambda parell: parell[0])
            for i, (_num_antic, feat_ordenat) in enumerate(llista, start=1):
                nou_codi = f"PA{i:02d}{estat}"
                lyr.changeAttributeValue(feat_ordenat.id(), idx, nou_codi)

        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            QMessageBox.critical(self, "Error renumeració", f"Error:\n{errs}")

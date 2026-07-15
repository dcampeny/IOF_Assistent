# -*- coding: utf-8 -*-
"""
iof_elements_dialog.py — Digitalitzar elements singulars.

Hereta de IOFBasePointDialog i sobreescriu la lògica específica:
  - Atributs: tipus_elem (combo), nom_elem (text lliure)
"""

from qgis.PyQt.QtWidgets import (
    QGroupBox, QGridLayout, QLabel, QComboBox, QLineEdit,
)

from .iof_base_point_dialog import IOFBasePointDialog

TIPUS_OPCIONS = [
    ("", "(sense tipus)"),
    ("Arquit", "Element arquitectònic singular"),
    ("Natural", "Element natural singular"),
]


class ElementsDialog(IOFBasePointDialog):

    LAYER_NAME = "IOF_Elements_Singulars"

    def _dialog_title(self):
        return "Digitalitzar elements singulars"

    def _heading_text(self):
        return "Digitalitzar elements singulars"

    def _info_color(self):
        return "#f3e5f5"

    def _info_border_color(self):
        return "#ce93d8"

    def _accent_color(self):
        return "#6a1b9a"

    def _counter_text(self, n):
        return f"Elements singulars afegits: {n}"

    def _feature_display_name(self, feat):
        return str(feat["nom_elem"] or feat.id())

    def _build_attr_group(self):
        grp = QGroupBox("Atributs de l'element")
        lay = QGridLayout(grp)

        lay.addWidget(QLabel("Tipus:"), 0, 0)
        self._combo_tipus = QComboBox()
        for val, desc in TIPUS_OPCIONS:
            self._combo_tipus.addItem(desc, val)
        self._combo_tipus.setMinimumWidth(240)
        self._combo_tipus.setToolTip(
            "Arquit = Element arquitectònic (ponts, barraques, forns de calç...).\n"
            "Natural = Element natural (arbres singulars, roques, fonts...)."
        )
        lay.addWidget(self._combo_tipus, 0, 1)

        lay.addWidget(QLabel("Nom:"), 1, 0)
        self._edit_nom = QLineEdit()
        self._edit_nom.setPlaceholderText("ex: Roure de Cal Peroi, Pont Medieval...")
        self._edit_nom.setToolTip(
            "Nom descriptiu o popular de l'element singular.\n"
            "Camp informatiu, no s'exporta al fitxer TXT."
        )
        lay.addWidget(self._edit_nom, 1, 1)

        return grp

    def _apply_attrs(self, fid, x, y):
        lyr = self._layer
        tipus = self._combo_tipus.currentData()
        nom = self._edit_nom.text().strip()
        fields = lyr.fields().names()
        if "tipus_elem" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("tipus_elem"), tipus or None)
        if "nom_elem" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("nom_elem"), nom or None)
        if "coord_x" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("coord_x"), round(x, 2))
        if "coord_y" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("coord_y"), round(y, 2))

    def _apply_attrs_new(self, feat, x, y):
        tipus = self._combo_tipus.currentData()
        nom = self._edit_nom.text().strip()
        fields = feat.fields().names()
        if "tipus_elem" in fields:
            feat.setAttribute("tipus_elem", tipus or None)
        if "nom_elem" in fields:
            feat.setAttribute("nom_elem", nom or None)
        if "coord_x" in fields:
            feat.setAttribute("coord_x", round(x, 2))
        if "coord_y" in fields:
            feat.setAttribute("coord_y", round(y, 2))

    def _reset_attr_fields(self):
        self._combo_tipus.setCurrentIndex(0)
        self._edit_nom.clear()

    def _load_attrs_for_mod(self, feat):
        tipus = feat["tipus_elem"] or ""
        nom = feat["nom_elem"] or ""
        for i in range(self._combo_tipus.count()):
            if self._combo_tipus.itemData(i) == tipus:
                self._combo_tipus.setCurrentIndex(i)
                break
        self._edit_nom.setText(str(nom))

    def _save_attrs_for_mod(self, fid):
        lyr = self._layer
        tipus = self._combo_tipus.currentData() or ""
        nom = self._edit_nom.text().strip()
        fields = lyr.fields().names()
        lyr.startEditing()
        if "tipus_elem" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("tipus_elem"), tipus)
        if "nom_elem" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("nom_elem"), nom)
        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"No s'ha pogut desar:\n{errs}")
            return False
        return True

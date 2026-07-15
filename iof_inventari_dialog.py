# -*- coding: utf-8 -*-
"""
iof_inventari_dialog.py — Digitalitzar punts d'inventari.

Hereta de IOFBasePointDialog. Diferències respecte al cas genèric:
  - No té atributs editables: el codi és un número correlatiu automàtic.
  - En eliminar un punt, renumera tots els restants.
  - El botó «Desar» al mode mapa és visible; no n'hi ha al mode coord
    (s'afegeix directament en clicar «Afegir punt»).
  - Incorpora un botó d'importació massiva des d'un fitxer CSV (columnes
    codi_pi, coord_x, coord_y).
"""

import csv

from qgis.PyQt.QtWidgets import (
    QGroupBox, QLabel, QVBoxLayout, QMessageBox, QPushButton, QFileDialog,
)
from qgis.core import QgsFeature, QgsGeometry, QgsPointXY

from .iof_base_point_dialog import IOFBasePointDialog


class InventariDialog(IOFBasePointDialog):

    LAYER_NAME = "IOF_Punts_Inventari"

    def _dialog_title(self):
        return "Digitalitzar inventaris"

    def _heading_text(self):
        return "Digitalitzar punts d'inventari"

    def _info_color(self):
        return "#e3f2fd"

    def _info_border_color(self):
        return "#90caf9"

    def _accent_color(self):
        return "#1976d2"

    def _counter_text(self, n):
        return f"Inventaris afegits: {n}"

    def _feature_display_name(self, feat):
        return str(feat["codi_pi"] or feat.id())

    def _build_attr_group(self):
        grp = QGroupBox("Atributs del punt d'inventari")
        lay = QVBoxLayout(grp)
        self._lbl_num = QLabel("Número assignat automàticament")
        self._lbl_num.setStyleSheet("color:#555; font-style:italic;")
        lay.addWidget(self._lbl_num)
        return grp

    def _build_import_group(self):
        grp = QGroupBox("Importació massiva")
        lay = QVBoxLayout(grp)
        lbl = QLabel(
            "Importa punts d'inventari des d'un fitxer CSV. Columnes "
            "esperades: codi_pi, coord_x, coord_y. Els punts es renumeren "
            "automàticament en importar-los."
        )
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        btn = QPushButton("📥  Importa punts des de CSV…")
        btn.setStyleSheet(
            f"background:{self._accent_color()}; color:white;"
            " font-weight:bold; padding:6px 16px;"
        )
        btn.clicked.connect(self._on_importar_csv)
        lay.addWidget(btn)
        return grp

    def _post_load_layer(self):
        self._recalcular_num()

    def _recalcular_num(self):
        if not self._layer:
            self._next_num = 1
            return
        max_num = 0
        for feat in self._layer.getFeatures():
            v = feat["codi_pi"]
            if v and v == v:
                try:
                    max_num = max(max_num, int(v))
                except (ValueError, TypeError):
                    pass
        self._next_num = max_num + 1
        self._lbl_comptador.setText(self._counter_text(self._next_num - 1))
        if hasattr(self, "_lbl_num"):
            self._lbl_num.setText(
                f"Número que s'assignarà al pròxim punt: {self._next_num}"
            )

    def _apply_attrs(self, fid, x, y):
        lyr = self._layer
        fields = lyr.fields().names()
        if "codi_pi" in fields:
            lyr.changeAttributeValue(
                fid, lyr.fields().indexOf("codi_pi"), self._next_num)
        if "coord_x" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("coord_x"), round(x, 2))
        if "coord_y" in fields:
            lyr.changeAttributeValue(fid, lyr.fields().indexOf("coord_y"), round(y, 2))

    def _apply_attrs_new(self, feat, x, y):
        fields = feat.fields().names()
        if "codi_pi" in fields:
            feat.setAttribute("codi_pi", self._next_num)
        if "coord_x" in fields:
            feat.setAttribute("coord_x", round(x, 2))
        if "coord_y" in fields:
            feat.setAttribute("coord_y", round(y, 2))

    def _reset_attr_fields(self):
        self._next_num += 1
        if hasattr(self, "_lbl_num"):
            self._lbl_num.setText(
                f"Número que s'assignarà al pròxim punt: {self._next_num}"
            )
        # Reajustar comptador (la base usa self._count, aquí synchronitzem)
        self._count = self._next_num - 1
        self._lbl_comptador.setText(self._counter_text(self._count))

    def _load_attrs_for_mod(self, feat):
        num = feat["codi_pi"]
        if hasattr(self, "_lbl_num"):
            self._lbl_num.setText(f"Editant punt número {num}")

    def _save_attrs_for_mod(self, fid):
        # Els punts d'inventari no tenen atributs editables manualment
        return True

    # Sobreescrivim _on_confirmar_elim per afegir la renumeració
    def _on_confirmar_elim(self):
        lyr = self._layer
        selected = lyr.selectedFeatures()
        if not selected:
            QMessageBox.information(
                self, "Cap punt seleccionat",
                "Selecciona primer un punt d'inventari al mapa."
            )
            return
        if len(selected) > 1:
            QMessageBox.warning(
                self, "Selecció múltiple",
                "Selecciona només un punt a la vegada."
            )
            return
        feat = selected[0]
        num = feat["codi_pi"]
        from qgis.PyQt.QtWidgets import QMessageBox as _QMB
        reply = _QMB.question(
            self, "Confirmar eliminació",
            f"Vols eliminar el punt d'inventari número {num}?\n\n"
            "La resta de punts es renumeraran automàticament.",
            _QMB.StandardButton.Yes | _QMB.StandardButton.No, _QMB.StandardButton.No
        )
        if reply != _QMB.StandardButton.Yes:
            return

        lyr.startEditing()
        lyr.deleteFeature(feat.id())
        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            _QMB.critical(self, "Error", f"No s'ha pogut eliminar:\n{errs}")
            return
        lyr.removeSelection()
        self._renumerar()
        self.iface.mapCanvas().refresh()
        self._on_cancel_elim()

    def _renumerar(self):
        lyr = self._layer
        if not lyr:
            return
        feats = sorted(
            list(lyr.getFeatures()),
            key=lambda f: (
                int(f["codi_pi"])
                if f["codi_pi"] and f["codi_pi"] == f["codi_pi"]
                else 9999
            )
        )
        idx = lyr.fields().indexOf("codi_pi")
        lyr.startEditing()
        for i, feat in enumerate(feats, start=1):
            lyr.changeAttributeValue(feat.id(), idx, i)
        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error renumeració", f"Error:\n{errs}")
            return
        self._recalcular_num()

    # ------------------------------------------------------------------
    # Importació massiva des de CSV
    # ------------------------------------------------------------------

    def _llegir_csv_punts(self, path):
        """
        Llegeix un fitxer CSV amb columnes coord_x, coord_y (i opcionalment
        codi_pi, usat només per ordenar els punts en el mateix ordre en què
        es van capturar). Retorna (files, errors):
          - files: llista de (ordre, x, y) ordenada per `ordre`
          - errors: llista de missatges (una línia de text per fila descartada)
        Llança OSError si el fitxer no es pot obrir.
        """
        files, errors = [], []
        with open(path, newline="", encoding="utf-8-sig") as f:
            mostra = f.read(2048)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(mostra, delimiters=",;")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(f, dialect=dialect)
            if not reader.fieldnames:
                errors.append("El fitxer no té capçalera.")
                return files, errors
            camp = {c.strip().lower(): c for c in reader.fieldnames}
            if not {"coord_x", "coord_y"}.issubset(camp.keys()):
                errors.append(
                    "El fitxer ha de tenir com a mínim les columnes "
                    "«coord_x» i «coord_y» (i opcionalment «codi_pi»)."
                )
                return files, errors
            for n_linia, row in enumerate(reader, start=2):
                x_raw = (row.get(camp["coord_x"]) or "").strip()
                y_raw = (row.get(camp["coord_y"]) or "").strip()
                if not x_raw or not y_raw:
                    errors.append(f"Línia {n_linia}: falten coordenades, s'ha omès.")
                    continue
                try:
                    x = float(x_raw.replace(",", "."))
                    y = float(y_raw.replace(",", "."))
                except ValueError:
                    errors.append(f"Línia {n_linia}: coordenades no vàlides, s'ha omès.")
                    continue
                ordre = n_linia
                if "codi_pi" in camp:
                    try:
                        ordre = int(str(row.get(camp["codi_pi"], "")).strip())
                    except (ValueError, TypeError):
                        pass
                files.append((ordre, x, y))
        files.sort(key=lambda r: r[0])
        return files, errors

    def _on_importar_csv(self):
        if not self._layer:
            QMessageBox.warning(
                self, "Capa no disponible",
                f"No s'ha trobat la capa «{self.LAYER_NAME}»."
            )
            return

        # No permetre importar mentre hi ha una modificació o eliminació en curs
        if self._btn_desar_mod.isVisible() or self._btn_confirmar_elim.isVisible():
            QMessageBox.information(
                self, "Operació en curs",
                "Acaba o cancel·la primer la modificació/eliminació en curs "
                "abans d'importar punts."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Selecciona el fitxer CSV a importar", "",
            "Fitxers CSV (*.csv);;Tots els fitxers (*.*)"
        )
        if not path:
            return

        try:
            files, errors = self._llegir_csv_punts(path)
        except OSError as e:
            QMessageBox.critical(self, "Error en llegir el fitxer", str(e))
            return

        if not files:
            msg = "No s'ha trobat cap punt vàlid al fitxer."
            if errors:
                msg += "\n\n" + "\n".join(errors[:15])
            QMessageBox.warning(self, "Cap punt importat", msg)
            return

        n_existents = self._layer.featureCount()
        sobreescriure = False

        if n_existents > 0:
            # La capa ja té punts (segona importació, o punts afegits
            # manualment abans): cal que l'usuari triï explícitament
            # què fer-ne, en lloc d'assumir que s'han d'afegir.
            text = (
                f"La capa ja conté {n_existents} punts d'inventari.\n\n"
                f"S'han trobat {len(files)} punts vàlids al fitxer.\n\n"
            )
            if errors:
                text += f"{len(errors)} línies del fitxer s'ometran per errors.\n\n"
            text += (
                "Vols sobreescriure els punts existents amb els del "
                "fitxer, o afegir-los als que ja hi ha?"
            )
            caixa = QMessageBox(self)
            caixa.setWindowTitle("Punts existents")
            caixa.setIcon(QMessageBox.Icon.Question)
            caixa.setText(text)
            btn_sobreescriure = caixa.addButton(
                "Sobreescriure", QMessageBox.ButtonRole.DestructiveRole
            )
            btn_afegir = caixa.addButton(
                "Afegir", QMessageBox.ButtonRole.AcceptRole
            )
            btn_cancelar = caixa.addButton(
                "Cancel·lar", QMessageBox.ButtonRole.RejectRole
            )
            caixa.setDefaultButton(btn_afegir)
            caixa.exec()
            clicat = caixa.clickedButton()
            if clicat == btn_cancelar:
                return
            sobreescriure = (clicat == btn_sobreescriure)
        else:
            num_ini, num_fi = self._next_num, self._next_num + len(files) - 1
            text = f"S'importaran {len(files)} punts nous "
            text += f"(numerats del {num_ini} al {num_fi}).\n\n"
            if errors:
                text += f"{len(errors)} línies del fitxer s'ometran per errors.\n\n"
            text += "Vols continuar?"
            resposta = QMessageBox.question(
                self, "Confirmar importació", text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return

        lyr = self._layer
        self._deactivate_map_tool()

        # Si hi havia un punt pendent sense desar (mode mapa), es descarta
        if self._pending_fid is not None and lyr.isEditable():
            lyr.deleteFeature(self._pending_fid)
            self._pending_fid = None
            self._pending_pt = None
            self._btn_desar.setEnabled(False)
            self._lbl_pendent.setText("")

        lyr.startEditing()

        eliminats = 0
        if sobreescriure:
            for feat_existent in list(lyr.getFeatures()):
                if lyr.deleteFeature(feat_existent.id()):
                    eliminats += 1
            self._next_num = 1

        afegits = 0
        for _, x, y in files:
            feat = QgsFeature(lyr.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
            self._apply_attrs_new(feat, x, y)
            if lyr.addFeature(feat):
                afegits += 1
                self._next_num += 1

        if not lyr.commitChanges():
            errs = "; ".join(lyr.commitErrors())
            lyr.rollBack()
            self._recalcular_num()
            if self._btn_mapa.isChecked():
                self._activate_map_tool()
            QMessageBox.critical(
                self, "Error", f"No s'han pogut importar els punts:\n{errs}"
            )
            return

        self._count = lyr.featureCount()
        self._lbl_comptador.setText(self._counter_text(self._count))
        self._recalcular_num()
        self.iface.mapCanvas().refresh()
        if self._btn_mapa.isChecked():
            self._activate_map_tool()

        if sobreescriure:
            resum = (
                f"S'han eliminat {eliminats} punts existents i "
                f"importat {afegits} punts nous."
            )
        else:
            resum = f"S'han importat {afegits} punts correctament."
        if errors:
            detall = "\n".join(errors[:15])
            resum += f"\n\n{len(errors)} línies s'han omès:\n{detall}"
            if len(errors) > 15:
                resum += f"\n… i {len(errors) - 15} més."
        QMessageBox.information(self, "Importació completada", resum)

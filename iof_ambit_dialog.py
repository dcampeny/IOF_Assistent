# -*- coding: utf-8 -*-
"""
Creació de l'àmbit de l'IOF a partir de les finques cadastrals desades.
"""

import os
import tempfile
from qgis.PyQt.QtWidgets import QMessageBox, QApplication
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsVectorFileWriter,
    QgsCoordinateTransformContext
)
import processing
from .iof_utils import aplica_qml as _aplica_qml


def _normalitza(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _elimina_capa_projecte(path):
    """Elimina del projecte qualsevol capa que apunti al fitxer."""
    import time
    path_norm = _normalitza(path)
    eliminat = False
    for lid, layer in list(QgsProject.instance().mapLayers().items()):
        src_norm = _normalitza(layer.source().split("|")[0])
        if src_norm == path_norm:
            QgsProject.instance().removeMapLayer(lid)
            eliminat = True
    if eliminat:
        QApplication.processEvents()
        time.sleep(0.5)
        QApplication.processEvents()
        time.sleep(0.3)
        QApplication.processEvents()


def _esborra_fitxer(path):
    """
    Esborra un fitxer gpkg amb reintents per Windows.
    Usa os.replace com a alternativa si os.remove falla.
    """
    import time
    for intent in range(20):
        try:
            if os.path.exists(path):
                # Intenta primer moure a temporal per alliberar el nom
                # i despres esborrar (mes robust a Windows)
                tmp = path + ".deleting"
                try:
                    os.rename(path, tmp)
                    os.remove(tmp)
                except OSError:
                    os.remove(path)
            for ext in ["-wal", "-shm", ".gpkg-journal", ".deleting"]:
                aux = path + ext
                if os.path.exists(aux):
                    try:
                        os.remove(aux)
                    except OSError:
                        pass
            return True
        except OSError:
            QApplication.processEvents()
            time.sleep(0.4)
    return False


def _find_zoning_layer():
    """Retorna la primera capa CadastralZoning."""
    for layer in QgsProject.instance().mapLayers().values():
        name = layer.name().lower()
        if any(kw in name for kw in [
            "polígons cadastrals", "poligons cadastrals", "cadastralzoning"
        ]):
            return layer
    return None


def _find_all_zoning_layers():
    """Retorna totes les capes CadastralZoning (una per municipi)."""
    result = []
    for layer in QgsProject.instance().mapLayers().values():
        name = layer.name().lower()
        if any(kw in name for kw in [
            "polígons cadastrals", "poligons cadastrals", "cadastralzoning"
        ]):
            result.append(layer)
    return result


def _nom_municipi_de_capa(lyr_zoning):
    """
    Extreu el nom del municipi del nom de la capa CadastralZoning.
    El nom de la capa te el format "Poligons cadastrals — NOM MUNICIPI".
    """
    nom = lyr_zoning.name()
    if " — " in nom:
        return nom.split(" — ", 1)[1].strip()
    if " - " in nom:
        return nom.split(" - ", 1)[1].strip()
    return "Municipi"


def _crear_municipi_cadastral(iface, finca_dir, mun_path, grp,
                              lyr_zoning=None, nom_mun=None):
    """
    Crea la capa Municipi Cadastral dissolent la capa CadastralZoning indicada.
    Si no s'indica cap capa, usa la primera disponible.
    Retorna True si s\'ha creat correctament.
    """
    from qgis.PyQt.QtCore import QVariant
    from qgis.core import (
        QgsField, QgsPalLayerSettings, QgsTextFormat,
        QgsVectorLayerSimpleLabeling
    )
    from qgis.PyQt.QtGui import QFont, QColor

    if lyr_zoning is None:
        lyr_zoning = _find_zoning_layer()
    if not lyr_zoning:
        return False

    # Nom del municipi
    if nom_mun is None:
        nom_mun = _nom_municipi_de_capa(lyr_zoning)

    # Elimina capa existent del projecte
    _elimina_capa_projecte(mun_path)

    # Corregeix geometries invalides
    res_fix = processing.run(
        "native:fixgeometries",
        {"INPUT": lyr_zoning, "METHOD": 1, "OUTPUT": "TEMPORARY_OUTPUT"}
    )
    fixed = res_fix["OUTPUT"]

    # Dissolucio total -> un sol poligon de municipi
    res = processing.run(
        "native:dissolve",
        {
            "INPUT": fixed,
            "FIELD": [],
            "SEPARATE_DISJOINT": False,
            "OUTPUT": "TEMPORARY_OUTPUT"
        }
    )
    dissolved_raw = res["OUTPUT"]
    if not dissolved_raw or dissolved_raw.featureCount() == 0:
        return False

    # Morphological closing: buffer+ / buffer- per eliminar falses linies
    res_buf1 = processing.run(
        "native:buffer",
        {
            "INPUT": dissolved_raw,
            "DISTANCE": 0.01,
            "SEGMENTS": 5,
            "DISSOLVE": True,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "OUTPUT": "TEMPORARY_OUTPUT"
        }
    )
    res_buf2 = processing.run(
        "native:buffer",
        {
            "INPUT": res_buf1["OUTPUT"],
            "DISTANCE": -0.01,
            "SEGMENTS": 5,
            "DISSOLVE": True,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "OUTPUT": "TEMPORARY_OUTPUT"
        }
    )
    dissolved = res_buf2["OUTPUT"]
    if not dissolved or dissolved.featureCount() == 0:
        return False

    # Construeix una capa neta amb NOMES el camp 'municipi'
    # (evita camps falsejats pel dissolve)
    from qgis.core import QgsFeature
    crs_auth = lyr_zoning.crs().authid()
    mem_lyr = QgsVectorLayer(
        "MultiPolygon?crs=" + crs_auth, "mun_tmp", "memory"
    )
    mem_prov = mem_lyr.dataProvider()
    mem_prov.addAttributes([QgsField("municipi", QVariant.String, len=100)])
    mem_lyr.updateFields()

    for diss_feat in dissolved.getFeatures():
        new_feat = QgsFeature(mem_lyr.fields())
        new_feat.setGeometry(diss_feat.geometry())
        new_feat.setAttribute("municipi", nom_mun)
        mem_prov.addFeature(new_feat)
    mem_lyr.updateExtents()

    # Desa a fitxer temporal
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".gpkg", dir=finca_dir)
    os.close(tmp_fd)
    os.remove(tmp_path)

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.fileEncoding = "UTF-8"
    error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem_lyr, tmp_path, QgsCoordinateTransformContext(), opts
    )
    if error != QgsVectorFileWriter.WriterError.NoError:
        from qgis.core import QgsMessageLog, Qgis
        QgsMessageLog.logMessage(
            "IOF Municipi: error escrivint GPKG: " + msg,
            "IOFAssistent", level=Qgis.MessageLevel.Warning
        )
        try:
            os.remove(tmp_path)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        return False

    # Esborra el fitxer destí si existeix (pot no existir la primera vegada)
    if os.path.exists(mun_path):
        if not _esborra_fitxer(mun_path):
            try:
                os.remove(tmp_path)
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass
            return False

    os.rename(tmp_path, mun_path)

    # Carrega la capa
    mun_layer = QgsVectorLayer(mun_path, "Municipi cadastral", "ogr")
    if not mun_layer.isValid():
        return False

    # Aplica estil QML
    _aplica_qml(mun_layer, "IOF-Cadastre-Municipi.qml")

    # Activa etiquetes amb el camp 'municipi'
    pal = QgsPalLayerSettings()
    pal.fieldName = "municipi"
    pal.enabled = True
    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial", 10))
    fmt.setColor(QColor(0, 38, 115))
    pal.setFormat(fmt)
    mun_layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    mun_layer.setLabelsEnabled(True)

    # Col·loca la capa dins el subgrup del municipi
    # Busca el subgrup que conte la capa de zones d'aquest municipi
    sub_grp = None
    nom_mun_l = nom_mun.lower()
    for child in grp.children():
        if hasattr(child, 'children'):
            # Comprova per nom del grup
            if nom_mun_l in child.name().lower():
                sub_grp = child
                break
            # O si conte la capa de poligons d'aquest municipi
            for subchild in child.children():
                if hasattr(subchild, 'layer') and subchild.layer():
                    if nom_mun_l in subchild.layer().name().lower():
                        sub_grp = child
                        break
        if sub_grp:
            break

    QgsProject.instance().addMapLayer(mun_layer, False)
    if sub_grp:
        # Insereix al principi del subgrup (per sobre de poligons i parcelles)
        sub_grp.insertLayer(0, mun_layer)
    else:
        # Si no hi ha subgrup, afegeix al grup principal
        grp.addLayer(mun_layer)

    return True


def _timestamp_finques(finca_dir):
    """Retorna el timestamp de modificació més recent entre totes les fincaN.gpkg."""
    ts = 0
    num = 1
    while True:
        fp = os.path.join(finca_dir, "finca" + str(num) + ".gpkg")
        if not os.path.exists(fp):
            break
        t = os.path.getmtime(fp)
        if t > ts:
            ts = t
        num += 1
    return ts


def crear_ambit_iof(iface, parent=None):
    proj_path = QgsProject.instance().absolutePath()
    if not proj_path:
        from .iof_utils import ensure_project_saved
        proj_path = ensure_project_saved(parent or iface.mainWindow())
        if not proj_path:
            return

    finca_dir = os.path.join(proj_path, "cadastre")
    ambit_path = os.path.join(finca_dir, "ambitIOF.gpkg")

    if not os.path.isdir(finca_dir):
        QMessageBox.warning(
            parent or iface.mainWindow(), "Sense finques",
            "No s'ha trobat la carpeta 'cadastre' al directori del projecte.\n"
            "Primer selecciona i desa les parcel\u00b7les cadastrals de cada finca."
        )
        return

    # Recull totes les fincaN.gpkg
    finques = []
    num = 1
    while True:
        fp = os.path.join(finca_dir, "finca" + str(num) + ".gpkg")
        if not os.path.exists(fp):
            break
        finques.append((num, fp))
        num += 1

    if not finques:
        QMessageBox.warning(
            parent or iface.mainWindow(), "Sense finques",
            "No s'ha trobat cap fitxer finca1.gpkg al directori 'cadastre'.\n"
            "Primer selecciona i desa les parcel\u00b7les cadastrals de cada finca."
        )
        return

    # Elimina qualsevol capa residual del projecte abans de generar
    _elimina_capa_projecte(ambit_path)

    import processing

    # Carrega les finques com a capes
    crs_auth = "EPSG:25831"
    total_parcelles = 0
    layers_tmp = []

    for num_f, fp in finques:
        lyr = QgsVectorLayer(fp, "finca_tmp_" + str(num_f), "ogr")
        if lyr.isValid():
            crs_auth = lyr.crs().authid()
            total_parcelles += lyr.featureCount()
            layers_tmp.append(lyr)

    if not layers_tmp:
        QMessageBox.warning(
            parent or iface.mainWindow(), "Error",
            "No s'han pogut llegir les finques."
        )
        return

    # 1. Fusiona totes les finques en una capa
    if len(layers_tmp) == 1:
        merged = layers_tmp[0]
    else:
        res = processing.run(
            "native:mergevectorlayers",
            {"LAYERS": layers_tmp, "CRS": None, "OUTPUT": "TEMPORARY_OUTPUT"}
        )
        merged = res["OUTPUT"]

    # 2. Corregeix geometries (elimina errors topològics del GML cadastral)
    res_fix = processing.run(
        "native:fixgeometries",
        {"INPUT": merged, "METHOD": 1, "OUTPUT": "TEMPORARY_OUTPUT"}
    )
    fixed = res_fix["OUTPUT"]

    # 3. Buffer positiu petit per fusionar parcel·les adjacents
    #    (elimina les línies fantasma entre vores compartides)
    res_buf1 = processing.run(
        "native:buffer",
        {
            "INPUT": fixed,
            "DISTANCE": 0.01,
            "SEGMENTS": 5,
            "DISSOLVE": True,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "OUTPUT": "TEMPORARY_OUTPUT"
        }
    )
    buf1 = res_buf1["OUTPUT"]

    # 4. Buffer negatiu equivalent per recuperar la mida original
    res_diss = processing.run(
        "native:buffer",
        {
            "INPUT": buf1,
            "DISTANCE": -0.01,
            "SEGMENTS": 5,
            "DISSOLVE": True,
            "END_CAP_STYLE": 0,
            "JOIN_STYLE": 0,
            "MITER_LIMIT": 2,
            "OUTPUT": "TEMPORARY_OUTPUT"
        }
    )
    dissolved = res_diss["OUTPUT"]

    # Allibera capes temporals
    for lyr in layers_tmp:
        del lyr

    if not dissolved or dissolved.featureCount() == 0:
        QMessageBox.warning(
            parent or iface.mainWindow(), "Error",
            "No s'ha pogut calcular l'\u00e0mbit de l'IOF."
        )
        return

    # Superfície total
    area_ha = sum(
        f.geometry().area() / 10000.0
        for f in dissolved.getFeatures()
    )

    # Obte els noms dels municipis de les capes Municipi cadastral, ordenats
    municipis_list = []
    for lyr in QgsProject.instance().mapLayers().values():
        if "municipi cadastral" in lyr.name().lower():
            idx_m = lyr.fields().lookupField("municipi")
            if idx_m >= 0:
                for feat in lyr.getFeatures():
                    val = str(feat[idx_m] or "").strip()
                    if val and val not in municipis_list:
                        municipis_list.append(val)
                    break
    municipis_list.sort()
    nom_municipi = ", ".join(municipis_list)

    # Construeix una capa neta amb NOMES els camps municipi i superficie
    from qgis.core import QgsFeature, QgsField
    from qgis.PyQt.QtCore import QVariant

    crs_auth = layers_tmp[0].crs().authid() if layers_tmp else "EPSG:25831"
    mem_ambit = QgsVectorLayer(
        "MultiPolygon?crs=" + crs_auth, "ambit_tmp", "memory"
    )
    prov_ambit = mem_ambit.dataProvider()
    prov_ambit.addAttributes([
        QgsField("municipi", QVariant.String, "string", 200, 0),
        QgsField("superficie", QVariant.Double, "double", 10, 2),
    ])
    mem_ambit.updateFields()

    for feat in dissolved.getFeatures():
        nf = QgsFeature(mem_ambit.fields())
        nf.setGeometry(feat.geometry())
        nf.setAttribute("municipi", nom_municipi)
        nf.setAttribute("superficie", round(area_ha, 2))
        prov_ambit.addFeature(nf)
    mem_ambit.updateExtents()

    # Escriu a fitxer temporal
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".gpkg", dir=finca_dir)
    os.close(tmp_fd)
    os.remove(tmp_path)

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.fileEncoding = "UTF-8"
    error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem_ambit, tmp_path, QgsCoordinateTransformContext(), opts
    )

    if error != QgsVectorFileWriter.WriterError.NoError:
        QMessageBox.critical(
            parent or iface.mainWindow(), "Error en desar",
            "No s'ha pogut desar l'\u00e0mbit:\n" + msg
        )
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass
        return

    # Substitueix l'original
    if not _esborra_fitxer(ambit_path):
        QMessageBox.critical(
            parent or iface.mainWindow(), "Error en desar",
            "No s'ha pogut sobreescriure ambitIOF.gpkg.\n\n"
            "Tanca la capa '\u00c0mbit IOF' del panell de capes i torna a intentar-ho."
        )
        try:
            os.remove(tmp_path)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        return

    os.rename(tmp_path, ambit_path)

    # Neteja fitxers temporals
    from .iof_utils import netejar_carpeta_cadastre
    netejar_carpeta_cadastre(finca_dir)

    # Carrega el grup Cadastre
    root = QgsProject.instance().layerTreeRoot()
    grp = root.findGroup("Cadastre")
    if grp is None:
        grp = root.insertGroup(0, "Cadastre")

    # Carrega la capa Ambit IOF amb l'estil QML
    ambit_layer = QgsVectorLayer(ambit_path, "\u00c0mbit IOF", "ogr")
    if ambit_layer.isValid():
        _aplica_qml(ambit_layer, "IOF-Cadastre-Finca.qml")
        QgsProject.instance().addMapLayer(ambit_layer, False)
        grp.insertLayer(0, ambit_layer)
        iface.mapCanvas().setExtent(ambit_layer.extent())
        iface.mapCanvas().refresh()

    # Missatge final
    QMessageBox.information(
        parent or iface.mainWindow(),
        "\u00c0mbit IOF creat",
        "L'\u00e0mbit de l'IOF s'ha creat correctament.\n\n"
        "Finques:     " + str(len(finques)) + "\n"
        "Parcel\u00b7les:  " + str(total_parcelles) + "\n"
        "Superf\u00edcie:  " + "{:.4f}".format(area_ha) + " ha\n\n"
        "Fitxer: " + ambit_path
    )

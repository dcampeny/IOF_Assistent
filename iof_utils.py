# -*- coding: utf-8 -*-
"""
IOF Assistent — Utilitats compartides.

Centralitza funcions que abans estaven duplicades en diversos mòduls:
  - localització de capes per nom (i opcionalment tipus de geometria)
  - neteja de forats d'una geometria (anell exterior)
  - detecció de polígons interiors / exclusions (bounding box)

Mantenir una sola implementació evita que les còpies divergeixin
(abans hi havia tres versions de la detecció d'exclusions amb llindars
diferents: 0.01, 0.1 i comparació d'àrees a 1 o 2 decimals).
"""

import re as _re
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsGeometry, QgsWkbTypes,
    QgsMessageLog, Qgis, QgsSnappingConfig, QgsSingleSymbolRenderer
)


def log(msg, level=Qgis.MessageLevel.Info):
    """Escriu un missatge al registre de QGIS sota la categoria del plugin."""
    QgsMessageLog.logMessage(str(msg), "IOF Assistent", level)


def avisa_capa_no_trobada(parent, layer_name, accio="realitzar la digitalització"):
    """
    Mostra l'avís estàndard de «Capa no trobada». S'ha de cridar sempre
    que un diàleg no trobi la capa IOF que necessita, ABANS de deixar
    que la resta del diàleg es mostri — qui el crida ha de comprovar
    un flag (p. ex. `self._cancelled`) i no mostrar el diàleg si la
    capa no existia.
    """
    from qgis.PyQt.QtWidgets import QMessageBox
    QMessageBox.warning(
        parent, "Capa no trobada",
        f"No s'ha trobat la capa «{layer_name}» al projecte.\n\n"
        f"Assegura't d'haver-la creat amb l'eina «Crear capes IOF» "
        f"abans de {accio}."
    )


def aplica_qml(layer, qml_name):
    """Aplica un estil de cadastre (de styles/cadastre_estils.json.gz,
    consolidat dels 4 fitxers .qml originals) a una capa.

    Abans hi havia dues còpies gairebé idèntiques d'aquesta funció, una a
    iof_ambit_dialog.py i una altra a iof_estil_cadastre.py, amb petites
    diferències (una no gestionava bé la tupla de retorn
    d'importNamedStyle). Consolidada aquí perquè no puguin tornar a
    divergir.
    """
    import os
    import gzip
    import json
    from qgis.PyQt.QtXml import QDomDocument

    json_path = os.path.join(os.path.dirname(__file__), "styles", "cadastre_estils.json.gz")
    if not os.path.exists(json_path):
        return False
    try:
        with gzip.open(json_path, "rb") as f:
            estils = json.loads(f.read().decode("utf-8"))
    except Exception:
        return False
    qml_xml = estils.get(qml_name)
    if not qml_xml:
        return False
    doc = QDomDocument()
    if not doc.setContent(qml_xml):
        return False
    ok, _err_msg = layer.importNamedStyle(doc)
    if ok:
        layer.triggerRepaint()
    return ok


# Memòria temporal de l'estat previ d'edició topològica / evitar superposicions,
# per poder-lo restaurar en tancar l'eina de digitalització.
_estat_previ_topo = {}


def activar_snapping_totes_capes(iface, tolerance=12):
    """
    Activa el snapping (vèrtex i segment, amb interseccions) contra totes
    les capes vectorials del projecte.

    L'API de `QgsSnappingConfig` ha canviat varies vegades entre versions de
    QGIS (`setType`→`setTypeFlag` a la 3.12, `setMode` amb enum diferent a la
    3.26...). Per evitar dependre d'endevinar exactament la versió instal·lada,
    aquesta funció:
      1. Parteix de la configuració JA EXISTENT del projecte
         (`QgsProject.instance().snappingConfig()`) en lloc de crear-ne una
         de zero, per no perdre cap altre paràmetre ja vàlid.
      2. Prova primer l'API moderna (`setTypeFlag` / `Qgis.SnappingMode`) i,
         si no existeix en aquesta versió de QGIS, cau automàticament a
         l'API antiga (`setType` / `QgsSnappingConfig.AllLayers`).
      3. No toca `IndividualLayerSettings` (no fa falta en mode AllLayers;
         tocar-los sense necessitat és una font extra de fallades).

    IMPORTANT: també desactiva temporalment l'«Edició topològica» i l'opció
    «Evita les superposicions a la capa activa» del projecte. Aquestes dues
    opcions (de la finestra "Configuració de l'ajust en el projecte") poden
    impedir que el cursor s'enganxi correctament durant la digitalització,
    encara que la configuració de snapping en si sigui correcta — és el cas
    detectat en proves: amb totes dues activades el snap no funcionava ni
    a la mateixa capa, i en desactivar-les va funcionar immediatament.
    Es restauren amb `restaurar_snapping()`.

    Cal cridar-la en obrir qualsevol eina de digitalització (camins,
    canvis d'ús, infraestructures, tipologies forestals/rodals).
    Utilitzar `restaurar_snapping()` per desactivar-lo en tancar.
    """
    try:
        proj = QgsProject.instance()

        # --- Desar i desactivar edició topològica / evita superposicions ---
        try:
            _estat_previ_topo["topo"] = proj.topologicalEditing()
            proj.setTopologicalEditing(False)
        except Exception as e:
            log(f"No s'ha pogut llegir/desactivar l'edició topològica: {e}", Qgis.MessageLevel.Warning)

        try:
            _estat_previ_topo["avoid"] = proj.avoidIntersectionsMode()
            proj.setAvoidIntersectionsMode(Qgis.AvoidIntersectionsMode.AllowIntersections)
        except Exception as e:
            log(f"No s'ha pogut llegir/desactivar evita superposicions: {e}", Qgis.MessageLevel.Warning)

        config = proj.snappingConfig()
        config.setEnabled(True)

        # --- Mode: totes les capes ---
        try:
            config.setMode(Qgis.SnappingMode.AllLayers)
        except Exception:
            config.setMode(QgsSnappingConfig.SnappingMode.AllLayers)

        # --- Tipus: vèrtex + segment ---
        try:
            tipus = Qgis.SnappingTypes(Qgis.SnappingType.Vertex | Qgis.SnappingType.Segment)
            config.setTypeFlag(tipus)
        except Exception:
            config.setType(QgsSnappingConfig.SnappingType.VertexAndSegment)

        config.setTolerance(tolerance)

        # --- Unitats: píxels ---
        try:
            config.setUnits(Qgis.MapToolUnit.Pixels)
        except Exception:
            from qgis.core import QgsTolerance
            config.setUnits(QgsTolerance.UnitType.Pixels)

        config.setIntersectionSnapping(True)

        proj.setSnappingConfig(config)
        iface.mapCanvas().snappingUtils().setConfig(config)
        log("Snapping activat correctament (AllLayers, Vèrtex+Segment, tolerància %spx)." % tolerance)
    except Exception as e:
        # No deixar mai que un canvi futur d'API de QGIS deixi el snapping
        # sense configurar de manera silenciosa: ho registrem al log del plugin.
        log(f"ERROR activant snapping: {e}", Qgis.MessageLevel.Critical)


def restaurar_snapping(iface=None):
    """
    Desactiva el snapping (estat per defecte en sortir d'una eina de
    digitalització) i restaura l'edició topològica / evita superposicions
    a l'estat que tenien abans d'obrir l'eina.
    """
    snap_off = QgsSnappingConfig()
    snap_off.setEnabled(False)
    QgsProject.instance().setSnappingConfig(snap_off)
    if iface is not None:
        iface.mapCanvas().snappingUtils().setConfig(snap_off)

    proj = QgsProject.instance()
    if "topo" in _estat_previ_topo:
        try:
            proj.setTopologicalEditing(_estat_previ_topo["topo"])
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
    if "avoid" in _estat_previ_topo:
        try:
            proj.setAvoidIntersectionsMode(_estat_previ_topo["avoid"])
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
    _estat_previ_topo.clear()


def get_layer(names, geom_type=None):
    """
    Retorna la primera capa vectorial del projecte el nom de la qual és
    a `names` (string o llista). Si `geom_type` s'indica
    (QgsWkbTypes.GeometryType.PolygonGeometry, LineGeometry o PointGeometry) també ha
    de coincidir el tipus de geometria.
    """
    if isinstance(names, str):
        names = [names]
    for lyr in QgsProject.instance().mapLayers().values():
        if not isinstance(lyr, QgsVectorLayer):
            continue
        if lyr.name() not in names:
            continue
        if geom_type is not None and \
                QgsWkbTypes.geometryType(lyr.wkbType()) != geom_type:
            continue
        return lyr
    return None


# Noms estàndard de les 9 capes IOF, creades totes de cop amb «Crear
# capes IOF» (iof_create_dialog.py). Es fa servir per saber si cal
# activar les eines que en depenen (digitalització, dades i estils,
# exportació).
IOF_LAYER_NAMES = (
    "IOF_Finques", "IOF_Rodals", "IOF_Unitats_Actuacio", "IOF_Camins",
    "IOF_Canvis_Us", "IOF_Infraestructures_PI", "IOF_Punts_Aigua",
    "IOF_Elements_Singulars", "IOF_Punts_Inventari",
)


def iof_layers_created():
    """Retorna True si el projecte actual ja té alguna de les capes
    estàndard de l'IOF (creades amb «Crear capes IOF»)."""
    for lyr in QgsProject.instance().mapLayers().values():
        if isinstance(lyr, QgsVectorLayer) and lyr.name() in IOF_LAYER_NAMES:
            return True
    return False


def geom_sense_forats(geom):
    """Retorna la geometria amb només l'anell exterior, sense forats."""
    if geom is None or geom.isEmpty():
        return geom
    if geom.isMultipart():
        parts = geom.asMultiPolygon()
        new_parts = [[part[0]] for part in parts if part]
        return QgsGeometry.fromMultiPolygonXY(new_parts)
    rings = geom.asPolygon()
    if rings:
        return QgsGeometry.fromPolygonXY([rings[0]])
    return geom


def _bbox_inside(bb_a, bb_b):
    """True si el bounding box bb_a cau completament dins de bb_b."""
    return all([
        bb_a.xMinimum() >= bb_b.xMinimum(),
        bb_a.yMinimum() >= bb_b.yMinimum(),
        bb_a.xMaximum() <= bb_b.xMaximum(),
        bb_a.yMaximum() <= bb_b.yMaximum(),
    ])


def find_interior_polygons(feats):
    """
    Retorna el conjunt d'IDs dels polígons que corresponen a forats
    (anells interiors) d'un altre polígon, i per tant són àrees excloses.

    No usa GEOS (contains/intersects) perquè quan el polígon gran ja
    integra l'anell interior a la seva geometria, GEOS falla.

    Detecció primària (precisa): per cada anell interior d'un polígon
    es desa la seva signatura (àrea + bbox); després es marca com a
    exclusió tot polígon separat la signatura del qual hi coincideix.
    Fallback (si no hi ha cap anell interior): un polígon és interior si
    el seu bbox cau completament dins del d'un altre de més àrea.
    """
    exclusion_ids = set()

    # Recollir signatures (àrea + bbox) de tots els anells interiors
    interior_signatures = []
    for feat in feats:
        geom = feat.geometry()
        if not geom or geom.isEmpty():
            continue
        parts = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]
        for part in parts:
            for ring in part[1:]:   # índex 0 = exterior, 1+ = interiors
                hole = QgsGeometry.fromPolygonXY([ring])
                if hole and not hole.isEmpty():
                    interior_signatures.append({
                        'area': round(hole.area(), 2),
                        'bbox': hole.boundingBox(),
                    })

    if interior_signatures:
        for feat in feats:
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            area_f = round(geom.area(), 2)
            bbox_f = geom.boundingBox()
            for sig in interior_signatures:
                sig_match = all([
                    area_f == sig['area'],
                    abs(bbox_f.xMinimum() - sig['bbox'].xMinimum()) < 0.01,
                    abs(bbox_f.yMinimum() - sig['bbox'].yMinimum()) < 0.01,
                    abs(bbox_f.xMaximum() - sig['bbox'].xMaximum()) < 0.01,
                    abs(bbox_f.yMaximum() - sig['bbox'].yMaximum()) < 0.01,
                ])
                if sig_match:
                    exclusion_ids.add(feat.id())
                    break
        return exclusion_ids

    # Fallback: bounding box + solapament geomètric real amb l'anell
    # exterior de l'altre polígon (sense forats).
    #
    # Comparar només bounding boxes (com es feia abans) produeix falsos
    # positius: dues finques totalment separades i que no es toquen en
    # cap punt poden tenir, per pura coincidència de la seva posició al
    # mapa, una bounding box continguda dins de l'altra (p. ex. una
    # finca petita situada dins l'extensió d'una de gran i allargada,
    # sense que els polígons se superposin gens). Això feia que una
    # finca nova, genuïnament independent, quedés exclosa i el wizard
    # d'unitats no la reconegués.
    #
    # Per evitar-ho, un cop la bbox ja hi cap, també cal que el propi
    # polígon quedi cobert quasi del tot per l'anell EXTERIOR de
    # l'altre (sense els seus forats): no es pot fer servir
    # contains()/intersects() directament sobre la geometria original,
    # perquè si el forat ja s'ha restat de la geometria del polígon
    # gran, GEOS no el reconeix com a "contingut". Reconstruint només
    # l'anell exterior s'evita aquest problema.
    data = []
    for f in feats:
        g = f.geometry()
        if g is None or g.isEmpty():
            continue
        if not g.isGeosValid():
            g = g.makeValid()
        data.append((f.id(), g, g.boundingBox(), g.area()))

    for i, (fid_a, geom_a, bb_a, area_a) in enumerate(data):
        for j, (fid_b, geom_b, bb_b, area_b) in enumerate(data):
            if i == j or area_a >= area_b:
                continue
            if not _bbox_inside(bb_a, bb_b):
                continue
            ext_b = geom_sense_forats(geom_b)
            if ext_b is None or ext_b.isEmpty() or area_a <= 0:
                continue
            coberta = ext_b.intersection(geom_a).area()
            if (coberta / area_a) >= 0.99:
                exclusion_ids.add(fid_a)
                break
    return exclusion_ids


# Alias per compatibilitat amb el nom usat anteriorment al wizard d'unitats.
find_exclusions = find_interior_polygons


def units_for_finca(layer_unitats, finca_feat):
    """
    Retorna la llista de features de `layer_unitats` que pertanyen a la
    finca donada. Criteri: un punt garantit dins la unitat (pointOnSurface,
    no centroid -- el centroide d'un polígon molt allargat o còncau pot
    caure fora del propi polígon) cau dins de la geometria de la finca.
    """
    if not layer_unitats:
        return []
    finca_geom = finca_feat.geometry()
    if not finca_geom or finca_geom.isEmpty():
        return []
    result = []
    for u in layer_unitats.getFeatures():
        g = u.geometry()
        if not g or g.isEmpty():
            continue
        punt = g.pointOnSurface()
        if finca_geom.contains(punt):
            result.append(u)
    return result


def finca_te_unitats_completes(layer_unitats, finca_feat):
    """
    Retorna True si la finca donada ja té tipologies forestals que
    cobreixen tota la seva geometria (àrea de la unió >= 99% de l'àrea
    de la finca). Mateix llindar que fa servir
    iof_unitats_wizard.py::_finca_is_complete().
    """
    units = units_for_finca(layer_unitats, finca_feat)
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


# ── Gestió del projecte ───────────────────────────────────────────────────────


def netejar_carpeta_cadastre(finca_dir):
    """
    Elimina fitxers temporals i obsolets de la carpeta cadastre/.
    Manté: fincaN.gpkg, ambitIOF.gpkg, municipiCadastral_*.gpkg
    Elimina: tmp*.gpkg, *.gpkg-wal, *.gpkg-shm, *.gpkg-journal
    Retorna el nombre de fitxers eliminats.
    """
    import os
    import re

    UTILS = [
        r'^finca\d+\.gpkg$',
        r'^ambitIOF\.gpkg$',
        r'^municipiCadastral_.*\.gpkg$',
    ]

    if not os.path.isdir(finca_dir):
        return 0

    eliminats = 0
    for nom in os.listdir(finca_dir):
        path = os.path.join(finca_dir, nom)
        if not os.path.isfile(path):
            continue
        # Si es un fitxer GPKG util, el mantenim
        if any(re.match(p, nom) for p in UTILS):
            continue
        # Elimina auxiliars i temporals
        if any([
            nom.endswith('.gpkg-wal'),
            nom.endswith('.gpkg-shm'),
            nom.endswith('.gpkg-journal'),
            re.match(r'^tmp[a-z0-9_\-]+\.gpkg$', nom),
        ]):
            try:
                os.remove(path)
                eliminats += 1
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass

    return eliminats


def ensure_project_saved(parent_widget):
    """
    Comprova que el projecte QGIS estigui desat.
    Si no ho està, ofereix desar-lo ara mateix.
    Retorna el path absolut del projecte, o None si no s'ha desat.
    """
    from qgis.PyQt.QtWidgets import QMessageBox, QFileDialog
    from qgis.core import QgsProject

    proj_path = QgsProject.instance().absolutePath()
    if proj_path:
        return proj_path

    resp = QMessageBox.question(
        parent_widget,
        "Projecte no desat",
        "Cal desar el projecte QGIS abans de continuar.\n\n"
        "Vols desar-lo ara?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes
    )
    if resp != QMessageBox.StandardButton.Yes:
        return None

    # Obre el diàleg de desar
    path, _ = QFileDialog.getSaveFileName(
        parent_widget,
        "Desa el projecte QGIS",
        "",
        "Projecte QGIS (*.qgz *.qgs)"
    )
    if not path:
        return None

    if not path.lower().endswith(('.qgz', '.qgs')):
        path += '.qgz'

    QgsProject.instance().setFileName(path)
    if QgsProject.instance().write():
        return QgsProject.instance().absolutePath()
    else:
        QMessageBox.critical(
            parent_widget,
            "Error en desar",
            f"No s\'ha pogut desar el projecte a:\n{path}"
        )
        return None


# ── Dimmat temporal de les altres capes IOF durant la digitalització ──────────
# Backup a nivell de mòdul: {layer_id: renderer_original_clonat}. Es manté
# mentre el diàleg de digitalització és obert; es buida en restaurar.
_renderers_originals_iof = {}

# Color de contorn propi per a cada capa IOF durant el dimmat (R,G,B).
# El farciment sempre queda transparent (alpha 0); només canvia el contorn.
_COLORS_DIMMAT_IOF = {
    "IOF_Finques": (147, 112, 219),   # lila
    "IOF_Punts_Aigua": (255, 0, 255),     # magenta
    "IOF_Elements_Singulars": (255, 0, 255),     # magenta
    "IOF_Punts_Inventari": (255, 0, 255),     # magenta
    "IOF_Camins": (255, 0, 0),       # vermell
    "IOF_Infraestructures_PI": (255, 140, 0),     # taronja
    "IOF_Canvis_Us": (0, 188, 212),     # cian
    "IOF_Unitats_Actuacio": (0, 150, 60),      # verd
    "IOF_Rodals": (0, 150, 60),      # verd (mateix, PSGF)
}


def _crea_simbol_dimmat(layer, color_rgb):
    """Crea un símbol amb farciment transparent i contorn/línia del
    color indicat, adaptat al tipus de geometria de `layer` (punt,
    línia o polígon)."""
    from qgis.core import (QgsWkbTypes, QgsMarkerSymbol, QgsLineSymbol,
                           QgsFillSymbol)
    r, g, b = color_rgb
    tipus = QgsWkbTypes.geometryType(layer.wkbType())
    if tipus == QgsWkbTypes.GeometryType.PointGeometry:
        return QgsMarkerSymbol.createSimple({
            'color': '0,0,0,0',
            'outline_color': f'{r},{g},{b},255',
            'outline_width': '0.6',
        })
    elif tipus == QgsWkbTypes.GeometryType.LineGeometry:
        return QgsLineSymbol.createSimple({
            'line_color': f'{r},{g},{b},255',
            'line_width': '0.6',
        })
    else:
        return QgsFillSymbol.createSimple({
            'color': '0,0,0,0',
            'outline_color': f'{r},{g},{b},255',
            'outline_width': '0.6',
            'outline_style': 'solid',
        })


def dimmar_altres_capes_iof(layer_actual):
    """A totes les altres capes IOF (les que comencen per "IOF_"), fa
    transparent el farciment i deixa un contorn/línia d'un color propi
    per capa (vegeu _COLORS_DIMMAT_IOF), perquè es vegi bé l'ortofotomapa
    de sota sense perdre de vista els límits de les altres capes.
    NOMÉS afecta les 8 capes IOF — Cadastre, Topogràfic territorial i
    l'ortofotomapa es queden tal com estaven. Guarda el renderitzador
    original (clonat) de cada capa perquè restaurar_opacitat_capes_iof()
    el pugui recuperar exactament."""
    for lyr in QgsProject.instance().mapLayers().values():
        if lyr.id() == layer_actual.id():
            continue
        if not lyr.name().startswith("IOF_"):
            continue
        color = _COLORS_DIMMAT_IOF.get(lyr.name())
        if color is None:
            continue  # capa IOF no reconeguda (p.ex. una de futura); no tocar
        try:
            _renderers_originals_iof[lyr.id()] = lyr.renderer().clone()
            simbol = _crea_simbol_dimmat(lyr, color)
            lyr.setRenderer(QgsSingleSymbolRenderer(simbol))
            lyr.triggerRepaint()
        except AttributeError:
            pass  # capes sense renderer (p.ex. taules no espacials)


def restaurar_opacitat_capes_iof():
    """Restaura el renderitzador original de les capes IOF que
    dimmar_altres_capes_iof() hagi canviat. Cridar sempre en tancar el
    diàleg de digitalització (closeEvent), fins i tot si l'usuari
    cancel·la sense desar."""
    for layer_id, renderer in list(_renderers_originals_iof.items()):
        lyr = QgsProject.instance().mapLayer(layer_id)
        if lyr is not None:
            try:
                lyr.setRenderer(renderer)
                lyr.triggerRepaint()
            except AttributeError:
                pass
    _renderers_originals_iof.clear()


# ── Numeració dels grups "Topogràfic territorial N" ───────────────────────────
# Cada capa de Referencial Topogràfic Territorial carregada (via
# descàrrega d'Open ICGC o carregant un .gpkg existent) obté el seu
# propi grup numerat, perquè no es barregin les subcapes de diferents
# descàrregues dins d'un sol grup. Es renumeren sempre consecutivament
# (1, 2, 3, ..., sense buits) cada cop que se n'afegeix o elimina un.
_PATRO_GRUP_TOPO = _re.compile(r"^Topogràfic territorial(?: (\d+))?$")


def cerca_grups_topografia():
    """Retorna una llista de (número, node_grup) de tots els grups
    "Topogràfic territorial" / "Topogràfic territorial N" existents a
    tot l'arbre de capes (a qualsevol profunditat), ordenats per número.
    Un grup sense número (d'abans d'introduir aquesta numeració, juliol
    2026) es tracta com a número 0, perquè quedi primer en renumerar."""
    from qgis.core import QgsLayerTreeGroup
    root = QgsProject.instance().layerTreeRoot()
    resultats = []

    def _cerca(node):
        for child in node.children():
            if isinstance(child, QgsLayerTreeGroup):
                m = _PATRO_GRUP_TOPO.match(child.name())
                if m:
                    num = int(m.group(1)) if m.group(1) else 0
                    resultats.append((num, child))
                _cerca(child)

    _cerca(root)
    resultats.sort(key=lambda parell: parell[0])
    return resultats


def renumera_grups_topografia():
    """Renombra tots els grups "Topogràfic territorial ..." perquè
    quedin numerats consecutivament (1, 2, 3, ...), sense buits.
    Cridar sempre després d'afegir o eliminar-ne un."""
    grups = cerca_grups_topografia()
    for i, (_num_antic, grup) in enumerate(grups, start=1):
        nou_nom = f"Topogràfic territorial {i}"
        if grup.name() != nou_nom:
            grup.setName(nou_nom)


def seguent_numero_topografia():
    """Número a assignar al proper grup "Topogràfic territorial N" que
    es creï (sempre consecutiu al final, ja que renumera_grups_topografia()
    manté la resta sense buits)."""
    return len(cerca_grups_topografia()) + 1

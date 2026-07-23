# -*- coding: utf-8 -*-
"""
IOF Assistent — Aplicar format a les capes IOF.
Aplica els mateixos colors que utilitza MiraMon a la capa IOF_Finques,
amb un color per a cada finca basat en el camp codi_finca.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton,
    QMessageBox, QFrame
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsProject, QgsVectorLayer,
    QgsSingleSymbolRenderer, QgsFillSymbol,
    QgsWkbTypes, QgsUnitTypes
)

from .iof_utils import avisa_capa_no_trobada
from .iof_utils import get_layer as _get_layer

# ---------------------------------------------------------------------------
# Paleta de colors Miramon per a finques (43 colors, indexats per codi_finca)
# Font: finques.dbf de les paletes MiraMon
# ---------------------------------------------------------------------------
PALETA_FINQUES = {
    1: (255, 255, 190),
    2: (255, 215, 195),
    3: (204, 255, 204),
    4: (210, 255, 255),
    5: (231, 237, 182),
    6: (255, 221, 255),
    7: (196, 225, 225),
    8: (226, 203, 194),
    9: (203, 235, 208),
    10: (155, 255, 205),
    11: (218, 180, 241),
    12: (255, 128, 0),
    13: (255, 0, 128),
    14: (128, 255, 255),
    15: (128, 128, 255),
    16: (128, 255, 128),
    17: (255, 128, 255),
    18: (255, 128, 128),
    19: (255, 255, 128),
    20: (128, 128, 128),
    21: (0, 0, 128),
    22: (0, 128, 128),
    23: (0, 128, 0),
    24: (128, 128, 0),
    25: (128, 0, 0),
    26: (128, 0, 128),
    27: (64, 64, 64),
    28: (0, 0, 191),
    29: (128, 128, 191),
    30: (0, 191, 191),
    31: (0, 191, 0),
    32: (191, 191, 0),
    33: (191, 0, 0),
    34: (191, 0, 191),
    35: (0, 128, 191),
    36: (128, 0, 191),
    37: (128, 191, 191),
    38: (0, 191, 128),
    39: (128, 191, 0),
    40: (128, 191, 128),
    41: (191, 191, 128),
    42: (191, 128, 0),
    43: (255, 255, 255),
}

LAYER_NAME = "IOF_Finques"  # Color i gruix del contorn de finques extrets de paleta_L.dbf (MiraMon)
# Registre "Límit de pla": /M;/H3/C128,0,128
# /H3 = gruix 3 unitats MiraMon ≈ 0.3 mm a QGIS
# /C128,0,128 = lila RGB(128,0,128) = #800080
BORDER_COLOR = QColor(128, 0, 128)  # lila MiraMon
BORDER_WIDTH = 0.3                   # gruix /H3 de paleta_L.dbf MiraMon


def _get_color_for_codi(codi):
    """Retorna el QColor corresponent al codi de finca (cicla cada 43)."""
    if not codi or codi != codi:
        return QColor(200, 200, 200)  # gris per a valors nuls
    try:
        n = int(codi)
    except (TypeError, ValueError):
        return QColor(200, 200, 200)
    # Ciclar la paleta si hi ha més de 43 finques
    idx = ((n - 1) % 43) + 1
    r, g, b = PALETA_FINQUES.get(idx, (200, 200, 200))
    return QColor(r, g, b)


# Codis compostos que inclouen àmbit geogràfic i cal normalitzar a codi base
_CODI_NORMALITZAT = {
    'PnMER': 'Pn', 'PnPRE': 'Pn',
    'PsMER': 'Ps', 'PsPIR': 'Ps',
    'PhCON': 'Ph', 'PhLIT': 'Ph',
    'QibMUN': 'Qib', 'QibTB': 'Qib',
    'QiiLIT': 'Qii', 'QiiMUN': 'Qii',
    'RIB_MUN_NO': 'RIB', 'RIB_PIR': 'RIB',
    'RIB_PRE': 'RIB', 'RIB_TB': 'RIB', 'RIB_TB_NOR': 'RIB',
}


def _normalitza_codi(codi):
    """Normalitza un codi de formació al seu codi base de color."""
    if not codi:
        return codi
    return _CODI_NORMALITZAT.get(codi, codi)


def _parse_codis_formacio(codi_for):
    """
    Separa un codi de formació forestal en (principal, secundari) normalitzats.
    Exemples:
      'Qs'       → ('Qs', None)
      'Qs_Al'    → ('Qs', 'Al')
      'PnMER_Ph' → ('Pn', 'Ph')
      'Ps_Al'    → ('Ps', 'Al')
    """
    if not codi_for:
        return None, None
    # Casos especials amb àmbit geogràfic al principi (PnMER, PsMER, etc.)
    if codi_for in _CODI_NORMALITZAT:
        return _CODI_NORMALITZAT[codi_for], None
    parts = codi_for.split('_', 1)
    principal = _normalitza_codi(parts[0]) if parts else None
    secundari = _normalitza_codi(parts[1]) if len(parts) > 1 else None
    return principal, secundari


def _apply_unitats_labels(layer):
    """
    Etiquetes de la capa d'unitats:
    - Unitats normals (_label = codi_ua): Arial 10pt negreta.
    - "Exclòs de l'IOF" (no ordenades): Arial 6pt gris.
    - Unitats sense _label (no forestals): sense etiqueta.
    Font d'etiqueta única amb mida i color condicionals via data-defined.
    """
    from qgis.core import (
        QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
        QgsVectorLayerSimpleLabeling, QgsProperty,
    )
    from qgis.PyQt.QtGui import QFont, QColor

    if "_label" not in layer.fields().names():
        layer.setLabelsEnabled(False)
        return

    pal = QgsPalLayerSettings()
    # Mostrar _label per a totes les unitats:
    # - Excloses: sempre (independentment de l'àrea)
    # - Resta: només el polígon més gran per _label (evitar duplicats)
    pal.fieldName = (
        'if("_label" IS NOT NULL,'
        ' if("_label" LIKE \'%Exclòs%\','
        '  "_label",'
        '  if($area = maximum($area, "_label"), "_label", NULL)'
        ' ),'
        ' NULL)'
    )
    pal.isExpression = True
    pal.enabled = True
    pal.labelPerPart = False
    pal.placement = QgsPalLayerSettings.Placement.AroundPoint

    fmt = QgsTextFormat()
    fmt.setFont(QFont("Arial", 14, QFont.Weight.Bold))
    fmt.setSize(14)
    fmt.setColor(QColor(0, 0, 0))
    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setColor(QColor(255, 255, 255))
    fmt.setBuffer(buf)
    pal.setFormat(fmt)

    # Mida condicional: 6pt per "Exclòs", 10pt per la resta
    pal.dataDefinedProperties().setProperty(
        QgsPalLayerSettings.Property.Size,
        QgsProperty.fromExpression(
            "CASE WHEN \"_label\" LIKE '%Exclòs%' THEN 6 ELSE 14 END"
        )
    )
    # Color condicional: gris per "Exclòs", negre per la resta
    pal.dataDefinedProperties().setProperty(
        QgsPalLayerSettings.Property.Color,
        QgsProperty.fromExpression(
            "CASE WHEN \"_label\" LIKE '%Exclòs%' THEN '128,128,128,255' ELSE '0,0,0,255' END"
        )
    )
    # Negreta condicional: no per "Exclòs"
    pal.dataDefinedProperties().setProperty(
        QgsPalLayerSettings.Property.Bold,
        QgsProperty.fromExpression(
            "\"_label\" NOT LIKE '%Exclòs%' AND \"_label\" IS NOT NULL"
        )
    )

    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    layer.setLabelsEnabled(True)


def _classifica_contorn(feat, all_feats_bbox, codi_field, codi_by_fid=None):
    """
    Retorna True (R, ratlla-punt) si el polígon té algun veí (per bbox)
    amb codi_rodal/codi_ua diferent.
    Retorna False (U, continu fi) si tots els veïns tenen el mateix codi.

    `codi_by_fid` (opcional) és un dict {fid: codi} precalculat que evita
    re-extreure i normalitzar el codi de cada veí a cada comparació.
    """
    def _codi_de(f):
        if codi_by_fid is not None:
            return codi_by_fid.get(f.id(), "")
        try:
            v = f[codi_field]
            if v and v == v:
                return str(v).strip()
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        return ""

    geom_a = feat.geometry()
    if not geom_a or geom_a.isEmpty():
        return False

    codi_a = _codi_de(feat)
    if not codi_a:
        return False

    bb_a = geom_a.boundingBox()
    from qgis.core import QgsRectangle
    bb_exp = QgsRectangle(
        bb_a.xMinimum() - 0.5,
        bb_a.yMinimum() - 0.5,
        bb_a.xMaximum() + 0.5,
        bb_a.yMaximum() + 0.5
    )

    for other_feat, bb_other in all_feats_bbox:
        if other_feat.id() == feat.id():
            continue
        if not bb_exp.intersects(bb_other):
            continue
        codi_b = _codi_de(other_feat)
        if codi_b and codi_a != codi_b:
            return True
    return False


def reset_finques_style(layer):
    """
    Reinicia l'estil de la capa IOF_Finques al símbol únic per defecte:
    farciment blanc semitransparent, contorn negre continu 0.5 mm.
    Desactiva les etiquetes.
    """
    sym = QgsFillSymbol.createSimple({
        'color': '255,255,255,180',
        'outline_color': '0,0,0',
        'outline_width': '0.5',
        'outline_style': 'solid',
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setLabelsEnabled(False)
    layer.setOpacity(1.0)
    layer.triggerRepaint()


def reset_unitats_style(layer):
    """
    Reinicia l'estil de la capa d'unitats al símbol únic per defecte:
    farciment blanc semitransparent, contorn negre continu 0.5 mm.
    Elimina també el camp _estil si existeix, i la capa auxiliar de
    límits de rodal generada per apply_unitats_style().
    """
    from qgis.core import QgsProject

    # El nom visible de la capa auxiliar és dinàmic (_lbl_limit: "Límit
    # d'unitat d'actuació" a un PTGMF, "Límit de rodal" a un PSGF), així
    # que es localitza per la taula tècnica dins del mateix gpkg
    # (fixa), no pel nom visible.
    NOM_TAULA_LIMITS = "limits_rodal_unitats_actuacio"
    for lyr in list(QgsProject.instance().mapLayers().values()):
        if f"layername={NOM_TAULA_LIMITS}" in lyr.dataProvider().dataSourceUri():
            QgsProject.instance().removeMapLayer(lyr.id())

    sym = QgsFillSymbol.createSimple({
        'color': '255,255,255,180',
        'outline_color': '0,0,0',
        'outline_width': '0.5',
        'outline_style': 'solid',
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setLabelsEnabled(False)

    # Eliminar els camps _estil i _draw_order si existeixen
    fields = layer.fields()
    to_delete = [fields.indexOf(c) for c in ('_estil', '_draw_order') if fields.indexOf(c) >= 0]
    if to_delete:
        layer.dataProvider().deleteAttributes(to_delete)
        layer.updateFields()

    layer.setOpacity(1.0)
    layer.triggerRepaint()


def reset_camins_style(layer):
    from qgis.core import QgsLineSymbol, QgsSingleSymbolRenderer
    sym = QgsLineSymbol.createSimple({'color': '0,0,0,255', 'width': '0.5', 'penstyle': 'solid'})
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setLabelsEnabled(False)
    layer.setOpacity(1.0)
    layer.triggerRepaint()


def reset_aigua_style(layer):
    from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer
    sym = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': '0,128,255,255', 'outline_style': 'no', 'size': '3'})
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setLabelsEnabled(False)
    layer.setOpacity(1.0)
    layer.triggerRepaint()


def reset_elements_style(layer):
    from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer
    sym = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': '0,0,0,255', 'outline_style': 'no', 'size': '3'})
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setLabelsEnabled(False)
    layer.setOpacity(1.0)
    layer.triggerRepaint()


def reset_inventari_style(layer):
    from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer
    sym = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': '0,0,0,255', 'outline_style': 'no', 'size': '3'})
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setLabelsEnabled(False)
    layer.setOpacity(1.0)
    layer.triggerRepaint()


def _apply_preview_labels(layer, expression, field_name=None):
    """
    Aplica un estil d'etiquetes provisional a la capa per mostrar
    el valor d'un camp numèric amb 2 decimals durant l'ompliment
    de la taula d'atributs.

    Paràmetres:
      layer      : QgsVectorLayer
      expression : expressió QGIS per al text de l'etiqueta
                   ex: "format_number(\"superficie\", 2) + ' ha'"
      field_name : (opcional) si s'indica, només aplica si el camp existeix

    L'estil definitiu (apply_*_style) eliminarà aquestes etiquetes
    i aplicarà les etiquetes definitives de MiraMon.
    """
    from qgis.core import (
        QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
        QgsVectorLayerSimpleLabeling,
    )
    from qgis.PyQt.QtGui import QFont, QColor

    if field_name and layer.fields().indexOf(field_name) < 0:
        return

    pal = QgsPalLayerSettings()
    pal.fieldName = expression
    pal.isExpression = True
    pal.enabled = True

    fmt = QgsTextFormat()
    fmt.setFont(QFont("Calibri", 8))
    fmt.setSize(8)
    fmt.setColor(QColor(30, 30, 30))

    buf = QgsTextBufferSettings()
    buf.setEnabled(True)
    buf.setSize(0.8)
    buf.setColor(QColor(255, 255, 255))
    fmt.setBuffer(buf)

    pal.setFormat(fmt)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
    layer.setLabelsEnabled(True)
    layer.setOpacity(1.0)
    layer.triggerRepaint()


def _apply_virtual_format_fields(layer, camp_configs):
    """
    Afegeix camps virtuals (format_number) per mostrar Double amb 2 decimals.
    """
    from qgis.core import QgsField, QgsAttributeTableConfig
    from qgis.PyQt.QtCore import QVariant
    for nom_real, alias_mostrat in camp_configs:
        nom_v = "v_" + nom_real
        while True:
            idx_v = layer.fields().indexOf(nom_v)
            if idx_v < 0:
                break
            layer.removeExpressionField(idx_v)
        if layer.fields().indexOf(nom_real) < 0:
            continue
        expr = 'COALESCE(format_number("' + nom_real + '", 2), \'\')'
        idx = layer.addExpressionField(
            expr, QgsField(nom_v, QVariant.String, "string", 20)
        )
        layer.setFieldAlias(idx, alias_mostrat)
    noms_reals = {nom for nom, _ in camp_configs}
    noms_virtuals = {"v_" + nom for nom in noms_reals}
    cfg = layer.attributeTableConfig()
    columns = cfg.columns()
    for col in columns:
        if col.name in noms_reals:
            col.hidden = True
        elif col.name in noms_virtuals:
            col.hidden = False
    noms_existents = {c.name for c in columns}
    for nom_real, alias in camp_configs:
        nom_v = "v_" + nom_real
        if nom_v not in noms_existents:
            nova = QgsAttributeTableConfig.ColumnConfig()
            nova.name = nom_v
            nova.hidden = False
            nova.width = -1
            pos = next((i for i, c in enumerate(columns)
                        if c.name == nom_real), len(columns))
            columns.insert(pos + 1, nova)
    cfg.setColumns(columns)
    layer.setAttributeTableConfig(cfg)


def apply_unitats_style(layer):
    """
    Aplica el format MiraMon a IOF_Rodals / IOF_Unitats_Actuacio.

    QgsRuleBasedRenderer amb DOS grups (dues passades visuals):

    GRUP 1 — "Vegetació" (llegenda de formacions/usos):
      Per a cada combinació (codi_for, codi_us): farciment sòlid MiraMon
      + contorn fi negre continu 0.26 mm. Totes les unitats.

    GRUP 2 — "Límits de rodal" (llegenda de límits):
      "Límit de rodal": sense farciment + ratlla-punt 0.7 mm negre.
        → NOMÉS unitats amb for_forestal i SENSE codi_us.
      (La resta no té contorn de rodal.)
    """
    from .iof_taules import is_forestal, COLORS_VEGETACIO, FORMACIONS, USOS_VEGETACIO
    from qgis.core import (
        QgsRuleBasedRenderer,
        QgsFillSymbol, QgsSimpleFillSymbolLayer,
        QgsLinePatternFillSymbolLayer, QgsField,
    )
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import QVariant

    desc_formacio = {codi: desc for codi, desc in FORMACIONS}
    desc_us = {codi: nom for codi, nom, _, _ in USOS_VEGETACIO}

    fields_names = layer.fields().names()
    campo_for = "for_forestal" if "for_forestal" in fields_names else None
    campo_us = "codi_us" if "codi_us" in fields_names else None
    codi_field = "codi_ua" if "codi_ua" in fields_names else \
                 "codi_rodal" if "codi_rodal" in fields_names else None

    feats = list(layer.getFeatures())

    # ------------------------------------------------------------------ #
    # Desar _estil, _draw_order, _label
    # ------------------------------------------------------------------ #
    CAMP_ESTIL = "_estil"
    CAMP_ORDER = "_draw_order"
    CAMP_LABEL = "_label"
    for camp, tq in [(CAMP_ESTIL, QVariant.String),
                     (CAMP_ORDER, QVariant.Int),
                     (CAMP_LABEL, QVariant.String)]:
        if camp not in layer.fields().names():
            layer.dataProvider().addAttributes([QgsField(name=camp, type=tq)])
            layer.updateFields()

    layer.startEditing()
    idx_estil = layer.fields().indexOf(CAMP_ESTIL)
    idx_order = layer.fields().indexOf(CAMP_ORDER)
    idx_label = layer.fields().indexOf(CAMP_LABEL)
    idx_codi = layer.fields().indexOf(codi_field) if codi_field else -1

    # Detectar unitats no ordenades llegint el camp _label existent
    # (el wizard escriu "No ordenat" o "Exclòs de l'IOF" en digitalitzar)
    campo_label_prev = "_label" if "_label" in fields_names else None

    estil_per_fid = {}  # fid -> (clau_visual, codi_for, codi_us)
    exclos_fids = set()  # fids de unitats excloses (encara que tinguin formació)
    for feat in feats:
        codi_for = str(feat[campo_for]).strip() \
            if campo_for and feat[campo_for] and feat[campo_for] == feat[campo_for] else ""
        codi_us = str(feat[campo_us]).strip() \
            if campo_us and feat[campo_us] and feat[campo_us] == feat[campo_us] else ""
        if codi_for.startswith("/"):
            codi_for = ""
        if codi_us.startswith("/"):
            codi_us = ""

        # Estat no ordenat detectat per l'etiqueta existent
        es_no_ordenat = False
        if campo_label_prev is not None:
            v_lbl = feat[campo_label_prev]
            if v_lbl and v_lbl == v_lbl:
                _lbl_txt = str(v_lbl).strip().lower()
                es_no_ordenat = (
                    "no ordenat" in _lbl_txt or "exclòs de l" in _lbl_txt or "exclos de l" in _lbl_txt
                )

        if idx_codi >= 0:
            v = feat[codi_field]
            if v and v == v and str(v).startswith("/"):
                layer.changeAttributeValue(feat.id(), idx_codi, None)

        # Unitat exclosa SENSE formació ni ús → estil blanc (__exclos__)
        if es_no_ordenat and not codi_for and not codi_us:
            layer.changeAttributeValue(feat.id(), idx_estil, '__exclos__')
            layer.changeAttributeValue(feat.id(), idx_order, 0)
            layer.changeAttributeValue(feat.id(), idx_label, "Exclòs de l'IOF")
            exclos_fids.add(feat.id())
            continue

        # Unitat exclosa AMB formació/ús → manté el farciment de la formació,
        # etiqueta = formació + Exclòs de l'IOF, límit de línia fina.
        if es_no_ordenat:
            clau_visual = f"{codi_for}|{codi_us}"
            estil_per_fid[feat.id()] = (clau_visual, codi_for, codi_us)
            layer.changeAttributeValue(feat.id(), idx_estil, clau_visual)
            layer.changeAttributeValue(feat.id(), idx_order, 0)
            layer.changeAttributeValue(feat.id(), idx_label, "Exclòs de l'IOF")
            exclos_fids.add(feat.id())
            continue

        # Unitat ordenada sense formació ni ús → blanc exclòs
        if not codi_for and not codi_us:
            layer.changeAttributeValue(feat.id(), idx_estil, '__exclos__')
            layer.changeAttributeValue(feat.id(), idx_order, 0)
            layer.changeAttributeValue(feat.id(), idx_label, "Exclòs de l'IOF")
            exclos_fids.add(feat.id())
            continue

        clau_visual = f"{codi_for}|{codi_us}"
        estil_per_fid[feat.id()] = (clau_visual, codi_for, codi_us)
        layer.changeAttributeValue(feat.id(), idx_estil, clau_visual)
        layer.changeAttributeValue(feat.id(), idx_order, 0)

        # _label
        codi_val = feat[codi_field] if codi_field else None
        codi_str = str(codi_val).strip() if codi_val and codi_val == codi_val else ""
        if codi_str and not codi_str.startswith("/"):
            lbl = codi_str
        else:
            lbl = None
        layer.changeAttributeValue(feat.id(), idx_label, lbl)

    if not layer.commitChanges():
        errs = "; ".join(layer.commitErrors())
        layer.rollBack()
        raise RuntimeError(f"No s'han pogut desar els camps d'estil: {errs}")

    # ------------------------------------------------------------------ #
    # Símbols de farciment (GRUP 1)
    # ------------------------------------------------------------------ #
    ALPHA = 128

    def _sym_farciment(codi_for, codi_us):
        """Farciment MiraMon sense contorn. Rendering pass 0."""
        if codi_us and codi_us in COLORS_VEGETACIO:
            r, g, b = COLORS_VEGETACIO[codi_us]
        else:
            principal, _ = _parse_codis_formacio(codi_for)
            r, g, b = COLORS_VEGETACIO.get(principal, (180, 230, 180)) \
                if principal else (180, 230, 180)

        principal, secundari = _parse_codis_formacio(codi_for)
        if secundari and secundari in COLORS_VEGETACIO and not (codi_us and codi_us in COLORS_VEGETACIO):
            rs, gs, bs = COLORS_VEGETACIO[secundari]
            fill = QgsSimpleFillSymbolLayer()
            fill.setFillColor(QColor(r, g, b, ALPHA))
            fill.setStrokeStyle(Qt.PenStyle.NoPen)
            fill.setRenderingPass(0)
            hatch = QgsLinePatternFillSymbolLayer()
            hatch.setColor(QColor(rs, gs, bs, ALPHA))
            hatch.setLineWidth(1.0)
            hatch.setDistance(4.0)
            hatch.setLineAngle(45)
            hatch.setRenderingPass(0)
            sym = QgsFillSymbol()
            sym.deleteSymbolLayer(0)
            sym.appendSymbolLayer(fill)
            sym.appendSymbolLayer(hatch)
        else:
            fill = QgsSimpleFillSymbolLayer()
            fill.setFillColor(QColor(r, g, b, ALPHA))
            fill.setStrokeStyle(Qt.PenStyle.NoPen)
            fill.setRenderingPass(0)
            sym = QgsFillSymbol()
            sym.deleteSymbolLayer(0)
            sym.appendSymbolLayer(fill)

        return sym

    def _sym_rodal():
        """Límit de rodal/UA: línia blanca gruixuda + negra discontínua per sobre.
        Usa QgsSimpleLineSymbolLayer dins QgsGeometryGeneratorSymbolLayer."""
        from qgis.core import (QgsGeometryGeneratorSymbolLayer, QgsSimpleLineSymbolLayer,
                               QgsLineSymbol)

        fill = QgsSimpleFillSymbolLayer.create({
            "color": "0,0,0,0", "outline_style": "no"})
        fill.setRenderingPass(0)

        # Línia exterior blanca (1.0 mm) — halo
        line_gen_ext = QgsGeometryGeneratorSymbolLayer.create({
            'geometryModifier': 'exterior_ring($geometry)',
            'SymbolType': 'Line',
        })
        lyr_ext = QgsSimpleLineSymbolLayer()
        lyr_ext.setColor(QColor(255, 255, 255))
        lyr_ext.setWidth(1.0)
        lyr_ext.setPenStyle(Qt.PenStyle.SolidLine)
        sym_ext = QgsLineSymbol()
        sym_ext.deleteSymbolLayer(0)
        sym_ext.appendSymbolLayer(lyr_ext)
        line_gen_ext.setSubSymbol(sym_ext)
        line_gen_ext.setRenderingPass(2)

        # Línia interior negra discontínua (0.7 mm)
        line_gen_int = QgsGeometryGeneratorSymbolLayer.create({
            'geometryModifier': 'exterior_ring($geometry)',
            'SymbolType': 'Line',
        })
        lyr_int = QgsSimpleLineSymbolLayer()
        lyr_int.setColor(QColor(0, 0, 0))
        lyr_int.setWidth(0.7)
        lyr_int.setPenStyle(Qt.PenStyle.DashDotLine)
        sym_int = QgsLineSymbol()
        sym_int.deleteSymbolLayer(0)
        sym_int.appendSymbolLayer(lyr_int)
        line_gen_int.setSubSymbol(sym_int)
        line_gen_int.setRenderingPass(2)

        sym = QgsFillSymbol()
        sym.deleteSymbolLayer(0)
        sym.appendSymbolLayer(fill)
        sym.appendSymbolLayer(line_gen_ext)
        sym.appendSymbolLayer(line_gen_int)
        return sym

    def _sym_linia_fina():
        """Transparent + línia contínua fina 0.26 mm via exterior_ring."""
        from qgis.core import QgsGeometryGeneratorSymbolLayer, QgsSymbol
        fill = QgsSimpleFillSymbolLayer.create({
            "color": "0,0,0,0", "outline_style": "no"})
        fill.setRenderingPass(0)
        line_gen = QgsGeometryGeneratorSymbolLayer.create({
            'geometryModifier': 'exterior_ring($geometry)',
            'SymbolType': 'Line',
        })
        line_sym = QgsSymbol.defaultSymbol(QgsWkbTypes.GeometryType.LineGeometry)
        if line_sym:
            line_sym.setColor(QColor(0, 0, 0))
            line_sym.setWidth(0.26)
            line_gen.setSubSymbol(line_sym)
        line_gen.setRenderingPass(1)
        sym = QgsFillSymbol()
        sym.deleteSymbolLayer(0)
        sym.appendSymbolLayer(fill)
        sym.appendSymbolLayer(line_gen)
        return sym

    def _sym_transparent():
        fill = QgsSimpleFillSymbolLayer.create({
            "color": "0,0,0,0", "outline_style": "no"})
        sym = QgsFillSymbol()
        sym.deleteSymbolLayer(0)
        sym.appendSymbolLayer(fill)
        return sym

    # ------------------------------------------------------------------ #
    # Construir QgsRuleBasedRenderer
    # ------------------------------------------------------------------ #
    ordre_for = [codi for codi, _ in FORMACIONS]
    ordre_us = [codi for codi, _, _, _ in USOS_VEGETACIO]

    def sort_key(codi_for, codi_us):
        # Primer formacions forestals (taula 1), després usos (taula 2)
        if codi_for and codi_for in ordre_for:
            return (0, ordre_for.index(codi_for))
        if codi_us and codi_us in ordre_us:
            return (1, ordre_us.index(codi_us))
        return (2, 9999)

    root = QgsRuleBasedRenderer.Rule(None)

    # Recollir claus úniques ordenades (per a les regles de farciment)
    claus_vistes = {}
    for fid, (clau_visual, codi_for, codi_us) in estil_per_fid.items():
        if clau_visual not in claus_vistes:
            claus_vistes[clau_visual] = (codi_for, codi_us)

    # ------------------------------------------------------------------ #
    # Classificar claus visuals en grups
    # ------------------------------------------------------------------ #
    from .iof_taules import is_arbrat as _is_arbrat

    _is_ptgmf = "codi_ua" in layer.fields().names()
    _lbl_limit = "Límit d'unitat d'actuació" if _is_ptgmf else "Límit de rodal"

    has_exclos = any(
        str(feat[campo_for] or '').strip() in ('', 'NULL') and str(feat[campo_us] or '').strip() in ('', 'NULL')
        for feat in feats
    ) if (campo_for or campo_us) else False
    if has_exclos:
        claus_vistes['__exclos__'] = ('', '')

    claus_no_ord = {}
    claus_us_veg = {}
    claus_formacio = {}

    for clau_visual, (codi_for, codi_us) in claus_vistes.items():
        if clau_visual == '__exclos__':
            claus_no_ord[clau_visual] = (codi_for, codi_us)
        elif codi_us and not is_forestal(codi_us):
            claus_no_ord[clau_visual] = (codi_for, codi_us)
        elif codi_us and is_forestal(codi_us) and not _is_arbrat(codi_us):
            claus_us_veg[clau_visual] = (codi_for, codi_us)
        else:
            claus_formacio[clau_visual] = (codi_for, codi_us)

    def _sym_limit_rodal_llegenda():
        return QgsFillSymbol.createSimple({
            'color': '0,0,0,0', 'outline_color': '0,0,0,255',
            'outline_width': '0.7', 'outline_style': 'dash',
        })

    from qgis.core import (QgsGeometryGeneratorSymbolLayer as _GGL,
                           QgsSimpleLineSymbolLayer as _SLL,
                           QgsLineSymbol as _LS)
    sq = "'"

    def _sym_linia_fina_real():
        """Símbol de mapa: línia contínua fina 0.26mm via exterior_ring (pass 1).
        Farciment data-defined: blanc per a __exclos__, transparent per la resta."""
        from qgis.core import QgsProperty, QgsSymbolLayer
        sym = QgsFillSymbol.createSimple({'color': '0,0,0,0', 'outline_style': 'no'})
        fill_layer = sym.symbolLayer(0)
        fill_layer.setRenderingPass(0)
        # Farciment blanc només per a unitats excloses
        fill_layer.dataDefinedProperties().setProperty(
            QgsSymbolLayer.Property.PropertyFillColor,
            QgsProperty.fromExpression(
                'CASE WHEN "_estil" = ' + sq + '__exclos__' + sq + ' THEN ' + sq + '255,255,255,200' + sq + ' ELSE ' + sq + '0,0,0,0' + sq + ' END'
            )
        )
        gen = _GGL.create({'geometryModifier': 'exterior_ring($geometry)', 'SymbolType': 'Line'})
        lyr = _SLL()
        lyr.setColor(QColor(0, 0, 0))
        lyr.setWidth(0.26)
        lyr.setPenStyle(Qt.PenStyle.SolidLine)
        ls = _LS()
        ls.deleteSymbolLayer(0)
        ls.appendSymbolLayer(lyr)
        gen.setSubSymbol(ls)
        gen.setRenderingPass(1)
        sym.appendSymbolLayer(gen)
        return sym

    # ============ GRUP: Límits del pla (dibuixen el limit al mapa) ============
    # Línia fina contínua per a TOTES les unitats, independentment de si
    # són forestals, tenen ús o estan excloses. El contorn gruixut de
    # ratlla-punt entre rodals/UA DIFERENTS es dibuixa a part, en una
    # capa auxiliar dissolta per codi_field (vegeu més avall) — depèn de
    # comparar cada unitat amb la seva veïna, no és un atribut de la
    # pròpia unitat que es pugui expressar amb una regla per feature.
    grup_limits = QgsRuleBasedRenderer.Rule(_sym_linia_fina_real())
    grup_limits.setLabel("Límit d'ús / vegetació")
    root.appendChild(grup_limits)

    # ============ GRUP: No ordenat (nomes farciment, sense contorn) ============
    grup_no_ord = QgsRuleBasedRenderer.Rule(None)
    grup_no_ord.setLabel("No ordenat")
    for clau_visual, (codi_for, codi_us) in sorted(
            claus_no_ord.items(), key=lambda x: sort_key(x[1][0], x[1][1])):
        if clau_visual == '__exclos__':
            continue
        sym = _sym_farciment(codi_for, codi_us)
        lbl = desc_us.get(codi_us, codi_us) if codi_us else '(sense codi)'
        regla = QgsRuleBasedRenderer.Rule(sym)
        regla.setLabel(lbl)
        regla.setFilterExpression('"_estil" = ' + sq + clau_visual + sq)
        grup_no_ord.appendChild(regla)
    root.appendChild(grup_no_ord)

    # ============ GRUP: Ús / Vegetació (nomes farciment) ============
    if claus_us_veg:
        grup_us_veg = QgsRuleBasedRenderer.Rule(None)
        grup_us_veg.setLabel("Ús / Vegetació")
        for clau_visual, (codi_for, codi_us) in sorted(
                claus_us_veg.items(), key=lambda x: sort_key(x[1][0], x[1][1])):
            sym = _sym_farciment(codi_for, codi_us)
            lbl = (desc_us.get(codi_us, codi_us) if codi_us
                   else desc_formacio.get(codi_for, codi_for))
            regla = QgsRuleBasedRenderer.Rule(sym)
            regla.setLabel(lbl)
            regla.setFilterExpression('"_estil" = ' + sq + clau_visual + sq)
            grup_us_veg.appendChild(regla)
        root.appendChild(grup_us_veg)

    # ============ GRUP: Formació forestal arbrada (nomes farciment) ============
    if claus_formacio:
        grup_for = QgsRuleBasedRenderer.Rule(None)
        grup_for.setLabel("Formació forestal arbrada")
        for clau_visual, (codi_for, codi_us) in sorted(
                claus_formacio.items(), key=lambda x: sort_key(x[1][0], x[1][1])):
            sym = _sym_farciment(codi_for, codi_us)
            lbl = (desc_us.get(codi_us, codi_us) if codi_us and codi_us in COLORS_VEGETACIO
                   else desc_formacio.get(codi_for, codi_for) if codi_for
                   else '(sense codi)')
            regla = QgsRuleBasedRenderer.Rule(sym)
            regla.setLabel(lbl)
            regla.setFilterExpression('"_estil" = ' + sq + clau_visual + sq)
            grup_for.appendChild(regla)
        root.appendChild(grup_for)

    renderer = QgsRuleBasedRenderer(root)
    renderer.setUsingSymbolLevels(True)
    layer.setRenderer(renderer)

    _apply_unitats_labels(layer)
    layer.setOpacity(1.0)
    _apply_virtual_format_fields(layer, [
        ("sup_ord", "Sup. ord. (ha)"),
        ("sup_forestal", "Sup. forestal (ha)"),
        ("sup_arbrada", "Sup. arbrada (ha)"),
    ])
    layer.setOpacity(1.0)
    layer.triggerRepaint()

    # ------------------------------------------------------------------ #
    # Capa auxiliar de límits de rodal/UA (dissolta per codi_field)
    # ------------------------------------------------------------------ #
    # El contorn gruixut de ratlla-punt només ha d'aparèixer entre
    # unitats amb un rodal/UA DIFERENT — mai entre tipologies forestals
    # que en comparteixen el número. Com que QGIS estilitza cada polígon
    # sencer, no cada costat per separat, no es pot expressar amb una
    # regla per feature (una unitat pot tenir una veïna del mateix rodal
    # en un costat i d'un altre rodal a l'altre costat). La solució és
    # dissoldre totes les unitats pel seu codi_field: les vores internes
    # entre unitats del mateix rodal desapareixen en dissoldre's, i el
    # contorn resultant són exactament (i només) els límits entre rodals
    # diferents. Es dibuixa com a capa independent, per sobre.
    if codi_field:
        _regenera_capa_limits_rodal(layer, codi_field, _sym_limit_rodal_dissolt, _lbl_limit)


def _sym_limit_rodal_dissolt():
    """Símbol per a la capa auxiliar de límits de rodal/UA (dissolta).

    Fa servir boundary($geometry) en lloc d'exterior_ring($geometry):
    un rodal amb parcel·les no contigües dona, en dissoldre's, un
    multi-polígon, i exterior_ring() només considera la primera part
    en geometries multi-part (patró conegut de QGIS en diverses
    funcions de conversió de geometria). boundary() gestiona
    correctament totes les parts, i també qualsevol forat intern —cosa
    que aquí és correcta, ja que un forat en un rodal dissolt representa
    un límit real amb el que hi ha a dins (un altre rodal o una
    exclusió)."""
    from qgis.core import (QgsGeometryGeneratorSymbolLayer, QgsSimpleLineSymbolLayer,
                           QgsLineSymbol)
    sym = QgsFillSymbol.createSimple({'color': '0,0,0,0', 'outline_style': 'no'})
    sym.symbolLayer(0).setRenderingPass(0)

    gen_ext = QgsGeometryGeneratorSymbolLayer.create(
        {'geometryModifier': 'boundary($geometry)', 'SymbolType': 'Line'})
    lyr_ext = QgsSimpleLineSymbolLayer()
    lyr_ext.setColor(QColor(255, 255, 255))
    lyr_ext.setWidth(1.0)
    lyr_ext.setPenStyle(Qt.PenStyle.SolidLine)
    ls_ext = QgsLineSymbol()
    ls_ext.deleteSymbolLayer(0)
    ls_ext.appendSymbolLayer(lyr_ext)
    gen_ext.setSubSymbol(ls_ext)
    gen_ext.setRenderingPass(2)
    sym.appendSymbolLayer(gen_ext)

    gen_int = QgsGeometryGeneratorSymbolLayer.create(
        {'geometryModifier': 'boundary($geometry)', 'SymbolType': 'Line'})
    lyr_int = QgsSimpleLineSymbolLayer()
    lyr_int.setColor(QColor(0, 0, 0))
    lyr_int.setWidth(0.7)
    lyr_int.setPenStyle(Qt.PenStyle.DashDotLine)
    ls_int = QgsLineSymbol()
    ls_int.deleteSymbolLayer(0)
    ls_int.appendSymbolLayer(lyr_int)
    gen_int.setSubSymbol(ls_int)
    gen_int.setRenderingPass(2)
    sym.appendSymbolLayer(gen_int)

    return sym


def _regenera_capa_limits_rodal(layer, codi_field, sym_limit_rodal_factory, etiqueta):
    """Dissol `layer` per `codi_field` i (re)crea la capa auxiliar amb el
    contorn de ratlla-punt, just a sobre de `layer` a l'arbre de capes.

    Es desa com a taula dins del mateix GeoPackage de `layer` (no com a
    capa en memòria/temporal) perquè no surti amb l'avís de "temporal"
    al panell de capes, i el seu nom visible és `etiqueta` (p. ex.
    "Límit d'unitat d'actuació" a un PTGMF, "Límit de rodal" a un
    PSGF) — el mateix text que ja es feia servir a la llegenda abans.

    Elimina la versió anterior (per nom de capa al projecte) abans de
    crear-ne una de nova, per no acumular-ne còpies cada cop que es
    torna a aplicar l'estil.
    """
    import os
    import processing
    from qgis.core import (QgsProject, QgsVectorLayer, QgsMessageLog, Qgis,
                           QgsFeatureRequest, QgsLayerTreeLayer)

    NOM_TAULA = "limits_rodal_unitats_actuacio"

    # Es localitza per la taula tècnica dins del gpkg, no pel nom
    # visible (etiqueta) — així funciona igual si mai canvia entre
    # PTGMF i PSGF dins del mateix projecte.
    for lyr_antiga in list(QgsProject.instance().mapLayers().values()):
        if f"layername={NOM_TAULA}" in lyr_antiga.dataProvider().dataSourceUri():
            QgsProject.instance().removeMapLayer(lyr_antiga.id())

    try:
        uri = layer.dataProvider().dataSourceUri()
        gpkg_path = uri.split('|')[0]
        if not os.path.exists(gpkg_path):
            raise RuntimeError(f"No s'ha trobat el fitxer GeoPackage: {gpkg_path}")

        # Les unitats que només tenen codi_us (sense for_forestal — p.ex.
        # erm, edificis...) no han de generar mai un límit de rodal propi:
        # sempre s'han de veure amb línia fina, encara que la unitat del
        # costat tingui un rodal diferent. Com que normalment aquestes
        # unitats no tenen (o no haurien de tenir) un codi_rodal/codi_ua
        # propi amb sentit de subdivisió forestal, dissoldre-les tal
        # qual les tractaria com un grup a part i hi dibuixaria ratlla-
        # punt on no toca. Per evitar-ho, es fusionen primer amb el veí
        # amb qui comparteixen més vora (qgis:eliminateselectedpolygons,
        # mode "Largest Common Boundary") — així "hereten" el codi_rodal
        # del veí forestal abans de dissoldre, i la vora que compartien
        # queda dins del mateix grup dissolt (línia fina, mai ratlla-punt).
        copia = layer.materialize(QgsFeatureRequest())
        copia.selectByExpression(
            '("codi_us" IS NOT NULL AND "codi_us" != \'\') '
            'AND ("for_forestal" IS NULL OR "for_forestal" = \'\')'
        )
        if copia.selectedFeatureCount() > 0:
            resultat_elim = processing.run("qgis:eliminateselectedpolygons", {
                'INPUT': copia,
                'MODE': 2,  # Largest Common Boundary
                'OUTPUT': 'memory:',
            })
            capa_per_dissoldre = resultat_elim['OUTPUT']
        else:
            capa_per_dissoldre = copia

        processing.run("native:dissolve", {
            'INPUT': capa_per_dissoldre,
            'FIELD': [codi_field],
            'OUTPUT': f'ogr:dbname=\'{gpkg_path}\' table="{NOM_TAULA}" (geom)',
        })

        capa_limits = QgsVectorLayer(
            f"{gpkg_path}|layername={NOM_TAULA}", etiqueta, "ogr")
        if not capa_limits.isValid():
            raise RuntimeError(
                f"La capa generada a {gpkg_path}|layername={NOM_TAULA} "
                "no és vàlida"
            )
        capa_limits.setRenderer(QgsSingleSymbolRenderer(sym_limit_rodal_factory()))
        QgsProject.instance().addMapLayer(capa_limits, False)

        # Agrupar la capa principal i la seva auxiliar de límits juntes,
        # perquè no quedin com a germanes soltes al panell de capes.
        # Idempotent: cerca un grup amb aquest nom A TOT L'ARBRE (no
        # només al pare immediat de la capa) — mirar només el pare
        # immediat feia que, si la capa ja estava dins d'un altre grup
        # (p.ex. "PTGMF — Capes de treball"), cada execució tornés a
        # crear un grup "IOF_Unitats_Actuacio" nou en lloc de reutilitzar
        # el ja existent, duplicant la capa a cada cop que s'apliqués
        # l'estil (bug real trobat en proves, juliol 2026).
        root = QgsProject.instance().layerTreeRoot()
        node_layer = root.findLayer(layer.id())
        nom_grup = layer.name()

        grup_existent = root.findGroup(nom_grup)
        if grup_existent is not None:
            grup_unitats = grup_existent
            ja_dins = any(
                isinstance(fill, QgsLayerTreeLayer) and fill.layerId() == layer.id()
                for fill in grup_existent.children()
            )
            if not ja_dins and node_layer is not None:
                parent_actual = node_layer.parent()
                clon = node_layer.clone()
                grup_unitats.insertChildNode(0, clon)
                if parent_actual is not None:
                    parent_actual.removeChildNode(node_layer)
        elif node_layer is not None:
            parent_actual = node_layer.parent() or root
            # Cercar per layerId() (una cadena de text), no per identitat
            # d'objecte Python — list.index(node_layer) pot fallar amb
            # "... is not in list" encara que el node hi sigui de debò
            # (PyQGIS pot donar embolcalls Python diferents per al mateix
            # node real de l'arbre segons per on s'hi accedeixi).
            idx = 0
            for i, fill in enumerate(parent_actual.children()):
                if isinstance(fill, QgsLayerTreeLayer) and fill.layerId() == layer.id():
                    idx = i
                    break
            grup_unitats = parent_actual.insertGroup(idx, nom_grup)
            clon = node_layer.clone()
            grup_unitats.insertChildNode(0, clon)
            parent_actual.removeChildNode(node_layer)
        else:
            grup_unitats = root

        grup_unitats.insertLayer(0, capa_limits)
        capa_limits.triggerRepaint()
    except Exception as e:
        QgsMessageLog.logMessage(
            f"IOF Assistent: no s'ha pogut generar la capa de límits de "
            f"rodal ({etiqueta}): {e}",
            "IOFAssistent", level=Qgis.MessageLevel.Warning
        )


def apply_finques_style(layer):
    """
    Aplica el format MiraMon a la capa IOF_Finques:
    - Sense farciment (transparent)
    - Contorn lila RGB(128,0,128) = #800080, gruix 1.0 mm
    - Símbol únic (totes les finques tenen el mateix contorn)
    Font: limits.dbf MiraMon, CLAUSIMBOL /C128,0,128
    """
    outline = '128,0,128'
    sym = QgsFillSymbol.createSimple({
        'color': '0,0,0,0',
        'outline_color': outline,
        'outline_width': '1.0',
        'outline_style': 'solid',
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.setOpacity(1.0)
    layer.setLabelsEnabled(False)
    layer.setOpacity(1.0)
    layer.triggerRepaint()


def apply_infra_style(layer):
    """
    Aplica el format MiraMon a la capa IOF_Infraestructures_PI.
    Contorn: halo blanc 1.0 mm + linia marro discontinua 0.5 mm per sobre
      (igual que limits d'actuacio/rodals: dos capes de linia via exterior_ring)
    Trama:
      - Existent  (E): gris  RGB(150,150,150)
      - Projectada (P): taronja RGB(245,168,37)
    Etiqueta: codi_infra, Calibri 9pt marro, halo blanc.
    """
    from qgis.core import (
        QgsCategorizedSymbolRenderer, QgsRendererCategory,
        QgsFillSymbol, QgsSimpleFillSymbolLayer,
        QgsLinePatternFillSymbolLayer,
        QgsGeometryGeneratorSymbolLayer,
        QgsSimpleLineSymbolLayer, QgsLineSymbol,
    )
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import Qt

    fields_names = layer.fields().names()
    camp_estat = "estat" if "estat" in fields_names else None

    COLOR_OUTLINE = QColor(155, 92, 47)   # marro V_infraes

    ESTILS = {
        "E": {"trama": QColor(150, 150, 150), "nom": "Linia de defensa existent"},
        "P": {"trama": QColor(245, 168, 37), "nom": "Linia de defensa projectada"},
    }

    def _sym_infra_contorn():
        """Halo blanc 1.0mm (pass 2) + linia marro discontinua 0.5mm (pass 2) per sobre."""
        # Halo blanc
        gen_ext = QgsGeometryGeneratorSymbolLayer.create({
            'geometryModifier': 'exterior_ring($geometry)', 'SymbolType': 'Line'})
        lyr_ext = QgsSimpleLineSymbolLayer()
        lyr_ext.setColor(QColor(255, 255, 255))
        lyr_ext.setWidth(0.8)
        lyr_ext.setPenStyle(Qt.PenStyle.SolidLine)
        ls_ext = QgsLineSymbol()
        ls_ext.deleteSymbolLayer(0)
        ls_ext.appendSymbolLayer(lyr_ext)
        gen_ext.setSubSymbol(ls_ext)
        gen_ext.setRenderingPass(2)

        # Linia marro discontinua per sobre
        gen_int = QgsGeometryGeneratorSymbolLayer.create({
            'geometryModifier': 'exterior_ring($geometry)', 'SymbolType': 'Line'})
        lyr_int = QgsSimpleLineSymbolLayer()
        lyr_int.setColor(COLOR_OUTLINE)
        lyr_int.setWidth(0.5)
        lyr_int.setPenStyle(Qt.PenStyle.DashLine)
        ls_int = QgsLineSymbol()
        ls_int.deleteSymbolLayer(0)
        ls_int.appendSymbolLayer(lyr_int)
        gen_int.setSubSymbol(ls_int)
        gen_int.setRenderingPass(2)
        return gen_ext, gen_int

    estats = set()
    for feat in layer.getFeatures():
        e = str(feat[camp_estat]).strip() if camp_estat and feat[camp_estat] \
            and feat[camp_estat] == feat[camp_estat] else "E"
        if e in ESTILS:
            estats.add(e)
    if not estats:
        estats = {"E"}

    categories = []
    for e in sorted(estats):
        info = ESTILS[e]

        # Base transparent (pass 0)
        fill_base = QgsSimpleFillSymbolLayer()
        fill_base.setFillColor(QColor(0, 0, 0, 0))
        fill_base.setStrokeStyle(Qt.PenStyle.NoPen)
        fill_base.setRenderingPass(0)

        # Trama diagonal (pass 0)
        hatch = QgsLinePatternFillSymbolLayer()
        hatch.setColor(info["trama"])
        hatch.setLineWidth(0.4)
        hatch.setDistance(2.0)
        hatch.setLineAngle(45)
        hatch.setRenderingPass(0)

        gen_ext, gen_int = _sym_infra_contorn()

        sym = QgsFillSymbol()
        sym.deleteSymbolLayer(0)
        sym.appendSymbolLayer(fill_base)
        sym.appendSymbolLayer(hatch)
        sym.appendSymbolLayer(gen_ext)
        sym.appendSymbolLayer(gen_int)

        cat = QgsRendererCategory(e, sym, info["nom"], True)
        categories.append(cat)

    expr = f'"{camp_estat}"' if camp_estat else "'E'"
    renderer = QgsCategorizedSymbolRenderer(expr, categories)
    renderer.setUsingSymbolLevels(True)
    layer.setRenderer(renderer)

    # Etiqueta: codi_infra - Calibri 9pt, marro, halo blanc
    camp_codi = "codi_infra" if "codi_infra" in fields_names else None
    if camp_codi:
        from qgis.core import (
            QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
            QgsVectorLayerSimpleLabeling,
        )
        from qgis.PyQt.QtGui import QFont
        pal = QgsPalLayerSettings()
        pal.fieldName = camp_codi
        pal.isExpression = False
        pal.enabled = True
        pal.placement = QgsPalLayerSettings.Placement.AroundPoint
        fmt = QgsTextFormat()
        font = QFont("Calibri", 9)
        font.setBold(True)
        fmt.setFont(font)
        fmt.setSize(9)
        fmt.setColor(COLOR_OUTLINE)
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(0.8)
        buf.setColor(QColor(255, 255, 255))
        fmt.setBuffer(buf)
        pal.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)

    layer.setOpacity(1.0)
    layer.triggerRepaint()


def apply_canvis_style(layer):
    """
    Aplica el format MiraMon a la capa IOF_Canvis_Us.
    Font: T_canvius.dbf (trama), V_canvius.dbf (contorn), F_canvius.dbf (etiqueta)

    RM (Rompuda):              trama blava RGB(130,215,255), contorn blau RGB(0,107,159)
    TP (Transf. a pastures):   trama verda RGB(115,225,60),  contorn verd RGB(45,115,15)
    Contorn: halo blanc 0.8mm + linia de color discontinua 0.5mm
    Etiqueta: codi_canvi, Calibri 9pt, halo blanc
    """
    from qgis.core import (
        QgsCategorizedSymbolRenderer, QgsRendererCategory,
        QgsFillSymbol, QgsSimpleFillSymbolLayer,
        QgsLinePatternFillSymbolLayer,
        QgsGeometryGeneratorSymbolLayer,
        QgsSimpleLineSymbolLayer, QgsLineSymbol,
    )
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import Qt

    fields_names = layer.fields().names()
    camp_tipus = "tipus_canvi" if "tipus_canvi" in fields_names else None

    ESTILS = {
        "RM": {"trama": QColor(130, 215, 255), "contorn": QColor(0, 107, 159),
               "nom": "Rompuda"},
        "TP": {"trama": QColor(115, 225, 60), "contorn": QColor(45, 115, 15),
               "nom": "Transformacio a pastures"},
    }

    def _sym_contorn(color):
        gen_ext = QgsGeometryGeneratorSymbolLayer.create({
            'geometryModifier': 'exterior_ring($geometry)', 'SymbolType': 'Line'})
        lyr_ext = QgsSimpleLineSymbolLayer()
        lyr_ext.setColor(QColor(255, 255, 255))
        lyr_ext.setWidth(0.8)
        lyr_ext.setPenStyle(Qt.PenStyle.SolidLine)
        ls_ext = QgsLineSymbol()
        ls_ext.deleteSymbolLayer(0)
        ls_ext.appendSymbolLayer(lyr_ext)
        gen_ext.setSubSymbol(ls_ext)
        gen_ext.setRenderingPass(2)

        gen_int = QgsGeometryGeneratorSymbolLayer.create({
            'geometryModifier': 'exterior_ring($geometry)', 'SymbolType': 'Line'})
        lyr_int = QgsSimpleLineSymbolLayer()
        lyr_int.setColor(color)
        lyr_int.setWidth(0.5)
        lyr_int.setPenStyle(Qt.PenStyle.DashLine)
        ls_int = QgsLineSymbol()
        ls_int.deleteSymbolLayer(0)
        ls_int.appendSymbolLayer(lyr_int)
        gen_int.setSubSymbol(ls_int)
        gen_int.setRenderingPass(2)
        return gen_ext, gen_int

    tipus_presents = set()
    for feat in layer.getFeatures():
        t = str(feat[camp_tipus]).strip() if camp_tipus and feat[camp_tipus] \
            and feat[camp_tipus] == feat[camp_tipus] else ""
        if t in ESTILS:
            tipus_presents.add(t)
    if not tipus_presents:
        tipus_presents = set(ESTILS.keys())

    categories = []
    for t in sorted(tipus_presents):
        info = ESTILS[t]

        fill_base = QgsSimpleFillSymbolLayer()
        fill_base.setFillColor(QColor(0, 0, 0, 0))
        fill_base.setStrokeStyle(Qt.PenStyle.NoPen)
        fill_base.setRenderingPass(0)

        hatch = QgsLinePatternFillSymbolLayer()
        hatch.setColor(info["trama"])
        hatch.setLineWidth(0.4)
        hatch.setDistance(2.0)
        hatch.setLineAngle(45)
        hatch.setRenderingPass(0)

        gen_ext, gen_int = _sym_contorn(info["contorn"])

        sym = QgsFillSymbol()
        sym.deleteSymbolLayer(0)
        sym.appendSymbolLayer(fill_base)
        sym.appendSymbolLayer(hatch)
        sym.appendSymbolLayer(gen_ext)
        sym.appendSymbolLayer(gen_int)

        cat = QgsRendererCategory(t, sym, info["nom"], True)
        categories.append(cat)

    expr = '"' + camp_tipus + '"' if camp_tipus else "'RM'"
    renderer = QgsCategorizedSymbolRenderer(expr, categories)
    renderer.setUsingSymbolLevels(True)
    layer.setRenderer(renderer)

    camp_codi = "codi_canvi" if "codi_canvi" in fields_names else None
    if camp_codi:
        from qgis.core import (
            QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
            QgsVectorLayerSimpleLabeling,
        )
        from qgis.PyQt.QtGui import QFont
        pal = QgsPalLayerSettings()
        pal.fieldName = camp_codi
        pal.isExpression = False
        pal.enabled = True
        pal.placement = QgsPalLayerSettings.Placement.AroundPoint
        fmt = QgsTextFormat()
        font = QFont("Calibri", 9)
        font.setBold(True)
        fmt.setFont(font)
        fmt.setSize(9)
        fmt.setColor(QColor(0, 107, 159))
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(0.8)
        buf.setColor(QColor(255, 255, 255))
        fmt.setBuffer(buf)
        pal.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)

    layer.setOpacity(1.0)
    layer.triggerRepaint()


# Estils de camins extrets de camins.dbf (MiraMon)
# (tipus, estat): (color_exterior, color_interior, gruix_ext, gruix_int, projectat)
ESTILS_CAMINS = {
    ('PR', 'E'): ('255,255,255', '64,0,128', 3.5, 2.7, False),
    ('PR', 'P'): ('228,228,228', '64,0,128', 3.5, 2.7, True),
    ('PM', 'E'): ('255,255,255', '255,0,0', 3.5, 2.7, False),
    ('PM', 'P'): ('228,228,228', '255,0,0', 3.5, 2.7, True),
    ('SC', 'E'): ('255,255,255', '255,128,64', 3.0, 2.2, False),
    ('SC', 'P'): ('228,228,228', '255,128,64', 3.0, 2.0, True),
    ('DB', 'E'): ('255,255,255', '0,128,0', 2.7, 2.0, False),
    ('DB', 'P'): ('229,229,229', '0,128,0', 2.7, 2.0, True),
}

ETIQUETES_CAMINS = {
    'PR': 'Cami Principal',
    'PM': 'Cami Primari',
    'SC': 'Cami Secundari',
    'DB': 'Cami de Desembosc',
}


def apply_camins_style(layer):
    """
    Aplica el format MiraMon a la capa IOF_Camins.
    Renderitzador categoritzat per tipus_vial + estat.
    Cada categoria té dues capes de línia (exterior blanca + interior de color).
    Els projectats usen línia discontínua.
    Etiqueta: codi_cami al centre del camí.
    """
    from qgis.core import (
        QgsCategorizedSymbolRenderer, QgsRendererCategory,
        QgsLineSymbol, QgsSimpleLineSymbolLayer,
        QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
        QgsVectorLayerSimpleLabeling
    )
    from qgis.PyQt.QtGui import QColor, QFont
    from qgis.PyQt.QtCore import Qt

    fields_names = layer.fields().names()
    camp_tipus = "tipus_vial" if "tipus_vial" in fields_names else None
    camp_estat = "estat" if "estat" in fields_names else None
    camp_codi = "codi_cami" if "codi_cami" in fields_names else None

    # Recollir combinacions presents
    combis = set()
    for feat in layer.getFeatures():
        t = str(feat[camp_tipus]).strip() if camp_tipus and feat[camp_tipus] and feat[camp_tipus] == feat[camp_tipus] else ""
        e = str(feat[camp_estat]).strip() if camp_estat and feat[camp_estat] and feat[camp_estat] == feat[camp_estat] else ""
        if t or e:
            combis.add((t, e))

    categories = []
    for t, e in sorted(combis):
        estil = ESTILS_CAMINS.get((t, e), ('255,255,255', '155,92,47', 2.5, 1.8, False))
        col_ext, col_int, w_ext, w_int, projectat = estil

        # Capa exterior (blanca/grisa, més gruixuda)
        line_ext = QgsSimpleLineSymbolLayer()
        line_ext.setColor(QColor(*[int(x) for x in col_ext.split(',')]))
        line_ext.setWidth(w_ext * 0.3)  # mm

        # Capa interior (de color, més fina)
        line_int = QgsSimpleLineSymbolLayer()
        line_int.setColor(QColor(*[int(x) for x in col_int.split(',')]))
        line_int.setWidth(w_int * 0.3)
        if projectat:
            line_int.setPenStyle(Qt.PenStyle.DashLine)

        sym = QgsLineSymbol()
        sym.deleteSymbolLayer(0)
        sym.appendSymbolLayer(line_ext)
        sym.appendSymbolLayer(line_int)

        nom = ETIQUETES_CAMINS.get(t, t or "Camí")
        if e == 'P':
            nom += " Projectat"
        clau = f"{t}|{e}"
        cat = QgsRendererCategory(clau, sym, nom, True)
        categories.append(cat)

    # Camp de categorització: expressió concatenada tipus_vial + '|' + estat
    if camp_tipus and camp_estat:
        expr = f'"{camp_tipus}" || \'|\' || "{camp_estat}"'
    elif camp_tipus:
        expr = f'"{camp_tipus}"'
    else:
        expr = "''"

    # Ordenar categories per jerarquia: PR→PM→SC→DB, dins de cada tipus E→P
    ORDRE_TIPUS = ['PR', 'PM', 'SC', 'DB']
    ORDRE_ESTAT = ['E', 'P']

    categories_ordenades = sorted(
        categories,
        key=lambda cat: (
            ORDRE_TIPUS.index(cat.value().split('|')[0])
            if cat.value().split('|')[0] in ORDRE_TIPUS else 99,
            ORDRE_ESTAT.index(cat.value().split('|')[1])
            if len(cat.value().split('|')) > 1 and cat.value().split('|')[1] in ORDRE_ESTAT else 99
        )
    )

    renderer = QgsCategorizedSymbolRenderer(expr, categories_ordenades)
    layer.setRenderer(renderer)

    # Etiquetes: codi_cami
    if camp_codi:
        settings = QgsPalLayerSettings()
        settings.fieldName = camp_codi
        settings.enabled = True
        settings.isExpression = False

        fmt = QgsTextFormat()
        fmt.setFont(QFont("Calibri", 10, -1, True))  # cursiva
        fmt.setSize(10)
        from qgis.PyQt.QtGui import QColor as QC
        fmt.setColor(QC(0, 0, 0))

        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(1)
        buf.setColor(QC(255, 255, 255))
        fmt.setBuffer(buf)

        settings.setFormat(fmt)
        settings.placement = QgsPalLayerSettings.Placement.Line

        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)

    layer.setOpacity(1.0)
    layer.triggerRepaint()


def apply_inventari_style(layer, svg_path):
    """
    Aplica el format MiraMon a IOF_Punts_Inventari:
    - Símbol: punt_N.svg (cercle negre), mida 4mm
    - Etiqueta: codi_pi, Arial 7pt, negreta, negre, bufet blanc
    """
    import os
    from qgis.core import (
        QgsSvgMarkerSymbolLayer, QgsMarkerSymbol,
        QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
        QgsVectorLayerSimpleLabeling, QgsSingleSymbolRenderer,
    )
    from qgis.PyQt.QtGui import QFont, QColor

    # Símbol SVG
    if svg_path and os.path.exists(svg_path):
        sl = QgsSvgMarkerSymbolLayer(svg_path)
        sl.setSize(2.0)
        sl.setSizeUnit(QgsSvgMarkerSymbolLayer.RenderUnit.RenderMillimeters
                       if hasattr(QgsSvgMarkerSymbolLayer, 'RenderUnit')
                       else sl.sizeUnit())
        sl.setFillColor(QColor(0, 0, 0))
        sl.setStrokeColor(QColor(0, 0, 0))
        sl.setStrokeWidth(0)
        sym = QgsMarkerSymbol()
        sym.deleteSymbolLayer(0)
        sym.appendSymbolLayer(sl)
    else:
        # Fallback: cercle negre simple
        sym = QgsMarkerSymbol.createSimple({
            'name': 'circle',
            'color': '0,0,0,255',
            'outline_style': 'no',
            'size': '3',
        })

    layer.setRenderer(QgsSingleSymbolRenderer(sym))

    # Etiqueta codi_pi
    if "codi_pi" in layer.fields().names():
        pal = QgsPalLayerSettings()
        pal.fieldName = '"codi_pi"'
        pal.isExpression = True
        pal.enabled = True
        # AroundPoint amb distància per col·locar text a la dreta sense solapar
        pal.placement = QgsPalLayerSettings.Placement.AroundPoint
        pal.dist = 1.0
        pal.distUnits = QgsUnitTypes.RenderUnit.RenderMillimeters

        fmt = QgsTextFormat()
        fmt.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        fmt.setSize(7)
        fmt.setColor(QColor(0, 0, 0))
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(0.6)
        buf.setColor(QColor(255, 255, 255))
        fmt.setBuffer(buf)
        pal.setFormat(fmt)

        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)
    else:
        layer.setLabelsEnabled(False)

    layer.setOpacity(1.0)
    layer.triggerRepaint()


def apply_elements_style(layer, svg_arquit, svg_natur):
    """
    Aplica estil a IOF_Elements_Singulars:
    - Arquit: símbol arquit.svg
    - Natural: símbol natur.svg
    - Sense tipus: cercle negre de fallback
    Etiqueta: nom_elem, Arial 7pt, a la dreta del punt.
    """
    import os
    from qgis.core import (
        QgsSvgMarkerSymbolLayer, QgsMarkerSymbol,
        QgsRuleBasedRenderer,
        QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
        QgsVectorLayerSimpleLabeling, QgsUnitTypes,
    )
    from qgis.PyQt.QtGui import QFont, QColor

    def _svg_sym(svg_path, size=4.0):
        if svg_path and os.path.exists(svg_path):
            sl = QgsSvgMarkerSymbolLayer(svg_path)
            sl.setSize(size)
            sl.setStrokeWidth(0)
            sym = QgsMarkerSymbol()
            sym.deleteSymbolLayer(0)
            sym.appendSymbolLayer(sl)
        else:
            sym = QgsMarkerSymbol.createSimple({
                'name': 'circle', 'color': '80,80,80,255',
                'outline_style': 'no', 'size': '3',
            })
        return sym

    root = QgsRuleBasedRenderer.Rule(None)

    regla_arquit = QgsRuleBasedRenderer.Rule(_svg_sym(svg_arquit))
    regla_arquit.setLabel("Element arquitectònic")
    regla_arquit.setFilterExpression("\"tipus_elem\" = 'Arquit'")
    root.appendChild(regla_arquit)

    regla_natur = QgsRuleBasedRenderer.Rule(_svg_sym(svg_natur))
    regla_natur.setLabel("Element natural")
    regla_natur.setFilterExpression("\"tipus_elem\" = 'Natural'")
    root.appendChild(regla_natur)

    layer.setRenderer(QgsRuleBasedRenderer(root))

    # Etiqueta nom_elem a la dreta
    if "nom_elem" in layer.fields().names():
        pal = QgsPalLayerSettings()
        pal.fieldName = '"nom_elem"'
        pal.isExpression = True
        pal.enabled = True
        pal.placement = QgsPalLayerSettings.Placement.AroundPoint
        pal.dist = 2.5
        pal.distUnits = QgsUnitTypes.RenderUnit.RenderMillimeters

        fmt = QgsTextFormat()
        font = QFont("Arial", 7)
        fmt.setFont(font)
        fmt.setSize(7)
        fmt.setSizeUnit(QgsUnitTypes.RenderUnit.RenderPoints)
        fmt.setColor(QColor(60, 60, 60))

        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(0.8)
        buf.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMillimeters)
        buf.setColor(QColor(255, 255, 255))
        fmt.setBuffer(buf)
        pal.setFormat(fmt)

        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)

    layer.triggerRepaint()


def apply_aigua_style(layer, svg_existent, svg_projectat):
    """
    Aplica estil a IOF_Punts_Aigua:
    - Existent (estat='E'): símbol aiguae.svg
    - Projectat (estat='P'): símbol aiguap.svg
    - Fallback: cercle blau
    Etiqueta: codi_pa, Arial 7pt, a la dreta.
    """
    import os
    from qgis.core import (
        QgsSvgMarkerSymbolLayer, QgsMarkerSymbol,
        QgsRuleBasedRenderer,
        QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
        QgsVectorLayerSimpleLabeling,
    )
    from qgis.PyQt.QtGui import QFont, QColor

    def _svg_sym(svg_path, size=4.0):
        if svg_path and os.path.exists(svg_path):
            sl = QgsSvgMarkerSymbolLayer(svg_path)
            sl.setSize(size)
            sl.setFillColor(QColor(0, 100, 200))
            sl.setStrokeColor(QColor(0, 60, 140))
            sl.setStrokeWidth(0)
            sym = QgsMarkerSymbol()
            sym.deleteSymbolLayer(0)
            sym.appendSymbolLayer(sl)
        else:
            sym = QgsMarkerSymbol.createSimple({
                'name': 'circle', 'color': '0,100,200,255',
                'outline_style': 'no', 'size': '3',
            })
        return sym

    root = QgsRuleBasedRenderer.Rule(None)

    regla_e = QgsRuleBasedRenderer.Rule(_svg_sym(svg_existent))
    regla_e.setLabel("Punt d'aigua existent")
    regla_e.setFilterExpression("\"estat\" = 'E'")
    root.appendChild(regla_e)

    regla_p = QgsRuleBasedRenderer.Rule(_svg_sym(svg_projectat))
    regla_p.setLabel("Punt d'aigua projectat")
    regla_p.setFilterExpression("\"estat\" = 'P'")
    root.appendChild(regla_p)

    layer.setRenderer(QgsRuleBasedRenderer(root))

    # Etiqueta codi_pa a la dreta
    if "codi_pa" in layer.fields().names():
        pal = QgsPalLayerSettings()
        pal.fieldName = '"codi_pa"'
        pal.isExpression = True
        pal.enabled = True
        pal.placement = QgsPalLayerSettings.Placement.AroundPoint
        pal.dist = 2.5
        pal.distUnits = QgsUnitTypes.RenderUnit.RenderMillimeters

        fmt = QgsTextFormat()
        fmt.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        fmt.setSize(7)
        fmt.setColor(QColor(0, 60, 140))
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(0.6)
        buf.setColor(QColor(255, 255, 255))
        fmt.setBuffer(buf)
        pal.setFormat(fmt)

        layer.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        layer.setLabelsEnabled(True)
    else:
        layer.setLabelsEnabled(False)

    layer.setOpacity(1.0)
    layer.triggerRepaint()


class FormatLayersDialog(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("IOF Assistent — Format de capes")
        self.setMinimumWidth(400)
        self.setWindowFlags(
            (self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint) | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel("<b>Aplicar format a les capes de l'IOF</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "padding:8px; background:#e8f4e8; border-radius:4px;"
        )
        layout.addWidget(title)

        def sep():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.HLine)
            s.setStyleSheet("color:#ddd;")
            return s

        # IOF_Finques — #e8f5e9 verd clar
        btn_finques = QPushButton("Aplicar estil a IOF_Finques")
        btn_finques.setStyleSheet(
            "background:#e8f5e9; color:#1b5e20; font-weight:bold; padding:6px 16px;"
            "border:1px solid #a5d6a7; border-radius:3px;"
        )
        btn_finques.clicked.connect(self._apply_finques)
        layout.addWidget(btn_finques)

        layout.addWidget(sep())

        # IOF_Rodals/Unitats — #e3f2fd blau clar
        btn_unitats = QPushButton("Aplicar estil a IOF_Rodals / IOF_Unitats_Actuacio")
        btn_unitats.setStyleSheet(
            "background:#e3f2fd; color:#0d47a1; font-weight:bold; padding:6px 16px;"
            "border:1px solid #90caf9; border-radius:3px;"
        )
        btn_unitats.clicked.connect(self._apply_unitats)
        layout.addWidget(btn_unitats)

        layout.addWidget(sep())

        # IOF_Camins — #fff8e1 groc clar
        btn_camins = QPushButton("Aplicar estil a IOF_Camins")
        btn_camins.setStyleSheet(
            "background:#fff8e1; color:#e65100; font-weight:bold; padding:6px 16px;"
            "border:1px solid #ffe082; border-radius:3px;"
        )
        btn_camins.clicked.connect(self._apply_camins)
        layout.addWidget(btn_camins)

        layout.addWidget(sep())

        # IOF_Infraestructures_PI — #fff3e0 taronja molt clar
        btn_infra = QPushButton("Aplicar estil a IOF_Infraestructures_PI")
        btn_infra.setStyleSheet(
            "background:#fff3e0; color:#bf360c; font-weight:bold; padding:6px 16px;"
            "border:1px solid #ffcc80; border-radius:3px;"
        )
        btn_infra.clicked.connect(self._apply_infra)
        layout.addWidget(btn_infra)

        layout.addWidget(sep())

        # IOF_Canvis_Us — #e8f5e9 verd molt clar
        btn_canvis = QPushButton("Aplicar estil a IOF_Canvis_Us")
        btn_canvis.setStyleSheet(
            "background:#e8f5e9; color:#1b5e20; font-weight:bold; padding:6px 16px;"
            "border:1px solid #a5d6a7; border-radius:3px;"
        )
        btn_canvis.clicked.connect(self._apply_canvis)
        layout.addWidget(btn_canvis)

        layout.addWidget(sep())

        # IOF_Punts_Aigua — #e1f5fe blau molt clar
        btn_aigua = QPushButton("Aplicar estil a IOF_Punts_Aigua")
        btn_aigua.setStyleSheet(
            "background:#e1f5fe; color:#01579b; font-weight:bold; padding:6px 16px;"
            "border:1px solid #81d4fa; border-radius:3px;"
        )
        btn_aigua.clicked.connect(self._apply_aigua)
        layout.addWidget(btn_aigua)

        layout.addWidget(sep())

        # IOF_Elements_Singulars — #f3e5f5 lila clar
        btn_elements = QPushButton("Aplicar estil a IOF_Elements_Singulars")
        btn_elements.setStyleSheet(
            "background:#f3e5f5; color:#4a148c; font-weight:bold; padding:6px 16px;"
            "border:1px solid #ce93d8; border-radius:3px;"
        )
        btn_elements.clicked.connect(self._apply_elements)
        layout.addWidget(btn_elements)

        layout.addWidget(sep())

        # IOF_Punts_Inventari — #efebe9 marró clar
        btn_inventari = QPushButton("Aplicar estil a IOF_Punts_Inventari")
        btn_inventari.setStyleSheet(
            "background:#efebe9; color:#3e2723; font-weight:bold; padding:6px 16px;"
            "border:1px solid #bcaaa4; border-radius:3px;"
        )
        btn_inventari.clicked.connect(self._apply_inventari)
        layout.addWidget(btn_inventari)

        layout.addWidget(sep())

        btn_reset_all = QPushButton("↳  Reiniciar tots els estils")
        btn_reset_all.setStyleSheet(
            "background:#fff3e0; color:#bf360c; font-weight:bold; padding:6px 16px;"
            "border:1px solid #ffcc80; border-radius:3px;"
        )
        btn_reset_all.clicked.connect(self._reset_all)
        layout.addWidget(btn_reset_all)

        layout.addWidget(sep())

        btn_close = QPushButton("Tancar")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    def _apply_layer(self, layer_name, style_func, msg):
        """Aplica un estil a la capa indicada."""
        layer = None
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == layer_name and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                layer = lyr
                break
        if layer is None:
            avisa_capa_no_trobada(self, layer_name, accio="aplicar l'estil")
            return
        if layer.featureCount() == 0:
            QMessageBox.information(
                self, "Capa buida",
                f"La capa «{layer_name}» no conté cap element.\n\n"
                "Digitalitza-la primer i torna a aplicar l'estil."
            )
            return
        try:
            style_func(layer)
            QMessageBox.information(self, "Estil aplicat", msg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error:\n{e}")

    def _apply_finques(self):
        self._apply_layer(
            LAYER_NAME,
            apply_finques_style,
            "S'ha aplicat el format correctament."
        )

    def _apply_camins(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Camins" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.LineGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Camins» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a aplicar l'estil."
                    )
                    return
                try:
                    # Comprovar si tots els camins tenen codi
                    fields_names = lyr.fields().names()
                    f_codi = "codi_cami" if "codi_cami" in fields_names else None
                    sense_codi = 0
                    if f_codi:
                        for feat in lyr.getFeatures():
                            v = feat[f_codi]
                            if not v or str(v).strip() == '' or str(v) == 'NULL':
                                sense_codi += 1
                    if sense_codi > 0:
                        QMessageBox.warning(
                            self, "Camins sense classificar",
                            f"Hi ha {sense_codi} camí{'ns' if sense_codi != 1 else ''} "
                            f"sense codi assignat.\n\n"
                            "Ves a «Omplir camps» per classificar-los "
                            "abans d'aplicar l'estil."
                        )
                        return
                    apply_camins_style(lyr)
                    QMessageBox.information(
                        self, "Estil aplicat",
                        "S'ha aplicat el format correctament."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Camins", accio="aplicar l'estil")

    def _apply_infra(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Infraestructures_PI" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Infraestructures_PI» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a aplicar l'estil."
                    )
                    return
                try:
                    apply_infra_style(lyr)
                    QMessageBox.information(
                        self, "Estil aplicat",
                        "S'ha aplicat el format correctament."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Infraestructures_PI", accio="aplicar l'estil")

    def _apply_canvis(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Canvis_Us" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Canvis_Us» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a aplicar l'estil."
                    )
                    return
                try:
                    apply_canvis_style(lyr)
                    QMessageBox.information(
                        self, "Estil aplicat",
                        "S'ha aplicat el format correctament."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Canvis_Us", accio="aplicar l'estil")

    def _apply_aigua(self):
        import os
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Punts_Aigua" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PointGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Punts_Aigua» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a aplicar l'estil."
                    )
                    return
                try:
                    plugin_dir = os.path.dirname(__file__)
                    svg_e = os.path.join(plugin_dir, "symbols", "aiguae.svg")
                    svg_p = os.path.join(plugin_dir, "symbols", "aiguap.svg")
                    apply_aigua_style(lyr, svg_e, svg_p)
                    QMessageBox.information(
                        self, "Estil aplicat",
                        "S'ha aplicat el format correctament."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Punts_Aigua", accio="aplicar l'estil")

    def _apply_inventari(self):
        import os
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Punts_Inventari" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PointGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Punts_Inventari» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a aplicar l'estil."
                    )
                    return
                try:
                    plugin_dir = os.path.dirname(__file__)
                    svg_path = os.path.join(plugin_dir, "symbols", "punt_N.svg")
                    apply_inventari_style(lyr, svg_path)
                    QMessageBox.information(
                        self, "Estil aplicat",
                        "S'ha aplicat el format correctament."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Punts_Inventari", accio="aplicar l'estil")

    def _apply_elements(self):
        import os
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Elements_Singulars" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PointGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Elements_Singulars» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a aplicar l'estil."
                    )
                    return
                try:
                    plugin_dir = os.path.dirname(__file__)
                    svg_arquit = os.path.join(plugin_dir, "symbols", "arquit.svg")
                    svg_natur = os.path.join(plugin_dir, "symbols", "natur.svg")
                    apply_elements_style(lyr, svg_arquit, svg_natur)
                    self._reorder_elements_above_inventari()
                    QMessageBox.information(
                        self, "Estil aplicat",
                        "S'ha aplicat el format correctament."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Elements_Singulars", accio="aplicar l'estil")

    def _reset_elements(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Elements_Singulars" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PointGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Elements_Singulars» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a reiniciar l'estil."
                    )
                    return
                try:
                    from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer
                    sym = QgsMarkerSymbol.createSimple({
                        'name': 'circle', 'color': '0,0,0,255',
                        'outline_style': 'no', 'size': '3',
                    })
                    lyr.setRenderer(QgsSingleSymbolRenderer(sym))
                    lyr.setLabelsEnabled(False)
                    lyr.setOpacity(1.0)
                    lyr.triggerRepaint()
                    QMessageBox.information(
                        self, "Estil reiniciat",
                        "S'ha reiniciat l'estil de «IOF_Elements_Singulars»."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Elements_Singulars", accio="aplicar l'estil")

    def _reset_inventari(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Punts_Inventari" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PointGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Punts_Inventari» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a reiniciar l'estil."
                    )
                    return
                try:
                    from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer
                    sym = QgsMarkerSymbol.createSimple({
                        'name': 'circle', 'color': '0,0,0,255',
                        'outline_style': 'no', 'size': '3',
                    })
                    lyr.setRenderer(QgsSingleSymbolRenderer(sym))
                    lyr.setLabelsEnabled(False)
                    lyr.setOpacity(1.0)
                    lyr.triggerRepaint()
                    QMessageBox.information(
                        self, "Estil reiniciat",
                        "S'ha reiniciat l'estil de «IOF_Punts_Inventari»."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Punts_Inventari", accio="aplicar l'estil")
        import os
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Elements_Singulars" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PointGeometry):
                try:
                    plugin_dir = os.path.dirname(__file__)
                    svg_arquit = os.path.join(plugin_dir, "symbols", "arquit.svg")
                    svg_natur = os.path.join(plugin_dir, "symbols", "natur.svg")
                    apply_elements_style(lyr, svg_arquit, svg_natur)
                    self._reorder_elements_above_inventari()
                    QMessageBox.information(
                        self, "Estil aplicat",
                        "S'ha aplicat el format correctament."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Elements_Singulars", accio="aplicar l'estil")

    def _reorder_elements_above_inventari(self):
        """Mou IOF_Elements_Singulars per sobre de IOF_Punts_Inventari al panell de capes."""
        from qgis.core import QgsLayerTreeLayer
        root = QgsProject.instance().layerTreeRoot()

        def find_node(parent, name):
            for child in parent.children():
                if isinstance(child, QgsLayerTreeLayer):
                    if child.layer() and child.layer().name() == name:
                        return child, parent
                elif hasattr(child, 'children'):
                    result = find_node(child, name)
                    if result:
                        return result
            return None

        res_e = find_node(root, "IOF_Elements_Singulars")
        res_i = find_node(root, "IOF_Punts_Inventari")
        if not res_e or not res_i:
            return

        node_e, parent_e = res_e
        node_i, parent_i = res_i

        # Només reordena si estan al mateix grup pare
        if parent_e is not parent_i:
            return

        children = parent_e.children()
        idx_e = children.index(node_e)
        idx_i = children.index(node_i)

        # Elements ha d'estar per sobre (índex menor) que Inventari
        if idx_e > idx_i:
            clone = node_e.clone()
            parent_e.insertChildNode(idx_i, clone)
            parent_e.removeChildNode(node_e)

    def _reset_unitats(self):
        for name in ["IOF_Unitats_Actuacio", "IOF_Rodals"]:
            for lyr in QgsProject.instance().mapLayers().values():
                if (isinstance(lyr, QgsVectorLayer) and lyr.name() == name and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                    if lyr.featureCount() == 0:
                        QMessageBox.information(
                            self, "Capa buida",
                            f"La capa «{name}» no conté cap element.\n\n"
                            "Digitalitza-la primer i torna a reiniciar l'estil."
                        )
                        return
                    try:
                        reset_unitats_style(lyr)
                        QMessageBox.information(
                            self, "Estil reiniciat",
                            f"S'ha reiniciat l'estil de «{name}»."
                        )
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Error:\n{e}")
                    return
        avisa_capa_no_trobada(
            self, "IOF_Rodals / IOF_Unitats_Actuacio", accio="aplicar l'estil"
        )

    def _reset_finques(self):
        for lyr in QgsProject.instance().mapLayers().values():
            if (isinstance(lyr, QgsVectorLayer) and lyr.name() == "IOF_Finques" and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                if lyr.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        "La capa «IOF_Finques» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a reiniciar l'estil."
                    )
                    return
                try:
                    reset_finques_style(lyr)
                    QMessageBox.information(
                        self, "Estil reiniciat",
                        "S'ha reiniciat l'estil de «IOF_Finques»."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Finques", accio="aplicar l'estil")

    def _reset_all(self):
        reply = QMessageBox.question(
            self, "Reiniciar tots els estils",
            "Es reiniciaran els estils de TOTES les capes IOF.\n"
            "Aquesta acció no es pot desfer.\n\nContinuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        reset_map = {
            ("IOF_Finques", QgsWkbTypes.GeometryType.PolygonGeometry): reset_finques_style,
            ("IOF_Unitats_Actuacio", QgsWkbTypes.GeometryType.PolygonGeometry): reset_unitats_style,
            ("IOF_Rodals", QgsWkbTypes.GeometryType.PolygonGeometry): reset_unitats_style,
            ("IOF_Camins", QgsWkbTypes.GeometryType.LineGeometry): reset_camins_style,
            ("IOF_Infraestructures_PI", QgsWkbTypes.GeometryType.PolygonGeometry): reset_unitats_style,
            ("IOF_Canvis_Us", QgsWkbTypes.GeometryType.PolygonGeometry): reset_unitats_style,
            ("IOF_Punts_Aigua", QgsWkbTypes.GeometryType.PointGeometry): reset_aigua_style,
            ("IOF_Elements_Singulars", QgsWkbTypes.GeometryType.PointGeometry): reset_elements_style,
            ("IOF_Punts_Inventari", QgsWkbTypes.GeometryType.PointGeometry): reset_inventari_style,
        }
        reiniciades = []
        buides = []
        # Còpia estàtica de la llista de capes (no la vista en viu del
        # projecte): algun reset (p.ex. reset_unitats_style) elimina ell
        # mateix la capa auxiliar de límits de rodal com a efecte
        # secundari, i si es continués iterant sobre la col·lecció en
        # viu del projecte, en arribar a aquella capa (ja eliminada) es
        # produiria un RuntimeError ("wrapped C/C++ object... has been
        # deleted"). La còpia sola no n'hi ha prou (l'objecte Python de
        # la capa eliminada continua a la còpia, però el seu C++ de
        # sota ja no existeix), per això cada iteració va també en un
        # try/except que salta la capa si ja ha quedat invalidada.
        for lyr in list(QgsProject.instance().mapLayers().values()):
            try:
                if not isinstance(lyr, QgsVectorLayer):
                    continue
                key = (lyr.name(), QgsWkbTypes.geometryType(lyr.wkbType()))
            except RuntimeError:
                continue  # la capa ja ha estat eliminada per un reset anterior
            if key in reset_map:
                if lyr.featureCount() == 0:
                    buides.append(lyr.name())
                    continue
                try:
                    reset_map[key](lyr)
                    reiniciades.append(lyr.name())
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error reiniciant «{lyr.name()}»:\n{e}")
        if reiniciades:
            text = "S'han reiniciat els estils de:\n" + "\n".join(f"  • {n}" for n in reiniciades)
            if buides:
                text += "\n\nNo s'han tocat (sense elements digitalitzats):\n" + \
                    "\n".join(f"  • {n}" for n in buides)
            QMessageBox.information(self, "Estils reiniciats", text)
        elif buides:
            QMessageBox.information(
                self, "Capes buides",
                "Cap de les capes IOF trobades té elements digitalitzats:\n" +
                "\n".join(f"  • {n}" for n in buides)
            )
        else:
            QMessageBox.warning(self, "Cap capa trobada", "No s'ha trobat cap capa IOF al projecte.")

    def _apply_unitats(self):
        # Detectar quina capa d'unitats existeix
        for name in ["IOF_Unitats_Actuacio", "IOF_Rodals"]:
            layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if (isinstance(lyr, QgsVectorLayer) and lyr.name() == name and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.GeometryType.PolygonGeometry):
                    layer = lyr
                    break
            if layer:
                if layer.featureCount() == 0:
                    QMessageBox.information(
                        self, "Capa buida",
                        f"La capa «{name}» no conté cap element.\n\n"
                        "Digitalitza-la primer i torna a aplicar l'estil."
                    )
                    return

                # Avisar (sense bloquejar del tot) si hi ha finques amb
                # tipologies forestals encara incompletes: una finca
                # sense cap unitat que la cobreixi es renderitza igual
                # que una àrea exclosa de l'IOF, i pot confondre's amb
                # una exclusió real si no s'avisa.
                finca_lyr = _get_layer("IOF_Finques")
                if finca_lyr is not None:
                    from .iof_utils import find_interior_polygons, finca_te_unitats_completes
                    all_finques = list(finca_lyr.getFeatures())
                    exclusion_ids = find_interior_polygons(all_finques)
                    finques_valides = [f for f in all_finques if f.id() not in exclusion_ids]
                    incompletes = [
                        f for f in finques_valides
                        if not finca_te_unitats_completes(layer, f)
                    ]
                    if incompletes:
                        fields_lower = {n.lower(): n for n in finca_lyr.fields().names()}
                        codi_field = fields_lower.get("codi_finca")
                        if codi_field:
                            noms = ", ".join(str(f[codi_field]) for f in incompletes)
                        else:
                            noms = ", ".join(str(f.id()) for f in incompletes)
                        resposta = QMessageBox.question(
                            self, "Unitats incompletes",
                            f"Hi ha finques sense tipologies forestals "
                            f"completes: {noms}.\n\n"
                            "Aquestes àrees es renderitzaran igual que "
                            "les zones excloses de l'IOF.\n\n"
                            "Vols continuar aplicant l'estil de totes "
                            "maneres?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No,
                        )
                        if resposta != QMessageBox.StandardButton.Yes:
                            return

                try:
                    apply_unitats_style(layer)
                    QMessageBox.information(
                        self, "Estil aplicat",
                        "S'ha aplicat el format correctament."
                    )
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error:\n{e}")
                return
        avisa_capa_no_trobada(self, "IOF_Rodals / IOF_Unitats_Actuacio", accio="aplicar l'estil")

# -*- coding: utf-8 -*-
"""
Aplica els estils de cadastre IOF a les capes del projecte QGIS.
- Ambit IOF: contorn discontinu gris, sense farciment
- Finques: farciment sense contorn, colors de la paleta finques_colors.json
- Municipi cadastral: estil de styles/cadastre_estils.json.gz (IOF-Cadastre-Municipi.qml)
- Poligons cadastrals: estil de styles/cadastre_estils.json.gz (IOF-Cadastre-Poligons.qml)
- Parcelles cadastrals: estil de styles/cadastre_estils.json.gz (IOF-Cadastre-Parcelles.qml)
"""

import os
import json
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import (
    QgsProject, QgsFillSymbol, QgsSingleSymbolRenderer
)
from .iof_utils import aplica_qml as _aplica_qml


# ── Colors de les finques de la paleta finques_colors.json ────────────────────
# Carregats una vegada i reutilitzats
_COLORS_FINCA = None


def _llegir_colors_finca():
    global _COLORS_FINCA
    if _COLORS_FINCA is not None:
        return _COLORS_FINCA
    _COLORS_FINCA = {}
    json_path = os.path.join(os.path.dirname(__file__), "styles", "finques_colors.json")
    if not os.path.exists(json_path):
        return _COLORS_FINCA
    try:
        with open(json_path, encoding="utf-8") as f:
            raw = json.load(f)
        for k, rgb in raw.items():
            _COLORS_FINCA[int(k)] = tuple(rgb)
    except Exception:  # nosec — error no crític, es descarta intencionadament
        pass
    return _COLORS_FINCA


def _plugin_dir():
    return os.path.dirname(__file__)


def _find_layers(*keywords):
    result = []
    for layer in QgsProject.instance().mapLayers().values():
        name = layer.name().lower()
        if any(kw.lower() in name for kw in keywords):
            result.append(layer)
    return result


def _num_finca(layer_name):
    """Extreu el numero de finca del nom de la capa.
    'Finca 3' -> 3
    'Finca 3 - Can Casals' -> 3
    """
    try:
        # El numero sempre es el segon element: "Finca N ..."
        parts = layer_name.strip().split()
        return int(parts[1])
    except (ValueError, IndexError):
        return 1


def _estil_ambit_iof(layer):
    """Ambit IOF: contorn discontinu gris, sense farciment."""
    sym = QgsFillSymbol.createSimple({
        "color": "0,0,0,0",
        "outline_color": "130,130,130",
        "outline_width": "1.0",
        "outline_style": "dash",
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.triggerRepaint()


def _estil_finca(layer):
    """Finca: farciment sense contorn. Color de la paleta pel numero de finca."""
    colors = _llegir_colors_finca()
    num = _num_finca(layer.name())
    # Finca 1 sempre groc palid (255,255,190), resta de la paleta
    if num in colors:
        r, g, b = colors[num]
    else:
        # Cicla pels colors disponibles
        idx = ((num - 1) % len(colors)) + 1 if colors else 1
        r, g, b = colors.get(idx, (220, 220, 180))

    sym = QgsFillSymbol.createSimple({
        "color": "{},{},{},180".format(r, g, b),
        "outline_style": "no",
        "outline_width": "0",
    })
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.triggerRepaint()


def aplicar_estil_cadastre(iface, parent=None):
    """Aplica els estils de cadastre IOF a les capes del projecte."""
    aplicats = []
    no_trobats = []

    # Ambit IOF: contorn discontinu gris, sense farciment
    capes_ambit = _find_layers("\u00e0mbit iof", "ambit iof", "ambitiof")
    if capes_ambit:
        for lyr in capes_ambit:
            _estil_ambit_iof(lyr)
        aplicats.append("\u00c0mbit IOF (" + str(len(capes_ambit)) + ")")
    else:
        no_trobats.append("\u00c0mbit IOF")

    # Finques: farciment sense contorn, color de la paleta
    capes_finques = _find_layers("finca ")
    if capes_finques:
        for lyr in capes_finques:
            _estil_finca(lyr)
        aplicats.append("Finques (" + str(len(capes_finques)) + ")")
    else:
        no_trobats.append("Finques")

    # Municipi cadastral: QML
    capes_municipi = _find_layers(
        "municipi cadastral", "municipicadastral"
    )
    if capes_municipi:
        ok_count = sum(1 for lyr in capes_municipi
                       if _aplica_qml(lyr, "IOF-Cadastre-Municipi.qml"))
        if ok_count:
            aplicats.append("Municipi cadastral (" + str(ok_count) + ")")
        else:
            no_trobats.append("Municipi cadastral (error QML)")
    else:
        no_trobats.append("Municipi cadastral")

    # Poligons cadastrals: QML
    capes_pol = _find_layers("pol\u00edgons cadastrals", "poligons cadastrals",
                             "cadastralzoning")
    if capes_pol:
        ok_count = sum(1 for lyr in capes_pol
                       if _aplica_qml(lyr, "IOF-Cadastre-Poligons.qml"))
        if ok_count:
            aplicats.append("Pol\u00edgons cadastrals (" + str(ok_count) + ")")
        else:
            no_trobats.append("Pol\u00edgons cadastrals (error QML)")
    else:
        no_trobats.append("Pol\u00edgons cadastrals")

    # Parcelles cadastrals: QML
    capes_parc = _find_layers("parcel\u00b7les cadastrals", "cadastralparcel")
    if capes_parc:
        ok_count = sum(1 for lyr in capes_parc
                       if _aplica_qml(lyr, "IOF-Cadastre-Parcelles.qml"))
        if ok_count:
            aplicats.append("Parcel\u00b7les cadastrals (" + str(ok_count) + ")")
        else:
            no_trobats.append("Parcel\u00b7les cadastrals (error QML)")
    else:
        no_trobats.append("Parcel\u00b7les cadastrals")

    iface.mapCanvas().refresh()

    if not aplicats:
        QMessageBox.warning(
            parent or iface.mainWindow(),
            "Cap capa trobada",
            "No s'ha trobat cap capa de cadastre al projecte.\n"
            "Primer importa el cadastre i genera les finques i l'\u00e0mbit."
        )
        return

    resum = "Estils aplicats correctament:\n\n"
    for a in aplicats:
        resum += "  \u2713  " + a + "\n"
    if no_trobats:
        resum += "\nCapes no trobades al projecte:\n"
        for n in no_trobats:
            resum += "  \u2013  " + n + "\n"

    QMessageBox.information(
        parent or iface.mainWindow(),
        "Estils de cadastre aplicats",
        resum
    )

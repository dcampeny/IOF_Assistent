# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.core import QgsProject

from .iof_utils import iof_layers_created


class IOFExporter:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = "IOF Assistent"
        self.toolbar = None
        # Widgets (QToolButton / QAction) que només s'han de poder fer
        # servir si el projecte ja té les capes IOF creades: cada
        # element és (widget, text_base_del_tooltip).
        self._layer_dependent_widgets = []
        # Cau de la plantilla d'estil QLR (Referencial Topogràfic
        # Territorial), perquè no calgui reanalitzar el XML (~3,5 MB)
        # cada cop que es descarrega un "Referencial topogràfic territorial vectorial" nou.
        self._qlr_style_cache = None

    def add_action(self, icon_path, text, callback, parent=None, requires_layers=False):
        px = QPixmap(icon_path)
        icon = QIcon(px)
        action = QAction(icon, text, parent or self.iface.mainWindow())
        action.triggered.connect(callback)
        self.toolbar.addAction(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        if requires_layers:
            self._layer_dependent_widgets.append((action, text))
        return action

    def initGui(self):
        self.toolbar = self.iface.mainWindow().addToolBar("IOF Assistent")
        self.toolbar.setObjectName("IOFAssistentToolBar")

        # ── Botó "Cadastre" (esquerra, separat de la resta per una barra vertical) ──
        self._add_dropdown_action(
            icon_path=os.path.join(self.plugin_dir, "icons", "region.png"),
            text="Cadastre",
            actions=[
                ("Importar cadastre", self.run_importar_cadastre, os.path.join(self.plugin_dir, "icons", "folder.png")),
                ("Seleccionar parcel·les cadastrals", self.run_seleccionar_parcelles, os.path.join(self.plugin_dir, "icons", "field.png")),
                ("Crear àmbit de l'IOF", self.run_crear_ambit, os.path.join(self.plugin_dir, "icons", "map1.png")),
                ("Aplicar estil de cadastre", self.run_aplicar_estil, os.path.join(self.plugin_dir, "icons", "label.png")),
            ]
        )

        # Separador entre Cadastre i la resta de botons
        self.toolbar.addSeparator()

        # ── Botons principals ──
        self.add_action(
            os.path.join(self.plugin_dir, "icons", "capa.png"),
            text="Crear capes IOF",
            callback=self.run_create,
        )
        # Botó "Digitalitzar" amb menú desplegable
        self._add_dropdown_action(
            icon_path=os.path.join(self.plugin_dir, "icons", "agregar-puntero.png"),
            text="Digitalitzar",
            actions=[
                ("Digitalitzar límits", self.run_limits, os.path.join(self.plugin_dir, "icons", "icon_border.png")),
                ("Digitalitzar unitats de vegetació", self.run_unitats, os.path.join(self.plugin_dir, "icons", "icon_unitats.png")),
                ("Digitalitzar camins", self.run_camins, os.path.join(self.plugin_dir, "icons", "icon_roads.png")),
                ("Digitalitzar infraestructures de prevenció d'incendis", self.run_infra, os.path.join(self.plugin_dir, "icons", "icon_infra.png")),
                ("Digitalitzar canvis d'ús", self.run_canvis, os.path.join(self.plugin_dir, "icons", "icon_canvis.png")),
                ("Digitalitzar punts d'aigua", self.run_aigua, os.path.join(self.plugin_dir, "icons", "icon_aigua.png")),
                ("Digitalitzar elements singulars", self.run_elements, os.path.join(self.plugin_dir, "icons", "icon_elements.png")),
                ("Digitalitzar inventaris", self.run_inventari, os.path.join(self.plugin_dir, "icons", "icon_inventari.png")),
            ],
            requires_layers=True,
        )
        # Botó "Dades i estils" amb submenú
        self._add_dropdown_action(
            icon_path=os.path.join(self.plugin_dir, "icons", "ajustes.png"),
            text="Dades i estils",
            actions=[
                ("Omplir camps", self.run_wizard, os.path.join(self.plugin_dir, "icons", "icon_wizard.png")),
                ("Aplicar estil de gestió", self.run_format, os.path.join(self.plugin_dir, "icons", "icon_format.png")),
            ],
            requires_layers=True,
        )

        # Separador vertical entre Dades i estils i Mapes ICGC
        self.toolbar.addSeparator()

        # ── Botó "Mapes ICGC" amb submenú ──
        self._add_dropdown_action(
            icon_path=os.path.join(self.plugin_dir, "icons", "globo.png"),
            text="Mapes ICGC",
            actions=[
                ("Base topogràfic", self.run_base_situacio, os.path.join(self.plugin_dir, "icons", "search.png")),
                ("Referencial topogràfic territorial vectorial", self.run_base_topografica, os.path.join(self.plugin_dir, "icons", "topografic.png")),
                ("Ortofotomapa", self.run_base_ortofoto, os.path.join(self.plugin_dir, "icons", "camera.png")),
            ]
        )

        # Separador vertical entre Mapes ICGC i Exportar IOF a TXT
        self.toolbar.addSeparator()

        self.add_action(
            os.path.join(self.plugin_dir, "icons", "icon_export.png"),
            text="Exportar IOF a TXT",
            callback=self.run_export,
            requires_layers=True,
        )

        # Separador vertical entre Exportar i Ajuda
        self.toolbar.addSeparator()

        # ── Botó "Ajuda" (dreta, separat de la resta per una barra vertical) ──
        self._add_dropdown_action(
            icon_path=os.path.join(self.plugin_dir, "icons", "help.png"),
            text="Ajuda",
            actions=[
                ("Sobre IOF Assistent", self.run_sobre_iof, os.path.join(self.plugin_dir, "icons", "icon.png")),
            ]
        )

        # Activa/desactiva "Digitalitzar", "Dades i estils" i "Exportar
        # IOF a TXT" segons si el projecte ja té les capes IOF creades,
        # i mantén-ho actualitzat en afegir/eliminar capes o en
        # obrir/crear un altre projecte.
        self._actualitza_estat_digitalitzacio()
        proj = QgsProject.instance()
        proj.layersAdded.connect(self._actualitza_estat_digitalitzacio)
        proj.layersRemoved.connect(self._actualitza_estat_digitalitzacio)
        proj.cleared.connect(self._actualitza_estat_digitalitzacio)

    def _actualitza_estat_digitalitzacio(self, *args):
        """Activa o desactiva els botons que necessiten les capes IOF
        (Digitalitzar, Dades i estils, Exportar IOF a TXT), segons si
        el projecte ja les té creades amb «Crear capes IOF»."""
        hi_ha_capes = iof_layers_created()
        avis = "" if hi_ha_capes else "\n\n(Cal crear primer les capes amb «Crear capes IOF».)"
        for widget, text_base in self._layer_dependent_widgets:
            widget.setEnabled(hi_ha_capes)
            widget.setToolTip(text_base + avis)

    def unload(self):
        proj = QgsProject.instance()
        try:
            proj.layersAdded.disconnect(self._actualitza_estat_digitalitzacio)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        try:
            proj.layersRemoved.disconnect(self._actualitza_estat_digitalitzacio)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        try:
            proj.cleared.disconnect(self._actualitza_estat_digitalitzacio)
        except Exception:  # nosec — error no crític, es descarta intencionadament
            pass
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
        if self.toolbar:
            self.toolbar.deleteLater()
            self.toolbar = None
        self.actions.clear()
        self._layer_dependent_widgets.clear()

    def run_create(self):
        from .iof_create_dialog import IOFCreateDialog
        dlg = IOFCreateDialog(self.iface)
        dlg.exec()

    def run_wizard(self):
        from .iof_selector_dialog import SelectorDialog
        dlg = SelectorDialog(self.iface)
        dlg.exec()
        # Crear el wizard AQUÍ, un cop dlg.exec() ha tornat (és a dir,
        # amb SelectorDialog ja tancat del tot) — no dins d'un dels
        # seus propis slots. Crear un diàleg no modal des d'un slot que
        # alhora tanca el seu diàleg modal contenidor fa que els clics
        # no arribin als seus botons, tot i que es vegi normal.
        if dlg.choice == 'finques':
            from .iof_finques_wizard import FinquesWizard
            self._finques_dlg = FinquesWizard(self.iface)
            if getattr(self._finques_dlg, "_cancelled", False):
                return
            self._finques_dlg.show()
            self._finques_dlg.raise_()
            self._finques_dlg.activateWindow()
        elif dlg.choice == 'unitats':
            from .iof_rodals_wizard import RodalsWizard
            self._rodals_dlg = RodalsWizard(self.iface)
            if getattr(self._rodals_dlg, "_cancelled", False):
                return
            self._rodals_dlg.show()
            self._rodals_dlg.raise_()
            self._rodals_dlg.activateWindow()
        elif dlg.choice == 'camins':
            from .iof_camins_wizard import CaminsWizard
            self._camins_dlg = CaminsWizard(self.iface)
            if getattr(self._camins_dlg, "_cancelled", False):
                return
            self._camins_dlg.show()
            self._camins_dlg.raise_()
            self._camins_dlg.activateWindow()

    def _add_dropdown_action(self, icon_path, text, actions, requires_layers=False):
        """Afegeix un QToolButton amb menú desplegable a la toolbar, i
        registra cada acció individual també al menú Complements ->
        IOF Assistent (abans només s'afegien a la barra d'eines, per
        això el menú de Complements sortia incomplet)."""
        menu = QMenu()
        first_action = None
        for label, callback, item_icon_path in actions:
            action = QAction(QIcon(QPixmap(item_icon_path)), label, self.iface.mainWindow())
            action.triggered.connect(callback)
            menu.addAction(action)
            self.iface.addPluginToMenu(self.menu, action)
            self.actions.append(action)
            if requires_layers:
                self._layer_dependent_widgets.append((action, label))
            if first_action is None:
                first_action = action

        btn = QToolButton()
        btn.setIcon(QIcon(QPixmap(icon_path)))
        btn.setToolTip(text)
        btn.setText(text)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        btn.setMenu(menu)
        # Clicar la icona obre el menú (igual que la fletxa)
        btn.clicked.connect(btn.showMenu)
        self.toolbar.addWidget(btn)
        if requires_layers:
            self._layer_dependent_widgets.append((btn, text))
        return btn

    def _show_if_ready(self, dlg):
        """Mostra el diàleg, tret que s'hagi marcat com a cancel·lat
        (típicament perquè no ha trobat la capa IOF que necessita al
        constructor — vegeu avisa_capa_no_trobada() a iof_utils.py)."""
        if getattr(dlg, "_cancelled", False):
            return
        dlg.show()

    def run_camins(self):
        from .iof_camins_dialog import CaminsDialog
        self._camins_dlg = CaminsDialog(self.iface)
        self._show_if_ready(self._camins_dlg)

    def run_infra(self):
        from .iof_infra_dialog import InfraDialog
        self._infra_dlg = InfraDialog(self.iface)
        self._show_if_ready(self._infra_dlg)

    def run_canvis(self):
        from .iof_canvis_dialog import CanvisDialog
        self._canvis_dlg = CanvisDialog(self.iface, self.iface.mainWindow())
        self._show_if_ready(self._canvis_dlg)

    def run_inventari(self):
        from .iof_inventari_dialog import InventariDialog
        self._inventari_dlg = InventariDialog(self.iface, self.iface.mainWindow())
        self._show_if_ready(self._inventari_dlg)

    def run_aigua(self):
        from .iof_aigua_dialog import AiguaDialog
        self._aigua_dlg = AiguaDialog(self.iface, self.iface.mainWindow())
        self._show_if_ready(self._aigua_dlg)

    def run_elements(self):
        from .iof_elements_dialog import ElementsDialog
        self._elements_dlg = ElementsDialog(self.iface, self.iface.mainWindow())
        self._show_if_ready(self._elements_dlg)

    def run_limits(self):
        from .iof_limits_dialog import LimitsDialog
        self._limits_dlg = LimitsDialog(self.iface)
        self._show_if_ready(self._limits_dlg)

    def run_unitats(self):
        from .iof_unitats_wizard import UnitatsWizard
        # Guardar la referència a self perquè el diàleg no bloquejant
        # no sigui destruït pel recol·lector d'escombraries
        self._unitats_dlg = UnitatsWizard(self.iface)
        # Si l'usuari ha cancel·lat des del diàleg "Unitats existents"
        # (mostrat dins del constructor, abans que existeixi cap
        # finestra visible), self.close() del wizard no evita que es
        # mostri — cal comprovar el flag explícitament i no continuar.
        if getattr(self._unitats_dlg, "_cancelled", False):
            return
        self._unitats_dlg.show()
        self._unitats_dlg.raise_()
        self._unitats_dlg.activateWindow()

    def run_aplicar_estil_cadastre(self):
        from .iof_estil_cadastre import aplicar_estil_cadastre
        aplicar_estil_cadastre(self.iface)

    def run_format(self):
        from .iof_format_dialog import FormatLayersDialog
        self._format_dlg = FormatLayersDialog(self.iface)
        self._format_dlg.show()
        self._format_dlg.raise_()
        self._format_dlg.activateWindow()

    def run_export(self):
        from .iof_dialog import IOFExporterDialog
        dlg = IOFExporterDialog(self.iface)
        dlg.exec()

    # ── Cadastre ──────────────────────────────────────────────────────────────

    def run_importar_cadastre(self):
        from .iof_importar_cadastre_dialog import ImportarCadastreDial
        dlg = ImportarCadastreDial(self.iface)
        dlg.exec()

    def run_aplicar_estil(self):
        from .iof_estil_cadastre import aplicar_estil_cadastre
        aplicar_estil_cadastre(self.iface)

    def run_crear_ambit(self):
        from .iof_ambit_dialog import crear_ambit_iof
        crear_ambit_iof(self.iface)

    def run_seleccionar_parcelles(self):
        from .iof_seleccio_parcelles_dialog import SeleccioParcellsDial
        if not hasattr(self, '_seleccio_dlg') or self._seleccio_dlg is None:
            self._seleccio_dlg = SeleccioParcellsDial(self.iface)
            self._seleccio_dlg.finished.connect(
                lambda: setattr(self, '_seleccio_dlg', None)
            )
        self._seleccio_dlg.show()
        self._seleccio_dlg.raise_()
        self._seleccio_dlg.activateWindow()

    # ── Mapes ICGC ────────────────────────────────────────────────────────────

    def run_base_situacio(self):
        """Carrega el Mapa Base Topogràfic de l'ICGC (WMS mapa-base, capa topografic)."""
        from qgis.core import QgsRasterLayer, QgsProject
        from qgis.PyQt.QtWidgets import QMessageBox

        NOM_CAPA = "Mapa base topogràfic (ICGC)"
        WMS_URL = "https://geoserveis.icgc.cat/servei/catalunya/mapa-base/wms"
        CAPA_WMS = "topografic"
        FORMAT = "image/png"
        CRS = "EPSG:3857"
        VERSIO = "1.1.1"

        # Evitar duplicats: si ja existeix, simplement la fa visible i surt
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == NOM_CAPA:
                QgsProject.instance().layerTreeRoot().findLayer(lyr).setItemVisibilityChecked(True)
                self.iface.setActiveLayer(lyr)
                return

        uri = (
            f"crs={CRS}"
            f"&format={FORMAT}"
            f"&layers={CAPA_WMS}"
            f"&styles="
            f"&url={WMS_URL}"
            f"&version={VERSIO}"
        )

        layer = QgsRasterLayer(uri, NOM_CAPA, "wms")

        if not layer.isValid():
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Mapes ICGC — Base topogràfic",
                "No s'ha pogut carregar el mapa base topogràfic de l'ICGC.\n\n"
                "Comproveu la connexió a internet i torneu-ho a intentar.\n\n"
                f"URL: {WMS_URL}\nCapa: {CAPA_WMS}"
            )
            return

        QgsProject.instance().addMapLayer(layer, False)

        # Afegir la capa al grup "Cartografia de referència" (el crea si no existeix)
        root = QgsProject.instance().layerTreeRoot()
        grup = root.findGroup("Cartografia de referència")
        if grup is None:
            grup = root.insertGroup(-1, "Cartografia de referència")
        grup.insertLayer(0, layer)

    # ── Plantilla d'estil per al Referencial topogràfic territorial ───────────

    def _get_qlr_style_template(self):
        """Llegeix (un sol cop, amb cau) la plantilla d'estil pròpia del
        complement (styles/topografic_estils.json.gz) i retorna
        (estils_per_subcapa, visibilitat_per_subcapa):
          - estils_per_subcapa: {nom_subcapa_gpkg: xml_estil_qgis}
          - visibilitat_per_subcapa: {nom_subcapa_gpkg: bool}
        indexats pel nom de la subcapa dins del GeoPackage (p. ex.
        "_10_noms_geografics_l"), que és estable entre descàrregues
        diferents del mateix producte.

        Aquest fitxer és una extracció compacta (JSON + gzip, ~68 KB) de
        l'estil actiu d'un .qlr exportat des de QGIS (~3,4 MB, generat
        per l'aplicació QGIS, no pel complement). Només es conserva el
        que realment s'aplica (renderer, etiquetatge, visibilitat per
        escala i quines capes eren visibles) — no l'estructura de grup,
        les extensions, els estils alternatius ("gris") ni la
        informació de connexió del .qlr original. Si mai cal actualitzar
        la plantilla, torna a exportar un .qlr des de QGIS i regenera
        aquest fitxer amb el mateix procediment (vegeu CLAUDE.md).
        """
        if self._qlr_style_cache is not None:
            return self._qlr_style_cache

        import gzip
        import json

        json_path = os.path.join(self.plugin_dir, "styles", "topografic_estils.json.gz")
        if not os.path.exists(json_path):
            self._qlr_style_cache = ({}, {})
            return self._qlr_style_cache

        try:
            with gzip.open(json_path, "rb") as f:
                payload = json.loads(f.read().decode("utf-8"))
            estils = payload.get("estils", {})
            visibilitat = payload.get("visibilitat", {})
        except Exception:
            estils, visibilitat = {}, {}

        self._qlr_style_cache = (estils, visibilitat)
        return self._qlr_style_cache

    def _aplicar_estil_qlr(self, layer_node, estils_per_subcapa, visibilitat_per_subcapa):
        """Aplica, si n'hi ha, l'estil i la visibilitat de la plantilla
        QLR a una capa carregada (identificant-la pel nom de la seva
        subcapa dins del GeoPackage, extret de layer.source())."""
        lyr = layer_node.layer()
        if lyr is None:
            return
        source = lyr.source()
        if "|layername=" not in source:
            return
        sublayer = source.split("|layername=")[-1]

        estil_xml = estils_per_subcapa.get(sublayer)
        if estil_xml:
            from qgis.PyQt.QtXml import QDomDocument
            doc = QDomDocument()
            if doc.setContent(estil_xml):
                try:
                    lyr.importNamedStyle(doc)
                except Exception:  # nosec — error no crític, es descarta intencionadament
                    pass
                lyr.triggerRepaint()

        if sublayer in visibilitat_per_subcapa:
            layer_node.setItemVisibilityChecked(visibilitat_per_subcapa[sublayer])

    def run_base_topografica(self):
        """Obre el Gestor de topografia (generar nova capa, gestionar la
        carregada, o carregar-ne una d'existent)."""
        from .iof_gestor_topografia_dialog import GestorTopografiaDialog
        dlg = GestorTopografiaDialog(self.iface, self)
        dlg.exec()

    def run_base_topografica_descarrega(self):
        """Obre el diàleg de descàrrega del complement oficial «Open ICGC»
        per al Referencial Topogràfic Territorial (format GeoPackage).

        L'ICGC no ofereix cap API senzilla de descàrrega directa per a
        aquest producte (a diferència del WMS de l'ortofoto o del mapa
        base). En lloc de reimplementar-la, es reutilitza el diàleg del
        complement oficial «Open ICGC» (github.com/OpenICGC/QgisPlugin),
        si l'usuari el té instal·lat i actiu — literalment el mateix
        mètode que crida el seu propi menú «Referencial topogràfic
        territorial dades vectorials (gpkg)».
        """
        from qgis.PyQt.QtWidgets import QMessageBox
        from qgis.utils import plugins

        PRODUCTE_ID = "topografia-territorial-gpkg"

        openicgc = None
        for plugin in plugins.values():
            if type(plugin).__name__ == "OpenICGC":
                openicgc = plugin
                break

        if openicgc is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Mapes ICGC — Referencial topogràfic territorial vectorial",
                "Aquesta opció necessita el complement oficial «Open ICGC» "
                "instal·lat i actiu.\n\n"
                "Complements → Administra i instal·la complements → "
                "cerca «Open ICGC» → Instal·la.\n\n"
                "Un cop instal·lat, torna a clicar aquest botó."
            )
            return

        fme_list = getattr(openicgc, "fme_services_list", None)
        if not fme_list:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Mapes ICGC — Referencial topogràfic territorial vectorial",
                "El complement «Open ICGC» encara no ha carregat el "
                "llistat de productes descarregables.\n\n"
                "Obre una vegada el seu propi menú de descàrregues des "
                "de la seva barra d'eines i torna-ho a provar."
            )
            return

        entry = None
        for item in fme_list:
            pid = item[0]
            if pid and pid.split("/")[-1] == PRODUCTE_ID:
                entry = item
                break

        if entry is None:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Mapes ICGC — Referencial topogràfic territorial vectorial",
                f"No s'ha trobat el producte «{PRODUCTE_ID}» al llistat "
                "de l'Open ICGC. És possible que n'hagin canviat "
                "l'identificador des del servidor de l'ICGC."
            )
            return

        (pid, name, min_side, max_query_area, min_px_side, max_px_area,
         _gsd, time_list, download_list, filename, limits,
         _url_pattern, url_ref_or_wms_tuple, _enabled) = entry

        # Nom de fitxer per defecte propi, preservant l'extensió que
        # Open ICGC espera per a aquest producte (normalment .gpkg)
        _base, _ext = os.path.splitext(filename or "")
        filename = "IOF_Topografia" + (_ext or ".gpkg")

        # Open ICGC indexa internament els productes per l'id SENSE el
        # prefix de grup (get_services_dict() fa id.split("/")[-1] com a
        # clau). Cal passar-li aquesta mateixa forma stripped, no l'id
        # complet de fme_services_list, o get_clip_data_url() no troba
        # el producte i cau a un valor per defecte amb download_list=None
        # → "TypeError: argument of type 'NoneType' is not iterable".
        pid_stripped = pid.split("/")[-1] if pid else pid

        # La carpeta de descàrregues és una configuració GLOBAL d'Open
        # ICGC (no depèn del producte), i el seu propi diàleg de
        # confirmació no permet canviar-la — només mostra la carpeta ja
        # configurada. Se li dona accés aquí, perquè es pugui triar o
        # canviar sense haver d'anar al menú propi d'Open ICGC.
        nova_carpeta = openicgc.set_download_folder()
        if not nova_carpeta:
            # L'usuari ha cancel·lat el selector de carpeta
            return

        # Open ICGC crea el seu propi grup "Descàrregues" (self.tr("Download"))
        # a l'arrel del projecte de manera asíncrona (la descàrrega passa
        # després que aquesta funció ja hagi acabat). S'hi deixa un
        # vigilant que, quan detecti que aquell grup s'ha acabat d'omplir,
        # el reanomeni com a "Topogràfic territorial N" (numerat) i el
        # mogui dins de "Cartografia de referència".
        nom_grup_openicgc = getattr(openicgc, "DOWNLOAD_GROUP_NAME", None) \
            or openicgc.tr("Download")
        self._openicgc_watch_and_regroup(
            nom_grup_openicgc, "Cartografia de referència"
        )

        openicgc.enable_download_subscene(
            pid_stripped, name, min_side, max_query_area, min_px_side,
            max_px_area, time_list, download_list, filename, limits,
            url_ref_or_wms_tuple
        )

    def _openicgc_watch_and_regroup(self, nom_grup_openicgc, nom_grup_pare):
        """Espera que Open ICGC creï/omplí el seu grup de descàrrega per
        defecte i, un cop s'estabilitzi (cap canvi a l'arbre de capes
        durant 1,5 s — senyal que ha acabat de carregar totes les capes
        del GPKG), el reanomena com a "Topogràfic territorial N" (el
        següent número disponible, vegeu iof_utils.seguent_numero_topografia())
        i el mou dins del grup `nom_grup_pare`. Es dona per vençut als 3
        minuts si no detecta res, per no deixar connexions de senyal
        penjades indefinidament si l'usuari cancel·la la descàrrega o
        hi ha un error abans de crear cap capa.
        """
        from qgis.PyQt.QtCore import QTimer
        from qgis.core import QgsProject

        root = QgsProject.instance().layerTreeRoot()
        state = {"timer": None, "giveup_timer": None}

        def _neteja():
            try:
                root.addedChildren.disconnect(_on_canvi)
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass
            try:
                root.removedChildren.disconnect(_on_canvi)
            except Exception:  # nosec — error no crític, es descarta intencionadament
                pass
            if state["timer"] is not None:
                state["timer"].stop()
            if state["giveup_timer"] is not None:
                state["giveup_timer"].stop()

        def _fer_reagrupament():
            from .iof_utils import seguent_numero_topografia, renumera_grups_topografia
            grup = root.findGroup(nom_grup_openicgc)
            if grup is None:
                return
            nom_grup_desti = f"Topogràfic territorial {seguent_numero_topografia()}"
            grup.setName(nom_grup_desti)
            grup_pare = root.findGroup(nom_grup_pare)
            if grup_pare is None:
                grup_pare = root.insertGroup(-1, nom_grup_pare)
            # Moure = clonar dins del nou pare + eliminar l'original
            # (l'API de QGIS no té un "moveTo" directe per a grups)
            clon = grup.clone()
            grup_pare.insertChildNode(0, clon)
            root.removeChildNode(grup)
            # Netejar el nom de cada capa individual: Open ICGC sempre
            # afegeix un sufix _AAAAMMDD_HHMMSS al nom de fitxer de
            # manera incondicional (download_map_area(), no és cap
            # paràmetre que puguem evitar). Es reconstrueix el nom com
            # "IOF_Topografia — <subcapa>", i s'aplica (si n'hi ha) la
            # plantilla d'estil/visibilitat del .qlr de referència.
            estils, visibilitat = self._get_qlr_style_template()
            for node in clon.findLayers():
                lyr = node.layer()
                if lyr is None:
                    continue
                self._aplicar_estil_qlr(node, estils, visibilitat)
                nom = lyr.name()
                if " — " in nom:
                    sufix = nom.split(" — ", 1)[1]
                    lyr.setName(f"IOF_Topografia — {sufix}")
            renumera_grups_topografia()
            _neteja()

        def _on_canvi(*_args):
            if root.findGroup(nom_grup_openicgc) is None:
                return
            if state["timer"] is None:
                state["timer"] = QTimer()
                state["timer"].setSingleShot(True)
                state["timer"].timeout.connect(_fer_reagrupament)
            state["timer"].start(1500)

        root.addedChildren.connect(_on_canvi)
        root.removedChildren.connect(_on_canvi)

        state["giveup_timer"] = QTimer()
        state["giveup_timer"].setSingleShot(True)
        state["giveup_timer"].timeout.connect(_neteja)
        state["giveup_timer"].start(180000)

    def run_base_ortofoto(self):
        """Carrega l'ortofotomapa vigent de l'ICGC (WMS orto-local-rgb-vigents)."""
        from qgis.core import QgsRasterLayer, QgsProject
        from qgis.PyQt.QtWidgets import QMessageBox

        NOM_CAPA = "Ortofotomapa vigent (ICGC)"
        WMS_URL = "https://geoserveis.icgc.cat/servei/catalunya/orto-territorial/wms"
        CAPA_WMS = "ortofoto_color_vigent"
        FORMAT = "image/jpeg"
        CRS = "EPSG:25831"
        VERSIO = "1.3.0"

        # Evitar duplicats: si ja existeix, simplement la fa visible i surt
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.name() == NOM_CAPA:
                QgsProject.instance().layerTreeRoot().findLayer(lyr).setItemVisibilityChecked(True)
                self.iface.setActiveLayer(lyr)
                return

        uri = (
            f"crs={CRS}"
            f"&format={FORMAT}"
            f"&layers={CAPA_WMS}"
            f"&styles="
            f"&url={WMS_URL}"
            f"&version={VERSIO}"
        )

        layer = QgsRasterLayer(uri, NOM_CAPA, "wms")

        if not layer.isValid():
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Mapes ICGC — Ortofotomapa",
                "No s'ha pogut carregar l'ortofotomapa de l'ICGC.\n\n"
                "Comproveu la connexió a internet i torneu-ho a intentar.\n\n"
                f"URL: {WMS_URL}\nCapa: {CAPA_WMS}"
            )
            return

        QgsProject.instance().addMapLayer(layer, False)

        # Afegir la capa al grup "Cartografia de referència" (el crea si no existeix)
        root = QgsProject.instance().layerTreeRoot()
        grup = root.findGroup("Cartografia de referència")
        if grup is None:
            grup = root.insertGroup(-1, "Cartografia de referència")
        grup.insertLayer(0, layer)

    # ── Ajuda ─────────────────────────────────────────────────────────────────

    def run_sobre_iof(self):
        from .iof_sobre_dialog import SobreIOFDialog
        dlg = SobreIOFDialog(self.iface.mainWindow())
        dlg.exec()

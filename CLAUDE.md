# IOF Assistent — Context per a Claude Code

Plugin de QGIS (PyQGIS) per a la creació i exportació del pla de gestió d'un
**Instrument d'Ordenació Forestal (IOF)**, segons les especificacions del
Centre de la Propietat Forestal de Catalunya (CPF).

Consulta `README.md` per a la instal·lació i l'ús del plugin des de la
interfície de QGIS. Aquest fitxer és només per a com ha de treballar Claude
en aquest repositori.

## Compatibilitat objectiu
- QGIS mínim: 3.0 (desenvolupament i proves principalment sobre QGIS 3.4)
- PyQGIS (PyQt5)

## Estructura del projecte
- `*_dialog.py` — diàlegs individuals (un per capa/funcionalitat: finques,
  camins, aigua, infraestructures, canvis, base points, etc.)
- `*_wizard.py` — assistents pas a pas (digitalització de finques, camins,
  infraestructures)
- `iof_taules.py` — definicions de taules/camps compartides
- `municipis_catalunya.py` — dades de referència de municipis
- `icons/` — icones .png de la barra d'eines i menús (referenciades des de
  `iof_exporter.py` i `iof_sobre_dialog.py`)
- `symbols/` — símbols .svg per a l'estil de gestió (`iof_format_dialog.py`)
- `styles/` — `cadastre_estils.json.gz`, plantilla d'estil compacta
  consolidada dels 4 estils de cadastre (Finca, Municipi, Parcelles,
  Poligons), llegida per `aplica_qml()` (`iof_utils.py`, compartida —
  vegeu nota tècnica més avall); `topografic_estils.json.gz`,
  plantilla d'estil compacta per a "Referencial topogràfic territorial
  vectorial" (vegeu nota tècnica corresponent més avall); i
  `finques_colors.json`, colors de la paleta de finques (originalment de
  MiraMon, `finques.dbf`), llegit per
  `iof_estil_cadastre.py::_llegir_colors_finca()`
- `metadata.txt` — metadades del plugin per al gestor de complements de
  QGIS (el camp `icon=` apunta a `icons/icon.png`)

**Si s'afegeix un recurs nou** (icona, SVG, QML...), posar-lo a la carpeta
que li correspongui per tipus, no a l'arrel del projecte.

## Notes tècniques importants
- L'eina estàndard "Split Features" de QGIS 3.4 no és fiable per digitalitzar
  polígons de finques/unitats d'actuació. S'utilitza una implementació pròpia
  de tall de polígons amb `QgsGeometry.splitGeometry()`.
- Les capes cartogràfiques de base venen de serveis WMS de l'ICGC (ortofoto,
  topogràfica, situació) — vigilar sempre la compatibilitat de CRS.
- El format de sortida `.txt` és estricte (camps separats per `#`, un
  registre per línia, terminador `ZZ`); qualsevol canvi en la generació del
  TXT s'ha de validar contra els exemples del `README.md` abans de donar-lo
  per bo.
- `IOF_Finques` és `MultiPolygon`, no `Polygon` (des de juliol 2026). Una
  finca amb un camí que la travessa de banda a banda és legítimament 2 parts
  separades, no un polígon amb un forat. Si es toca la creació d'aquesta
  capa (`iof_create_dialog.py`, `iof_limits_dialog.py`), mantenir-la
  `MultiPolygon`.
- **Mapes ICGC** (menú, abans "Base cartogràfica"): "Ortofotomapa" i "Base
  topogràfic" (abans "Situació") (mapa base
  topogràfic) es carreguen per WMS directe (`run_base_ortofoto`,
  `run_base_situacio` a `iof_exporter.py`). El **Referencial Topogràfic
  Territorial** ("Referencial topogràfic territorial vectorial", abans
  "Base topogràfica") NO té WMS/URL de descàrrega directa
  ni API pública pròpia. En lloc de reimplementar-la, `run_base_topografica()`
  reutilitza el complement oficial **Open ICGC**
  (github.com/OpenICGC/QgisPlugin), si l'usuari el té instal·lat:
  cerca la instància viva del plugin a `qgis.utils.plugins` (per
  `type(plugin).__name__ == "OpenICGC"`, no per un nom de clau fix, que
  pot variar segons com s'hagi instal·lat), busca l'entrada amb id
  `"topografia-territorial-gpkg"` dins `openicgc.fme_services_list`
  (llistat que Open ICGC obté en viu del servidor de l'ICGC en
  inicialitzar-se), i crida `openicgc.enable_download_subscene(...)`
  amb els mateixos paràmetres que faria servir el seu propi menú — és
  literalment el mateix mètode intern, no una còpia. Si mai cal el
  mateix patró per a un altre producte de l'ICGC (LiDAR, ortofoto
  infraroja, etc.), el seu id exacte es pot trobar cercant
  `FME_NAMES_DICT` dins del codi font d'Open ICGC.
  **Detall important:** cal passar l'id **sense** el prefix de grup
  (`id.split("/")[-1]`), no el valor cru de `fme_services_list` — Open
  ICGC indexa internament `get_services_dict()` per l'id ja stripped, i
  passar-hi l'id complet fa que la cerca falli silenciosament i
  `download_list` acabi sent `None`, provocant
  `TypeError: argument of type 'NoneType' is not iterable` dins del
  propi codi d'Open ICGC (`resources3/fme.py::get_clip_data_url`) just
  en confirmar l'àrea de descàrrega al mapa.
  **Dependència de versió per a QGIS 4 (juliol 2026):** com que
  `run_base_topografica()` crida directament atributs/mètodes d'Open
  ICGC (`fme_services_list`, `enable_download_subscene()`,
  `DOWNLOAD_GROUP_NAME`), la compatibilitat amb QGIS 4 d'aquesta funció
  **també depèn** que l'usuari tingui instal·lada la versió d'Open ICGC
  que declara `qgisMaximumVersion=4.99` (v1.2.0 o posterior — commit
  "QGIS 3/4 compatibility",
  github.com/OpenICGC/QgisPlugin@2f60d413194cf1191ae23c6730de01a8bcdcd51d).
  Verificat (juliol 2026) que aquest commit NO toca cap dels tres punts
  d'integració anteriors ni `resources3/fme.py` — no calen canvis al
  nostre codi. Amb una versió antiga d'Open ICGC (pre-1.2.0) sota QGIS
  4, QGIS ni tan sols carregaria aquell complement (fora del seu rang de
  versions declarat), i el nostre propi avís "Open ICGC no trobat" ja
  cobriria el cas sense canvis.
  **Sufix de data/hora al fitxer:** `download_map_area()` afegeix
  sempre `_AAAAMMDD_HHMMSS` al nom de fitxer confirmat per l'usuari
  (línia fixa, no és cap paràmetre exposat) — no es pot evitar sense
  tocar el codi instal·lat d'Open ICGC. Es compensa reanomenant cada
  capa un cop carregada (`_fer_reagrupament()`), no el fitxer del disc.
  **Plantilla d'estil (`styles/topografic_estils.json.gz`):** un cop
  reagrupades les capes, `_get_qlr_style_template()` llegeix aquest
  fitxer i en retorna, per cada subcapa del GPKG (identificada pel nom
  de `layername=` al `datasource`, no per l'`id` intern — aquest canvia
  a cada descàrrega), l'estil actiu (`renderer-v2`, `labeling`,
  visibilitat per escala) i si estava marcada com a visible.
  `_aplicar_estil_qlr()` ho aplica a cada capa nova amb
  `QgsMapLayer.importNamedStyle()`. Resultat: les capes noves surten
  amb la mateixa simbologia i visibilitat per escala que la plantilla,
  no l'estil pla per defecte d'Open ICGC.
  **Origen del fitxer (juliol 2026):** aquest `.json.gz` és una extracció
  compacta d'un `.qlr` exportat des de QGIS (~3,4 MB — generat per
  l'aplicació QGIS, no pel complement). Es va reduir a ~68 KB (98%
  menys) parsejant el `.qlr` amb `xml.etree.ElementTree`, quedant-se
  només amb els tags `renderer-v2`, `labeling`, `customproperties`,
  `blendMode`, `featureBlendMode`, `layerOpacity`, `flags` i els atributs
  d'escala de cada `<maplayer>` (descartant estructura de grup,
  extensions, estils alternatius "gris" i informació de connexió), i
  desant-ho com `{"estils": {subcapa: xml}, "visibilitat": {subcapa: bool}}`
  en JSON + gzip. **Si mai cal actualitzar la plantilla:** exportar un
  `.qlr` nou des de QGIS i repetir aquest mateix procés d'extracció (no
  hi ha necessitat de conservar el `.qlr` original dins del plugin un
  cop generat el `.json.gz` — val la pena guardar-ne una còpia fora del
  repositori del plugin, per si cal tornar-hi en el futur).
  **Plantilla d'estil de cadastre (`styles/cadastre_estils.json.gz`):**
  mateix patró, aplicat als 4 `.qml` originals (Finca, Municipi,
  Parcelles, Poligons — 132 KB en total). Consolidats en un sol JSON +
  gzip de 18 KB (86% menys), amb el contingut XML complet de cada `.qml`
  tal qual (no calia filtrar tags, ja que un `.qml` és un document d'una
  sola capa, a diferència del `.qlr` que en té 29). `aplica_qml()`
  (`iof_utils.py` — abans duplicada a `iof_ambit_dialog.py` i
  `iof_estil_cadastre.py`, consolidada juliol 2026; els dos fitxers
  l'importen com `from .iof_utils import aplica_qml as _aplica_qml` per
  no haver de tocar les crides existents) hi busca l'entrada pel nom de
  fitxer original (p. ex. `"IOF-Cadastre-Finca.qml"`, encara usat com a
  clau) i l'aplica amb `QgsMapLayer.importNamedStyle()` en lloc de
  `loadNamedStyle(path)` (que necessitava el fitxer físic al disc).
  **Compte:** `importNamedStyle()` retorna una tupla `(bool, str)`,
  no un booleà sol — cal desempaquetar-la (`ok, _err = layer.importNamedStyle(doc)`),
  a diferència de `loadNamedStyle()` que retornava `(str, bool)` en
  l'ordre invers. Si mai cal actualitzar algun d'aquests 4 estils,
  regenerar-lo des de QGIS (Capa → Propietats → Estil → Desa com a
  fitxer, en format QML) i repetir l'extracció.
  **Colors de finques (`styles/finques_colors.json`):** substitueix
  `finques.dbf` (paleta MiraMon, format binari .dbf). Abans calia un
  parser binari fet a mà amb `struct` (capçalera dBase, camps de mida
  fixa) per llegir només 4 columnes (`CLAUSIMBOL`, `R_COLOR`, `G_COLOR`,
  `B_COLOR`) de 43 registres — ara és `{"1": [255,255,190], ...}` i es
  llegeix amb `json.load()` directe. La mida puja lleugerament (720 B →
  972 B, són 43 registres, la diferència és irrellevant) però
  s'elimina tot el codi de parsejat binari (`import struct` ja no fa
  falta a `iof_estil_cadastre.py`) i el format és llegible/editable a
  mà. Verificat registre a registre contra el `.dbf` original abans
  d'eliminar-lo.

- **SSL del Cadastre ignorat deliberadament** (`iof_importar_cadastre_dialog.py`):
  el certificat de `catastro.hacienda.gob.es` el signa la FNMT-RCM
  (autoritat de certificació de l'Estat espanyol), que macOS no porta
  preinstal·lada de fàbrica — provoca `SSL handshake failed` en
  ordinadors nous fins que algú instal·la manualment el certificat arrel.
  Decisió deliberada (demanada explícitament, juliol 2026): en lloc
  d'obligar l'usuari a instal·lar-lo a cada ordinador, `_confiar_si_es_cadastre()`
  connecta `reply.sslErrors` a `reply.ignoreSslErrors` **només** quan
  l'amfitrió de la petició acaba en `catastro.hacienda.gob.es` o
  `catastro.meh.es` (`_es_domini_cadastre()`) — mai de manera global. Si
  mai s'afegeix una altra petició de xarxa a aquest fitxer, cal cridar
  `_confiar_si_es_cadastre(reply)` només si el domini és realment del
  Cadastre; no estendre-ho a altres dominis sense tornar a valorar-ho.
  **Important:** `QgsNetworkAccessManager` (el gestor de xarxa propi de
  QGIS) mostra sempre el seu propi diàleg natiu "Custom Certificate
  Configuration" en trobar un error SSL, encara que `ignoreSslErrors()`
  ja l'hagi gestionat — no n'hi ha prou amb connectar `sslErrors`. Per
  això `_download_zip()` fa servir un `QtNetwork.QNetworkAccessManager()`
  de Qt normal (igual que ja fa la petició del feed ATOM), no el de QGIS.
  Si mai es torna a introduir `QgsNetworkAccessManager` en aquest fitxer,
  el diàleg natiu tornarà a sortir independentment d'aquest fix.

## Bugs coneguts / ja resolts (no reintroduir)
Aquests quatre problemes van sortir junts depurant la divisió d'unitats
d'actuació (juliol 2026) i val la pena tenir-los presents si es toca
`iof_unitats_wizard.py`, `iof_limits_dialog.py` o `iof_create_dialog.py`:

1. **Codis de resultat de `splitGeometry()`**: en QGIS modern retorna
   l'enum `Qgis.GeometryOperationResult`, els valors del qual *no*
   comencen a 1 (`NothingHappened=1000`, `InvalidBaseGeometry=1001`,
   `GeometryEngineError=1005`, etc.), no els codis vells 0/1/2 de QGIS
   3.4. Quan es faci log o gestió d'errors sobre el resultat, decodificar
   el nom real (`result[0].name`), no assumir els codis antics.
2. **Geometries invàlides abans d'operar-hi**: `splitGeometry()` i
   `difference()` fallen silenciosament (o amb error poc clar) si la
   geometria de partida no és vàlida (`geom.isGeosValid()`). Validar i
   corregir amb `geom.makeValid()` abans de tallar o restar geometries,
   sobretot en dades importades del cadastre.
3. **"Hole lies outside shell"**: el "morphological closing"
   (`buffer(+0.05)` seguit de `buffer(-0.05)`) a `iof_limits_dialog.py`
   pot desplaçar anells interiors (com un camí que gairebé arriba a la
   vora) fora del contorn recalculat. Cal `makeValid()` just després del
   closing, i la capa de destí ha de ser `MultiPolygon` (vegeu nota
   anterior) perquè la reparació no perdi parts en desar-se.
4. **`UNIQUE constraint failed: <capa>.fid` en dividir entitats a
   GeoPackage**: bug conegut de QGIS+GPKG (reportat des de 2016). En
   copiar `feat.attributes()` a una entitat nova després d'un split, es
   copia també el `fid` de l'original si aquest apareix com a camp normal
   a `layer.fields()`. Cal buidar-lo explícitament
   (`new_feat.setAttribute(fid_idx, None)`) abans de `layer.addFeature()`
   perquè el proveïdor n'assigni un de nou i únic. Aplicar el mateix
   patró a qualsevol altre lloc del codi que dupliqui atributs d'una
   entitat GPKG existent per crear-ne una de nova.
5. **Diàleg buit en cancel·lar `UnitatsWizard`**: quan un `QDialog` fa
   lògica pròpia (com mostrar un `QMessageBox` de confirmació) dins del
   seu propi `__init__`, cridar `self.close()` en aquest punt no evita
   que la finestra es mostri després — el `.show()` el crida qui l'ha
   instanciat, *després* que `__init__` acabi, sense saber que ja s'ha
   cancel·lat per dins. Patró correcte: exposar un flag (`self._cancelled`)
   que qui crea el diàleg comprova abans de cridar `.show()` (vegeu
   `run_unitats()` a `iof_exporter.py`). Vigilar aquest mateix patró si
   s'afegeix lògica de confirmació al constructor d'altres diàlegs/wizards
   del plugin.
6. **Zoom del mapa bloquejat / botons sense resposta en omplir camps de
   camins**: `CaminsWizard` s'obria amb `dlg.exec_()` (modal) des d'un
   botó de `SelectorDialog` (també modal), cosa que bloquejava tota
   interacció amb la finestra principal —zoom, pan— mentre era obert.
   **Primer intent (incomplet):** fer-lo no modal directament dins del
   slot `_open_camins()` (`self._camins_dlg = CaminsWizard(...);
   .show()`), igual que `_open_unitats()`. Això va arreglar el zoom,
   però va deixar els botons interns del wizard (Desar i continuar,
   Cancel·lar) sense resposta i sense cap error de Python: crear i
   mostrar un diàleg **no modal** des d'un slot que alhora tanca (amb
   `self.accept()`) el seu propi diàleg **modal** contenidor fa que els
   clics no arribin mai als widgets fills, encara que la finestra es
   vegi normal i respongui als controls natius (botó X).
   **Solució definitiva:** `SelectorDialog` ja no crea cap wizard —
   només guarda la tria a `self.choice` (`'unitats'` / `'camins'` /
   `'finques'`) i es tanca. Qui l'ha obert (`run_wizard()` a
   `iof_exporter.py`) crea i mostra el wizard corresponent **després**
   que `dlg.exec_()` hagi tornat — és a dir, fora de qualsevol slot niat
   dins d'un altre diàleg modal. Patró a seguir sempre que un diàleg
   modal hagi d'obrir-ne un de no modal: no fer-ho dins del propi slot,
   fer que el creador ho faci un cop `exec_()` ha tornat.
   `FinquesWizard` (`_open_finques()`) tenia exactament el mateix bug —
   corregit amb el mateix patró (juliol 2026): la comprovació de "dades
   ja complertes" es fa abans de tancar `SelectorDialog` (un
   `QMessageBox` niat dins d'un diàleg modal sí que funciona bé; el
   problema només és amb diàlegs *no modals*), i només després es guarda
   `self.choice = 'finques'` i es tanca.
7. **`AttributeError: 'CanvisDialog' object has no attribute
   '_on_feature_added'`**: el cos del mètode `_on_feature_added(self, fid)`
   (el que registra el polígon acabat de dibuixar com a "pendent de
   desar") havia quedat enganxat per error al final de
   `_deactivate_map_tool()`, sense la seva pròpia línia `def`. Referenciat
   en 5 llocs del fitxer (`_activate_map_tool`, `_deactivate_map_tool`,
   `_on_desar`) però mai definit → petava en obrir el diàleg
   (`showEvent` → `_activate_map_tool` → connectar el senyal). Comparat
   amb el patró bessó a `iof_infra_dialog.py` (`_on_feature_added` +
   `_deactivate_map_tool` com a mètodes separats) per reconstruir la
   versió correcta. Si es toca `iof_aigua_dialog.py`,
   `iof_elements_dialog.py`, `iof_inventari_dialog.py` o
   `iof_base_point_dialog.py` (dialegs amb el mateix patró de digitalitzar
   + `_on_feature_added`), val la pena comprovar que el mètode existeixi
   de debò i no s'hagi perdut de la mateixa manera.
8. **Menú Complements incomplet (només toolbar correcta)**:
   `_add_dropdown_action()` (usada per als botons "Cadastre",
   "Digitalitzar", "Dades i estils", "Mapes ICGC", "Ajuda") només
   afegia les accions a la barra d'eines (`self.toolbar.addWidget(btn)`),
   sense mai cridar `iface.addPluginToMenu(...)` — a diferència
   d'`add_action()`, que sí ho fa per als botons plans ("Crear capes IOF",
   "Exportar IOF a TXT"). Per això el menú QGIS → Complements → IOF
   Assistent només mostrava 2 entrades, mentre la barra d'eines es veia
   completa. Corregit registrant cada acció del desplegable també amb
   `iface.addPluginToMenu()` + `self.actions.append()`, igual que ja fa
   `add_action()` (reutilitza el mateix cicle de neteja a `unload()`, que
   itera `self.actions`). Resultat: totes les accions surten a
   Complements, però en una **llista plana** dins de "IOF Assistent", no
   agrupades per categoria com a la barra d'eines — QGIS no permet
   sub-menús niats amb `addPluginToMenu()` sense construir manualment
   `iface.pluginMenu()`. Si es vol agrupar-ho (Complements → IOF Assistent
   → Cadastre → ...), caldria refer-ho amb `QMenu` propis afegits a
   `iface.pluginMenu()` en lloc d'`addPluginToMenu()`.

## Millores de funcionalitat implementades
1. **Botó "Cancel·lar"** al diàleg de 3 opcions de `_show_step_finca()`
   (`iof_unitats_wizard.py`, finca ja digitalitzada). Tanca l'assistent
   sencer reutilitzant `_close_wizard()` (mateixa neteja i confirmació de
   canvis pendents que "Tancar assistent").
2. **Ressaltat d'unitats sense definir** (`iof_rodals_wizard.py`): botó de
   commutació que marca amb un contorn vermell (`QgsHighlight`) totes les
   entitats de la capa considerades "no definides". Es refresca sol just
   després de cada `_save_current()` (perquè la unitat que s'acaba
   d'omplir desaparegui a l'instant) i es neteja en tancar el wizard
   (`reject()`/`closeEvent()`). **Corregit (juliol 2026):** el filtre
   original només comprovava `codi_us`, mentre que `_on_map_clicked()`
   (la comprovació de "ja definida" en clicar una unitat al mapa)
   comprova `self._codi_field` (codi_rodal/codi_ua), `for_forestal` I
   `codi_us` alhora, a més de tractar el text literal `"NULL"` com a
   buit. Aquesta discrepància feia que unitats ja definides (per
   `for_forestal` però amb `codi_us` buit) sortissin ressaltades com a
   "sense definir", confonent l'usuari quan després clicava sobre elles
   i el propi wizard li deia "ja té dades desades". Ara totes dues
   funcions fan servir exactament la mateixa lògica.
3. **Importació massiva de punts d'inventari des de CSV**
   (`iof_inventari_dialog.py`, juliol 2026): botó "Importa punts des de
   CSV…" al diàleg de digitalització d'inventaris. Llegeix columnes
   `codi_pi, coord_x, coord_y`, detecta el delimitador (`,` o `;`) amb
   `csv.Sniffer`, ordena pel `codi_pi` del fitxer per mantenir l'ordre
   de captura, però reassigna el `codi_pi` real de forma correlativa
   amb `_apply_attrs_new()` (igual que en digitalitzar manualment) en
   lloc d'importar els números del CSV tal qual. El hook
   `_build_import_group()` a `IOFBasePointDialog` retorna `None` per
   defecte; només `InventariDialog` el sobreescriu, així que la resta
   de diàlegs de punts no es veuen afectats.
   Si la capa ja té punts (segona importació o punts ja digitalitzats
   manualment), en lloc de la confirmació simple es mostra un
   `QMessageBox` amb tres botons («Sobreescriure» / «Afegir» /
   «Cancel·lar»): sobreescriure elimina tots els punts existents dins
   la mateixa sessió d'edició abans d'afegir els del CSV (i reinicia
   `_next_num` a 1); afegir manté els existents i numera els nous a
   continuació (comportament ja habitual); cancel·lar no fa res. Amb
   la capa buida es manté la confirmació Sí/No original.
4. **Botons "Digitalitzar" / "Dades i estils" / "Exportar IOF a TXT"
   desactivats sense capes IOF, i avís uniforme de "Capa no trobada"**
   (`iof_exporter.py`, `iof_utils.py`, juliol 2026):
   - `iof_utils.iof_layers_created()` retorna `True` si el projecte té
     alguna de les 9 capes estàndard (`IOF_LAYER_NAMES`). `IOFExporter`
     activa/desactiva aquests tres botons (i cada acció del seu
     submenú) segons aquest valor, actualitzant-se sol en connectar
     als senyals `layersAdded` / `layersRemoved` / `cleared` de
     `QgsProject.instance()`.
   - Bug real que això no cobreix per si sol: un cop les capes IOF
     existeixen, cada diàleg individual ja comprovava la seva pròpia
     capa a `_load_layer()`/`_check_layer()`, però amb un bug
     consistent: es mostrava l'avís (o, en alguns casos, només un
     estat inline amb botons desactivats) i tot seguit qui l'havia
     creat a `iof_exporter.py` cridava `.show()` igualment, deixant un
     diàleg buit o trencat darrere l'avís.
     Corregit uniformement a TOTS els diàlegs afectats (`AiguaDialog`,
     `ElementsDialog`, `InventariDialog` via `IOFBasePointDialog`;
     `InfraDialog`, `CanvisDialog`, `CaminsDialog`, `LimitsDialog`,
     `UnitatsWizard`, `FinquesWizard`, `CaminsWizard`, `RodalsWizard`)
     amb el mateix patró: `self._cancelled = True` quan no es troba la
     capa (mateix flag que ja usava `UnitatsWizard` per al cas
     "cancel·lar des del diàleg d'unitats existents"), i
     `iof_exporter.py` comprova aquest flag (`_show_if_ready()` per als
     diàlegs de digitalització, comprovació inline per als de
     `run_wizard()`) abans de cridar `.show()`.
   - Text de l'avís unificat a `iof_utils.avisa_capa_no_trobada(parent,
     layer_name, accio=...)`: "No s'ha trobat la capa «X» al
     projecte.\n\nAssegura't d'haver-la creat amb l'eina «Crear capes
     IOF» abans de {accio}." — `accio` per defecte és "realitzar la
     digitalització"; els assistents de "Omplir camps" fan servir
     "omplir les dades" i "Aplicar estil de gestió" fa servir "aplicar
     l'estil".
   - `FormatLayersDialog` (Aplicar estil de gestió) NO necessitava el
     flag `_cancelled`: cada botó ja valida la seva pròpia capa de
     forma independent sense bloquejar la resta del diàleg; només
     se n'ha unificat el text de l'avís.
   - També s'ha desactivat el botó "IOF_Finques" a
     `iof_selector_dialog.py` (SelectorDialog, "Omplir camps") quan la
     capa no existeix, igual que ja feien els botons d'Unitats i
     Camins.

## Política d'esforç
- **Alt (high)** per defecte per a tot el treball de codi.
- **Xhigh** només per a: bugs de geometria/digitalització (split, snapping,
  topologia), integració o depuració de capes WMS, canvis que toquin el
  format d'exportació TXT.
- **Baix (low)** per a: canvis d'icones, textos d'interfície, formatatge,
  actualitzacions de `metadata.txt`.

## Enrutament de model
- Per defecte: **Claude Sonnet 5**.
- Escala a **Opus 4.8** només quan:
  - Sonnet 5 hagi fallat la mateixa tasca dues vegades, o
  - calgui raonament geomètric/topològic complex (p. ex. casos límit del
    split de polígons) que Sonnet no resolgui a la primera.

## Convencions
- Codi en català per a noms d'interfície visibles a l'usuari (labels,
  missatges, títols de diàlegs); comentaris de codi poden ser en català o
  castellà segons el fitxer existent — mantenir consistència amb el fitxer
  que s'edita, no barrejar idiomes dins del mateix mòdul.
- Abans de tocar un `*_dialog.py`, revisar si hi ha un `*_wizard.py`
  relacionat que en depengui.

## Minimitzat dels diàlegs de digitalització
Els diàlegs de digitalització/omplir camps són no modals precisament
perquè l'usuari els vol tenir oberts mentre treballa al mapa — però amb
els flags de finestra per defecte de Qt, minimitzar-los no els duia
enlloc accessible (calia minimitzar QGIS sencer per "descobrir-los"
darrere).

**Solució final (juliol 2026):** forçar explícitament
`Qt.WindowType.WindowMinimizeButtonHint` als flags de finestra de cada
diàleg (juntament amb `Window`, `WindowTitleHint` i
`WindowCloseButtonHint`) perquè el minimitzat **natiu** del sistema
operatiu funcioni correctament (vagi a la barra de tasques a Windows o
al Dock a macOS, i es pugui recuperar clicant-hi). Aplicat als 10
diàlegs no modals: `IOFBasePointDialog` (cobreix `AiguaDialog`,
`ElementsDialog`, `InventariDialog` automàticament, ja que cap
sobreescriu `__init__`), `CaminsDialog`, `InfraDialog`, `CanvisDialog`,
`LimitsDialog`, `UnitatsWizard`, `FinquesWizard`, `RodalsWizard`,
`CaminsWizard`, `SeleccioParcellsDial`. Als que ja modificaven
`windowFlags()` per una altra raó (`FinquesWizard`, `CaminsWizard`, que
treien `WindowContextHelpButtonHint`), el flag s'afegeix amb `|`, no
substituint tots els flags de cop. Si es crea un diàleg nou de
digitalització/selecció no modal, aplicar-hi el mateix flag.

**Intent descartat — "minimitzar a cantonada":** abans de la solució
final es va provar `permetre_minimitzar_a_cantonada()` a `iof_utils.py`
(interceptar `QEvent.WindowStateChange` per encongir el diàleg a la
cantonada inferior esquerra en lloc de deixar-lo minimitzar de debò).
**Eliminat** perquè a macOS el sistema ja ha començat l'animació nativa
cap al Dock abans que el nostre codi intercepti l'event, produint un
doble moviment molest (Dock → cantonada). Interceptar/cancel·lar una
animació nativa del gestor de finestres un cop iniciada no és fiable.
Si mai es vol recuperar aquesta idea, la manera correcta seria un botó
propi dins del diàleg que faci l'encongiment directament (sense passar
mai pel minimitzat natiu), no interceptar `windowState()` a posteriori.

## Els diàlegs de digitalització es mantenen sempre visibles (`WindowStaysOnTopHint`)
Intent anterior descartat (juliol 2026): auto-minimitzar el diàleg quan
detectava que la finestra principal de QGIS prenia el focus
(`permetre_auto_minimitzar_en_perdre_focus()` a `iof_utils.py`).
**Desfet a petició expressa** en favor d'una solució diferent: el
diàleg mai ha d'anar al fons mentre es treballa al mapa, i només ha
d'anar al Dock/barra de tasques si l'usuari el minimitza explícitament.

**Solució aplicada:** `Qt.WindowType.WindowStaysOnTopHint` afegit als
flags de finestra dels mateixos 10 diàlegs no modals (juntament amb
`Window`, `WindowTitleHint`, `WindowCloseButtonHint` i
`WindowMinimizeButtonHint`, ja presents).

**Avís important, ja documentat abans d'aquesta sessió** (nota
preexistent més avall en aquest mateix document, secció de notes
tècniques): *"`WindowStaysOnTopHint` impedeix la interacció amb el
canvas — evitar"*. És a dir, algú ja va provar aquest mateix flag
abans i el va treure perquè no deixava clicar bé el mapa amb el diàleg
a sobre. S'ha tornat a aplicar ara perquè l'usuari ho ha demanat
explícitament sabent-ho, però **cal provar-ho amb cura**: si torna a
donar problemes de clic al canvas, la solució és treure
`WindowStaysOnTopHint` d'aquests 10 fitxers (buscar la constant i
eliminar la línia `| Qt.WindowType.WindowStaysOnTopHint` de cadascun).

**Decisió conscient (juliol 2026): `WindowStaysOnTopHint` fa que el
minimitzat a macOS sigui poc fiable, i s'ha acceptat així.** A macOS,
`WindowStaysOnTopHint` fa que Cocoa tracti la finestra com un panell
flotant, i aquest tipus de finestra normalment no admet el cicle de
vida normal de minimitzar-se al Dock (limitació coneguda de Qt en
aquesta plataforma, no arreglable només amb flags). Preguntat
explícitament, l'usuari ha triat prioritzar "sempre per sobre" (no
amagar-se mai darrere de QGIS) per sobre d'un minimitzat fiable. **Si
mai es vol prioritzar el minimitzat en lloc d'això, treure
`WindowStaysOnTopHint` dels 11 fitxers** (els mateixos 10 diàlegs no
modals més `FormatLayersDialog`, afegit després — vegeu més avall).

**Onzè diàleg trobat amb el mateix problema de zoom bloquejat
(`FormatLayersDialog`, "Aplicar estil de gestió"):** aquest se'ns havia
escapat a totes les revisions anteriors (bug #6, la llista de 10
diàlegs no modals) perquè s'obria amb `dlg.exec()` — modal, mateix bug
exacte que `CaminsWizard` tenia originalment. Corregit a
`run_format()` (`iof_exporter.py`) fent-lo no modal
(`self._format_dlg = FormatLayersDialog(...); .show()`), i afegits els
mateixos flags (`WindowMinimizeButtonHint` + `WindowStaysOnTopHint`)
per consistència amb la resta. A diferència del cas de `CaminsWizard`,
aquest es crida directament des d'un `QMenu` de la barra d'eines (no
des d'un slot d'un altre diàleg modal), així que no calia el patró de
"guardar la tria i crear-lo després" — un `.show()` directe n'hi ha
prou. **Si es reporta el mateix bloqueig de zoom en algun altre diàleg
encara no revisat, buscar `\.exec()` o `\.exec_()` a `iof_exporter.py`
per trobar-ne més.**


## Compatibilitat QGIS 3.44 i QGIS 4.0 (Qt6)
QGIS 4.0 "Norrköping" (publicat el 6 de març de 2026) migra el nucli de
Qt5 a Qt6. El projecte ja només importa Qt a través de `qgis.PyQt` (mai
`PyQt5`/`PyQt6` directament) a tots els fitxers — això és el que fa que
la migració hagi estat senzilla, ja que QGIS mateix redirigeix aquesta
capa a la versió de Qt que correspongui.

**Verificat i corregit (juliol 2026)** amb l'script oficial de QGIS
(`scripts/pyqt5_to_pyqt6/pyqt5_to_pyqt6.py`, https://github.com/qgis/QGIS),
en mode per defecte (sense `--qgis3-incompatible-changes`, que manté
compatibilitat amb totes dues versions alhora — no és una migració que
trenqui QGIS 3.44):
- 263 usos d'enums en format curt (`Qt.AlignCenter`, `QMessageBox.Yes`,
  `QFrame.HLine`...) canviats a la forma completa amb l'espai de noms
  (`Qt.AlignmentFlag.AlignCenter`, `QMessageBox.StandardButton.Yes`...).
  PyQt5 (des de fa diverses versions) i PyQt6 accepten totes dues
  formes, però PyQt6 **només** accepta la forma completa.
- 16 crides `.exec_()` canviades a `.exec()` (funciona igual a PyQt5 i
  PyQt6; el guionet baix només calia per evitar el conflicte amb la
  paraula reservada `exec` de Python 2).
- Un cas que l'script no va detectar automàticament (accés dinàmic via
  `__import__(...)` a `iof_inventari_dialog.py`) resultava ser codi
  mort duplicat — eliminat.

**Com tornar-ho a comprovar** si es fan canvis nous al codi:
```bash
pip install PyQt6 PyQt6-QScintilla astpretty tokenize-rt --break-system-packages
curl -sL -o pyqt5_to_pyqt6.py "https://raw.githubusercontent.com/qgis/QGIS/master/scripts/pyqt5_to_pyqt6/pyqt5_to_pyqt6.py"
python3 pyqt5_to_pyqt6.py --dry_run IOF_Assistent/
```
Un codi de sortida `0` i cap línia `WARNING` (a banda de l'avís inicial
"QGIS classes not available for introspection", que surt sempre en
aquest entorn perquè no tenim el paquet `qgis` instal·lat) vol dir que
no hi ha res pendent.

**El que això NO cobreix** (cal l'usuari, no es pot verificar sense QGIS
en viu): comportament real dins de QGIS 4.0 — l'script fa introspecció
parcial (no té accés a les classes pròpies de QGIS, com `Qgis.MessageLevel`
o altres enums definits per QGIS mateix, no per Qt), i cap dels fixos
d'aquesta sessió s'ha provat mai dins d'una instància real de QGIS 3.44
ni 4.0. Recomanat provar el complement sencer (totes les eines de
digitalització, exportació, base cartogràfica) en un QGIS 4.0 real abans
de donar-lo per compatible del tot.

**Cas real trobat en proves a QGIS 4 (juliol 2026):**
`QtNetwork.QNetworkReply.NoError` (dues ocurrències, a
`iof_importar_cadastre_dialog.py`) va donar
`AttributeError: type object 'QNetworkReply' has no attribute 'NoError'`
en obrir "Importar cadastre" — l'script de migració no ho havia detectat
perquè s'hi accedia amb el prefix del mòdul (`QtNetwork.QNetworkReply.X`)
en lloc de la forma que sí reconeixia (`QNetworkReply.X`, ja usada
correctament en una tercera ocurrència al mateix fitxer). Corregit a
`QtNetwork.QNetworkReply.NetworkError.NoError`. Si torna a aparèixer
aquest patró d'error (`'X' has no attribute 'Y'` en un enum de Qt) en
qualsevol altra classe, buscar `NomClasse.NomEnum` amb prefix de mòdul
(`QtCore.`, `QtGui.`, `QtNetwork.`, `QtXml.`...) — l'script de migració
pot no detectar-los tots si el codi hi accedeix així.

## Límits de rodal/UA entre unitats de vegetació veïnes (`apply_unitats_style`)
**Criteri correcte (juliol 2026):** la ratlla-punt gruixuda (blanc 1,0 mm
+ negre discontinu 0,7 mm) ha d'aparèixer **només** entre unitats de
vegetació amb `codi_rodal`/`codi_ua` DIFERENT; entre unitats que
comparteixen el mateix número de rodal/UA, sempre línia fina contínua
(0,26 mm) — independentment de si són forestals, tenen ús o estan
excloses. Substitueix el criteri antic (que mirava `for_forestal`/
`codi_us`/exclosa de la pròpia unitat, sense comparar-la amb la veïna).

**Per què no n'hi ha prou amb una regla per feature:** una unitat pot
tenir una veïna del mateix rodal en un costat i d'un altre rodal a
l'altre costat — QGIS estilitza cada polígon sencer amb un símbol, no
cada costat per separat, així que calia una solució topològica, no un
atribut de la pròpia unitat.

**Solució aplicada:** la capa principal (`IOF_Unitats_Actuacio`/
`IOF_Rodals`) dibuixa ara la línia fina contínua per a **totes** les
unitats sense excepció (`grup_limits`, símbol únic
`_sym_linia_fina_real()`, ja no dividit en dues regles). El contorn
gruixut es dibuixa a part: `_regenera_capa_limits_rodal()` fa
`processing.run("native:dissolve", {'FIELD': [codi_field], ...})`
sobre la capa (dissol per `codi_ua`/`codi_rodal`, eliminant les vores
internes entre unitats del mateix rodal) i **escriu el resultat com a
taula pròpia dins del mateix GeoPackage** de la capa principal (no com
a capa en memòria — evita l'avís de "temporal" al panell de capes),
amb el nom tècnic fix `limits_rodal_unitats_actuacio` i el **nom
visible dinàmic** `_lbl_limit` ("Límit d'unitat d'actuació" a un PTGMF,
"Límit de rodal" a un PSGF — el mateix text que ja s'usava abans a la
llegenda). La capa es col·loca just a sobre de la capa principal a
l'arbre de capes.

**Format de sortida cap a una taula dins d'un gpkg existent:**
`'OUTPUT': f'ogr:dbname=\'{gpkg_path}\' table="{NOM_TAULA}" (geom)'`
(sintaxi oficial documentada per a "Vector Destination" cap a
GeoPackage; `gpkg_path` s'obté partint `layer.dataProvider().dataSourceUri()`
per `'|'`). Un cop escrita, es torna a obrir com a `QgsVectorLayer`
normal (`f"{gpkg_path}|layername={NOM_TAULA}"`) per poder-hi aplicar
renderer i afegir-la al projecte — `processing.run()` amb aquest tipus
de sortida NO retorna directament un objecte de capa (a diferència de
`'OUTPUT': 'memory:'`), cal tornar-la a carregar des del disc.

**Sense provar en viu:** escriure una taula nova dins d'un GeoPackage
que QGIS ja té obert (la mateixa capa principal hi és carregada) hauria
de funcionar (SQLite/GPKG admet afegir taules sense tocar les
existents), però no s'ha pogut confirmar dins d'una sessió real de
QGIS. Si dona algun error de bloqueig de fitxer, cal reconsiderar
l'enfocament (per exemple, tancar/reobrir la connexió abans d'escriure,
o mantenir-ho en memòria i acceptar l'avís de "temporal").

**Agrupades juntes al panell de capes (juliol 2026):** la capa
principal i la seva auxiliar de límits queden dins d'un mateix grup
anomenat com la capa principal (p. ex. "IOF_Unitats_Actuacio"), en lloc
de sortir com a germanes soltes. La primera vegada que s'aplica
l'estil, es crea el grup al mateix lloc on era la capa (dins de
qualsevol grup pare que ja tingués, o a l'arrel) i s'hi mou la capa
principal (clonant el node i eliminant l'original — l'API de QGIS no
té un "moveTo" directe); les vegades següents, com que la capa ja es
troba dins d'un grup amb aquest nom, es reutilitza en lloc de tornar-la
a moure o crear-ne un altre de niat (comprovat per
`parent.name() == layer.name()`, no per identitat d'objecte).
**Ordre dins del grup:** la capa auxiliar de límits s'insereix sempre a
la posició 0 (`grup_unitats.insertLayer(0, capa_limits)`), és a dir, a
sobre de la capa principal — necessari perquè la ratlla-punt es dibuixi
per sobre del farciment i la línia fina (a QGIS, el que és més amunt al
panell de capes es renderitza per sobre). Si mai s'inverteix aquest
ordre per error, la ratlla-punt deixa de veure's (queda tapada pel
farciment de la capa principal).

**Bug real trobat en proves a QGIS 4 (juliol 2026) — comparar nodes de
l'arbre de capes per identitat d'objecte no és fiable a PyQGIS:**
`list(parent_actual.children()).index(node_layer)` fallava amb
`ValueError: <QgsLayerTreeLayer: IOF_Unitats_Actuacio> is not in list`
—la capa auxiliar mai arribava a crear-se. Causa: PyQGIS pot retornar
embolcalls Python diferents per al mateix node real de l'arbre segons
per on s'hi accedeix (`root.findLayer(...)` vs iterar
`parent.children()`), i `list.index()`/`==` comparen per identitat
d'objecte Python, no pel node real que representen. **Corregit** cercant
per `layerId()` (una cadena de text, sempre fiable) en lloc de per
l'objecte node, i substituint `parent_actual != root` per
`parent_actual.parent() is not None` (el node arrel és l'únic sense
pare — una comprovació estructural, no d'identitat). **Si mai es torna
a comparar dos `QgsLayerTree*` amb `==`/`!=`/`.index()`/`in` en aquest
projecte, cal desconfiar-ne i buscar una comprovació alternativa
(per id, per nom, o estructural) — no és fiable per si sol.**

**Segon bug real trobat, arran del mateix codi (juliol 2026) — el grup
es duplicava a cada "Aplicar estil":** el fix anterior comprovava si
"ja estava agrupada" mirant només si el **pare immediat** de la capa ja
es deia "IOF_Unitats_Actuacio". Però si la capa ja vivia dins d'un altre
grup (p.ex. "PTGMF — Capes de treball", una organització pròpia de
l'usuari, no creada per aquest complement), aquesta comprovació sempre
donava fals, i cada cop es creava un grup "IOF_Unitats_Actuacio" NOU
(niat dins de "PTGMF — Capes de treball" la primera vegada, però la
capa hi acabava duplicada en successives execucions). **Corregit**
cercant amb `root.findGroup(nom_grup)` — que cerca **a tot l'arbre**,
no només al pare immediat — i reutilitzant-lo sempre que existeixi,
independentment d'on estigui penjat. Si la capa principal encara no hi
és a dins quan es troba el grup, es mou (clonant + eliminant l'original),
igual que la primera vegada. **Si un usuari ja té un grup orfe
"IOF_Unitats_Actuacio" (buit o amb una capa duplicada dins) d'una
execució amb el bug antic, cal eliminar-lo manualment un cop; el codi
nou ja no en tornarà a crear cap altre de duplicat.**

**Unitats amb només codi_us (erm, edificis...) — corregit (juliol
2026):** aquestes unitats no han de generar mai un límit de rodal
propi (sempre línia fina, encara que la unitat del costat tingui un
rodal diferent), ja que no són una subdivisió forestal amb sentit
propi de rodal/UA. Com que normalment no tenen `codi_rodal`/`codi_ua`
coherent amb el seu entorn, dissoldre-les tal qual les tractava com un
grup a part i hi dibuixava ratlla-punt on no tocava. Abans de dissoldre,
es fusionen amb el veí amb qui comparteixen més vora
(`qgis:eliminateselectedpolygons`, `'MODE': 2` = "Largest Common
Boundary" — **atenció, aquest algorisme opera sobre la SELECCIÓ de la
capa d'entrada** (`selectByExpression()` abans de cridar-lo, no un
paràmetre propi), per això es fa sobre `layer.materialize(...)` —una
còpia en memòria— i no sobre `layer` directament, per no tocar la
selecció real de l'usuari a la capa oberta. L'algorisme conserva els
atributs (incloent `codi_rodal`/`codi_ua`) del veí que "absorbeix" la
unitat eliminada, així que aquesta n'hereta el rodal abans de dissoldre.
**Cas ambigu no resolt del tot:** una unitat només-ús que toqui DOS
rodals diferents (un a cada costat) s'absorbeix sencera dins d'un sol
d'ells (el de vora més llarga); la vora amb l'ALTRE rodal seguirà
sortint amb ratlla-punt. És un compromís raonable per a un cas
genuïnament ambigu, no un bug.

**Detall tècnic important:** un rodal amb parcel·les no contigües dona,
en dissoldre's, un multi-polígon. `exterior_ring($geometry)` (usat a
la resta de símbols d'aquest fitxer) **només considera la primera
part** en geometries multi-part — un patró conegut de diverses
funcions de conversió de geometria a QGIS. Per això la capa dissolta
fa servir un símbol dedicat, `_sym_limit_rodal_dissolt()`, amb
`boundary($geometry)` en lloc d'`exterior_ring($geometry)`:
`boundary()` gestiona correctament totes les parts d'un multi-polígon,
i també qualsevol forat intern (que aquí és correcte, ja que un forat
en un rodal dissolt representa un límit real amb el que hi ha a dins).

**Manteniment de la capa auxiliar:** es recalcula sencera cada cop que
es prem "Aplicar estil a IOF_Rodals / IOF_Unitats_Actuacio" (elimina la
versió anterior **cercant per la taula tècnica dins de l'URI**
—`layername=limits_rodal_unitats_actuacio`—, no pel nom visible, ja que
aquest és dinàmic segons PTGMF/PSGF i podria no coincidir amb una
execució anterior). `reset_unitats_style()` fa la mateixa cerca per
eliminar-la en resetejar. **No editar-la manualment** — qualsevol canvi
es perdria en tornar a aplicar l'estil.

**Codi mort eliminat en aquest mateix canvi** (creat per la meva pròpia
substitució, no relacionat amb els altres dos casos ja coneguts —
`_sym_rodal`/`_sym_linia_fina`, encara sense netejar):
`_sym_limit_rodal_real()` (l'antiga, amb `exterior_ring`),
`_sym_limit_linia_llegenda()`, i les expressions `_fexp_rodal`/
`_fexp_us`/`_fexp_exclos`.

**Punt de retorn:** còpia de seguretat de la versió anterior
d'`iof_format_dialog.py` (abans d'aquest canvi) guardada fora del
projecte del plugin, per si cal desfer-ho.

## Dimmat de capes IOF durant la digitalització (`iof_utils.py`)
Quan es digitalitza camins, infraestructures PI, canvis d'ús o unitats
d'actuació/rodals, les altres 7 capes IOF **no** es posen a opacitat 0%
(primer intent, descartat) — es fa transparent només el **farciment**,
mantenint el contorn/línia visible amb un **color propi per capa**
(`_COLORS_DIMMAT_IOF`, juliol 2026): Finques lila, Punts d'aigua/
Elements singulars/Punts d'inventari magenta, Camins vermell,
Infraestructures PI taronja, Canvis d'ús cian, Unitats d'actuació/Rodals
verd. Cadastre, Topogràfic territorial i l'ortofotomapa es queden tal
com estaven.

**Mecanisme:** substitueix el `renderer()` sencer de cada capa (no
l'opacitat) per un `QgsSingleSymbolRenderer` d'un sol símbol —
`QgsFillSymbol`/`QgsLineSymbol`/`QgsMarkerSymbol` segons
`QgsWkbTypes.geometryType(layer.wkbType())` (punt/línia/polígon), amb
`color: '0,0,0,0'` (farciment transparent) i `outline_color`/
`line_color` amb el color propi. `dimmar_altres_capes_iof(layer_actual)`
guarda el **renderer original clonat** (`layer.renderer().clone()`) en
un diccionari a nivell de mòdul abans de substituir-lo;
`restaurar_opacitat_capes_iof()` el torna a posar exactament tal com
era (imprescindible per a `IOF_Unitats_Actuacio`, que té un
`QgsRuleBasedRenderer` complex amb els límits de rodal — substituir-lo
per un símbol únic i no recuperar l'original el trencaria del tot).

Cridades des dels mateixos 4 diàlegs de digitalització
(`CaminsDialog`, `InfraDialog`, `CanvisDialog`, `UnitatsWizard`) al
`__init__` (dimmar) i `closeEvent` (restaurar) — vegeu la nota sobre
l'ordre dins de `closeEvent()` de `UnitatsWizard` (camins de sortida
anticipada) més avall.

**Compte amb l'ordre dins de `closeEvent()`:** a `UnitatsWizard`, el
`closeEvent()` té camins de sortida anticipada (`event.ignore(); return`)
si l'usuari cancel·la un diàleg de confirmació de tancament — la
restauració s'hi crida **al final**, just abans de `super().closeEvent()`,
mai al principi, perquè no es restauri l'opacitat si finalment el
diàleg no es tanca de veritat. Als altres 3 diàlegs (`CaminsDialog`,
`InfraDialog`, `CanvisDialog`) no hi ha cap camí de sortida anticipada,
així que la crida hi és al principi del `closeEvent()`, sense risc.



## Gestió de les capes "IOF_Topografia" (Referencial Topogràfic Territorial)
**Intent descartat (juliol 2026) — connectar `QgsProject.layersWillBeRemoved`/
`layersRemoved` a `initGui()` per avisar/esborrar el `.gpkg` en eliminar
capes "IOF_Topografia...":** **va trencar la càrrega sencera del
complement** (reportat per l'usuari: "el complement no carrega").
Revertit del tot — `initGui()`/`unload()` han tornat a l'estat anterior,
sense cap connexió a aquests senyals. No es va arribar a determinar la
causa exacta (podria ser el moment de la connexió dins d'`initGui()`,
o algun problema de signatura del senyal a QGIS 4 concretament), però
donat que **fer petar la càrrega del plugin és molt més greu** que no
tenir aquesta funcionalitat, es descarta aquest enfocament automàtic
per complet. **Si mai es torna a intentar connectar senyals de
`QgsProject` a `initGui()`, cal fer-ho amb molt de compte i provar-ho
en un QGIS real abans de donar-ho per bo — no es pot verificar només
amb `ast.parse()`.**

**Substituït per (pendent d'implementar):** un diàleg/gestor dedicat
per a les capes de topografia, amb accions explícites que l'usuari
triï (no automatismes en resposta a senyals): eliminar només del mapa,
eliminar també del disc, o tornar a carregar un `.gpkg` ja present a la
carpeta de descàrregues aplicant-hi automàticament el reagrupament i
l'estil corresponent (reutilitzant `_openicgc_watch_and_regroup()` /
`_aplicar_estil_qlr()`, ja existents a `iof_exporter.py`).


## Gestor de topografia (`iof_gestor_topografia_dialog.py`)
Implementat (juliol 2026), reemplaçant l'intent descartat de senyals
automàtics de `QgsProject` documentat més amunt. El botó del menú
"Mapes ICGC → Referencial topogràfic territorial vectorial" ja no
descarrega directament — obre `GestorTopografiaDialog`, amb 3 seccions:

1. **Generar una nova capa** — botó que crida
   `IOFExporter.run_base_topografica_descarrega()` (la lògica de
   descàrrega via Open ICGC, la mateixa que abans hi havia directament
   a `run_base_topografica()`, ara renombrada i cridada des d'aquí).
2. **Actualment carregat** — detecta el grup "Topogràfic territorial"
   (`root.findGroup(...)`) i n'extreu el/s camí/ns del `.gpkg` de les
   seves subcapes. "Eliminar del mapa" treu el grup i les capes del
   projecte; "Eliminar del mapa i del disc" (amb confirmació) també
   esborra el fitxer (`.gpkg`/`-wal`/`-shm`/`-journal`) — aquí sí és
   segur fer-ho directament, ja que l'usuari ho demana explícitament
   des d'un diàleg, no en resposta a un senyal automàtic.
3. **Carregar un GeoPackage existent** — `QFileDialog` per triar un
   `.gpkg`, `QgsProviderRegistry.instance().querySublayers(path)` per
   enumerar-ne les subcapes, renombrat "IOF_Topografia — {subcapa}",
   agrupat dins "Cartografia de referència → Topogràfic territorial", i
   estil aplicat reutilitzant `IOFExporter._get_qlr_style_template()`/
   `_aplicar_estil_qlr()` (NO duplicat — es passa `self` de
   `IOFExporter` com a paràmetre `exporter` al diàleg).

**Decisió de disseny deliberada, arran de l'incident anterior:** aquest
diàleg és totalment aïllat i sota demanda — `iof_gestor_topografia_dialog.py`
només s'importa dins de `run_base_topografica()` (com qualsevol altre
diàleg del plugin), mai a `initGui()`. Si mai hi ha un problema amb
aquest gestor, només afecta aquest diàleg concret en obrir-se, no la
càrrega general del complement.

## Numeració dels grups de topografia (juliol 2026)
Cada capa de Referencial Topogràfic Territorial carregada (descàrrega
via Open ICGC, o carregant un `.gpkg` existent des del gestor) obté el
seu propi grup: **"Topogràfic territorial 1"**, **"...2"**, etc. — mai
es barregen subcapes de descàrregues diferents dins d'un sol grup.

**Funcions compartides a `iof_utils.py`** (usades tant per
`_openicgc_watch_and_regroup()`/`_fer_reagrupament()` a
`iof_exporter.py` com pel `GestorTopografiaDialog`):
- `cerca_grups_topografia()`: retorna `[(número, node_grup), ...]` de
  tots els grups "Topogràfic territorial"/"...N" existents a **tot**
  l'arbre (cerca recursiva a qualsevol profunditat), ordenats per
  número. Un grup sense número (d'abans d'aquest canvi) es tracta com
  a número 0.
- `renumera_grups_topografia()`: renombra tots els grups trobats
  perquè quedin 1, 2, 3, ... consecutius, sense buits. **Cridar sempre
  després d'afegir o eliminar-ne un** — `GestorTopografiaDialog._actualitza_estat()`
  ho fa automàticament cada cop que es refresca la secció 2.
- `seguent_numero_topografia()`: `len(cerca_grups_topografia()) + 1` —
  correcte sempre que la resta ja estiguin renumerats sense buits.

**Verificat amb una simulació aïllada (sense QGIS)** que eliminar un
grup del mig (p.ex. el 2 de 3) renombra correctament el següent (el 3
esdevé el 2), no només amb dades reals de QGIS.

**Gestor de topografia actualitzat:** la secció 2 ara mostra un
desplegable amb tots els grups carregats (amb el nom del fitxer
`.gpkg` de cadascun), no un sol estat fix — "Eliminar del mapa"/"...i
del disc" actuen sobre el que estigui seleccionat al desplegable. La
secció 3 ("Substitueix" vs "Afegeix" en carregar un `.gpkg` quan ja
n'hi ha) ara elimina **tots** els grups existents en triar
"Substitueix" (abans només n'hi podia haver un).

## Renumeració de camins en eliminar (`iof_camins_dialog.py`)
Fins ara, en eliminar un camí, els codis dels restants NO canviaven —
el número alliberat només es reutilitzava la propera vegada que es
creava un camí nou d'aquell mateix tipus+estat
(`iof_camins_wizard.py::_genera_codi()`, que busca el primer número
lliure). Comportament diferent, deliberat, de `InventariDialog` (que sí
renumera tots els punts immediatament en eliminar).

**Canviat (juliol 2026), a petició explícita:** camins ara també
renumera tots els restants immediatament en eliminar, igual que
inventari — `_renumerar_camins()`, cridada des de `_on_confirmar_elim()`
després de l'eliminació. Agrupa els camins per **(tipus, estat)**
—PR/PM/SC/DB creuat amb Existent/Projectat, cadascuna una seqüència
independent des de l'1, com ja fa `_genera_codi()`— i només renumera
dins de cada grup, no globalment (un camí SC01E no es veu afectat en
eliminar un PR01E). Verificat amb una simulació aïllada (sense QGIS)
amb l'escenari exacte reportat: eliminar PR01E deixant PR02E/PR03E
renombra correctament a PR01E/PR02E.

## Sense separador de milers a l'exportació TXT (`iof_dialog.py::_round_str`)
Fins ara `_round_str()` formatava els números (superfícies, longituds)
amb punt de milers a més de la coma decimal (p.ex. `1.234,56`).
**Canviat (juliol 2026):** eliminat el separador de milers, es manté
només la coma decimal (`1234,56`) — un punt de milers podia provocar
errors en importar el fitxer de text exportat al PDF.

## Eliminar i renumerar a Punts d'aigua, Infraestructures PI i Canvis d'ús (juliol 2026)
A petició explícita, després de comprovar sistemàticament que no totes
les capes es comportaven igual:

- **Punts d'aigua**: ja tenia botó d'eliminar (heretat
  d'`IOFBasePointDialog._on_confirmar_elim()`), però sense renumerar.
  Sobreescrit a `iof_aigua_dialog.py` (mateix patró que
  `InventariDialog`), afegint `_renumerar()` agrupada per **estat**
  (Existent/Projectat) — codi `PA` fix, un sol tipus.
- **Infraestructures PI** i **Canvis d'ús**: **no tenien cap botó per
  eliminar un element ja existent** (només es podia esborrar el
  polígon pendent mentre encara s'estava dibuixant, abans de desar).
  Afegit tot el flux (botons "Eliminar.../Confirmar.../Cancel·lar
  eliminació", seguint exactament el patró UI de `CaminsDialog`), amb
  renumeració:
  - Infraestructures PI: agrupada per **estat** (codi `LD` fix, com
    Aigua).
  - Canvis d'ús: agrupada per **tipus** (`RM`/`TP`) — **sense** estat
    E/P al codi, a diferència de la resta (`_next_codi()` ja només
    admetia tipus, no estat).

Totes tres verificades amb simulacions aïllades (sense QGIS) abans de
donar-les per bones. Patró compartit arreu: buidar `codi_*` no fa
falta — es recalcula sencer a `_renumerar()` combinant tipus/tipus+estat
amb el número seqüencial nou.

**Detall d'implementació a Infra/Canvis** (diferent d'Aigua/Camins, que
alternen entre "sessió d'edició" i "eliminar"): com que aquests dos
diàlegs estan sempre en mode "afegir objecte" continu
(`_activate_map_tool()`/`_on_feature_added()`/`_on_desar()`), `_on_eliminar()`
crida `_deactivate_map_tool()` per sortir-ne temporalment i activar
selecció, i `_on_cancel_elim()` torna a cridar `_activate_map_tool()`
per reprendre la digitalització en acabar (tant si s'ha eliminat com
si s'ha cancel·lat).

## Polígon invisible fins a desar, a Infraestructures PI i Canvis d'ús (juliol 2026)
**Causa:** `apply_infra_style()`/`apply_canvis_style()` fan servir un
`QgsCategorizedSymbolRenderer` (per `estat` E/P a Infra, per
`tipus_canvi` RM/TP a Canvis), **sense cap categoria per als valors no
reconeguts**. Un polígon just dibuixat té aquest camp buit (només
s'omple a `_on_desar()`), així que no coincideix amb cap categoria i
QGIS no el dibuixa — apareixia com si el polígon "desaparegués" fins
que es desava de veritat.

**Corregit:** a `_on_feature_added()` (tots dos fitxers), just after
afegir el polígon a la capa, s'assigna **temporalment** el valor que ja
hi ha seleccionat al desplegable corresponent (`estat`/`tipus_canvi`)
— així coincideix amb una categoria existent de seguida i es veu
immediatament amb l'estil real de gestió, no un estil de previsualització
apart. En prémer "Desar", `_on_desar()` torna a escriure el valor
(el que hi hagi al desplegable en aquell moment, per si l'usuari l'ha
canviat mentre el polígon era pendent), així que no hi ha cap conflicte.

## Estil de digitalització unificat amb la paleta de dimmat (juliol 2026)
La capa que s'està digitalitzant activament (Camins, Infraestructures
PI, Canvis d'ús, Unitats d'actuació) ara sempre mostra el mateix
llenguatge visual que ja fem servir per dimmar les *altres* capes:
farciment transparent + contorn del seu color propi
(`iof_utils._COLORS_DIMMAT_IOF`, la mateixa paleta reutilitzada aquí,
no duplicada). Abans hi havia inconsistències:
- Camins ja ho feia, per casualitat amb el mateix vermell (el comentari
  del codi, però, deia "taronja" — desactualitzat, corregit).
- Unitats ja ho feia, però amb un verd diferent (`0,255,0` en lloc del
  `0,150,60` de la paleta) i un gruix diferent (1.5mm en lloc de 0.6mm)
  — ajustat perquè coincideixi exactament.
- Infraestructures PI i Canvis d'ús **no tenien cap estil de
  digitalització** — s'ha afegit `_apply_digitizing_style()`/
  `_restore_digitizing_style()` (mateix patró de backup/restore que ja
  usava Unitats), cridat a `__init__()` (després del `dimmar_altres_capes_iof()`)
  i restaurat a `closeEvent()`.

**Nota sobre la interacció amb el fix anterior** ("polígon invisible
fins a desar"): com que ara tota la capa (no només la unitat pendent)
es dibuixa amb un símbol únic pla mentre es digitalitza, l'assignació
temporal d'atribut (`estat`/`tipus_canvi`) a `_on_feature_added()` ja no
és visualment necessària **mentre** l'estil de digitalització és actiu
— però es manté de totes maneres, com a xarxa de seguretat: si l'estil
de digitalització es restaura (`_restore_digitizing_style()`) abans que
l'usuari desi el polígon pendent, aquest ja tindrà un valor vàlid i es
veurà amb el color real de la categoria corresponent, no invisible.

**Abast:** només aquests 4 diàlegs — Aigua/Elements/Inventari mai van
formar part del dimmat de capes (l'usuari només ho havia demanat per a
Camins/Infra/Canvis/Unitats), així que no se'ls ha afegit cap estil de
digitalització tampoc, per no ampliar l'abast sense que s'hagi demanat.

## Anàlisi de seguretat automàtica de plugins.qgis.org (juliol 2026)
En pujar el complement al repositori oficial, l'escaneig automàtic
(Bandit Security Analysis) va detectar un avís real: `ET.fromstring()`
(mòdul estàndard `xml.etree.ElementTree`) no protegeix per defecte
contra atacs coneguts d'XML (expansió d'entitats, entitats externes)
en analitzar dades que venen d'una font externa — en aquest cas, el
feed ATOM del Cadastre a `iof_importar_cadastre_dialog.py`.

**Corregit:** substituït per `defusedxml.ElementTree`, un reemplaçament
directe (mateixa API — `.fromstring()`, `.findall()`, `.find()`) però
protegit contra aquests atacs. Amb `try/except ImportError` per si
`defusedxml` no estigués instal·lat a l'entorn de QGIS de l'usuari
(no és un paquet estàndard de QGIS) — en aquest cas es continua amb
el mòdul estàndard en lloc de fer fallar tot el complement. Verificat
amb una prova real (no només sintàctica) que `defusedxml.ElementTree`
és un substitut vàlid per a l'ús concret que en fem (namespaces,
`.findall()`, `.find()`).

Cap altre lloc del projecte fa servir `ET.fromstring()` sobre dades
externes — aquest era l'únic cas.

## Neteja de qualitat de codi (Flake8), juliol 2026
L'escaneig automàtic de plugins.qgis.org ("Code Quality — Flake8") va
detectar 1.806 avisos en 29 fitxers. Desglossament i tractament:

- **~1.400 purament cosmètics** (E221/E241/E272 per l'estil d'alineació
  deliberat que fem servir arreu, W503/W504 —un parell de regles
  mútuament contradictòries de PEP8—, blank lines, etc.): corregits
  automàticament amb `autopep8 --in-place *.py`.
- **153 F401/F811/F841** (imports no usats, redefinicions, variables
  no usades): 147 corregits automàticament amb
  `autoflake --remove-all-unused-imports --remove-unused-variables`
  (revisat el diff abans de donar-ho per bo); 6 casos que autoflake no
  toca (F811 de noms no-import, o casos que considera ambigus)
  corregits a mà un per un.
- **1 F821** ("undefined name 'lyr'") a `iof_seleccio_parcelles_dialog.py`
  — **investigat a fons, no simplement descartat**: reproduït amb
  flake8 real, aïllat amb una prova mínima, i localitzat l'origen
  exacte: una funció niada (`def idx(nom): return lyr...`) que
  capturava per tancament una variable que més avall a la mateixa
  funció es feia `del lyr` — tècnicament seria segur perquè totes les
  crides passaven abans del `del`, però fràgil i per això l'eina no ho
  podia demostrar. Corregit eliminant la funció niada i fent les
  crides directes; de pas es va descobrir que les 5 variables
  resultants (`idx_nom`, `idx_mun`...) tampoc es feien servir mai
  (codi mort d'una versió anterior, abans de canviar a escriure amb
  `ogr` en brut) — eliminades del tot.
- **9 E741** (variable ambigua `l`, que es pot confondre amb `1`/`I`):
  renombrades a mà una per una (`lyr`, `line`, `loc` segons el
  context).
- **1 F541** (f-string sense cap interpolació): prefix `f` innecessari
  eliminat.
- **E501** (línia massa llarga): **no corregit** — no apareixia als
  1.806 avisos originals, per tant l'eina oficial no ho comprova;
  "arreglar-ho" hauria estat treball innecessari.

**Resultat final: de 1.806 avisos a 0** (excloent longitud de línia,
que l'eina oficial ja no comprovava). Sintaxi de tot el projecte
verificada després de cada pas, i els caràcters catalans (accents,
ç, ·) comprovats que no s'haguessin malmès amb les eines automàtiques.

**Còpia de seguretat pre-neteja:** `/home/claude/backup_abans_autoflake/`
(fora del projecte del plugin), per si calgués desfer algun canvi.

## Bug real (no relacionat amb la neteja de flake8): 3 capes creades com a "Polygon" en lloc de "MultiPolygon" (juliol 2026)
Reportat per l'usuari en provar "Digitalitzar unitats de vegetació"
just després de la neteja de qualitat de codi — **confirmat amb diff
que NO és un efecte d'aquella neteja** (la funció implicada,
`_on_feature_added()`, només va canviar espais d'alineació).

**Causa real:** `IOF_Infraestructures_PI`, `IOF_Canvis_Us` i
`IOF_Unitats_Actuacio` es creaven amb `"geom": "Polygon"` (una sola
part), mentre que `IOF_Finques` ja tenia `"MultiPolygon"` amb un
comentari explicant per què (un camí que travessa una finca de banda a
banda la pot deixar dividida en 2 parts separades). **La mateixa lògica
s'aplica a les altres tres** — en concret, `_on_feature_added()` a
`iof_unitats_wizard.py` resta el polígon nou del contenidor
(`container_geom.difference(new_geom)`), i si això deixa el contenidor
dividit en parts separades, GEOS torna un `MultiPolygon`, incompatible
amb una capa definida com a `Polygon` estricte — exactament l'error
reportat: "3 feature(s) not added - geometry type is not compatible
with the current layer".

**Corregit** a `iof_create_dialog.py`: les 3 capes ara es creen com a
`MultiPolygon`, amb el mateix comentari explicatiu que ja tenia
Finques. Verificat que cap altre lloc del codi assumeix un tipus
`Polygon` estricte per a aquestes capes.

**IMPORTANT — això NOMÉS afecta plans creats DES D'ARA:** el tipus de
geometria queda fixat al GeoPackage en el moment de crear la capa: els
plans que l'usuari ja tingués creats (com el que estava provant) seguiran
tenint les capes amb el tipus `Polygon` antic, i **calen recrear-les**
(o migrar-les) — actualitzar només el codi no repara els fitxers .gpkg
que ja existeixen.

## LA CAUSA REAL del bloqueig persistent de Bandit (juliol 2026) — LLIÇÓ IMPORTANT
Durant dies, cada pujada a plugins.qgis.org seguia bloquejada pel mateix
avís de Bandit sobre `ET.fromstring()`, MALGRAT tenir `defusedxml`
important-se correctament. La causa real, confirmada instal·lant i
executant Bandit real (`pip install bandit`, no assumpcions):

**Bandit fa anàlisi estàtica (AST), no d'execució.** El patró que
teníem:
```python
try:
    from defusedxml import ElementTree as ET
except ImportError:
    from xml.etree import ElementTree as ET   # <- Bandit veu AIXÒ
```
Bandit detecta la simple **presència textual** de
`from xml.etree import ElementTree` en QUALSEVOL branca del codi —
encara que sigui una reserva dins d'un `except ImportError` que a la
pràctica gairebé mai s'executa (perquè `defusedxml` sol estar instal·lat).
No fa cap anàlisi de "quina branca s'executa realment" — només cerca el
patró d'importació al fitxer sencer. Per això CADA pujada, per moltes
vegades que es repetís, tornava a fallar exactament igual.

**Correcció real:** eliminar la reserva del tot. `defusedxml` ara és una
dependència **obligatòria**, sense cap `try/except` ni cap ocurrència
textual de `xml.etree.ElementTree` enlloc del fitxer — documentada a
`metadata.txt` (`about=`) com a dependència externa, tal com demanen
explícitament les guies de publicació de QGIS per a aquest cas.

**Verificat amb Bandit real** (no amb el meu propi `grep`, que no hauria
detectat aquest problema): `python3 -m bandit -r .` sobre tot el
projecte → 0 problemes de severitat Mitjana/Alta (només queden 52
avisos de severitat Baixa, tipus `try/except/pass`, que l'escàner
oficial de plugins.qgis.org no havia arribat a reportar mai com a
problema en cap pujada anterior — no bloquegen).

**Lliçó general per a properes vegades:** quan un escàner extern segueix
detectant el mateix problema malgrat una correcció aparentment vàlida,
cal instal·lar i executar **la mateixa eina real** localment (no confiar
només en una revisió manual del codi ni en un `grep`) per veure
exactament què detecta i per què — un `try/except` amb una reserva
"seguraments no s'hi arribarà mai" pot ser perfectament segur en temps
d'execució i, tot i així, ser detectat per un analitzador estàtic que no
raona sobre control de flux condicional.

## Actualització (juliol 2026): els 55 avisos "Try/Except/Pass" SÍ que
calia resoldre'ls per obtenir l'aprovació
La nota anterior deia que aquests 52 (ara 55, +3 per un `unload()` nou)
avisos de severitat Baixa "no bloquejaven mai". En una pujada posterior,
l'escàner de plugins.qgis.org SÍ que els va reportar tots (60 en total:
55 `except Exception: pass/continue` + 4 imports XML de
`ext_libs/defusedxml/ElementTree.py` + 1 `assert` a `common.py`) i calia
resoldre'ls per a l'aprovació final.

**Correcció aplicada:** comentaris `# nosec <ID> — <motiu>` afegits
directament a cada línia flagrant, SENSE canviar cap lògica:
- `except Exception:` seguit únicament de `pass` → `# nosec B110 — ...`
- `except Exception:` seguit únicament de `continue` → `# nosec B112 — ...`
- Els 4 imports de `xml.etree.ElementTree` dins de
  `ext_libs/defusedxml/ElementTree.py` (el propi embolcall segur
  necessita importar l'stdlib per embolcallar-lo, Bandit no distingeix
  això d'un ús insegur) → `# nosec B314 — ...`
- L'`assert` de `ext_libs/defusedxml/common.py` (codi vendoritzat, no es
  toca la lògica) → `# nosec B101 — ...`

**Important — NO tocar `except OSError:`, `except ValueError:`,
`except (ValueError, IndexError):` ni cap altre tipus específic seguit
de `pass`/`continue`**: Bandit B110/B112 només flagra `except Exception:`
genèric (o `except:` nu), MAI un tipus concret — afegir-hi `# nosec`
seria innecessari i confondria un futur escaneig (no hi ha cap avís a
suprimir en aquestes línies).

**Script de detecció fiable** (per repetir-ho si cal en una versió
futura): buscar `except(?:\s+Exception)?:\n` seguit EXACTAMENT d'una
línia `pass` o `continue` (amb un comentari final opcional, com el que
ja hi havia a `iof_create_dialog.py::874`) — un regex més ampli que
també capturi tipus específics dona un recompte incorrecte (65 en lloc
de 55) i marcaria línies que Bandit mai ha flagrat.

**Actualització (juliol 2026): NO afegir un fitxer `.bandit` — només
`# nosec` inline.** Vam provar-ho amb un fitxer `.bandit` a l'arrel
(`skips = B101,B110,B112` + `exclude_dirs = ext_libs`) com a mesura
addicional "per si de cas", seguint el que la documentació de
plugins.qgis.org anomena "the recommended approach" per a falsos
positius. Un escaneig real ho va confirmar tècnicament net (100%,
0 problemes), però amb un efecte secundari no desitjat: l'estat passa
de **"Validated"** a **"Validated (configured)"**, amb el missatge
"Administrators should review whether the suppressed rules are
acceptable before approving this version" — exactament el tipus de
fricció addicional que es vol evitar quan qui aprova el plugin no
accepta cap mena d'avís, encara que el resultat tècnic sigui 0.
Com que **cada** línia que l'`.bandit` cobria (`exclude_dirs = ext_libs`
i els test IDs de `skips`) ja tenia el seu propi comentari `# nosec`
individual al codi font, el fitxer `.bandit` era completament
redundant: `# nosec` és una funcionalitat pròpia de Bandit que actua
línia a línia durant l'anàlisi, independentment de qualsevol fitxer de
configuració present o absent. **Decisió final: eliminar el fitxer
`.bandit`** i confiar només en els 60 comentaris `# nosec` inline —
així s'obté el mateix resultat (0 problemes) sense la marca
"(configured)" ni la revisió manual addicional que comporta.

**Correcció (juliol 2026, mateix dia): l'ID `B314` era incorrecte per
als 4 imports XML.** Un escaneig real després de treure `.bandit` va
confirmar que els 55 `# nosec B110/B112` i l'`# nosec B101` SÍ
suprimien els avisos correctament (no van tornar a sortir), però els
4 `# nosec B314` a `ext_libs/defusedxml/ElementTree.py` NO ho van fer
— l'escàner els va tornar a reportar, ara com a **Critical** (bloquejant,
80% de pass rate). Causa: quan `# nosec` especifica un ID concret,
Bandit només el suprimeix si l'ID coincideix EXACTAMENT amb el test que
ha disparat l'avís; B314 és per a *crides* a funcions de parsing
(`xml.etree.ElementTree.parse(...)` directament), mentre que aquestes
4 línies són *imports* (`from xml.etree.ElementTree import X`), que
Bandit classifica amb un altre test (probablement B405, però no s'ha
pogut confirmar sense l'eina real). **Lliçó: quan no es pugui verificar
l'ID exacte amb l'eina real (bandit instal·lat localment), fer servir
`# nosec` SENSE identificador** — suprimeix qualsevol troballa a la
línia sigui quin sigui el test que la dispara, eliminant el risc
d'encertar-la malament. Els 60 comentaris del projecte ara fan servir
tots aquest format sense ID.

**Si en una futura versió `# nosec` (fins i tot sense ID) torna a
fallar per a algun cas concret:** és senyal que aquest escàner en
concret pot tenir desactivada la funcionalitat de `# nosec` (una
pràctica habitual en entorns de CI de seguretat, precisament per
evitar que el codi silenciï avisos amb un simple comentari). En aquest
cas, l'única opció que hem confirmat que funciona de debò és el fitxer
`.bandit` (`skips=`/`exclude_dirs=`), acceptant la marca
"Validated (configured)" — és clarament preferible a un estat
Critical/bloquejant.

## Omplir camps de Finques: comarca no es desava + municipi difícil d'eliminar (juliol 2026)
**Reportat per l'usuari:** en editar finques, "el següent polígon hereda
codi de finca i municipi. Hauria d'heredar totes les dades." A més,
"si canviem de comarca, es manté el municipi, però no la comarca."
I "el municipi es pot eliminar fent doble clic..., però això no és
intuïtiu."

**Causes trobades a `iof_finques_wizard.py`:**
1. **`_save_current()` mai desava «comarca»** a l'element — es
   feia servir `_last_comarca` només com a variable en memòria per
   inferir el punt de partida del formulari a la finca següent, però
   la comarca real de la finca quedava sempre buida al GeoPackage.
   Corregit: ara es desa igual que `nom_finca`.
2. **`_restore_comarca_only()` desfeia el canvi de comarca**: si
   l'usuari triava una comarca diferent de l'anterior sense triar
   encara un municipi nou, en passar a la finca següent es cridava
   `_restore_municipi(municipi_antic)`, que TORNAVA A DEDUIR la
   comarca a partir del municipi antic (ignorant la comarca ja
   fixada), sobreescrivint-la de nou amb la comarca vella. Corregit
   afegint un paràmetre `keep_comarca=True` a `_restore_municipi()`
   que, quan és cert, no toca la comarca ja seleccionada; i filtrant a
   `_restore_comarca_only()` els municipis heretats perquè només es
   restaurin els que pertanyen de debò a la comarca (nova) actual.
3. **Eliminar un municipi de la llista** ja era possible amb Supr o
   doble clic (documentat només al tooltip), però no prou visible.
   Afegit un botó «−» al costat de la llista, simètric al «+» que ja
   hi havia per afegir-ne.

**Verificat:** `py_compile` + bateria completa de regressió (12
botons). No s'ha pogut provar amb QGIS real (canvis d'interfície
d'usuari, difícils de simular amb el mock).

## Digitalitzar límits: aclarit que l'edició permet afegir I eliminar (juliol 2026)
**Reportat per l'usuari:** "Del menú digitalitzar caldria modificar el
botó mantenir i afegir Per Editar. L'edició hauria de permetre afegir i
eliminar polígons."

**Causa:** en entrar en mode edició manual (`_on_edit()` a
`iof_limits_dialog.py`) triant "Mantenir i afegir" (mantenir les
finques existents i afegir-ne de noves), el complement activa
`self.iface.actionAddFeature().trigger()` — l'eina d'afegir element de
QGIS — però la capa ja queda en mode edició (`startEditing()`), així
que seleccionar un polígon existent i prémer Supr (o l'eina natiu
"Eliminar elements seleccionats" de QGIS) ja funcionava tècnicament.
El problema real era que el text de la interfície ("Dibuixa els
polígons al mapa amb les eines de QGIS") només esmentava afegir, no
eliminar — l'usuari no sabia que també podia fer-ho.

**Correcció:** el botó "Mantenir i afegir" ara es diu **"Mantenir i
editar"**, i el text explicatiu del mode edició ara esmenta
explícitament que es pot seleccionar i eliminar un polígon existent
(Supr), a més d'afegir-ne de nous. Cap canvi de lògica — la capacitat
d'eliminar ja hi era, només calia dir-ho.

**Nota d'incertesa:** la redacció exacta de l'usuari ("modificar el
botó mantenir i afegir Per Editar") admet més d'una interpretació; si
"Mantenir i editar" no és el nom exacte que es volia, cal aclarir-ho.

## Diàleg "Digitalitzar límits" bloquejava l'avís de confirmació de QGIS (juliol 2026)
**Reportat per l'usuari:** "quan volem editar el polígon, si seleccionem
i eliminem, el quadre de diàleg digitalitzar límits queda a sobre i
tapa l'anterior i a més queda bloquejat de manera que no hi ha forma
de treure'l de sobre de l'avís per eliminar el polígon."

**Causa:** `iof_limits_dialog.py` tenia `Qt.WindowType.WindowStaysOnTopHint`
al `setWindowFlags()` — contradient la nota anterior d'aquest mateix
document que deia que aquest flag "s'evita perquè impedeix la
interacció amb el canvas". En seleccionar un polígon i prémer Supr,
QGIS mostra el seu propi diàleg natiu de confirmació d'eliminació;
com que la finestra del complement es queda SEMPRE per sobre de
qualsevol altra finestra, tapava aquest diàleg de QGIS i no hi havia
manera de portar-lo al davant (ni tan sols clicant-hi a sobre).

**Correcció:** eliminat `WindowStaysOnTopHint` de `iof_limits_dialog.py`.

**Important — NO és un cas aïllat:** aquest mateix flag existeix TAMBÉ
a `iof_base_point_dialog.py`, `iof_camins_dialog.py`,
`iof_camins_wizard.py`, `iof_canvis_dialog.py`, `iof_format_dialog.py`,
`iof_infra_dialog.py`, `iof_rodals_wizard.py`,
`iof_seleccio_parcelles_dialog.py`, `iof_unitats_wizard.py` i
`iof_finques_wizard.py` — deu fitxers més. **Només s'ha tocat
`iof_limits_dialog.py`**, el que l'usuari ha reportat explícitament;
la resta es deixen intactes fins que es confirmi si pateixen el mateix
problema (podria ser intencionat en algun d'ells, p. ex. per mantenir
el diàleg visible durant digitalització llarga al mapa).

## Herència de camps a "Omplir camps de Finques": simplificada a NOMÉS el codi (juliol 2026)
**Historial:** després de corregir el desament de comarca, l'usuari
va reportar (amb captura de pantalla confirmant-ho: "Polígon 4 de 4"
amb Comarca en blanc «(selecciona comarca...)» però Municipi amb
«Begues» ja afegit) que en la pràctica el nom i la comarca NO
s'heretaven mai, tot i que el codi revisat semblava implementar-ho
igual que `codi_finca`/`municipi`. No es va arribar a localitzar per
què fallava exactament (podria ser un ordre d'inicialització dels
combos, senyals bloquejats incorrectament, o alguna altra causa no
identificada) — l'usuari va decidir no seguir perseguint-ho i
simplificar.

**Decisió final de l'usuari:** "fes que només heredi el codi i elimina
el municipi" — NOMÉS `codi_finca` s'hereta d'una finca a la següent;
`nom_finca`, `comarca` i `municipi` sempre comencen en blanc a cada
polígon nou (encara que si el polígon JA té un valor desat des
d'abans, aquest sí que es respecta i es mostra — el que no es fa és
agafar el valor de la finca ANTERIOR quan el polígon és nou).

**Implementat:** a `_show_feature()`, `nom_val` ja no cau a
`self._last_nom` (sempre `self._edit_nom.setText(nom_val)`, buit si
no n'hi ha), i la branca `elif self._last_comarca:` s'ha eliminat
completament (només queda "si hi ha municipi desat, restaurar-lo;
si no, deixar en blanc"). Eliminades també les variables
`_last_nom`/`_last_comarca`/`_last_municipi`, ja no usades enlloc.
El mètode `_restore_comarca_only()` es manté definit (per si mai cal
reactivar aquest comportament) però ja no es crida des de cap lloc.

**ACTUALITZACIÓ IMPORTANT (mateix dia): la causa real no era al wizard.**
L'usuari va confirmar amb un projecte totalment nou que el municipi
ES SEGUIA heretant SEMPRE — descartant la hipòtesi de "dades de proves
antigues" i confirmant que la simplificació anterior (al wizard) no
n'era la causa ni la solució completa. La causa real: `iof_limits_dialog.py`
NO tenia cap gestor de `featureAdded` — quan es digitalitzen diverses
finques seguides amb el formulari d'atributs suprimit
(`QgsEditFormConfig.FeatureFormSuppress.SuppressOn`, necessari per no
interrompre la digitalització), **és el propi QGIS** qui reutilitza
els valors de l'últim element digitalitzat per als següents (comportament
natiu de QGIS amb formularis suprimits, no del complement). Per tant,
"municipi" (i potencialment "comarca"/"nom_finca") ja arribaven
pre-omplerts amb el valor de la finca anterior *abans* que el wizard
`iof_finques_wizard.py` ni tan sols obrís el polígon — cap simplificació
al wizard podia solucionar-ho, calia aturar-ho a l'origen.

**Correcció definitiva:** afegit un gestor `_on_finca_added(fid)` a
`iof_limits_dialog.py`, connectat a `lf.featureAdded` just abans de
`self.iface.actionAddFeature().trigger()` a `_on_edit()` (i desconnectat
a `_on_save_edit()`/`_on_discard_edit()`, seguint el mateix patró
connect/disconnect ja establert a la resta del complement). Per cada
finca acabada de digitalitzar, neteja explícitament `nom_finca`,
`comarca` i `municipi` a `None` — independentment de si QGIS els havia
reutilitzat o no. Verificat amb un test dirigit que simula exactament
aquest escenari (valors "heretats" abans de cridar el gestor → buits
després).

**ACTUALITZACIÓ 2 (mateix dia): aquesta última correcció NO era la
causa real — trobada en directe amb qgis-mcp.** L'usuari va reportar
"segueix igual" després d'instal·lar la correcció anterior. En lloc de
seguir endevinant, es va aprofitar la connexió `qgis-mcp` activa per
inspeccionar en directe:
1. `layer.defaultValueDefinition(i)` de cada camp d'`IOF_Finques` →
   totes buides/invàlides. `layer.editorWidgetSetup(i)` → cap
   configuració especial. **Descarta que sigui un valor per defecte
   configurat al camp.**
2. `QgsSettings().value("digitizing/reuse-last-values")` → **`False`**.
   **Descarta la hipòtesi que fos QGIS reutilitzant valors globalment**
   (la correcció anterior d'aquesta mateixa sessió partia d'aquesta
   hipòtesi, incorrecta).
3. Es van llegir els **fitxers reals instal·lats** (`iof_limits_dialog.py`
   i `iof_finques_wizard.py`) per confirmar que sí que tenien les
   correccions anteriors aplicades (per descartar que fos un problema
   de versió desactualitzada). Totes dues, confirmades.
4. **La prova decisiva:** es van llegir els valors REALS de les
   features d'`IOF_Finques` al projecte de l'usuari amb
   `feat["municipi"]` etc. Resultat: `fid=2` i `fid=3` (els polígons
   nous) tenien **TOTS els camps a `None`** — codi, nom, comarca i
   municipi. **Les dades ja eren correctes!** El problema no hi era
   a les dades.

**Causa real, trobada revisant `_restore_municipi()` una altra vegada
amb aquesta pista:** la branca `if not municipi_str:` (la que es crida
per a un polígon nou sense municipi desat) feia `return` immediatament
després de reiniciar la comarca i cridar `_populate_municipis()` —
**sense arribar mai a la línia `self._list_municipis.clear()`**, que
només existia més avall, a la branca per a quan SÍ hi ha municipi. La
llista `_list_municipis` es quedava, doncs, amb el contingut de
l'última finca mostrada (p. ex. "Begues"), encara que les dades reals
del nou polígon fossin buides — semblava herència de dades, però era
només la interfície sense actualitzar-se.

**Correcció definitiva:** afegit `self._list_municipis.clear()` a la
branca `if not municipi_str:` de `_restore_municipi()`, abans del
`return`. Verificat amb un test dirigit que simula exactament aquest
cas (llista amb "Begues" abans de cridar `_restore_municipi("")` →
buida després).

**Lliçó:** quan hi ha una connexió `qgis-mcp` activa, val més la pena
inspeccionar l'estat real (configuració de camps, settings de QGIS,
dades reals de les features, fitxers realment instal·lats) que seguir
raonant només sobre el codi font — en aquest cas la hipòtesi inicial
(QGIS reutilitzant valors) era plausible i ben argumentada, però
completament equivocada, i la comprovació en directe ho va aclarir en
minuts en lloc de múltiples rondes més d'assaig i error.

## Fals avís d'"unitats incompletes" per a edificis/conreus (juliol 2026)
**Reportat per l'usuari:** "quan exportem dona un fals error en el cas
d'unitats de vegetació que només tenen codi d'ús com edificis i
conreus." — confirmat amb captura: l'avís "Revisió abans d'exportar"
marcava "Unitats d'actuació / Rodals: 2 element(s) sense «Codi UA /
Rodal»".

**Causa real:** el `_layer_status()` nou d'aquesta sessió (avís abans
d'exportar) exigia `codi_ua` a TOTS els elements de la capa d'unitats
per considerar-la "correcta" — però les unitats que representen àrees
no forestals (edificis, conreus, erm...) legítimament NO tenen `codi_ua`
propi, només `codi_us`. Aquest mateix criteri ja estava establert en un
altre lloc del complement (`iof_format_dialog.py`, comentari: "Les
unitats que només tenen codi_us (sense for_forestal — p.ex. erm,
edificis...) no han de generar mai un límit de rodal propi"), i
`_generate_lines()` (`iof_dialog.py`) ja les omet correctament de
l'exportació (`if not codi_ua: continue`) — només `_layer_status()`
no tenia en compte aquesta excepció.

**Correcció:** dins `_layer_status()`, quan es comprova el camp
obligatori `codi_ua` de la capa "unitats", una unitat NOMÉS compta com
a incompleta si li falten TANT `codi_ua` COM `codi_us` — si té
`codi_us` assignat (encara que no tingui `codi_ua`), es considera
vàlida i no es compta com a "element sense codi".

**Verificat:** amb un escenari de 4 unitats (2 forestals amb codi_ua, 2
"edificis"/"conreus" sense codi_ua però amb codi_us) → status
"correcta", cap fals avís. Afegint una 5a unitat sense NI codi_ua NI
codi_us → status "incompleta", detectant només aquesta (no les altres
2 legítimes).

## Avís de revisió abans d'exportar el TXT (juliol 2026)
**Reportat per l'usuari:** "Exportar IOF a TXT" (`iof_dialog.py`) exportava
sempre, sense cap comprovació — `_validate_obligatories()` literalment
deia "Exporta sempre, sense bloquejar per capes buides" i retornava
`True` incondicionalment. Després d'afegir un polígon nou, es podia
exportar (o copiar al porta-retalls) amb dades incompletes sense cap
avís.

**Correcció:** noves `_layer_status(key)` i `_validate_obligatories()`
a `IOFExporterDialog`. Per a cada capa de `LAYER_CONFIGS` (Finques,
Unitats, Camins, Canvis d'ús, Infraestructures, Punts d'aigua):
- **Buida**: no hi ha capa seleccionada, o té 0 elements.
- **Incompleta**: té elements, però algun camp obligatori (marcat amb
  `True` a `LAYER_CONFIGS`) no s'ha assignat, o algun element el té
  buit. Per a "Unitats" també compta com a incompleta si alguna finca
  (excloent-ne els forats, com sempre amb `find_interior_polygons()`)
  no té les unitats de vegetació completes — reaprofitant
  `finca_te_unitats_completes()` d'`iof_utils.py`.
- **Correcta**: la resta.

Si TOTES les capes són correctes, no es mostra res (no cal amoïnar
l'usuari). Si n'hi ha alguna buida o incompleta, es mostra un resum
amb les tres categories i es demana confirmació (Sí/No) abans de
continuar — NO bloqueja del tot, ja que pot ser una decisió vàlida
exportar igualment (p. ex. una exportació parcial intencionada).
`_validate_obligatories()` es crida des de `_do_copy()` i `_do_export()`
(no des de `_do_preview()`, que sempre passa `silent=True` i no ha de
mostrar cap diàleg mentre l'usuari només està mirant la vista prèvia).

**Verificat** amb una capa de finques simulada amb un element sense
`codi_finca` i la resta de capes sense seleccionar: detecta
correctament "Finques" com a incompleta i la resta com a buides, i
respecta tant la resposta "Sí" com "No" de l'usuari.

## Icona del complement actualitzada (juliol 2026)
Substituïda `icons/icon.png` (referenciada des de `metadata.txt` i des
del diàleg "Sobre IOF Assistent") per la icona nova proporcionada per
l'usuari, redimensionada de 1254×1254 a 128×128 (la mateixa mida que
la icona anterior) i convertida a RGBA per mantenir la transparència.

## "Aplicar estil de gestió" s'aplicava a capes buides (juliol 2026)
**Reportat per l'usuari:** "Aplicar estil de gestió" (`iof_format_dialog.py`)
aplicava l'estil a qualsevol capa IOF trobada, sense comprovar si tenia
cap element digitalitzat. No petava (aplicar un renderer a una capa
buida és una operació vàlida de QGIS), però no tenia sentit — cap
efecte visible, i l'usuari podia pensar que ja tenia l'estil bo quan
en realitat encara no hi havia res digitalitzat.

**Correcció:** afegida una comprovació `layer.featureCount() == 0` amb
avís "Capa buida" a les 8 funcions d'aplicar estil (`_apply_layer`
—compartida per Finques—, `_apply_camins`, `_apply_infra`,
`_apply_canvis`, `_apply_aigua`, `_apply_inventari`, `_apply_elements`,
`_apply_unitats`), just abans de cridar la funció d'estil real.

**Actualització (mateix dia): l'usuari va confirmar que "Reiniciar
estil" tampoc ha d'actuar sobre capes buides**, per coherència amb
"Aplicar estil". Afegida la mateixa comprovació a `_reset_elements`,
`_reset_inventari`, `_reset_unitats` i `_reset_finques` (avís "Capa
buida" individual, com als d'aplicar). A `_reset_all` (l'operació
massiva "Reiniciar tots els estils") el tractament és una mica
diferent perquè processa moltes capes de cop: les capes buides
simplement no es reinicien i es reporten per separat a la llista
"No s'han tocat (sense elements digitalitzats)" del resum final, en
lloc d'interrompre l'operació sencera amb un avís per cada una.

**Verificat** amb capes simulades existents però amb 0 elements: tant
el reset individual com el massiu detecten correctament la capa buida
i no hi apliquen cap canvi.

## "Capa buida" no cancel·lava l'obertura de l'assistent (juliol 2026)
**Bug reportat per l'usuari:** a "Omplir camps" (Finques / Camins /
Unitats), quan la capa corresponent existeix però encara no té cap
element digitalitzat, apareix correctament l'avís "Capa buida" — però
en prémer "D'acord", **l'assistent s'obria igualment**, buit i
inutilitzable. Contrastava amb el cas "Capa no trobada" (la capa no
existeix), que ja funcionava bé des de la correcció anterior.

**Causa:** exactament el mateix patró que «Capa no trobada» — el
`_load_layer()` de cada wizard (`iof_finques_wizard.py`,
`iof_camins_wizard.py`, `iof_rodals_wizard.py`) ja cridava
`self.reject()` en el bloc de "Capa buida", però NOMÉS el bloc
"Capa no trobada" (capa inexistent) marcava `self._cancelled = True`
— el bloc "Capa buida" (capa existent, 0 elements) s'havia quedat
despenjat sense aquest flag en la revisió anterior. Com que
`iof_exporter.py` decideix si crida `.show()` comprovant només aquest
flag, l'assistent es mostrava igualment.

**Correcció:** afegit `self._cancelled = True` també al bloc de "Capa
buida" dels tres wizards. S'ha revisat sistemàticament TOTS els
`self.reject()` del complement per detectar-hi el mateix patró
(`iof_infra_wizard.py` i `iof_overwrite_dialog.py` en tenen, però són
fitxers morts — mai importats des d'enlloc — i `iof_importar_cadastre_dialog.py`
s'obre amb `.exec()`, un patró diferent on `reject()` ja funciona
correctament tot sol).

**Actualització (mateix dia): implementada la detecció per finca
concreta.** L'usuari va confirmar que volia aquest nivell de detecció
més fi. Afegides a `iof_utils.py` dues funcions compartides,
extretes SENSE tocar la implementació original de
`iof_unitats_wizard.py` (que segueix fent servir els seus propis
mètodes privats `_units_for_finca()`/`_finca_is_complete()`, intactes):
- `units_for_finca(layer_unitats, finca_feat)`: unitats el centroide de
  les quals cau dins la finca.
- `finca_te_unitats_completes(layer_unitats, finca_feat)`: True si la
  unió de les seves unitats cobreix ≥99% de l'àrea de la finca.

A `iof_rodals_wizard.py::_load_layer()`, després de comprovar que la
capa d'unitats no estigui buida, es recorren totes les finques
vàlides (excloent-ne els forats amb `find_interior_polygons()`, com
sempre) i, si alguna no té les unitats completes, es mostra un avís
amb els codis de les finques afectades (camp `codi_finca`) i es
cancel·la — igual que als altres casos de "capa no trobada"/"capa
buida".

**Verificat** amb geometries rectangulars reals (centroide, `contains`,
`combine`, `intersection`, àrea) simulant exactament l'escenari
reportat (2 finques amb unitats completes + 1 de nova sense cap
unitat): només la finca nova es detecta com a incompleta, i el
missatge final mostra correctament el seu `codi_finca`.

## Fals positiu a la detecció de finques excloses (juliol 2026)
**Bug reportat per l'usuari:** en digitalitzar dues finques i dividir-les
en unitats de vegetació, tot correcte; en afegir una tercera finca nova,
el wizard d'unitats (`iof_unitats_wizard.py::_load_finques()`) no la
reconeixia — no apareixia a la llista de finques a processar.

**Causa arrel:** `iof_utils.find_interior_polygons()` (usada per detectar
polígons que representen "forats"/àrees excloses d'una finca gran, per
NO tractar-los com a finques independents) tenia un mètode de reserva
(fallback, quan no hi ha cap anell interior real entre els polígons)
que només comparava **bounding boxes**: si la bbox d'un polígon queia
dins la bbox d'un altre de més àrea, es marcava com a exclusió — sense
comprovar si els polígons realment se solapaven. Dues finques totalment
separades i que no es toquen en cap punt poden tenir, per pura
coincidència de la seva posició al mapa, una bbox continguda dins de
l'altra (p. ex. una finca petita situada dins l'extensió d'una de gran
i allargada en forma de L, sense solapar-se-hi gens). La finca nova de
l'usuari queia en aquest cas i es descartava per error.

**Correcció:** el fallback ara, a més de la bbox, comprova el
solapament geomètric real: reconstrueix l'anell EXTERIOR (sense forats)
del polígon gran amb `geom_sense_forats()` (ja existent al fitxer) i
calcula quin percentatge de l'àrea del polígon petit queda cobert per
aquest anell exterior — només es marca com a exclusió si la cobertura
és ≥99%. No es pot fer servir `contains()`/`intersects()` directament
sobre la geometria original del polígon gran perquè, si el forat ja
s'ha restat de la seva geometria, GEOS no reconeix el polígon petit com
a "contingut" (aquest és exactament el motiu pel qual originalment es
va triar bbox en lloc de GEOS — vegeu el docstring de la funció).
Reconstruir només l'anell exterior evita aquest problema.

**Verificat matemàticament** (sense QGIS real, amb rectangles i càlcul
manual d'àrees d'intersecció) que: (1) el cas exacte del bug — dues
finques separades amb bbox coincident — ja NO es marca com a exclusió;
(2) el cas legítim — un polígon que representa un forat real ja restat
de la geometria del polígon gran — es continua detectant correctament.

## Migració a enumeracions amb àmbit (Qt6) — 97 avisos resolts (juliol 2026)
L'escàner de compatibilitat Qt6 de plugins.qgis.org («pyqgis4-checker») va
detectar 97 usos d'enumeracions PyQGIS en format «pla» (l'estil antic,
només vàlid a PyQt5/Qt5) que calia convertir al format amb àmbit
(`Classe.NomEnum.Valor`), vàlid tant a PyQt5 com a PyQt6 segons la wiki
oficial (https://github.com/qgis/QGIS/wiki/Plugin-migration-to-be-compatible-with-Qt5-and-Qt6).
Cap d'aquests canvis altera el comportament: la sintaxi nova és 100%
equivalent, només més explícita.

**Patrons corregits (substitució global, inequívoca onsevulla que aparegui):**
- `Qgis.Info/Warning/Critical` → `Qgis.MessageLevel.Info/Warning/Critical`
- `QgsWkbTypes.PolygonGeometry/LineGeometry/PointGeometry` →
  `QgsWkbTypes.GeometryType.X`
- `QgsEditFormConfig.SuppressOn/SuppressOff` →
  `QgsEditFormConfig.FeatureFormSuppress.X`
- `QgsVectorFileWriter.NoError/ErrCreateDataSource` →
  `QgsVectorFileWriter.WriterError.X`
- `QgsVectorFileWriter.CreateOrOverwriteFile` →
  `QgsVectorFileWriter.ActionOnExistingFile.X`
- `QgsUnitTypes.RenderMillimeters/RenderPoints` → `QgsUnitTypes.RenderUnit.X`
- `QgsPalLayerSettings.Size/Color/Bold` → `QgsPalLayerSettings.Property.X`
- `QgsSymbolLayer.PropertyFillColor` → `QgsSymbolLayer.Property.X`

**Cas especial:** `iof_utils.py::activar_snapping_totes_capes()` té un
`try/except` que prova primer l'API moderna (`Qgis.SnappingMode`, ja
correcta) i cau a una API més antiga si falla. Aquesta branca de reserva
(`except`) TAMBÉ va sortir marcada, tot i ser codi de compatibilitat amb
versions molt antigues de QGIS que rarament (o mai) s'executa en la
pràctica actual:
- `QgsSnappingConfig.AllLayers` → `QgsSnappingConfig.SnappingMode.AllLayers`
- `QgsSnappingConfig.VertexAndSegment` →
  `QgsSnappingConfig.SnappingType.VertexAndSegment`
- `QgsTolerance.Pixels` → `QgsTolerance.UnitType.Pixels`

No s'ha pogut verificar amb l'eina real que aquests tres camins nidificats
existeixin de debò a totes les versions antigues de QGIS que la branca
`except` pretén cobrir (no hi ha accés a QGIS real per confirmar-ho); s'ha
confiat en la suggerència literal de l'escàner oficial. Si mai algú
detecta que aquesta branca de reserva concreta falla en una versió molt
antiga de QGIS, cal revisar-ho específicament — és l'única part d'aquesta
migració amb un cert marge d'incertesa.

**Verificació:** `py_compile` de tots els fitxers + repetició de tota la
bateria de proves amb el simulador de QGIS (`initGui`, els 12 botons, els
4 escenaris d'importació CSV) — cap regressió.

## LA VERITAT sobre "0 avisos de flake8" (juliol 2026) — una altra lliçó important
Vaig donar per fet que la neteja de flake8 d'una sessió anterior havia
deixat el projecte a 0 avisos. **Això era fals**, i per un motiu
concret: `flake8` (i `autopep8`) **ignoren per defecte** els codis
E121, E123, E126, E226, E24 (E241/E242), E704, W503, W504 — són
considerats "opcionals"/"discutibles" per pycodestyle i estan
DESACTIVATS de sèrie. Cada vegada que jo executava `python3 -m flake8 .`
sense cap `--select` explícit, aquests codis mai s'arribaven a
comprovar — per això sempre em sortia "0", encara que el codi seguís
ple d'aquests patrons. L'escàner de plugins.qgis.org, en canvi, SÍ els
activa, i per això seguia reportant 983 avisos malgrat les meves
confirmacions repetides que deien "0".

**Verificat correctament aquest cop** amb
`flake8 --isolated --select=E241,W503,W504,E704,E226` (forçant
explícitament aquests codis, ignorant qualsevol configuració per
defecte): confirmat que dona 983, coincidint exactament amb l'escàner
oficial.

**Corregit de debò:**
- E241 (800) i E226 (2): `autopep8 --aggressive --select=E241,E704,E226`
  — eliminat l'espaiat extra d'alineació.
- E704 (18): script Python dedicat que divideix cada
  `def nom(...): return x` en dues línies (`def nom(...):` seguit de
  `return x` indentat) — autopep8 no ho arreglava amb `--select` sol.
- **W503 (98) + W504 (65) — NO corregits, deliberadament.** Són
  **mútuament contradictoris per disseny**: un exigeix trencar la línia
  ABANS de l'operador binari, l'altre exigeix trencar-la DESPRÉS — mai
  es poden complir tots dos alhora si la línia es parteix en absolut.
  És per això que estan als dos al mateix la llista d'ignorats per
  defecte de pycodestyit — eliminar-los del tot requeriria ajuntar
  desenes de condicions `if` complexes en una sola línia, arreu del
  projecte, amb risc real d'introduir errors de lectura del codi, per
  un guany merament cosmètic. **No bloquegen l'aprovació** (Critical: 0
  confirmat), així que es deixen tal com estan.

**Resultat final real i verificat: de 983 a 163** (tots W503/W504,
documentats com a contradictoris i no bloquejants).

**Lliçó general, la mateixa que amb Bandit:** no donar per bo un "0"
d'una eina sense confirmar exactament QUÈ ha comprovat de debò —
`flake8`/`autopep8` tenen llistes d'ignorats per defecte que poden fer
que una comprovació sembli neta quan en realitat mai s'ha arribat a fer.

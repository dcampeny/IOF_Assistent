# IOF Assistent — Complement de QGIS

Complement de QGIS per a la creació de la cartografia d'un **Instrument
d'Ordenació Forestal (IOF)** segons les especificacions del Centre de la
Propietat Forestal de Catalunya, i l'exportació de les seves dades SIG.

Permet crear les 8 capes vectorials d'un IOF amb tots els camps necessaris,
incorporar cartografia de suport (cadastral i de referència de l'ICGC:
mapa base topogràfic, mapa referencial topogràfic territorial i
ortofotomapa), digitalitzar-ne els elements (finques, unitats de
vegetació, camins, infraestructures de prevenció d'incendis, canvis d'ús,
punts d'aigua, elements singulars i inventaris forestals), i exportar el
fitxer `.txt` per a la importació a PDF segons les normes de redacció del
CPF.

**Compatibilitat:** QGIS 3.x (Qt5) i QGIS 4.x (Qt6). Verificat amb
l'escàner oficial de compatibilitat Qt6 de plugins.qgis.org — 0 incidències.

## Format de sortida

Cada registre segueix l'estructura:

```
ID#CODI#MIDA#FORESTAL#ARBRAT#TIPUSZZ
```

| ID  | Tipus de registre                                |
|-----|--------------------------------------------------|
| FI  | Finca                                            |
| UT  | Unitat d'actuació                                |
| US  | Usos i vegetació de les unitats d'actuació       |
| CA  | Camí                                             |
| IE  | Infraestructura, Canvis d'ús o Punts d'aigua     |

### Exemple de sortida

```
FI#1#21.30###TonaZZ
FI#2#89.12###Seva,TonaZZ
UT#1#24.42#24.42#19.91#PhLIT_QibZZ
US#1####PhZZ
CA#DB01E#40.61#0#0#ZZ
IE#LD01E#0.15###ZZ
IE#PA01E####438830,4634856ZZ
FINAL DEL PROGRAMA
```

## Instal·lació

1. Descarrega o clona aquest repositori.
2. Copia la carpeta `IOF_Assistent` a:
   - **Windows:** `C:\Users\<usuari>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
   - **Linux/Mac:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
3. Obre QGIS → Menú **Complements → Gestiona i instal·la complements**.
4. A la pestanya **Instal·lats**, activa **IOF Assistent**.
5. Apareixerà com a barra d'eines pròpia i també al menú
   **Complements → IOF Assistent**.

## Ús

Ordre de treball recomanat:

1. **Crear les capes IOF** — *Complements → IOF Assistent → Crear capes IOF*
   (genera les 8 capes buides amb tots els camps necessaris).
2. **Importar cartografia cadastral** — *Cadastre → Importar cadastre*
   (servei ATOM de la Direcció General del Cadastre, sense autenticació).
3. **Delimitar finques i àmbit** — *Cadastre → Seleccionar parcel·les
   cadastrals* i *Crear àmbit de l'IOF*.
4. **Carregar cartografia de suport** (opcional) — *Mapes ICGC → Base
   topogràfic / Referencial topogràfic territorial vectorial /
   Ortofotomapa*, com a referència visual per digitalitzar.
5. **Digitalitzar cada capa** — *Digitalitzar → ...* per a unitats de
   vegetació, camins, infraestructures de prevenció d'incendis, canvis
   d'ús, punts d'aigua, elements singulars i inventaris forestals. Al
   diàleg d'inventaris hi ha també un botó per **importar punts
   massivament des d'un fitxer CSV** (columnes `codi_pi`, `coord_x`,
   `coord_y`). Si la capa ja té punts, es pot triar sobreescriure'ls o
   afegir-hi els nous.
6. **Omplir camps i aplicar estil** — *Dades i estils → Omplir camps*
   per assignar codis i formacions a cada element, i *Aplicar estil de
   gestió* per a la simbologia final del plànol.
7. **Exportar el fitxer TXT** — *Exportar IOF a TXT*: selecciona la capa
   vectorial i els camps corresponents per a cada tipus de registre, prem
   **Vista prèvia** per comprovar-los, i **Exportar fitxer TXT** per
   generar el fitxer final per a la importació a PDF. Abans de copiar o
   exportar, es mostra un resum de quines capes tenen dades correctes,
   incompletes o buides, i es demana confirmació si n'hi ha alguna amb
   problemes.

## Capes suportades

| Capa                         | Geometria               | Registres generats |
|------------------------------|--------------------------|--------------------|
| Finques                      | Polígon / MultiPolígon   | FI                 |
| Unitats d'actuació           | Polígon                  | UT + US            |
| Camins                       | Línia                    | CA                 |
| Canvis d'ús                  | Polígon                  | IE                 |
| Infraestructures PI          | Polígon                  | IE                 |
| Punts d'aigua                | Punt                     | IE                 |
| Elements singulars           | Punt                     | (informatiu)       |
| Punts d'inventari            | Punt                     | (informatiu)       |

## Notes

- Les superfícies es calculen automàticament des de la geometria (en hectàrees).
- Les longituds dels camins es calculen en metres.
- Les coordenades dels punts d'aigua s'exporten en UTM (les coordenades del CRS del projecte).
- El fitxer acaba sempre amb la línia `FINAL DEL PROGRAMA`.
- Es recomana que el projecte QGIS estigui en **ETRS89 / UTM zona 31N (EPSG:25831)**.
- Els botons "Digitalitzar", "Dades i estils" i "Exportar IOF a TXT" només
  estan actius si el projecte ja té alguna capa IOF creada. Si s'elimina
  la capa que necessita un diàleg concret (p. ex. `IOF_Finques`) després
  d'haver-la creat, en obrir aquell diàleg apareix un avís de "Capa no
  trobada" i no s'obre res més fins que es torni a crear amb **Crear
  capes IOF**.

## Problemes coneguts (resolts)

Aquests problemes de digitalització/geometria es van detectar i corregir el
juliol de 2026. Es documenten aquí per si tornen a aparèixer amb dades noves:

- **Compatibilitat total amb Qt6 (QGIS 4.x)**: totes les enumeracions de
  PyQGIS s'han convertit al format amb àmbit (p. ex. `Qgis.MessageLevel.Info`
  en lloc de `Qgis.Info`, `QgsWkbTypes.GeometryType.PolygonGeometry` en lloc
  de `QgsWkbTypes.PolygonGeometry`), vàlid tant a QGIS 3.x (Qt5) com a
  QGIS 4.x (Qt6). Verificat amb l'escàner oficial de compatibilitat Qt6 de
  plugins.qgis.org: **0 incidències**.
- **Divisió d'unitats d'actuació fallava sense motiu clar**: els codis
  d'error de `splitGeometry()` han canviat en versions modernes de QGIS
  (ja no són els 0/1/2 de QGIS 3.4). Corregit perquè el registre mostri el
  motiu real de l'error.
- **`Hole lies outside shell` en algunes finques**: apareixia en finques
  amb un camí que gairebé arriba a la vora del polígon. Corregit validant
  i reparant la geometria (`makeValid()`) durant la creació de
  `IOF_Finques`, i canviant aquesta capa de `Polygon` a `MultiPolygon` per
  admetre correctament finques que un camí divideix en dues parts
  separades.
- **`UNIQUE constraint failed` en dividir un polígon**: bug conegut de
  QGIS amb capes GeoPackage — el `fid` de l'entitat original es copiava a
  les parts noves. Corregit buidant el `fid` abans de desar cada part
  nova.

Si reapareix algun d'aquests errors amb dades noves, consulta la secció
"Bugs coneguts / ja resolts" del `CLAUDE.md` per al detall tècnic.

## Referència

Especificació tècnica: *Dades SIG per a l'elaboració d'Instruments d'Ordenació Forestal* d'acord amb les instruccions del Centre de la Propietat Forestal.

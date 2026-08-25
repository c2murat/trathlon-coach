# Spanish municipality dataset

`spain_municipalities_2026.csv` is an offline snapshot of the Generalitat de
Catalunya open-data dataset **Municipis d'Espanya**, downloaded on 2026-08-25:

- Dataset: https://analisi.transparenciacatalunya.cat/d/x5xm-w9x7
- CSV export: https://analisi.transparenciacatalunya.cat/api/v3/views/x5xm-w9x7/export.csv?accessType=DOWNLOAD
- Catalogue record: https://datos.gob.es/es/catalogo/a09002970-municipios-de-espana
- Publisher: Generalitat de Catalunya
- Source description: Spanish municipalities and their INE province codes
- Snapshot coverage: 8,132 municipalities, 52 provinces, 19 autonomous
  communities/cities
- Licence: Generalitat open-data reuse terms
  https://web.gencat.cat/ca/generalitat/dades-indicadors/dades-obertes/llicencies

The INE province-to-autonomous-community mapping and display aliases live in
`geography.py`. The underlying INE municipal register is published annually:
https://www.ine.es/dyngs/INEbase/operacion.htm?c=Estadistica_C&cid=1254736177031&menu=ultiDatos&idp=1254734710990

To update, download a new CSV snapshot, verify its UTF-8 header and row count,
replace the versioned file, update this note, and run
`tests/test_competition_geography.py` plus the Tavily/catalog suites. Runtime
never downloads or geocodes data.

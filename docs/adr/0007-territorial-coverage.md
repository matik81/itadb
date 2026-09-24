# ADR 0007 — copertura territoriale, geografie e acquisizioni

Stato: accettato, 23 settembre 2026.

Le pubblicazioni di aggregati multiserie dichiarano la copertura esplicita per
serie, periodo e geografia; il campo serie della release rimane la selezione
iniziale per i client precedenti. Le API v1/v2
esistenti conservano i loro contratti e ricevono endpoint aggiuntivi di lettura.

I territori sono identificati dalla codifica e dalla versione, non dal solo
codice. Snapshot geografici e collegamenti tra versioni sono evidenze immutabili.
Fusioni, scissioni e ricodifiche conservano fonte e decorrenza; i collegamenti
strutturali non costituiscono pesi demografici. Le somme attraversano solo
partizioni dichiarate disgiunte; il cambio di vintage richiede riconciliazione
esplicita. Nessuna ripartizione automatica per area geometrica.

`pyshp` legge gli shapefile ufficiali ISTAT (SHP/DBF/PRJ) in modo iterativo.
La dipendenza gestisce il formato della fonte senza un parser proprietario.
La trasformazione da
EPSG:32632 a EPSG:4326 e i controlli geometrici usano PostGIS già presente.
Non si introducono GDAL, GeoPandas, scheduler o servizi aggiuntivi.

L'acquisizione statica ha URL curati, dimensioni massime, timeout, progressi e
manifest SHA-256. Gli originali rimangono fuori Git. Gli otto eventi sono
trascritti nel contratto revisionato dal prospetto PDF ISTAT e riconciliati con
i codici geografici; non si introduce un estrattore generico di documenti.

L'audit reale ha rilevato 25 anelli non validi e disallineamenti tra livelli.
Si ammettono solo riparazioni elencate nel contratto con conservazione dell'area;
province e regioni sono derivate dall'unione dei comuni, mantenendo originali e
rapporto delle differenze. Si evita una tolleranza geografica crescente che
accetterebbe annidamenti incoerenti. Vedi [perimetro e misure](../sources/territorial-aggregates.md).

Il database ripete il controllo del contesto alla pubblicazione, così
modifiche ai metadati draft successive al caricamento non eludono i vincoli.
Le migrazioni precedentemente applicate rimangono immutate.

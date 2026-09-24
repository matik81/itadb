# Confini amministrativi sulla mappa

Mostrare regioni, province/UTS e comuni con tratti rispettivamente di 1,5,
0,8 e 0,35 pixel, stabili durante lo zoom. Conservare i marker ad area
proporzionale alla popolazione.

- [x] Riutilizzare le geometrie regionali e comunali già associate allo snapshot.
- [x] Aggiungere cartografia provinciale dalla stessa fonte geografica archiviata,
  con checksum verificato, controllo dei codici e caricamento atomico/idempotente.
  Nuova migrazione dopo la baseline; nessuna riscrittura dei dati pubblicati.
- [x] Estendere `/map`, OpenAPI e tipi client; disegnare i confini dal livello
  comunale al regionale, mantenendo in primo piano i tratti più importanti.
- [x] Verificare integrità, isolamento degli snapshot, API, frontend e carico reale.
- [x] Aggiornare lo stack locale e controllare la mappa nel browser.

Le geometrie sono semplificate per visualizzazione. Le province conservano
il checksum della fonte già presente nello snapshot e sono append-only;
`publish-population-boundaries` completa gli snapshot pubblicati prima della
nuova migrazione. Le nuove pubblicazioni le importano nella stessa transazione.
L'API resta indipendente dagli archivi originali e legge solo viste pubblicate.

Verifica locale del 24 settembre 2026: 107 province importate e retry senza
duplicati; 20 regioni e 7.896 confini comunali serviti nello stesso snapshot.
Piani PostgreSQL eseguiti sul volume nazionale: lettura dei confini provinciali
6,5 ms e comunali 20,4 ms. Risposta HTTP completa circa 6,5 MB in 0,40 s sullo
stack locale; queste misure non rappresentano una rete mobile o un deployment remoto.

Passano 284 test backend, 43 distinti di integrazione (41 nella suite completa
e i due nuovi, dopo aver corretto il percorso dell'archivio nelle fixture),
25 frontend, tipi, lint e build. Browser reale desktop/mobile: geometrie presenti,
spessori corretti e invarianti allo zoom, navigazione funzionante e nessun errore.
Log e piani sono conservati localmente in `.tools/map-boundaries-*.log` e
`.tools/map-boundaries-query-plans.json`, esclusi da Git.

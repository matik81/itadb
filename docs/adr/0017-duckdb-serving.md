# ADR 0017 — Consultazione completa con DuckDB incorporato

Stato: accettato. Sostituisce la scelta PostgreSQL online dell'ADR 0015;
non cambia il modello sintetico né le revisioni SQL già applicate.

## Contesto

L'esperimento nazionale dell'ADR 0016 misura un vantaggio di spazio e CPU per
DuckDB. L'obiettivo richiesto è eliminare Neon, incluse le funzioni v1/v2,
validazioni e cartografia, mantenendo API e frontend compatibili.

## Decisione

FastAPI consulta un singolo archivio DuckDB in sola lettura sul volume locale o
Railway. Le geometrie sono GeoJSON calcolati offline con le stesse espressioni
PostGIS già utilizzate. Non serve un'estensione spaziale nel processo online.
DuckDB è già una dipendenza del progetto; non si aggiungono servizi. Si aggiunge
`pytz`, richiesto dal client DuckDB per restituire i TIMESTAMPTZ già presenti nelle
release: il test di parità ha rilevato un errore di conversione senza il modulo.

PostgreSQL/PostGIS è confinato al workflow offline esistente. L'esportatore legge
esclusivamente le viste `api` in una transazione consistente e salva tutte le
release pubblicate. Tipi decimal, date, null, provenienza e natura sintetica
restano conservati. Nessun URL PostgreSQL viene utilizzato dal serving predefinito.
Una tabella di ranghi testuali conserva l'ordinamento PostgreSQL di nomi, codici,
etichette e metadati: il confronto nazionale ha rilevato differenze tra collation
libc e DuckDB, in particolare con underscore. I ranghi sono calcolati offline;
non dipendono dalla locale o dalla versione ICU del server online. I timestamp
sono restituiti in UTC anche nei cursori concorrenti.
L'adattatore PostgreSQL resta selezionabile esplicitamente per confronto e test.

La pubblicazione produce directory nuove, schema versionato e checksum. Solo una
release verificata può diventare `current`; un errore lascia intatta la precedente.
Ogni processo API fissa una release all'avvio: il cambio richiede riavvio, evitando
risposte composte da versioni diverse. Il ripristino riattiva una release conservata.

## Conseguenze

Il deployment richiede un volume e un backup esterno dell'archivio, non un database
gestito. La generazione non avviene nelle richieste. Concorrenza, memoria, thread e
timeout sono limitati nel backend; l'archivio non è aperto in scrittura durante il
serving. Una sola istanza può gestire più richieste contemporanee.

La dimensione finale comprende anche geografia e storico: i 224 MB del benchmark
non rappresentano una promessa per tutta l'app. L'export e i controlli nazionali
sono operazioni offline; una nuova release richiede spazio per vecchia e nuova.

Riferimenti: [thread Python DuckDB](https://duckdb.org/docs/current/guides/python/multiple_threads),
[concorrenza DuckDB](https://duckdb.org/docs/current/connect/concurrency),
[volumi Railway](https://docs.railway.com/volumes).

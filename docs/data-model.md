# Modello dati

Lo schema pubblico `api` è definito in `src/itadb/serving/schema.py`.
Tutte le tabelle appartengono a un archivio DuckDB immutabile. Il manifest
conserva formato, schema, conteggi, versione del motore e checksum.

| Tabelle | Contenuto |
|---|---|
| `population_snapshots` | Identità del run, fonti, modello, audit e controlli di pubblicazione |
| `population_persons`, `population_households` | Individui e famiglie sintetici completi |
| `population_cells`, `population_validation` | Distribuzioni dei record e confronto con i vincoli |
| `population_municipalities`, `population_provinces`, `population_regions` | Geografia, conteggi e GeoJSON |
| `sources`, `releases`, `releases_v2` | Catalogo e provenienza degli aggregati |
| `observations`, `observations_v2`, `coverage_v2` | Misure, flag upstream e copertura |
| `quality`, `quality_v2`, `artifacts_v2` | Gate, checksum e dimensioni delle evidenze |
| `territories_v2`, `boundaries_v2`, `crosswalks_v2` | Geografie versionate, confini e cambi territoriali |
| `text_order` | Ordinamento stabile delle etichette nell'archivio |

Le API leggono soltanto dati pubblicati. La pipeline lavora su una copia separata;
nessun draft incompleto può diventare `current`. Le versioni precedenti restano
leggibili. La pipeline controlla unicità, relazioni, domini, riconciliazioni,
provenienza e revisioni prima dell'attivazione; lo schema pubblico non è un
catalogo amministrativo da modificare con SQL manuale.

Gli identificativi di persone e famiglie sono locali allo snapshot. Il modello
ammette adulti senza famiglia e richiede almeno un adulto di riferimento per
famiglia; tutti i minori devono essere assegnati. Età 100 con `age_is_lower_bound`
indica 100+. Le coordinate sono punti territoriali, non residenze.

Le osservazioni usano `DECIMAL(20,6)` e l'API restituisce stringhe. Null non vale
zero. Una release regionale e una comunale possono avere geografie e periodi
diversi: non vanno sommate indiscriminatamente. Fixture e dati sintetici
conservano marcature esplicite. [Metodo](population.md), [contratto API](api/README.md).

Le revisioni dello schema richiedono un nuovo formato e un nuovo archivio.
Una release verificata non viene modificata sul posto.

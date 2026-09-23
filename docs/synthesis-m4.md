# M4 — sintesi nazionale locale 1:1

M4 genera **58.943.464 persone virtuali** calibrate sui conteggi ISTAT al
1° gennaio 2025. Il rapporto 1:1 riguarda il numero di residenti per cella,
non una corrispondenza con persone reali. Le famiglie sono virtuali e la
loro composizione resta una baseline casuale vincolata.

La successiva [integrazione della cittadinanza](citizenship.md) produce uno
snapshot derivato con `citizenship_code`, conservando tutti gli attributi e
le famiglie di questa base. Il riferimento descritto qui resta immutabile.

## Fonti e riferimento unico

Il contratto [`istat-m4-national-v1.json`](../contracts/istat-m4-national-v1.json)
fissa originali, URL, SHA-256, dimensioni, intestazioni, domini e riferimenti.
Il riferimento [`m4-reference-v1.json`](../contracts/m4-reference-v1.json)
fissa seed **1701**, classe **6+ = 6** e le priorità demografia/geografia/famiglie.
La continuità con M3 riguarda le regole; anno, geografia, algoritmo e popolazione
cambiano e producono una nuova identità. Gli esperimenti M3 restano immutabili.

| Evidenza | Data | Copertura e uso |
|---|---|---|
| POSAS comunale | 01/01/2025 | 7.896 comuni × 102 righe: età 0–99, 100+, totale; conteggi M/F e totale |
| POSAS provinciale | 01/01/2025 | 107 province, verifica di tutte le congiunte sesso/età |
| SDMX popolazione | 01/01/2025 | 20 regioni e Italia, verifica di tutte le congiunte sesso/età |
| SDMX famiglie | 31/12/2024 | Numero e classi 1–5, 6+, totale per comune e livelli superiori |
| Geografia amministrativa | 01/01/2025 | Snapshot coerente: 7.896 comuni, 107 UTS, 20 regioni, Italia |
| DSD/codelist, dataflow, licenza, pagina POSAS e campioni | Acquisizioni archiviate | Semantica, legami padre, attribuzione e tracciabilità |

Fonti: [POSAS ISTAT 2025](https://demo.istat.it/app/?i=POS&a=2025),
[IstatData](https://esploradati.istat.it/),
[confini ISTAT](https://www.istat.it/storage/cartografia/confini_amministrativi/generalizzati/2025/Limiti01012025_g.zip),
[CC BY 4.0](https://www.istat.it/dati/open-data/).

L'inventario selettivo delle famiglie interrogato per il 2021–2025 restituisce
2021–2024. Il 2024/2025 è quindi il più recente confine annuale comune
verificato, aggiornando il 2021/2022 di M3. Non si usano le stime POSAS 2026.
Le date di pubblicazione upstream non accertate non vengono dedotte dalle
acquisizioni. Le colonne di stato civile presenti nello ZIP non entrano nel
modello: non vengono trasformate in attributi o legami individuali.

Ogni comune ha 202 conteggi M/F per età espliciti, inclusi gli zeri.
Per le famiglie, 727 categorie mancanti nell'intero file SDMX sono dedotte
pari a zero **soltanto** perché le altre categorie non negative esauriscono
esattamente il totale pubblicato. Un totale non riconciliato, una cella
soppressa, un flag o una nota non ammessi bloccano gli input. Non si imputano
valori mancanti per convenienza.

## Metodo e capacità effettive

[ADR 0012](adr/0012-national-territorial-snapshots.md) descrive algoritmo,
seed territoriali, budget e protocollo di recupero. L'espansione è vettoriale,
con batch provinciali e conteggi aggregati in Python. Non esiste una lista
Python nazionale di residenti. Ogni famiglia appartiene a un comune e tutti
i componenti, compreso l'adulto di riferimento, hanno lo stesso comune.
I minori sono assegnati; gli adulti eccedenti la capacità restano senza famiglia.

I Parquet persone contengono ID int64, ID famiglia nullable, codici comune/UTS/
regione, `birth_year`, `birth_year_upper_bound`, sesso, adulto di riferimento
e `data_kind=synthetic`. Età al 1° gennaio Y: `Y - birth_year - 1`.
Nel riferimento 2025 la coorte 100+ ha `birth_year=null` e limite superiore
1924; non si inventa l'età esatta. I Parquet famiglie contengono ID, geografia,
dimensione e natura sintetica. Nessun nome, indirizzo o identificativo reale.

L'audit indipendente rilegge i Parquet e verifica **1.594.992 vincoli sesso/età
comunali**, cardinalità familiari, assenza di duplicati, riferimenti, coorti,
residuo e gerarchia. L'esattezza dei margini è calibrazione. Non sono disponibili
statistiche familiari inutilizzate che validino la composizione casuale; le
congiunte provinciali/regionali sono controlli di riconciliazione della stessa
fonte, non una validazione scientifica indipendente.

La [valutazione disclosure e distribuzione](reviews/m4-disclosure.md) delimita
ciò che può essere condiviso. Microdati, originali, checkpoint e log restano
nell'archivio locale escluso da Git. Non esistono API nazionali di microdati.

## Riproduzione

```sh
uv sync --locked
uv run python scripts/run_logged.py --label "Fonti M4" --log .tools/m4-progress.log -- uv run itadb fetch-m4
# Riutilizzare l'inventario stampato:
uv run python scripts/run_logged.py --label "Sintesi M4" --log .tools/m4-progress.log -- uv run itadb synthesize-m4 --inputs data/state/m4-inputs-UUID.json
# Riutilizzare lo snapshot stampato:
uv run python scripts/run_logged.py --label "Audit M4" --log .tools/m4-progress.log -- uv run itadb verify-m4 --run data/curated/m4/HASH
uv run python scripts/run_logged.py --label "Carico 1M" --log .tools/m4-progress.log -- uv run python scripts/benchmark_m4.py --population 1000000
uv run python scripts/run_logged.py --label "Carico 10M e recupero" --log .tools/m4-progress.log -- uv run python scripts/benchmark_m4.py --population 10000000 --recovery
```

Su Windows `scripts/watch-progress.ps1 -LogPath .tools/m4-progress.log` segue
il log in un terminale. Il runner stampa fase, batch, residenti, elapsed,
picchi RAM/disco ed esito; il wrapper mostra heartbeat anche durante rete e test.
Il monitor campiona il disco ogni secondo; il picco RSS proviene dal sistema
operativo. Le misure includono il processo Python/DuckDB, non il sistema intero.

`synthesize-m4` rifiuta fixture attraverso il contratto ufficiale. I benchmark
usano invece un namespace geografico separato e `invented_load_fixture`.
Un retry completo verifica tutti i file e ricalcola gli audit; un retry
interrotto riusa soltanto checkpoint integri. File mancanti o alterati falliscono,
senza riscrivere lo snapshot. Per riprodurre un archivio danneggiato occorre
una nuova root, conservando l'evidenza precedente.

La riproduzione byte per byte richiede gli originali fissati, i sorgenti
registrati, il lockfile e l'ambiente indicato nel manifest. Una modifica
upstream produce un blocco e richiede un nuovo contratto. Conservare l'archivio
raw insieme agli snapshot: la sola disponibilità futura degli URL non è garantita.

## Misure e verifica

Le misure definitive e l'identità dello snapshot sono registrate al termine
delle esecuzioni nella [validazione](validation.md#m4--scala-nazionale-11).
Il budget preventivo è 8 GiB RSS, 40 GiB disco e 7.200 secondi per prova;
DuckDB 2 GiB, due thread, batch fino a 5M. Non si estrapolano tempi del pilota
o della fixture alla popolazione nazionale.

Il riferimento verificato è
`7a27c844410adf29262477114bfeecc3a55743a454dfd392d4708c8163858eb8`:
26.670.169 famiglie e 560.159 adulti non assegnati. Generazione e audit nel
runner monitorato: 177,61 s; picco RSS 1.114,90 MiB; snapshot finale
251.203.541 byte. Audit successivo: 28,65 s. Retry nazionale: stessi artefatti.
Tutte le prove rispettano i budget; i 10M inventati includono un'interruzione
e recupero effettivi. Dettagli dei perimetri temporali e dei picchi campionati
nel [JSON delle misure](benchmarks/m4-national-2026-09-24.json).

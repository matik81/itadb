# Cittadinanza nella popolazione virtuale

Il riferimento `citizenship-reference/1` aggiunge `citizenship_code` a ogni
individuo del riferimento M4 al **1° gennaio 2025**, mantenendo identici
ID, coorti, sesso, geografia, famiglia e adulto di riferimento. Lo snapshot
M4 di partenza rimane immutabile. [Decisione e metodo](adr/0013-citizenship-enrichment.md).

Assegnazione nazionale verificata: **53.572.213 individui nella categoria
italiana**, **5.371.251 nella popolazione straniera**, inclusi **525 apolidi**.
Totale 58.943.464, 196 categorie, 7.896 comuni. Errore zero sulle celle STR
e sui 375.226 conteggi comunali non nulli sesso/cittadinanza di RCS.

## Dati esterni integrati

| Fonte ISTAT | Vincolo | Riscontro |
|---|---|---|
| [STRASA 2025](https://demo.istat.it/app/?i=STR&a=2025&l=it) | Stranieri per comune, sesso ed età 0–99/100+ | 7.896 comuni, 1.594.992 celle esplicite; riconciliazione regionale |
| [RCS 2025](https://demo.istat.it/app/?i=RCS&a=2025&l=it) | Residenti per comune, sesso e singola cittadinanza | 196 categorie; riconciliazione con M4, STR e tutti i livelli territoriali superiori |

Il [contratto degli originali](../contracts/istat-citizenship-v1.json)
fissa URL, SHA-256, byte, intestazioni, righe, data e dizionario delle
cittadinanze. CSV ufficiali in ZIP: circa 2,84 MB STR comunale, 1,99 MB RCS,
14,6 kB STR regionale. I file sono acquisiti separatamente, con limiti e riuso;
nessun download dell'intera serie storica.

RCS contiene 267.367 righe su più livelli: i totali territoriali non si
sommano ai comuni. Le celle non presenti sono ammesse come zero solo dopo
la riconciliazione esatta delle partizioni esaustive con M4 e STR, oltre
ai conteggi per cittadinanza dei livelli superiori. Nessuna imputazione di
valori stimati, soppressi o sconosciuti. Attribuzione ISTAT, CC BY 4.0.

## Attributo e assunzioni

`citizenship_code` è una stringa a tre cifre, codificata secondo il dizionario
ISTAT incluso in `input.json` (`country_labels`): per esempio `100` Italia,
`201` Albania, `235` Romania e `999` Apolide. Non sono codici ISO alpha-2.
`999` non rappresenta un valore mancante. Gli apolidi sono inclusi nel totale
STR degli stranieri. Per la definizione adottata, la cittadinanza italiana
prevale quando una persona ne possiede anche un'altra; il modello assegna
una sola categoria statistica, non una lista di passaporti.

Sesso/età degli stranieri e totali per cittadinanza sono calibrati esattamente.
L'associazione fra **età e specifica cittadinanza è sintetica**, ottenuta
mescolando in modo deterministico le cittadinanze entro comune e sesso.
Non è calibrata la cittadinanza dei componenti della stessa famiglia.
Non si rappresentano acquisizioni, trasmissione ai figli, migrazioni o
cambiamenti di cittadinanza negli anni successivi.

## Comandi e riproduzione

```sh
uv run python scripts/run_logged.py --label "Fonti cittadinanza" --log .tools/citizenship-progress.log -- uv run itadb fetch-citizenship
# Riutilizzare l'inventario stampato e lo snapshot M4 verificato:
uv run python scripts/run_logged.py --label "Assegnazione cittadinanza" --log .tools/citizenship-progress.log -- uv run itadb synthesize-citizenship --base-run data/curated/m4/BASE_HASH --inputs data/state/citizenship-inputs-UUID.json
uv run python scripts/run_logged.py --label "Audit cittadinanza" --log .tools/citizenship-progress.log -- uv run itadb verify-citizenship --base-run data/curated/m4/BASE_HASH --run data/curated/citizenship/HASH
```

Su Windows il log è seguito con
`scripts/watch-progress.ps1 -LogPath .tools/citizenship-progress.log`.
Il runner stampa fase, batch, popolazione, tempo e misure RAM/disco.
Budget: 8 GiB RSS, 40 GiB nella directory di lavoro, 7.200 s, DuckDB 2 GiB e
due thread. I batch seguono quelli della base, fino a 5M; l'audit della base
è incluso nel tempo del runner. Sono limiti controllati fra fasi, non limiti
RAM imposti dal sistema operativo.

Il risultato contiene `input.json`, `report.json`, `manifest.json` e, per
ogni batch, persone arricchite, famiglie immutate e checkpoint. Il manifest
collega la base tramite run ID e checksum. Conservare base, originali,
sorgenti archiviati e lockfile per ripetere le verifiche. Un retry ricalcola
gli audit; un file corrotto non viene sostituito. I tentativi incompleti sono
conservati nello stato o in quarantena.

Le fixture di carico sono separate dai dati ISTAT e richiedono una base
`invented_load_fixture` prodotta da `scripts/benchmark_m4.py`:

```sh
uv run python scripts/benchmark_citizenship.py --base-run data/curated/m4/FIXTURE_HASH --recovery
# Una root separata consente il confronto con ordine invertito:
uv run python scripts/benchmark_citizenship.py --base-run data/curated/m4/FIXTURE_HASH --root data/state/citizenship-reproduction --reverse-order
```

Le [misure effettive](benchmarks/citizenship-2026-09-24.json) e le prove sono
riportate nella [validazione](validation.md#integrazione-della-cittadinanza).
Gli output restano locali (`public_release=false`). La diagnostica di rarità
include comune/sesso/età/cittadinanza; non è una garanzia di anonimato.
Si misurano 2.698.397 celle non vuote sotto 5 individui, contenenti 4.028.154
individui sintetici (6,8339%). Rispetto ai soli quasi-identificatori M4,
la cittadinanza aumenta la granularità; le celle includono inoltre un incrocio
sintetico non osservato, quindi non descrivono rarità individuale reale.
La revisione scientifica esterna e l'autorizzazione alla distribuzione dei
microdati non sono implicite nell'integrazione tecnica.

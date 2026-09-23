# Registro delle verifiche

## M3 — sintesi pilota

### Revisione v3 — coorti di nascita stabili

Verifiche del 23 settembre 2026. [Decisione](adr/0011-stable-birth-cohorts.md),
[schema e uso](synthesis-m3.md#proprietà-individuali-e-anno-di-nascita),
[nuovo riferimento unico](reviews/m3-birth-year-reference.md).

- `uv sync --locked`, Ruff check/format e mypy: passati.
- **189 test Python non integration passati**, di cui **85** su demografia,
  sintesi e input M3. Verificati età zero, soglie 18/65, 99 e 100+, avanzamento
  annuale anche oltre 100, domini stretti, corruzione dei campi e dei metadati,
  tutte le celle sesso/età, versioni v1/v2 rifiutate senza alterazioni,
  determinismo, concorrenza, retry, quarantena e mancato completamento dopo errori.
- **15/15 repliche ufficiali v3 generate offline**, senza nuove acquisizioni:
  123.360 persone virtuali e 60.468 famiglie per replica. Ogni replica ha
  123.327 anni di nascita sintetici puntuali e 33 limiti superiori per 100+.
- Confronto diretto delle età ricostruite dal Parquet con il CSV ISTAT:
  **3.030/3.030 celle esatte**, errore massimo zero. I 33 record 100+ conservano
  la distinzione dalla nascita puntuale: non sono trasformati in centenari esatti.
- Confronto individuale con tutte le repliche del riferimento v2: identità,
  sesso, appartenenza e adulto di riferimento invariati su **1.850.400 record**.
  I 15 Parquet delle famiglie sono identici per checksum.
- Verifica indipendente e retry passati: **34/34 file v3 invariati**;
  **136/136 file storici conservati**. Nessun esperimento precedente riscritto.
- I **38 test integration sono esclusi**, non eseguiti in questa revisione;
  suite web e Docker non ripetute. Non cambiano DB, HTTP o frontend.
  Due warning di deprecazione Starlette/AnyIO già presenti nella suite Python.

Esperimento:
`7ffa65715dd035357e71f33feed373528b2cfe490393be318cb898e841dc98ce`.
Input `m3-input/2`, persone `m3-persons/3`, rapporto `m3-report/3`, algoritmo
e audit `3.0.0`. Riferimento `m3-reference/2`: classe 6+ = 6, seed 1701.
La selezione rimane documentale; formula e semantica della nascita sono
registrate e verificate nei metadati eseguibili `person_model`.

Generazione e audit: **4,3 s**; accettazione completa con confronto v2/ISTAT,
checksum, rilettura e retry: **7,3 s**. Singola esecuzione locale, con la
suite test in parallelo: non è una misura di capacità nazionale o del picco RAM.
Log: `.tools/m3-birth-year-checks.log` e `.tools/m3-birth-year-progress.log`.
Evidenza aggregata:
`data/reports/m3/acceptance-birth-year-7ffa65715dd035357e71f33feed373528b2cfe490393be318cb898e841dc98ce-c455c572ddbe41f197c35da145e18c5b.json`.

La regola annuale preserva la calibrazione iniziale; non simula mortalità,
nuovi nati o evoluzione familiare. Le età future derivano dalla convenzione,
non da nuove osservazioni. Restano i limiti scientifici e di distribuzione M3.

### Correzione prima del merge: staging dei retry

Il rilievo di revisione sulla PR #14 segnalava che ogni retry riuscito creava
una directory `m3-attempt-*` contenente soltanto l'input. La preparazione
calcola ora l'hash dell'input in memoria; lo staging viene creato sotto lock
soltanto quando manca un esperimento completato da riutilizzare.

Ruff check/format, mypy e **160 test Python non integration passati**.
Il test di concorrenza/retry verifica che due invocazioni e tre retry successivi
non lascino nuove directory di tentativo, preservando un tentativo precedente
interrotto e i checksum degli output. Restano verificati quarantena e
conservazione delle evidenze in caso di errore. Nuova rilettura del run di
riferimento `ee50a4c577b6462db82c909ea54b092ddc8346c4b8d6463286f848e55d3219a0`
passata, senza rigenerare o modificare dati. Log: `.tools/m3-merge-checks.log`.
La correzione riguarda il ciclo dei tentativi, non il metodo statistico o
la replica di riferimento scelta nella revisione umana.

### Chiusura della revisione umana di progetto

Il 23 settembre 2026 l'utente accetta il modello familiare casuale vincolato
come prima versione e stabilisce la graduatoria età/sesso → geografia → famiglie.
L'[esito della revisione](reviews/m3-human-review.md) adotta un riferimento unico,
6+ = 6 e seed 1701, con razionale, run, replica e checksum. Le altre repliche
rimangono sensibilità; i risultati precedenti non sono stati riscritti.

Verifica ripetuta del run `ee50a4c577b6462db82c909ea54b092ddc8346c4b8d6463286f848e55d3219a0`:
integrità e ricalcolo SQL delle 15 repliche passati; replica selezionata con
123.360 persone, 60.468 famiglie e 929 adulti non assegnati. Controllati
87 collegamenti documentali e la coerenza dei valori con manifest/report/Parquet.
Log della verifica: `.tools/m3-review-progress.log`.
Questa modifica è documentale: codice, contratti, input e output immutati;
suite applicative locali non ripetute. La CI della PR controlla il commit.

**M3 accettato per proseguire in M4** secondo il [piano](plans/m4-national-synthesis.md).
L'esito riguarda la revisione umana di progetto, distinta dalla revisione
scientifica esterna e disclosure, che restano non svolte. Non attesta una
distribuzione comunale o prestazioni nazionali già implementate.

### Revisione v2 — sesso ed età esattamente uguali a ISTAT

Verifiche del 23 settembre 2026, dopo la richiesta di corrispondenza 1:1.
[Metodo attuale](adr/0009-exact-demographic-calibration.md) e
[procedura](synthesis-m3.md). Gli esiti v1 più sotto sono storici.

- `uv sync --locked`, Ruff check/format e mypy: passati.
- **160 test Python non integration passati**, di cui **56 M3**. Coperti
  conteggi esatti, zeri, tutto M/tutto F, classe 100+, seed/scenari,
  input incoerenti, versioni storiche, conservazione delle release, retry,
  quarantena e ricalcolo dei report. Lo scambio di sesso tra due età che
  lascia invariati i margini per fascia viene rilevato dal nuovo audit.
- **15/15 repliche ufficiali rigenerate** dagli otto originali già archiviati,
  senza nuove acquisizioni. Ogni replica contiene 123.360 record virtuali
  e 60.468 famiglie; maschi 60.413, femmine 62.947.
- Confronto diretto del CSV ISTAT originale con i Parquet: **3.030/3.030
  celle uguali** (202 per replica), errore massimo **0**. Anche TVD ed errore
  medio di calibrazione sono zero. Maschi di 68 anni: 766; classe 100+:
  6 maschi e 27 femmine, esattamente come nella fonte.
- Retry identico e rilettura indipendente completa passati; checksum di
  tutti i nuovi file invariati. I **102 file dei tre esperimenti precedenti**
  risultano tutti immutati.
- Nessuna modifica DB/API/web. Le suite DB e web non sono state rieseguite
  localmente per questa revisione; la [CI della PR](https://github.com/matik81/itadb/pull/14/checks)
  verifica Python, PostgreSQL, web e Compose sul commit proposto.

Nuovo esperimento:
`ee50a4c577b6462db82c909ea54b092ddc8346c4b8d6463286f848e55d3219a0`.
Input `m3-input/2`, rapporto `m3-report/2`, algoritmo e audit `2.0.0`.
Manifest con sorgenti effettivi archiviati, commit precedente e working tree
dirty: il run è stato eseguito prima del commit della revisione.

| Ipotesi dimensione 6+ | Residuo adulto non assegnato | Famiglie con minori, intervallo tra 5 seed | Famiglie solo 65+, intervallo tra 5 seed |
|---|---:|---:|---:|
| 6 | 929 | 15.381–15.564 | 8.802–8.927 |
| 7 | 503 | 15.356–15.429 | 8.731–8.965 |
| 8 | 77 | 15.248–15.409 | 8.806–8.916 |

La congiunta sesso/età è fissa e calibra ogni replica; **non è più un holdout**.
La variabilità della tabella riguarda le famiglie del modello. Non sono
disponibili statistiche osservate inutilizzate per validazione fuori calibrazione;
il rapporto lo dichiara. Restano da svolgere revisione scientifica esterna
e valutazione disclosure; nessun microdato è distribuito.

Generazione e audit: **4,78 s** in una singola esecuzione locale, **10.615.513 byte**
complessivi. Windows AMD64, Python 3.13.15, DuckDB 1.5.5; stesso limite DuckDB
di 256 MB/un thread, senza misura del picco RAM o capacità nazionale.
Evidenze locali: `data/curated/m3/HASH/`,
`data/reports/m3/acceptance-exact-HASH-83f49c2f744c48a29552e24cbd1aa68b.json`,
log per tentativo, `.tools/m3-exact-progress.log` e `.tools/m3-exact-tests.log`.

### Storico v1 — congiunta sesso/età fuori calibrazione

Verifiche locali del 23 settembre 2026. [Perimetro e procedura](synthesis-m3.md),
[metodo e revisione](adr/0008-synthesis-pilot.md).

- `uv sync --locked`, Ruff check/format e mypy: passati.
- Suite Python non integration: **149 passati**, di cui **45 nuovi test M3**.
  Coprono ricostruzione intera, zeri, limiti, margini impossibili, vincoli
  familiari, namespace fixture, provenienza, vintage, stati, idempotenza,
  concorrenza, assenza di completamento dopo errore e corruzione dei Parquet.
  Un report alterato e nuovamente hashato viene rifiutato dal ricalcolo SQL.
  La modifica del solo holdout mantiene identici tutti i Parquet.
- PostgreSQL/PostGIS: **38 test passati** su database dedicato
  `itadb_m2_test_7a2dfa2ef947`; migrazioni applicate due volte. Nessuna modifica
  allo schema M3 o ai dati applicativi; database/evidenze di test conservati.
- Web: `npm ci`, tipi API rigenerati senza diff, typecheck, format check,
  **17 test passati** e build. OpenAPI esportata senza diff. Nessuna modifica
  alla UI o al contratto HTTP.
- Immagine applicativa costruita con il trust store locale già configurato;
  smoke Linux senza rete passato: generazione della fixture inventata,
  quattro repliche, retry e verifica indipendente. Container e artefatti
  conservati in `itadb-m3-smoke-20260923`; log `.tools/m3-docker.log`.
- Restano warning di deprecazione già presenti da Starlette/AnyIO/Alembic;
  non sono test saltati. I 38 test esclusi dalla suite rapida sono stati
  eseguiti nella suite PostgreSQL separata.

Esecuzione ufficiale: inventario di otto originali verificati, compreso il
nuovo campione ISTAT di 306 celle/26.579 byte. Due richieste esplorative
ristrette a indicatori familiari aggiuntivi hanno restituito 404: nessun
risultato da esse entra nel pilota. L'acquisizione demografica e la
riconciliazione POP21/FAM21 sono riuscite; nessun download massivo.

Esperimento locale completato:
`e1e286dd737e18d70f7e13bb98cb208574ba2fee97bc47b423421fd992bd8457`.
Il manifest registra sorgenti effettivi, lockfile, runtime, commit precedente
e working tree dirty: l'esecuzione precede il commit della modifica.
15/15 repliche, ciascuna con 123.360 persone virtuali e 60.468 famiglie,
tutti i gate strutturali superati e massimo errore di calibrazione **zero**.
Retry: identità e checksum di **tutti** i file invariati; verifica indipendente
successiva ricalcolata per tutte le repliche.

| Ipotesi dimensione 6+ | Residuo adulto non assegnato | Famiglie con minori, intervallo tra 5 seed | Famiglie solo 65+, intervallo tra 5 seed |
|---|---:|---:|---:|
| 6 | 929 | 15.352–15.523 | 8.810–8.887 |
| 7 | 503 | 15.324–15.458 | 8.794–8.925 |
| 8 | 77 | 15.226–15.344 | 8.799–8.968 |

Sono statistiche del **modello**, non osservazioni o intervalli di confidenza.
La congiunta sesso/età fuori calibrazione ha TVD **0,0209468223**, errore
assoluto medio **25,5842** e massimo **86 persone per cella** in tutte le
repliche. Per esempio, tra i maschi di 68 anni la baseline genera 680 contro
766 osservati. La metrica stabile tra seed riflette l'arrotondamento stabile;
non elimina il bias dell'ipotesi d'indipendenza entro fascia. Non è stata
fissata a posteriori una soglia per dichiarare valido il modello.

Misura locale singola: preparazione, generazione e audit in **4,30 s**;
30 Parquet più input/report/manifest occupano **10.627.232 byte**.
Windows AMD64, Python 3.13.15, DuckDB 1.5.5, DuckDB a un thread e limite
256 MB. Il limite DuckDB non è una misura della RAM totale del processo;
picco RSS, concorrenza di carico e capacità nazionale **non misurati**.
Nessuna estrapolazione a M4. Evidenze locali escluse da Git:
`data/curated/m3/HASH/`, `data/reports/m3/acceptance-HASH.json`, log per tentativo,
`.tools/m3-progress.log`, `.tools/m3-integration.log`, `.tools/m3-web.log`.

La revisione indipendente eseguita è software, con rilettura SQL separata.
**Revisione scientifica umana esterna e valutazione disclosure non eseguite**;
composizioni familiari non validate rispetto a una congiunta osservata.
Gli esperimenti restano locali, `experimental_not_certified`, senza
pubblicazione di microdati nelle API, nel web o nella PR.

Verifica eseguita il 23 settembre 2026. Repository pubblico:
[matik81/itadb](https://github.com/matik81/itadb).

## Controlli locali Windows

- Python 3.13.15: 24 test unitari/contratto superati; 3 test di integrazione richiedono
  PostgreSQL e sono eseguiti separatamente in GitHub.
- Ruff lint e format, mypy strict: superati.
- Generazione OpenAPI e tipi TypeScript verificata; nessuna connessione DB necessaria.
- Frontend: TypeScript, 3 test Vitest, Prettier e build Vite superati.
- npm audit: zero vulnerabilità note alla data del controllo.
- `git diff --check`: nessun errore nel diff finale.
- Generazione SQL Alembic offline: riuscita.

I test Python emettono due avvisi di deprecazione upstream (TestClient/httpx e alias
AnyIO); non sono errori applicativi. Le dipendenze sono bloccate in uv.lock e aggiornabili
tramite Dependabot. L'audit pip-audit locale non ha completato per il trust store Requests;
lo stesso controllo è stato eseguito con successo in CI Linux, senza disabilitare TLS.

## PostgreSQL e container su GitHub Actions

[CI completa passata](https://github.com/matik81/itadb/actions/runs/35795918660):
unit/contratti, frontend, migrazioni ripetute, integrazione PostgreSQL/PostGIS e smoke
Docker Compose. Il percorso di importazione demo è stato eseguito contro un DB reale;
testati idempotenza, immutabilità, privilegi reader, paginazione, rollback del gate e
pruning a una partizione. Il Compose costruisce entrambe le immagini, avvia i servizi,
importa la demo e verifica web e API attraverso Nginx.

[Audit dipendenze passato](https://github.com/matik81/itadb/actions/runs/35795812590):
pip-audit e npm audit. Questi controlli rilevano vulnerabilità conosciute nei pacchetti;
non costituiscono una revisione di sicurezza completa del prodotto.

La prima esecuzione ha individuato una compilazione errata dei `%s` nella funzione
PostgreSQL `format()`. Corretta la compilazione tramite SQLAlchemy TextClause; nuovo
upgrade da database vuoto e avvio Compose riusciti. Le correzioni sono nella cronologia.

## Prova di capacità colonnare

`uv run python scripts/benchmark.py`, 1.000.000 righe artificiali, DuckDB 1.5.5,
Windows, limite 1 GiB e 4 thread: Parquet 1.817.914 byte, scrittura circa 0,091 s,
aggregazione su 8.000 codici circa 0,008 s. Dati regolari a bassissima entropia, cache
non controllata: prova funzionale del percorso colonnare, **non** stima di produzione
o benchmark della popolazione italiana. Nessun test nazionale 1:1 è stato eseguito.

## Configurazione GitHub verificata

Repository pubblico, branch principale main, CODEOWNERS @matik81, Discussions abilitate,
cancellazione automatica dei branch dopo merge. Abilitati segnalazioni private di
vulnerabilità, Dependabot security updates, secret scanning e push protection.
Le protezioni del branch si verificano nelle impostazioni GitHub; il relativo stato
non si deduce dalla sola presenza della CI.

## Limiti della verifica iniziale dello scaffold

La verifica iniziale dello scaffold non comprendeva import live ISTAT/Eurostat,
validazione statistica reale, test di carico concorrente, generazione della popolazione
sintetica o deploy pubblico dell'applicazione. Il primo campione live è descritto sotto.
Nessun controllo visuale nel browser: frontend verificato con component test e build.
Docker/PostgreSQL non sono stati installati su questa macchina; i test corrispondenti
sono stati eseguiti in runner GitHub isolati. Per le installazioni locali vedere
[local-environment.md](local-environment.md).

## Primo onboarding ISTAT, 23 settembre 2026

Incremento successivo allo scaffold nella stessa giornata:

- `uv sync --locked`, Ruff lint/format e mypy: superati.
- **75 test Python unitari/contratto superati**; 3 test PostgreSQL esclusi con
  `-m "not integration"`. Restano i due avvisi upstream descritti sopra.
- Baseline frontend rieseguita: typecheck, 3 test Vitest e build superati.
  Nessuna modifica al frontend, alle dipendenze o al contratto OpenAPI.
- Acquisizioni live ISTAT selettive: dataflow, DSD/codelist e CSV di 21 osservazioni
  (20 regioni e Italia) per il 1° gennaio 2024. Licenza e metadati conservati.
- Controllo CLI sul campione ufficiale: tutti i gate passati, somma regionale e
  totale nazionale pari a 58.971.230; campione di quattro righe revisionato tra
  risposta originale e rapporto. Non è un confronto statistico tra fonti indipendenti.
- Seconda esecuzione offline sugli stessi input: stesso percorso, SHA-256 e data
  di modifica del rapporto. Nei test, dati invalidi producono quarantena senza
  rapporto di successo; evidenze modificate non vengono sovrascritte.
- `git diff --check`: superato. Nessun originale acquisito incluso in Git;
  fixture numerica inventata e metadati ridotti con attribuzione separata.

Rapporto locale di questa verifica:
`data/reports/istat-population-84c0e35d-1064-5215-b85c-4e2502643c9b.json`.
Il nome dipende dagli input e dai manifest di acquisizione, non è un ID di release.
[Procedura, hash, licenza e limiti](sources/istat-population.md).

Nessuna pubblicazione ufficiale in DB/API/web, nessuna migrazione e nessun test di
integrazione PostgreSQL eseguito in questo primo incremento. La pubblicazione
successiva, descritta sotto, completa il [piano](plans/m1-istat-population.md).

## Pubblicazione ISTAT locale, 23 settembre 2026

Secondo incremento, con Docker Desktop disponibile e PostgreSQL 17.5/PostGIS 3.5
in container. I test usano un server separato dallo stack applicativo.

- **90 test Python superati: 77 unitari/contratto e 13 di integrazione PostgreSQL**,
  nessun test saltato nell'esecuzione completa. Ruff lint/format e mypy superati.
  Restano avvisi upstream TestClient/httpx, AnyIO e configurazione Alembic.
- Frontend: typecheck, **4 test Vitest**, Prettier e build Vite superati.
  OpenAPI esportata e tipi TypeScript rigenerati; route e schemi di risposta v1
  confrontati con la versione precedente e identici.
- Migrazione 0002 verificata da database vuoto, ripetuta e applicata a una demo
  già pubblicata. Testati privilegi reader, vincoli territoriali e temporali,
  revisione con predecessore esplicito, idempotenza e concorrenza, rifiuto di fork,
  mancata pubblicazione per dati invalidi, artefatti mancanti, gate falliti e
  rollback dopo COPY. Nessuna migrazione applicata riscritta.
- Piano di query su **20.000 righe artificiali**: una partizione, accesso tramite
  indice e pagina di 51 righe. Un'esecuzione ha misurato 1,249 ms di pianificazione
  e 0,294 ms di esecuzione; cache non controllata, nessuna stima nazionale.
  Evidenza: `data/reports/m1-query-plan-25c89092-e119-4c74-af39-0e2c9f387a87.json`.
- Backup pre-0002 conservato in `.tools/backups/itadb-before-0002-20260923.dump`.
  **Restore realmente eseguito** nel database isolato `itadb_m1_restore_20260923`:
  versione schema 0001, ID, checksum originale e conteggio della demo verificati.
- Stack locale ricostruito e avviato, migrazione applicata e originali ISTAT
  pubblicati nel catalogo applicativo. Ripetere l'import riusa la stessa release.
  Archivio originale, metadati, licenza e rapporti nel volume `itadb_evidence`.
- Verifica HTTP attraverso Nginx: tutte le **21 osservazioni e i quattro attributi
  upstream** coincidono con il CSV acquisito, anche paginando a 7 righe. Totale
  regionale 58.971.230, **72 controlli qualità passati e 12 artefatti registrati**.
  Readiness positiva; v1 continua a mostrare la demo e non espone le release v2.
- Verifica visiva con Chrome headless a 1440 px e 600 px; evidenze in
  `data/reports/m1-web-final-desktop.png` e `data/reports/m1-web-narrow.png`.
  Nessuna verifica interattiva completa o su dispositivo mobile fisico.

Release corrente: `eaef6df9-96db-58bd-9b9d-9e203d89d030`, successiva a
`4d602369-9057-57a0-9942-9d0ac9bcb91e`. La revisione rende portabili i checksum
dei contratti tra Windows e Linux (terminatori LF); tutti i valori statistici
sono invariati e la prima release resta consultabile. Rapporto di verifica HTTP:
`data/reports/m1-publication-eaef6df9-96db-58bd-9b9d-9e203d89d030.json`.

M1 è completata per il solo snapshot regionale del 1° gennaio 2024. Non sono
stati eseguiti un deploy pubblico, una nuova CI remota di queste modifiche,
una validazione statistica indipendente o un benchmark nazionale. La data di
pubblicazione upstream rimane non accertata; gli stati senza flag non sono
convertiti in dati osservati. Storia territoriale e altri periodi restano in M2.

## M2 — 23 settembre 2026

- Perimetro e fonti: [onboarding M2](sources/istat-m2.md), 14 originali revisionati,
  317 selezioni serie/periodo, 22.678 osservazioni, 24.091 versioni territoriali,
  2.815 equazioni e riconciliazione dei cambi di codice tra tre snapshot.
- Accettazione ufficiale su PostgreSQL isolato e nello stack Compose locale:
  pubblicazione atomica, retry idempotente, confronto integrale Parquet/DB,
  45 gate superati e otto artefatti con inventario di provenienza.
- Audit geometrico realmente eseguito: 25 riparazioni revisionate con variazione
  d'area ≤ 4,1×10⁻¹⁵; originali conservati. Province/regioni derivate dall'unione
  dei comuni dopo aver misurato incoerenze nei confini fonte tra livelli.
  Rapporti locali `m2-geometry-audit.json` e `m2-hierarchy-audit.json` in `data/reports/`.
- Release ufficiale **`85e67cbd-ced9-5a5d-85b5-8e1b2ca3141e`**, riprodotta con lo
  stesso UUID su Windows e Linux grazie ai terminatori LF dei JSON generati.
  Evidenze applicative nel volume `itadb_evidence`; fixture solo nei DB di test.
- Verifica HTTP attraverso Nginx: **16.147 osservazioni confrontate** con gli
  input, sei serie incluse famiglie comunali, età 0 e 100+, tutti gli attributi
  upstream, paginazione a 500, otto eventi/15 collegamenti, confini e compatibilità v1.
  Rapporto `data/reports/m2-http-acceptance.json`.
- Backup pre-M2 ripristinato realmente in `itadb_m2_restore_386e34f94dec` e
  aggiornato due volte a 0004: tre release M0/M1 conservate con UUID/hash/conteggi.
  Backup fuori Git; rapporto `data/reports/m2-backup-restore.json`.
- [Benchmark su 1.024.000 aggregati inventati](benchmarks/m2.md): circa 30 s di
  caricamento, p50 1,79 ms e p95 2,36 ms SQL; indice e pruning verificati.
  Nessuna misura di sintesi nazionale, picco RSS o SLA.
- Test offline, PostgreSQL/PostGIS e web coprono inventario/fonte modificata,
  partizioni sovrapposte, vintage errato, gerarchie, crosswalk, concorrenza,
  revisioni senza fork, modifiche draft prima della pubblicazione, privilegi
  reader, immutabilità e rollback dopo COPY. Il web verifica cambio periodo,
  categoria, livello e reset della paginazione. OpenAPI e tipi client rigenerati.
  Esito locale: **103 test offline, 23 di integrazione, 5 web passati**; Ruff,
  formattazione, mypy, TypeScript, build web e installazione lock verificati.
  Gli schemi API preesistenti e tutte le route v1 sono invariati.
- **26 controlli** nella verifica visuale e interattiva con **Playwright 1.63.0 e Chrome
  153.0.8010.53** su Windows, contro lo stack reale `http://localhost:8080`.
  Controllati desktop a 1440 px e viewport a 768, 390 e 320 px: nessun overflow
  orizzontale della pagina; tabelle scorrevoli internamente, categoria completa
  leggibile, provenienza e checksum consultabili. Nessuna prova su dispositivo
  mobile fisico, altri motori browser o deploy pubblico.
- Nel browser: filtri periodo/categoria/livello e unità, totale nazionale 2024,
  due pagine comunali senza duplicati, ritorno alla prima pagina, reset cursore,
  107 province in pagine da 100 e 7, selezioni prive di copertura, 15 crosswalk,
  apertura dei confini, catalogo 2020 e otto artefatti. Verificati Tab, cambio
  periodo con freccia e collegamento «Vai ai dati».
- La verifica ha riprodotto un HTTP 429 durante cambi rapidi: il web ricaricava
  qualità e artefatti a ogni filtro/pagina. Ora questi metadati sono acquisiti
  solo al cambio release o retry; una sequenza di 15 transizioni rapide passa
  senza 429, con una sola richiesta per coverage/quality/artifacts. Il test
  componente controlla anche il numero delle richieste. Il limite Nginx rimane
  attivo: tre ritorni rapidissimi da pagine JSON possono raggiungerlo; verificati
  messaggio esplicito e recupero con «Riprova» dopo un intervallo.
- Corretta anche la leggibilità delle categorie lunghe su mobile: il titolo
  completo appare sotto i filtri e le età sono ordinate numericamente nel menu.
  Errori 503 simulati con intercettazione Playwright per osservazioni, qualità
  e crosswalk: messaggi e retry verificati, senza dati inventati. Nessun errore
  JavaScript rilevato nella sessione principale.
- Evidenze locali fuori Git: `data/reports/m2-ui-playwright.json`,
  `m2-ui-progress.log`, `m2-ui-trace.zip`, `m2-ui-desktop-final.png`,
  `m2-ui-mobile-filters.png`, `m2-ui-mobile-table.png`,
  `m2-ui-mobile-evidence.png` e `m2-ui-desktop-history.png`, nella stessa cartella.
  Test web, TypeScript, formattazione e build ricontrollati dopo le correzioni.

M2 è completa per il perimetro dichiarato. Non implica storia amministrativa
continua, tutti gli anni/indicatori per comune o una validazione statistica
indipendente. La creazione dei circa 60 milioni di individui virtuali rimane M4.

## Scheda territoriale M2 con mappa — 23 settembre 2026

Il nome del territorio ora apre una scheda nella web app, anziché navigare
direttamente alla risposta JSON. Il dato mostrato coincide con la riga selezionata;
fonte, periodo, snapshot, stato upstream e licenza sono visibili. La mappa SVG
proietta in Mercatore il confine pubblicato, mantiene isole e anelli interni e
offre zoom, trascinamento e comandi da tastiera. Un collegamento distinto scarica
una Feature GeoJSON con coordinate originali della risposta API e provenienza.
Non sono state aggiunte dipendenze, sorgenti esterne, API o migrazioni.

- **16 test web superati**, inclusi proiezione/orientamento, poligoni multipli
  e anelli interni, geometrie malformate, identità release/territorio, valori
  mancanti, errore/retry, zoom e download esplicito. TypeScript, Prettier e build
  superati; ricostruito il frontend nello stack Compose locale.
- **Playwright 1.63.0 / Chrome 153.0.8010.53**: clic e rendering reale di tutte
  le 20 regioni dello snapshot 2024, incluse le 52 parti della Sicilia e le 170
  della Sardegna. Verificata inoltre la scheda famiglie Piemonte 2021, la provincia
  di Torino e il comune di Reano nella seconda pagina comunale. Chiusura con
  pulsante/Escape, ritorno del focus, confinamento del Tab e conservazione di
  filtri, categoria e paginazione verificati nel browser.
- Provati zoom, frecce, trascinamento mouse, ripristino vista completa e input
  touch emulato. Download `.geojson` realmente salvato e letto: Feature valida
  con geometria, territorio, release, snapshot e licenza. Viewport a 1440, 768,
  390 e 320 px: mappa visibile all'apertura su mobile, nessun overflow orizzontale
  nel dialog, chiusura disponibile anche dopo lo scorrimento.
- Risposta confine 503 simulata: dato ancora leggibile, nessuna geometria
  inventata, retry riuscito. Caricamento rallentato e chiusura anticipata provati:
  richiesta annullata e apertura successiva della Sicilia corretta. Nessun errore
  JavaScript; unico errore HTTP nella sessione principale: il 503 introdotto dal test.
- Evidenze locali fuori Git in `data/reports/`: `m2-map-playwright.json`,
  `m2-map-progress.log`, `m2-map-trace.zip`, `m2-map-piemonte-desktop.png`,
  `m2-map-piemonte-mobile.png`, `m2-map-sicilia.png`, `m2-map-sardegna.png`,
  `m2-map-320-statistic.png`, `m2-map-error-503.png` e
  `m2-map-piemonte-download.geojson`.

Verifica limitata a Chrome e dispositivi emulati. Il confine è semplificato per
la consultazione e non è una carta catastale o stradale.

## Tabelle e icone M2 — 23 settembre 2026

Entrambe le tabelle offrono pulsanti crescenti/decrescenti nelle intestazioni,
con stato `aria-sort`, e filtri per selezione. Le osservazioni filtrano regione
o provincia padre e stato, con ricerca letterale per nome/codice. Lo storico
filtra tipo di variazione e utilizzo. Ogni modifica riparte dalla prima pagina;
il database ordina e filtra tutta la selezione prima di limitarne la pagina.
La colonna ripetitiva «Livello» è sostituita da icone territoriali accessibili.
Le schede hanno icone SVG locali distinte per persone, famiglie e abitazioni.
Le preferenze sono conservate in `apps/web/AGENTS.md`.

- **104 test offline, 25 di integrazione e 17 web superati**. I nuovi test
  PostgreSQL confrontano entrambe le direzioni su più pagine, valori numerici
  uguali e nulli, filtri combinati e ricerca contenente caratteri SQL trattati
  letteralmente. Le API respingono colonne, direzioni e filtri fuori elenco.
  Ruff, mypy, TypeScript, Prettier, build web e contratto OpenAPI verificati.
- Sulla release ufficiale locale: tutti i **7.904 comuni del 2021**, in 16 pagine
  da massimo 500 righe, coincidono con una query SQL indipendente sia in ordine
  numerico crescente sia decrescente; nessun ID duplicato o perso. Quattro
  `EXPLAIN (ANALYZE, BUFFERS)` conservati: prime pagine circa 14 ms, seconde
  circa 43–46 ms in questa esecuzione locale. È una misura di questa selezione,
  non uno SLA né un benchmark della futura popolazione sintetica.
- **16 controlli Playwright 1.63.0 / Chrome 153.0.8010.53**: regioni in entrambe
  le direzioni; Roma e Milano in testa ai comuni per popolazione decrescente;
  200 comuni su due pagine senza duplicati; filtro Torino con codice UTS `201`,
  ricerca Moncalieri, otto province del Piemonte, stato mancante e reset.
  Storico: scissioni, utilizzi strutturali/esatti, selezione vuota e data decrescente.
- Le tre icone nelle schede sono state controllate visivamente insieme alla mappa.
  Viewport 1440, 768, 390 e 320 px; pagina e scheda senza overflow orizzontale,
  tabelle scorrevoli internamente. Ordinamento da tastiera verificato.
  Errore 503 simulato nel catalogo dei territori padre: retry riuscito senza
  modificare periodo/categoria. Nessun errore JavaScript o HTTP inatteso.
- Evidenze locali fuori Git in `data/reports/`: `m2-tables-playwright.json`,
  `m2-tables-progress.log`, `m2-tables-trace.zip`, `m2-tables-query-plans.json`,
  screenshot `m2-tables-*.png`. Build e controlli registrati anche nel log
  `.tools/m2-progress.log`; API e web ricostruiti nello stack locale.

Nessuna nuova dipendenza, migrazione o modifica alle evidenze pubblicate.
Verifica browser limitata a Chrome e viewport emulati.

## Chiusura dei rilievi M2 prima del merge — 23 settembre 2026

Corretti tre rilievi della PR #13: readiness che non controllava le viste M2,
contesto degli eventi non ricontrollato dopo modifiche draft e contenimento
geometrico verificato soltanto durante il caricamento. La nuova revisione 0005
aggiunge i controlli alla pubblicazione senza alterare 0001–0004 o evidenze pubblicate.

- **104 test offline e 38 di integrazione superati**, Ruff/formattazione e mypy
  superati; OpenAPI e tipi client rigenerati senza cambiamenti al contratto.
  Tredici casi aggiunti: schema 0002 e singole viste M2 indisponibili, upgrade
  ripetuto con fingerprint invariati di release, osservazioni, geografie,
  artefatti e gate; eventi con date, livelli, cardinalità o pesi incoerenti;
  confini figli e padri alterati dopo il caricamento. I fallimenti lasciano
  run fallito e quarantena, senza release parziale.
- Ripetuta la stessa politica geometrica della pipeline: contenimento esatto
  per unioni dei figli, tolleranza del 2% per confini fonte. Provati uno
  scostamento ammesso e due rifiutati. La politica è esplicita nel dettaglio
  del gate `boundary_hierarchy` per le nuove pubblicazioni.
- Backup pre-0005 ripristinato in `itadb_m2_restore_d81007d8507e`, poi aggiornato
  due volte: quattro release con identità, hash originali e conteggi conservati.
  Tre piani `EXPLAIN (ANALYZE, BUFFERS)` delle nuove query su **24.088 confini e
  15 crosswalk** della release ufficiale: nessuna incoerenza; il controllo
  geometrico ha richiesto circa **3,57 s** in questa esecuzione locale.
  È un controllo batch alla pubblicazione, non una query sincrona della web app.
- Evidenze fuori Git: `data/reports/m2-review-backup-restore.json`,
  `data/reports/m2-review-query-plans.json`, backup `.tools/backups/itadb-before-0005-*.dump`
  e log delle operazioni `.tools/m2-progress.log`.

## M4 — scala nazionale 1:1

Verifiche locali del 24 settembre 2026. Dati e misure sono distinti dalle
prove precedenti. [Rapporto M4](synthesis-m4.md),
[dettaglio machine-readable](benchmarks/m4-national-2026-09-24.json).

### Input e output effettivi

- 15 originali fissati e archiviati. Famiglie 31/12/2024, popolazione e
  geografia 01/01/2025: ultimo riferimento comune verificato dall'inventario.
- Campione POSAS/SDMX: 612 celle identiche. POSAS nazionale: 805.392 righe;
  popolazione M/F per singola età, 100+ aperto, totali espliciti.
- 58.943.464 persone sintetiche; 26.670.169 famiglie; 560.159 adulti non
  assegnati. 7.896 comuni, 107 province/UTS, 20 regioni.
- 107 batch, 214 Parquet. Errore nullo su 1.594.992 celle comunali; input
  riconciliati anche con tutte le congiunte provinciali, regionali e nazionali
  e con le classi dimensionali delle famiglie ai livelli superiori.
- Rilettura indipendente successiva e retry nazionale: esito positivo,
  stesso run e stessi checksum; nessuna nuova directory di snapshot.
- Diagnostica disclosure: 362.643 celle non vuote comune/sesso/età sotto 5,
  851.968 persone sintetiche. Pacchetto aggregato: 400 celle regione/sesso/
  decade, 90+ raggruppato, minimo 483; nessuna distribuzione di microdati.

Snapshot nazionale:
`data/curated/m4/7a27c844410adf29262477114bfeecc3a55743a454dfd392d4708c8163858eb8`.
Il manifest registra gli hash dei sorgenti effettivi e il working tree dirty
precedente al commit. Hash di input, manifest, rapporto e aggregati nel JSON
delle misure; tutti i dati originali e sintetici restano fuori da Git.

### Benchmark realmente eseguiti

Windows AMD64, Ryzen 9 9900X, 24 CPU logiche, 65.939.009.536 byte RAM;
Python 3.13.15, DuckDB 1.5.5. Budget preventivi: RSS 8 GiB, directory di lavoro
40 GiB, tempo 7.200 s; DuckDB 2 GiB e due thread, massimo 5M per batch.

| Prova | Tempo runner monitorato | Picco RSS | Picco disco campionato | Audit indipendente successivo |
|---|---:|---:|---:|---:|
| 1M, fixture inventata | 1,58 s | 214,54 MiB | 3,38 MiB | 0,32 s |
| 10M, fixture inventata con interruzione/ripresa | 8,24 + 10,96 s | 999,50 MiB | 36,81 MiB | 4,40 s |
| 58.943.464, nazionale calibrato | 177,61 s | 1.114,90 MiB | 239,53 MiB | 28,65 s |

I tempi del runner comprendono generazione, audit inline e completamento
dei rapporti fino al controllo finale del budget; escludono acquisizione,
ammissione iniziale e parte della finalizzazione dei metadati. Il comando
nazionale completo ha impiegato 182,8 s; lo snapshot finale occupa
251.203.541 byte. Il disco è campionato ogni secondo nella directory di lavoro,
inclusi gli spill del generatore; archivio raw, precedenti run e log esterni
sono esclusi. Il picco RSS è quello dell'intero processo, non del solo DuckDB.
L'audit nazionale successivo ha misurato 603.820.032 byte di picco RSS.

La prova 10M contiene due tentativi: dopo 5M si provoca un'interruzione, poi
si verificano e riusano i checkpoint e si completano gli altri 5M. Il tempo
complessivo dello script, compreso audit finale e recupero, è 23,88 s. Non
viene presentato come tempo di una generazione continua senza interruzioni.
Una seconda generazione a 10M in una root separata, con ordine dei batch
invertito, ha prodotto tutti i 10 file identici (17,33 s).
Il retry nazionale completato ha richiesto 34,3 s compresa la ri-ammissione.
Queste misure sono locali, su una singola esecuzione per scenario; non sono
SLA, distribuzioni p95/p99 o stime di prestazioni su altri sistemi.

### Controlli del repository

- `uv sync --locked`, Ruff check/format, mypy per Windows e Linux: passati.
- Python non integration: **219 passati**, 38 deselected perché eseguiti
  separatamente; nessun test saltato nel perimetro selezionato.
- PostgreSQL su database dedicato `itadb_m4_test_7be9191e7d6d`, migrazioni
  eseguite due volte: **38 passati**, 219 deselected. Nessun volume eliminato.
- Frontend: `npm.cmd ci` (audit zero vulnerabilità), typecheck, format,
  **17 test**, build passati. OpenAPI e tipi client rigenerati senza drift.
- 30 nuovi test coprono parser/zeri dimostrati, dati mancanti/stimati,
  integrità, coorti, comuni/famiglie, ordine dei batch, recupero, checksum,
  rapporti/aggregati falsificati e budget superato senza completamento.
- Warning già presenti: deprecazioni Starlette/AnyIO e configurazione Alembic.

Nessuna nuova dipendenza, migrazione, endpoint o modifica della web app.
L'esito della CI è consultabile nei controlli della PR. Revisione
scientifica esterna, dinamiche demografiche, sensibilità nazionale tra seed
e distribuzione pubblica dei microdati **non eseguite**; non sono implicite
nella corrispondenza dei conteggi. [Valutazione e limiti](reviews/m4-disclosure.md).

## Integrazione della cittadinanza

Verifiche del 24 settembre 2026. [Metodo](citizenship.md),
[ADR 0013](adr/0013-citizenship-enrichment.md),
[misure e fingerprint](benchmarks/citizenship-2026-09-24.json).

- Sei originali fissati: STR comunale/regionale, RCS, pagine di definizione
  e licenza. RCS contiene 267.367 righe su cinque livelli territoriali;
  nessuna somma di totali sovrapposti. Copertura: 7.896 comuni, 196 categorie.
- Ammissione: ogni cella STR è entro il conteggio M4; ogni totale RCS per
  comune/sesso coincide con M4; stranieri RCS e STR coincidono. Riconciliate
  tutte le congiunte STR regionali e tutte le cittadinanze RCS a provincia,
  regione, ripartizione e Italia. Il campione preliminare Valle d'Aosta
  coincide su 8.821 stranieri complessivi.
- Risultato nazionale: 53.572.213 individui nella categoria italiana e
  5.371.251 nella popolazione straniera (di cui 525 apolidi), totale 58.943.464.
  Esatti 1.594.992 vincoli STR e 375.226 celle RCS comunali non nulle.
- 107 batch, 214 Parquet. Tutti i dieci attributi preesistenti sono uguali
  alla base, famiglie identiche byte per byte; aggiunta la sola colonna
  `citizenship_code`. Base originale conservata, nuovi run immutabili.
- Prova 10M interrotta dopo il primo checkpoint e ripresa con successo.
  Una generazione in root separata e ordine dei batch invertito ha prodotto
  tutti i nove file identici, in 12,69 s. Retry nazionale e riuso dei sei
  originali senza nuovi download verificati.
- Disclosure su comune/sesso/età/cittadinanza: 2.698.397 celle non vuote sotto
  5 individui, 4.028.154 individui sintetici coinvolti (6,8339%). Diagnostica
  tecnica, non rischio di identificazione misurato né certificazione.

Nuovo snapshot:
`data/curated/citizenship/d7ab8f19cc590fa6cba0a9ea9964f3ee0dcde5327b0019c8f63d48e896dab6a5`.
Base M4:
`7a27c844410adf29262477114bfeecc3a55743a454dfd392d4708c8163858eb8`.
Gli hash del codice finale coincidono con il descrittore del run; sorgenti
archiviati prima del commit, working tree dirty dichiarato.

| Prova | Runner monitorato | Picco RSS | Disco campionato | Audit successivo, inclusa base |
|---|---:|---:|---:|---:|
| 1M inventato | 1,24 s | 226,87 MiB | 3,51 MiB | 0,56 s |
| 10M inventato, due tentativi con recupero | 7,83 + 9,77 s | 1.066,99 MiB | 38,20 MiB | 6,60 s |
| 58.943.464 nazionale | 86,13 s | 1.093,04 MiB | 249,60 MiB | 45,07 s |

Macchina: Ryzen 9 9900X, 24 CPU logiche, Windows AMD64; Python 3.13.15,
DuckDB 1.5.5. Il runner include audit completo della base, arricchimento e
audit inline; esclude ammissione iniziale e parte della finalizzazione.
CLI nazionale: 92,2 s. Snapshot finale: 261.766.895 byte. Il disco è campionato
ogni secondo nella directory di lavoro: base, raw, altri run e log esterni
sono esclusi. Budget rispettati: 8 GiB RSS, 40 GiB disco, 7.200 s, DuckDB
2 GiB e due thread. Misure locali, non SLA o proiezioni per altri sistemi.

Controlli: **266 test Python non integration passati**, inclusi **47 nuovi
test** per STR/RCS, conservazione degli attributi, schema, recupero,
riproducibilità, corruzione, metadati alterati, artefatti inattesi e budget.
Ruff check/format e mypy Windows/Linux passati. OpenAPI senza modifiche.
I 38 test PostgreSQL sono esclusi dal comando locale di questa iterazione;
nessuna modifica a DB, API o frontend. La CI della PR esegue anche PostgreSQL,
web e Compose; il suo esito è nei controlli della PR.

Non eseguite: validazione osservata dell'incrocio età–singola cittadinanza,
calibrazione delle relazioni familiari per cittadinanza, revisione scientifica
esterna e distribuzione pubblica dei microdati. Il nuovo attributo resta
una categoria sintetica calibrata su fonti aggregate.

# M1 — pubblicazione regionale ISTAT

## Risultato

Pubblicare le 21 osservazioni già acquisite (20 regioni + controllo Italia,
1° gennaio 2024) in una release immutabile, interrogabile via API e web app.
Preservare DSD, codelist, licenza, flag e provenienza. Nessuna nuova acquisizione
statistica necessaria; usare gli originali conservati dall'onboarding.

## Decisioni

- Migrazione `0002` aggiuntiva; mai riscrivere `0001` o le evidenze precedenti.
- Revisioni lineari per dataset/periodo: predecessore e motivazione espliciti,
  lock transazionale e rifiuto di predecessori obsoleti. Retry identici riusano la release.
- Snapshot dei territori valido solo alla data verificata: intervallo giornaliero
  `[2024-01-01, 2024-01-02)`, namespace versionato dalla definizione territoriale,
  regioni figlie di Italia, esclusione di intervalli sovrapposti e controllo del periodo.
  Non equivale a una ricostruzione storica di confini, fusioni o scissioni.
- Stato `unflagged_upstream` e API v2: i client v1 conservano il contratto precedente
  e vedono solo release compatibili. UI migrata a v2, demo sempre riconoscibile.
- Estensione PostgreSQL inclusa `btree_gist` per l'integrità temporale:
  motivazione e alternative in ADR 0006. Nessuna dipendenza Python/npm aggiuntiva.

## Fasi completate il 23 settembre 2026

1. Schema revisioni/territori, viste v2 e contratto di pubblicazione.
2. Adapter Parquet e pubblicazione con COPY, quality gate, archiviazione e rollback.
3. API v2, OpenAPI/tipi generati e UI con livello territoriale, stato e revisioni.
4. Test PostgreSQL su DB dedicato: upgrade vuoto/ripetuto, integrità, retry,
   concorrenza, fallimenti, reader, paginazione e piano di query su volume artificiale.
5. Migrazione dello stack locale dopo test, import degli originali ufficiali,
   confronto API/CSV, verifica visiva dell'interfaccia e documentazione aggiornata.

Release corrente `eaef6df9-96db-58bd-9b9d-9e203d89d030`, con 21 osservazioni,
72 controlli qualità superati e 12 artefatti. Una revisione esplicita ha reso
portabili i checksum dei contratti senza cambiare i valori della prima release.
Verifiche: 90 test Python (13 PostgreSQL), 4 frontend, lint, tipi e build passati;
backup pre-migrazione ripristinato in un DB isolato. Dettagli ed evidenze nel
[registro delle verifiche](../validation.md#pubblicazione-istat-locale-23-settembre-2026).

## Verifica e limiti

Docker disponibile in questa sessione. Container di test separato
`itadb-m1-test-db`, porta locale 55432, volume persistente dedicato; non eliminare
volumi o evidenze. Il campione reale non è un benchmark nazionale.
`LAST_UPDATE` resta distinto dalla pubblicazione upstream non accertata (`null`).
I test usano conteggi inventati esclusivamente nel database di test.

# Consolidamento delle migrazioni

Su richiesta dell'utente, dopo il commit di prodotto `9cd934a`, le sei
revisioni iniziali vengono sostituite da `0001_baseline`, senza predecessori.
Il risultato è lo stesso schema finale, creato direttamente da un database vuoto.
Non è un reset dei dati: volumi, popolazione, release e originali restano conservati.

- [x] Commit separato della riorganizzazione del prodotto.
- [x] DDL consolidato con sole definizioni finali, senza ALTER o DROP intermedi.
- [x] Confronto su PostgreSQL/PostGIS tra la vecchia catena recuperata dal commit
  e la nuova baseline: schema e dati iniziali equivalenti, upgrade ripetuto riuscito.
- [x] Test aggiornati alla nuova radice; resta la verifica dell'immutabilità
  delle release pubblicate durante gli upgrade ripetuti.
- [x] Suite di integrazione: 41 test passati su PostgreSQL/PostGIS creato dalla
  baseline. Ruff, formattazione e mypy passano. Il precedente test separato di
  readiness a 0002 è integrato nel test di indisponibilità delle singole viste.
- [x] Schema statico dei database applicativo e di test confrontato con quello
  storico prima dell'allineamento; cambiato solo il registro Alembic. Conservate
  4 partizioni applicative e 16 di test. Health, catalogo e query individuale
  applicativi identici prima e dopo; upgrade successivo riuscito su entrambi.
- [x] Secondo commit dedicato al reset della storia delle migrazioni.

Per database precedenti a 0006 occorre prima completare la vecchia catena con
il codice storico. Non si può applicare la baseline sopra tabelle già esistenti.
La [procedura operativa](../operations.md#baseline-consolidata) distingue nuova
installazione e allineamento dei database già aggiornati. Le prossime modifiche
torneranno a usare nuove revisioni, senza riscrivere questa baseline.

Log locali, esclusi da Git: `.tools/migration-baseline-verification.log`,
`.tools/migration-baseline-tests.log`, `.tools/migration-baseline-adoption.log`.
Il confronto usa dump di solo schema normalizzati per spazi/commenti e senza
owner/grant, più confronto separato dei dati iniziali. Nessun dump è versionato.

# Pipeline
- Leggi docs/sources.md e docs/data-quality.md.
- Ogni nuova fonte ha contratto, licenza, fixture ridotta e test senza rete.
- Archivia gli originali con SHA-256, data di acquisizione e URL prima di trasformare.
- Aggiorna TRANSFORM_VERSION per ogni cambiamento semantico della normalizzazione.
- Non pubblicare dati con quality gate falliti. Conserva report di quarantena.
- Usa COPY e batch limitati; vietato caricare la futura popolazione nazionale in liste Python.
- La pipeline reale non può riutilizzare lo schema ITADB_DEMO o lo stato demo.

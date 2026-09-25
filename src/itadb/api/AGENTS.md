# API
- Leggi docs/api/README.md. Versiona le rotture del contratto con un nuovo prefisso.
- Usa esclusivamente lo schema api dell’archivio DuckDB in sola lettura.
- La readiness verifica archivio e schema; la liveness non dipende dal database.
- Mantieni Decimal in risposta come stringa. Null, zero e dato soppresso sono distinti.
- Verifica paginazione stabile, limiti, errori senza dettagli sensibili e indisponibilità DB.
- Rigenera OpenAPI e tipi TypeScript; non modificarli manualmente.

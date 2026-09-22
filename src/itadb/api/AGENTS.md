# API
- Leggi docs/api/README.md. Versiona le rotture del contratto con un nuovo prefisso.
- Usa esclusivamente le viste api e il ruolo reader; non l'URL amministrativo.
- La readiness verifica lo schema; la liveness non dipende dal database.
- Mantieni Decimal in risposta come stringa. Null, zero e dato soppresso sono distinti.
- Verifica paginazione stabile, limiti, errori senza dettagli sensibili e indisponibilità DB.
- Rigenera OpenAPI e tipi TypeScript; non modificarli manualmente.

# Database
- Leggi docs/data-model.md e docs/architecture.md prima di modificare il DDL.
- PostgreSQL/PostGIS è il riferimento: SQLite non è un sostituto nei test di integrazione.
- Non aggiungere JSONB o indici per ogni attributo di individui sintetici.
- Chiavi uniche delle tabelle partizionate includono la chiave di partizione.
- Mantieni le viste pubbliche ristrette alle versioni pubblicate e i grant minimi.
- Le operazioni distruttive richiedono un piano concreto di recupero; lo scaffold iniziale
  rifiuta il downgrade perché perderebbe evidenze. Testare upgrade da database vuoto.

# Piano corrente

Obiettivo: distribuire Itadb su Railway e Vercel tramite CLI, con aggiornamento
automatico dal branch GitHub `main`. Identificativi cloud e credenziali restano
nelle configurazioni locali escluse da Git.

- [x] Pubblicazione diretta dei Parquet e degli aggregati in nuovi archivi DuckDB.
- [x] Un solo percorso di configurazione; rimozione di servizi e strumenti dismessi.
- [x] Documentazione corrente; eliminazione di benchmark, piani ed esperimenti superati.
- [x] Verifica di idempotenza, revisioni, quarantena, ripristino, cartografia e API.
- [x] Pubblicazione nazionale verificata, build e prove locali di deployment.

- [x] Creare e configurare progetto/servizio Railway e volume persistente.
- [x] Trasferire e verificare il pacchetto DuckDB, attivare API e healthcheck.
- [x] Creare e configurare il frontend Vercel, URL API e CORS.
- [x] Collegare Railway a GitHub con deploy da `main` dopo i controlli CI.
- [x] Collegare Vercel a GitHub con deploy automatici e branch di produzione `main`.
- [x] Verificare configurazioni remote e risposte pubbliche; aggiornare la guida.
- [ ] Al prossimo push, confrontare il commit dei deployment di entrambi i provider.

[Esiti e limiti](docs/validation.md). Registrare separatamente il collegamento
GitHub, le prove HTTP e un aggiornamento effettivo da push.

## Consolidamento del deployment

- [x] Abilitare i controlli CI prima della promozione Vercel in produzione.
- [ ] Attivare monitoraggio periodico e verificare il carico con richieste limitate.
- [x] Sostituire la configurazione Railway legacy con impostazioni versionate.
- [ ] Verificare, pubblicare le modifiche e controllare i deployment automatici.
- [x] Aggiornare le guide senza dati personali o identificativi degli account.

Il backup cloud non è previsto per decisione dell'utente: il recupero parte dalla
popolazione preparata localmente o dalla rigenerazione con il metodo versionato.

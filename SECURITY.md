# Sicurezza

La versione 0.1 è un prodotto in sviluppo, senza SLA né hardening produttivo completo.
La sola linea supportata inizialmente è main. Non pubblicare credenziali o dati personali
in issue. Usare la segnalazione privata GitHub del repository quando abilitata; in sua
assenza contattare privatamente il maintainer attraverso un canale del suo profilo.

Il codice pubblico è read-only, ma questo non elimina abusi di risorse. Prima dell'esposizione:
TLS, gateway con rate limit, segreti gestiti, DB non pubblico, backup/PITR verificati,
monitoraggio e aggiornamenti di sicurezza. Il ruolo amministrativo appartiene solo alle
migrazioni; quello di pipeline va ulteriormente ristretto in produzione.

Non inviare identificativi reali a connettori o pipeline. Non tentare di collegare agenti
sintetici a persone. Vedi docs/operations.md per il confine operativo del prodotto.

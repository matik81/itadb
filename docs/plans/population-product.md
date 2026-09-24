# Popolazione sintetica come prodotto

## Richiesta e risultato

La popolazione verificata diventa il contenuto principale di PostgreSQL, API e
web app. Il workflow di generazione rimane eseguibile da CLI e documentato su
GitHub. Il prodotto ha due viste: esplorazione della popolazione su mappa scura
a schermo intero e spiegazione di fonti, integrazioni, assunzioni e verifiche.
I servizi gestiti (es. Vercel, Neon, Railway, Cloudflare) sono la destinazione
prevista; scelta del provider e deployment sono esplicitamente fuori ambito.

## Decisioni

- Nuova pubblicazione degli snapshot `population-reference/1` verificati;
  gli artefatti e i manifest storici rimangono immutabili.
- Individui e famiglie completi nel DB, con importazione COPY a blocchi,
  pubblicazione atomica e query parametrizzate, limitate e indicizzate.
- API v3 indipendenti dal filesystem della generazione e utilizzabili anche
  da un futuro client mobile. Le API v1/v2 conservano la compatibilità storica.
- Geografia dello stesso riferimento degli individui. I marcatori comunali
  rappresentano aggregati; nessuna residenza individuale inventata.
- Nessuna nuova dipendenza o servizio per disegnare la mappa corrente.

## Fasi e verifiche

- [x] Migrazione, importatore e controlli di pubblicazione degli snapshot.
- [x] API per catalogo, territori, persone, famiglie, distribuzioni e metodo.
- [x] Interfaccia operativa su mappa e sezione esplicativa collegata allo snapshot.
- [x] Documentazione e rimozione delle indicazioni correnti incompatibili.
- [x] Test di integrità, idempotenza, rollback, API e interfaccia.
- [x] Importazione nazionale locale, piani di query e misure effettive.

## Limiti espliciti

Il riferimento attuale non contiene coordinate di residenza. Il rendering
di punti individuali dipenderà dalla futura integrazione geografica, con
query per area visibile e livelli di dettaglio. Non si spediscono decine di
milioni di record al browser per ogni visualizzazione. La pubblicazione nel
DB locale non è un deployment Internet; nessun provider viene configurato.

Esito: popolazione nazionale importata e interrogata localmente. Verifiche e
misure effettive registrate in [validation.md](../validation.md#prodotto-popolazione--postgresql-api-v3-e-web-24-settembre-2026).

# Verifiche del progetto

I comandi riproducibili sono nel [README](../README.md#verifiche-di-sviluppo)
e nella [guida PostgreSQL isolata](local-environment.md#postgresql-dedicato-ai-test).
I controlli verificano il software e la conservazione dei vincoli; i limiti
scientifici sono descritti nelle [priorità di fedeltà](model-fidelity.md).

## Controlli del repository

La verifica del 24 settembre 2026 ha eseguito:

- 290 test Python e 43 test su PostgreSQL/PostGIS isolato, senza test selezionati saltati.
- 25 test frontend, TypeScript, Prettier e build Vite.
- Ruff, formattazione, mypy e controllo dei link Markdown locali.
- Installazione dai lockfile e rigenerazione di OpenAPI/tipi client senza differenze.
- Audit dipendenze Python/npm, senza vulnerabilità note segnalate.
- Build container API/web e controllo degli ingressi CLI e degli asset.

I log sono locali in `.tools/repository-review/` e `.tools/documentation-current/`.
Restano avvisi di deprecazione delle dipendenze di test. Non è stata eseguita
una nuova prova visiva interattiva del browser o una verifica scientifica esterna.

## Integrità della popolazione

Il riferimento verificato contiene **58.943.464 individui e 26.670.169 famiglie**,
in 107 batch, con run ID
`24a56e3bdb58fb1af523ea1b6019e8de04292ecdf11105fc6885cacc4903b76c`.
L'audit del 24 settembre 2026 ha riletto tutti i batch, verificando hash,
rapporti, margini e invarianza degli attributi prima/dopo le famiglie.
Sono passate anche le richieste del codice corrente sul database applicativo,
con ruolo reader: readiness, cataloghi v1/v2/v3, individui, famiglie,
confronto dei vincoli e geografia.

I test coprono retry, checkpoint, input incompatibili, corruzioni, immutabilità,
paginazione, rollback, rifiuto delle fixture e distinzione degli errori dopo
il commit. Gli originali e gli snapshot verificati restano nell'archivio dati.

## Prestazioni misurate

| Ambito | Evidenza |
|---|---|
| Generazione, recupero e riproduzione a 1M/10M e volume nazionale | [Misure della pipeline](benchmarks/population-order-2026-09-24.json) |
| Query sul database nazionale | [Misure del servizio](benchmarks/population-serving-2026-09-24.json) |

I benchmark riportano ambiente, quantità e limiti della singola esecuzione.
Le prove con fixture inventate non rappresentano statistiche osservate.
La rilettura di uno snapshot non misura il costo di rigenerarlo; i risultati
locali non costituiscono un benchmark di concorrenza o di un servizio gestito.

# Contratti versionati

I JSON sono input eseguibili. URL, checksum, definizioni e identificativi
serializzati sono parte della provenienza degli snapshot; una modifica
semantica richiede una nuova versione e un confronto esplicito.

| Uso | Contratto |
|---|---|
| Input nazionali: demografia, geografia e famiglie | [istat-national-v1.json](istat-national-v1.json) |
| Input STR/RCS | [istat-citizenship-v1.json](istat-citizenship-v1.json) |
| Modello corrente, ordine v5 | [population-reference-v1.json](population-reference-v1.json) |
| Budget dei workflow nazionali | [national-budget-v1.json](national-budget-v1.json) |
| Aggregati territoriali, API v2 | [istat-territorial-aggregates-v1.json](istat-territorial-aggregates-v1.json) |
| Popolazione regionale, ammissione e pubblicazione | [input](istat-population-regions-v1.json), [pubblicazione](istat-population-publication-v1.json) |
| Esperimenti regionali | [input Valle d'Aosta](istat-pilot-valle-aosta-v1.json), [esperimento](pilot-experiment-v1.json) |
| Sintesi nazionale senza cittadinanza | [national-reference-v1.json](national-reference-v1.json) |
| Cittadinanza su uno snapshot esistente | [citizenship-reference-v1.json](citizenship-reference-v1.json) |
| Fixture inventata degli aggregati | [population-demo-v1.json](population-demo-v1.json) |

Per il prodotto usare il [workflow della popolazione](../docs/population.md).
I nomi dei file descrivono la funzione; il contenuto e i checksum dei contratti
restano stabili per consentire l'audit dei dati già prodotti.

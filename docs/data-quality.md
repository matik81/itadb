# Qualità, riproducibilità e limiti

## Popolazione corrente

Il riferimento `population-reference/1` applica le [priorità v5](model-fidelity.md).
I controlli sono implementati nei moduli `synthesis/` e `population/`; il
workflow riproducibile è descritto in [population.md](population.md).

| Fase | Controllo bloccante | Evidenza |
|---|---|---|
| Acquisizione | Inventario finito, limite di byte, URL e checksum del contratto | Originali e manifest in `raw/` |
| Ammissione | Provenienza, licenza, schema, territori, periodi e riconciliazioni coerenti | Input ammessi e rapporti di ammissione |
| Generazione | Congiunte demografiche e margini STR/RCS esatti; budget e vincoli familiari | Parquet e checkpoint per batch |
| Audit indipendente | Rilettura SQL, schemi, ID, relazioni, margini, hash e invarianza degli attributi prima/dopo le famiglie | Manifest e rapporto dello snapshot |
| Importazione | Audit ripetuto, originali verificati, COPY e confronto delle distribuzioni PostgreSQL | Controlli di pubblicazione nel database |
| Servizio | Snapshot pubblicati, ruolo reader, query parametrizzate, filtri e limiti | Test API e PostgreSQL |

I retry verificano gli artefatti esistenti. File inattesi, corruzioni, input
incompatibili e gate falliti impediscono il completamento o la pubblicazione.
Checkpoint, tentativi interrotti e quarantene restano evidenze; non vanno cancellati
per forzare la ripresa. Gli snapshot completati sono immutabili.

La pubblicazione nel DB è atomica e idempotente. Il filesystem non partecipa
alla transazione PostgreSQL: un errore nel rapporto locale dopo il commit viene
segnalato con `published=true` e snapshot ID; il retry riconosce il commit.
[Recupero e operazioni](operations.md).

## Cosa dimostrano i controlli

I conteggi calibrati coincidono con le celle osservate disponibili. Questo non
costituisce validazione esterna della composizione familiare o dell'incrocio
età–singola cittadinanza. Il modello dichiara ipotesi, residui e assenza di dati
fuori calibrazione. Gli individui sono sintetici, senza corrispondenza con persone reali.

Fixture e benchmark inventati verificano il software e i carichi; non sono dati
osservati. L'importatore applicativo rifiuta le fixture. La distribuzione pubblica
resta soggetta alla [governance](../GOVERNANCE.md); il completamento tecnico non
implica revisione scientifica esterna o deployment pubblico.

## Aggregati statistici

Le API v1/v2 conservano i controlli per demo, popolazione regionale e copertura
territoriale: namespace distinti, flag upstream, partizioni disgiunte, gerarchie,
geometrie e riconciliazioni. I contratti e le procedure sono descritti nelle guide di
[popolazione regionale](sources/istat-population.md) e
[copertura territoriale](sources/territorial-aggregates.md).

## Verifiche di sviluppo

La suite comprende casi di successo, retry, corruzione, input incompatibili,
mancata pubblicazione, accesso reader e paginazione. Eseguire i controlli del
[README](../README.md#verifiche-di-sviluppo) e i test su PostgreSQL isolato.
Esiti recenti e limiti sono in [validation.md](validation.md).

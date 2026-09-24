# Roadmap del prodotto

## Implementato

Il riferimento unico `population-reference/1` applica la graduatoria di fedeltà
v5: **sesso/età → geografia → cittadinanza → famiglie**. Gli snapshot verificati
contengono individui e famiglie completi, sono caricati in PostgreSQL e serviti
dalle API v3 e dalla web app. Generazione, audit e pubblicazione sono passaggi
espliciti, con checkpoint, quarantena e retry verificati.

La web app offre una mappa con modalità Regioni, Province e Comuni, filtri,
istogrammi, record paginati, famiglie e confronto tra conteggi di origine e
sintetici. Confini, aggregati e selezione seguono il livello scelto; i punti
rappresentano territori, senza coordinate residenziali individuali.
[Metodo](population.md), [architettura](architecture.md), [verifiche](validation.md).

## Prossimi incrementi

| Obiettivo | Criterio di completamento |
|---|---|
| Densità e coordinate di residenza | Fonti ammesse, ipotesi versionate, nuovo riferimento e audit che conserva i margini prioritari |
| Esplorazione spaziale degli individui | Query limitate all'area visibile, indici e benchmark su dati adeguati, rappresentazione esplicita per scala |
| Deployment gestito | Provider scelto su capacità misurate, budget connessioni e spazio, backup/restore e procedura operativa verificati |
| Composizione familiare più fedele | Nuove evidenze di età/cittadinanza o relazioni familiari, confronto con il riferimento e conservazione dei vincoli adottati |

Questi incrementi non sono dichiarati implementati. Lavoro, istruzione, servizi,
dinamiche demografiche e scenari causali richiederanno obiettivi e priorità
espliciti; non sono proprietà dell'attuale popolazione.

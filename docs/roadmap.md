# Roadmap del prodotto

## Implementato

Il riferimento unico `population-reference/1` applica la graduatoria di fedeltà
v5: **sesso/età → geografia → cittadinanza → famiglie**. Gli snapshot verificati
contengono individui e famiglie completi, sono preparati in PostgreSQL offline e serviti
da DuckDB tramite API v1/v2/v3 e web app, senza Neon online. Generazione, audit e pubblicazione sono passaggi
espliciti, con checkpoint, quarantena e retry verificati.

La web app offre una mappa con modalità Regioni, Province e Comuni, filtri,
istogrammi, record paginati, famiglie e confronto tra conteggi di origine e
sintetici. Confini, aggregati e selezione seguono il livello scelto; i punti
rappresentano territori, senza coordinate residenziali individuali.
[Metodo](population.md), [architettura](architecture.md), [verifiche](validation.md).

L’export completo, l’attivazione e la configurazione del deployment sono descritti
nella [procedura senza Neon](deployment.md). Il deployment cloud resta da eseguire.

## Prossimi incrementi

| Obiettivo | Criterio di completamento |
|---|---|
| Densità e coordinate di residenza | Fonti ammesse, ipotesi versionate, nuovo riferimento e audit che conserva i margini prioritari |
| Esplorazione spaziale degli individui | Query limitate all'area visibile, indici e benchmark su dati adeguati, rappresentazione esplicita per scala |
| Deployment gestito | Provider scelto su capacità misurate, memoria/CPU e spazio, backup/restore e procedura Railway eseguita sul cloud |
| Composizione familiare più fedele | Nuove evidenze di età/cittadinanza o relazioni familiari, confronto con il riferimento e conservazione dei vincoli adottati |

Questi incrementi non sono dichiarati implementati. Lavoro, istruzione, servizi,
dinamiche demografiche e scenari causali richiederanno obiettivi e priorità
espliciti; non sono proprietà dell'attuale popolazione.

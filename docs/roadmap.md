# Roadmap

## Prodotto corrente

La popolazione sintetica segue il riferimento unico `population-reference/1`:
sesso/età → geografia → cittadinanza → famiglie. Generazione e audit producono
Parquet verificati; la pubblicazione prepara direttamente archivi DuckDB completi.
Le API v1/v2 conservano gli aggregati e v3 espone individui, famiglie e verifiche.

La web app offre mappa per regioni, province e comuni, filtri, istogrammi,
record paginati e metodo. Le coordinate rappresentano territori, non residenze.
[Metodo](population.md), [architettura](architecture.md), [verifiche](validation.md).

## Prossimi passi

| Obiettivo | Criterio di completamento |
|---|---|
| Verificare i prossimi rilasci Vercel/Railway | Deploy GitHub con controlli CI, configurazione IaC e monitor periodico; verificare ogni rilascio e recuperare i dati dalla preparazione locale |
| Densità e coordinate residenziali | Fonti ammesse, ipotesi versionate e nuovo snapshot con audit dei margini prioritari |
| Composizione familiare più fedele | Nuove evidenze e confronto con il riferimento, mantenendo i vincoli adottati |

Lavoro, istruzione, servizi e dinamiche causali richiedono obiettivi e priorità
espliciti; non sono proprietà dell'attuale popolazione.

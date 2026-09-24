# Baseline Linux e portabilità del repository

Stato: implementazione e verifiche completate il 24 settembre 2026.

## Obiettivo

Consentire lo sviluppo da un clone su Linux, con Ubuntu e WSL2 come ambiente
di riferimento, senza account personali, percorsi della macchina o configurazioni
locali implicite nei file pubblicati.

## Ambito e decisioni

- Guida di avvio Linux, diagnostica e database di test separato e riproducibile.
- Metadati della fixture identificati da URI del progetto, indipendenti dal remoto Git.
- Documentazione e strumenti di sviluppo coerenti con Bash e Python.
- Resoconti della postazione conservati fuori dal repository; benchmark pubblici
  come estratti storici con sistema operativo omesso, senza attribuirli alla baseline.
- Nessuna riscrittura della cronologia Git o dei dati pubblicati nei database.
- Nessuna modifica ai contratti statistici, dipendenze o schema applicativo.
- Eccezione autorizzata alla conservazione delle migrazioni: nella SQL `0001`
  cambia soltanto l’URI descrittivo della fonte demo; nessuna riscrittura DB.
  Le nuove pubblicazioni demo usano `population-demo/1.0.1` per preservare
  l’identità e i metadati delle release precedenti.

## Fasi e verifiche

1. Inventario e rimozione completati; resoconti della postazione archiviati fuori Git.
2. Guide, strumenti Bash, provenienza della demo e presentazione web aggiornati.
3. Passati 284 test Python, 38 di integrazione e 17 frontend, lint, tipi e build.
4. Installazione da copia pulita e database da vuoto verificati; corretta l’attesa
   TCP di PostgreSQL durante l’inizializzazione. Stack Docker completo verificato
   con la CA locale richiesta dalla rete, senza versionare il trust store.
5. Scansione dei 211 file distribuibili e link locali superati; OpenAPI e lockfile
   invariati. [Esiti e limiti](../validation.md#baseline-linux--24-settembre-2026).

## Limiti

La rimozione dai file correnti non rimuove contenuti dai commit precedenti o
dalle impostazioni dell’hosting. Le misure storiche non costituiscono benchmark
dell’ambiente Linux corrente. Nessuna nuova sintesi nazionale prevista.

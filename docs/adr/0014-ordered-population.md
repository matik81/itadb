# ADR 0014 — cittadinanza prima della composizione familiare

Stato: adottata. Data: 24 settembre 2026.

## Decisione

Il riferimento unico `population-reference/1` esegue **sesso/età → geografia →
cittadinanza → famiglie**, secondo la graduatoria v5. Usa gli input ammessi
POSAS, geografia, famiglie e STR/RCS, senza richiedere uno snapshot sintetico
precedente. `synthesize-population` e `verify-population` sono i comandi del workflow.

Per ogni batch i primi tre passaggi producono `individuals.parquet`: ID,
territorio, coorte, sesso, natura sintetica e cittadinanza. Il quarto legge
questo file e aggiunge `household_id` e `reference_adult` al Parquet finale.
L'ordine è registrato nel manifest e nel rapporto.

L'audit SQL indipendente confronta ogni attributo prima e dopo le famiglie.
Verifica STR/RCS su entrambi i file, margini demografici, geografia e vincoli
familiari. Gli individui prima delle famiglie restano nello snapshot,
inventariati e protetti da checksum.

## Regole e conseguenze

Seed 1701; selezione degli stranieri per comune/sesso/età; permutazione delle
cittadinanze entro comune/sesso; composizione familiare casuale vincolata entro
il comune. Nessuna nuova correlazione osservata viene dedotta dai soli margini.
I dettagli sono nelle [priorità di fedeltà](../model-fidelity.md).

Il Parquet aggiuntivo aumenta lo spazio necessario e rende verificabile
l'invarianza dei primi tre passaggi. Checkpoint, retry, budget e quarantena
proteggono le esecuzioni; la pubblicazione applicativa è un passaggio distinto.
Il completamento della sintesi non pubblica automaticamente dati sul servizio.

I test coprono ordine, invarianti, interruzioni, ripresa, ordine inverso,
input incompatibili, corruzione e metadati alterati. Le
[verifiche e misure](../validation.md) dichiarano quantità, ambiente e limiti.

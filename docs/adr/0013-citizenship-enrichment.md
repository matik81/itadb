# ADR 0013 — cittadinanza come arricchimento immutabile di M4

Data: 24 settembre 2026. Stato: adottata per l'integrazione locale richiesta.

## Problema

M4 comprende tutta la popolazione residente, ma non assegna cittadinanza ai
record sintetici. Le fonti ISTAT 2025 sono compatibili con il riferimento:
STRASA fornisce comune/sesso/età degli stranieri complessivi; RCS fornisce
comune/sesso/singola cittadinanza, incluse Italia e apolidia. L'incrocio
età–singola cittadinanza non è disponibile in queste tavole.

## Decisione

Creare uno snapshot derivato, senza rigenerare o modificare il riferimento
M4. Il Parquet persone conserva le dieci colonne esistenti e aggiunge
`citizenship_code` VARCHAR con i codici ISTAT. I Parquet famiglie vengono
copiati identici. Manifest e identità includono run/checksum della base,
input ammessi, sorgenti eseguibili, lockfile, ambiente e riferimento unico.
Per ripetere l'audit è necessario conservare anche lo snapshot di base.

`citizenship-reference/1`, seed 1701, applica due passaggi per ogni comune:

1. Seleziona esattamente il numero STR di stranieri in ciascuna cella
   sesso/età, ordinando gli ID della base tramite hash e spareggio esplicito.
2. Assegna le cittadinanze RCS agli stranieri, entro comune e sesso, con
   permutazioni distinte e deterministiche delle persone e dei posti per
   cittadinanza. Ai restanti individui assegna `100` (Italia).

Il seed comunale è derivato dai primi 64 bit di
`SHA256("itadb:citizenship:1:1701:" + comune)`. Le permutazioni usano hash
DuckDB con namespace distinti. L'ordine dei batch non cambia l'assegnazione;
versione del motore e ambiente sono parte dell'identità riproducibile.
Il codice `999` indica apolidia, non cittadinanza sconosciuta. La definizione
ISTAT considera italiano chi possiede anche la cittadinanza italiana.

L'ipotesi unica è la scambiabilità delle cittadinanze specifiche fra gli
stranieri dello stesso comune e sesso. La distribuzione risultante per età
e specifica cittadinanza è sintetica, non osservata. Non si ricavano legami
familiari, cittadinanza dei figli, acquisizioni o paese di nascita.

## Ammissione e verifiche

Un contratto fissa sei originali: STR comunale/regionale, RCS, pagine di
definizione e licenza. ZIP, dimensioni, intestazioni, periodo, codici e
conteggi sono verificati offline. STR richiede tutte le età e zeri espliciti.
RCS contiene righe sparse: le assenze possono valere zero soltanto dopo
che le categorie non negative esauriscono esattamente i totali M4 e STR e
riconciliano per singola cittadinanza a provincia, regione, ripartizione e Italia.
Qualunque incompatibilità blocca l'ammissione; nessun riallineamento stimato.

L'audit SQL separato dal generatore rilegge base e arricchimento e verifica:
unicità degli ID, uguaglianza di tutti gli attributi preesistenti, famiglie
identiche byte per byte, celle STR, conteggi RCS e diagnostica disclosure.
Checkpoint, inventari, checksum, budget, quarantena e ripresa seguono il
protocollo locale M4. File corrotti o inattesi impediscono il completamento.
Nessuna nuova dipendenza, API, tabella DB o migrazione.

## Priorità e distribuzione

Nella versione 4 delle priorità, adottata per questo riferimento, la
cittadinanza è stata aggiunta dopo sesso/età, geografia e famiglie,
conservando tutti i vincoli precedenti. Il successivo aggiornamento
concordato con l'utente, [versione 5 delle priorità](../model-fidelity.md),
porta la cittadinanza al terzo posto e le famiglie al quarto per distinguere
i margini osservati esatti dalla composizione familiare ancora grezza.
L'[ADR 0014](0014-ordered-population.md) applica l'ordine al nuovo riferimento
eseguibile corrente. Il metodo e i metadati storici di questo riferimento
restano invariati.
Il riferimento M4 originale resta una base immutabile, non una popolazione
alternativa fra cui scegliere a posteriori.

Lo snapshot arricchito è locale, `public_release=false`. La disclosure
considera anche la cittadinanza nei quasi-identificatori; l'aumento di
granularità non eredita alcuna garanzia dai soli margini demografici M4.
Non viene prodotto un nuovo pacchetto pubblico. Calibrazione esatta e audit
tecnico non sostituiscono revisione scientifica o certificazione di anonimato.

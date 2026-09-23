# ADR 0008 — sintesi pilota locale, ricostruzione vincolata

Stato: adottato per il pilota M3, 23 settembre 2026.
La calibrazione demografica e il relativo holdout sono sostituiti da
[ADR 0009](0009-exact-demographic-calibration.md). Il testo seguente conserva
la decisione v1; allocazione familiare e condizioni di distribuzione restano valide.

## Contesto

Le evidenze M2 sono aggregate: non esiste un microcampione autorizzato di famiglie.
Sesso/età sono disponibili nel 2024, famiglie nel 2021. Una sintesi che li
combinasse senza dichiararlo costruirebbe una popolazione temporalmente incoerente.
È stato acquisito un solo nuovo campione: 306 celle sesso/età della Valle d'Aosta
al 1° gennaio 2022. Il totale 123.360 coincide esattamente con POP21; 60.468
famiglie SDMX coincidono con FAM21. Restano due riferimenti temporali distinti,
riconciliati su questo specifico confine d'anno.

## Scelta e alternative

Ricostruzione senza donatori, limitata a 200.000 residenti e 100.000 famiglie.
Il generatore riceve 101 margini d'età (0–99, 100+), maschi nelle fasce 0–17,
18–64, 65+ e famiglie per dimensione 1–5, 6+. La congiunta puntuale sesso/età
rimane al verificatore e non può influenzare l'allocazione.

Entro ogni fascia il numero atteso di maschi di età `a` è
`N[a] * M[fascia] / N[fascia]`: soluzione di indipendenza condizionata, equivalente
al punto fisso IPF con prior uniforme e questi soli margini. Il metodo dei
resti maggiori rende interi i conteggi maschili; quelli femminili sono i
complementi. Calcolo intero e pareggi risolti con seed preservano entrambi i
margini. Non sono necessari un solutore iterativo, SciPy o un nuovo servizio.

Segue una ricostruzione costruttiva: dimensioni familiari esatte, un adulto
di riferimento casuale per famiglia, assegnazione casuale dei minori agli
slot restanti, riempimento con adulti e residuo adulto esplicito. Non si
attribuiscono ruoli di genitore, coniuge, parentela, abitazioni o indirizzi.
Il vincolo adulto/minore è una regola del modello, non una descrizione di
tutte le possibili famiglie osservate. La classe 6+ usa tre scenari omogenei
di dimensione 6, 7, 8; non una stima della sua distribuzione reale.

IPU con replicazione di microfamiglie non è appropriato senza donatori
ammessi. IPF generalizzato e ottimizzazione combinatoria restano alternative
quando siano disponibili altri vincoli congiunti, soprattutto familiari.
Il codice non pretende di implementare integralmente un algoritmo pubblicato.
La letteratura considera sia fitting sia allocazione senza campione e mostra
che le ipotesi dipendono dalle informazioni disponibili:
[Huynh, Barthélemy e Perez, 2016](https://jasss.soc.surrey.ac.uk/19/4/11.html),
[Ye et al., 2017](https://jasss.soc.surrey.ac.uk/20/4/16.html).

## Verifica e distribuzione

Un secondo modulo legge esclusivamente i Parquet e verifica con SQL domini,
identità, cardinalità, riferimenti, vincoli familiari, margini e residuo.
Non importa il generatore. Ricalcola la distanza della congiunta esclusa
dalla calibrazione, errori per cella e statistiche familiari del modello.
Questa indipendenza implementativa non sostituisce una revisione scientifica
umana esterna: il rapporto registra esplicitamente che non è stata svolta.

Cinque seed per tre scenari sono pubblicati nel rapporto locale senza
selezionare il seed migliore. Minimo, massimo, media e deviazione standard
campionaria misurano variabilità algoritmica; non sono intervalli di
confidenza né incorporano errori della fonte o tutto il bias strutturale.
I margini esatti non sono prova di validità della congiunta o delle famiglie.

Ogni esperimento conserva codice sorgente, lockfile, input e loro checksum,
ambiente, commit/stato dirty, seed, parametri e rapporto. Il completamento
è un rename atomico di directory; errori mantengono tentativo e quarantena.
Retry e verifica ricalcolano i controlli sui file immutabili. Nessuna modifica
DB/API/web: i record locali sono sempre `synthetic`; distribuzione di microdati
bloccata in attesa di revisione scientifica e valutazione disclosure.

## Condizioni di revisione

Margini demografici/familiari dello stesso universo statistico, composizioni
osservate per validazione esterna, distribuzione effettiva della classe 6+,
popolazione in convivenze, analisi disclosure e revisione scientifica esterna
prima di considerare distribuzioni pubbliche. M4 richiede misure proprie a
1M, 10M e scala nazionale: il limite attuale impedisce tali esecuzioni.

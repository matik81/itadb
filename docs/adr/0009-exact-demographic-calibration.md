# ADR 0009 — calibrazione demografica esatta nel pilota M3

Stato: adottato il 23 settembre 2026 su richiesta dell'utente. Sostituisce la
calibrazione e la validazione demografica dell'[ADR 0008](0008-synthesis-pilot.md).

## Contesto

Il pilota v1 manteneva esatti i totali per età e il sesso in tre fasce larghe.
Stimava la congiunta con indipendenza condizionata e usava la tabella puntuale
ISTAT per misurare l'errore. L'utente richiede ora che sesso ed età della
popolazione virtuale rispecchino 1:1 i conteggi osservati già disponibili.

## Scelta

Usare tutte le 202 celle (M/F × età 0–99 e 100+) come vincoli interi esatti.
L'adapter riconcilia sul CSV originale maschi, femmine e totale per ogni età,
oltre ai totali per sesso. Il modello normalizzato conserva totale e maschi
per età; le femmine si ottengono per differenza. Il generatore materializza
direttamente questi conteggi. Nessuna stima, campionamento o arrotondamento
della distribuzione demografica è necessario.

Seed e ipotesi sulla classe familiare 6+ riguardano l'allocazione familiare.
Ogni replica mantiene la stessa congiunta sesso/età. L'audit SQL separato
rilegge i Parquet e impedisce il completamento se una qualsiasi cella differisce.
Il test decisivo scambia sesso tra due età della stessa fascia: i margini
precedenti restano corretti, ma il nuovo controllo fallisce.

Input e rapporto passano a v2, algoritmo e audit a 2.0.0. Contratto degli
originali e parametri sperimentali non cambiano. L'identità del nuovo
esperimento cambia e i precedenti artefatti restano immutabili, verificabili
con la rispettiva implementazione registrata. Non servono nuove dipendenze,
migrazioni, API o componenti frontend.

## Alternative e conseguenze

Conservare il fitting sui margini larghi introdurrebbe uno scostamento evitabile
rispetto a celle già osservate. IPF o un'ottimizzazione iterativa non aggiungono
informazione quando la congiunta richiesta è completa e internamente coerente.

La tabella sesso/età non è più un holdout. Il rapporto la chiama
`calibration_joint` e dichiara `out_of_calibration_validation=not_available`.
Errore zero dimostra la corrispondenza ai vincoli, non la validità delle
composizioni familiari. La variabilità tra seed riguarda queste ultime.

Il significato di 1:1 è uguaglianza dei conteggi, senza associazione tra record
virtuale e individuo reale. 100+ resta una classe aperta. Servono ancora
congiunte familiari osservate inutilizzate per validare il modello, revisione
scientifica esterna e valutazione disclosure prima della distribuzione.

# ADR 0010 — priorità di fedeltà e riferimento unico M3

Stato: adottato il 23 settembre 2026. Recepisce le conclusioni dell'utente
sulla revisione M3 e precisa la scelta tecnica del riferimento iniziale.
Integra ADR 0008/0009; sostituisce il trattamento paritario dei tre scenari
6/7/8 nell'interpretazione del pilota, conservando gli esperimenti originali.

## Contesto e decisione

L'utente stabilisce l'ordine iniziale di fedeltà: (1) età e sesso,
(2) distribuzione geografica regionale, provinciale e comunale,
(3) composizione delle famiglie. È una graduatoria rivedibile e da estendere
con il progetto. Accetta l'allocazione familiare casuale vincolata come
prima versione e richiede assunzioni uniche, dichiarate e motivate.

La [policy di fedeltà](../model-fidelity.md) rende operativo questo ordine,
senza consentire compromessi impliciti sui vincoli osservati già adottati.
La revisione umana di progetto si chiude con accettazione del perimetro M3
e dei suoi limiti, consentendo l'avvio di M4. La revisione scientifica esterna
e l'analisi disclosure restano distinte e non risultano svolte.

Si adotta **6 per tutte le famiglie 6+ e seed 1701**. È la selezione tecnica
che attua la richiesta di un solo riferimento: il minimo osservabile della
classe, senza una media stimata della coda; il primo seed già dichiarato,
senza ottimizzarlo sui risultati. Non si attribuisce alla scelta una maggiore
verità statistica. Restano 929 adulti non assegnati, esplicitamente conservati.

## Alternative e conseguenze

- Tenere 6/7/8 come tre riferimenti equivalenti non soddisfa l'univocità richiesta.
- Usare 7 perché intermedio non è sostenuto da una media osservata. Usare 8
  perché lascia meno residuo confonderebbe un'ipotesi con evidenza sulle convivenze.
- I tre scenari e tutti i seed restano utili per la sensibilità. Non vengono
  rimossi né rietichettati dentro gli artefatti immutabili: un nuovo documento
  di revisione seleziona run e replica con checksum.

Non cambia il codice del generatore, né il contratto dell'esperimento a 15
repliche. La CLI produce ancora l'insieme sperimentale; il riferimento unico
è la replica precisamente indicata nella [revisione](../reviews/m3-human-review.md).
M4 dovrà rendere questa selezione esplicita anche in configurazione e manifest.

Il miglioramento della composizione familiare può procedere dopo M3 senza
bloccare l'inizio dei lavori di scala. La priorità geografica, invece, richiede
in M4 nuovi input e un'assegnazione territoriale che il pilota non possiede.
I dettagli di fonte mancanti non si ricavano da soli totali regionali.

## Condizioni di revisione

Nuove fonti coerenti, distribuzione effettiva della classe 6+, composizione
familiare o convivenze possono sostituire le ipotesi in una nuova versione.
La scelta del riferimento, le priorità e i risultati precedenti restano
tracciati. [Piano M4](../plans/m4-national-synthesis.md): prima copertura
temporale/territoriale, poi batch, recupero e benchmark progressivi.

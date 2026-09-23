# Priorità di fedeltà del modello

Versione 2, aggiornata il 23 settembre 2026 per le coorti di nascita stabili.
La graduatoria adottata nella versione 1 dalla revisione umana M3 resta invariata.
La graduatoria è una decisione di progetto evolutiva: orienta lavoro e
valutazione delle versioni, senza attribuire uguale affidabilità a tutti gli
attributi degli agenti. [Decisione](adr/0010-model-fidelity-and-m3-reference.md).

## Graduatoria iniziale

| Priorità | Proprietà | Obiettivo di fedeltà | Stato effettivo in M3 |
|---|---|---|---|
| 1 | Distribuzione congiunta per età e sesso | Uguaglianza dei conteggi per ogni cella osservata ammessa, al territorio e alla data dichiarati | Esatta sulle 202 celle regionali della Valle d'Aosta; 100+ resta una classe aperta |
| 2 | Distribuzione geografica: regioni, province/UTS e comuni | Conteggi territoriali esatti e gerarchia coerente sullo stesso riferimento; nessun doppio conteggio | Solo appartenenza regionale del pilota; persone e famiglie non hanno ancora un'assegnazione provinciale/comunale |
| 3 | Composizione delle famiglie | Conservare i conteggi familiari ammessi; migliorare gradualmente composizioni, ruoli e relazioni mediante evidenze | Numero e classi dimensionali vincolati; appartenenza casuale con regole esplicite, accettata per la prima versione |

Le altre proprietà, per esempio lavoro, istruzione o abitazione, non hanno
ancora una posizione concordata. Si aggiungeranno quando entrano nel modello,
motivando il loro ordine e i criteri verificabili di fedeltà.

## Come applicare le priorità

- Un miglioramento familiare non può modificare i conteggi vincolanti di età,
  sesso o territorio. Le priorità guidano lo sviluppo; non autorizzano ad
  allentare silenziosamente vincoli già adottati, neppure quelli sulle famiglie.
- Si confrontano dati dello stesso universo, periodo e definizione territoriale.
  In caso di incompatibilità si conserva l'evidenza e si blocca la versione
  interessata: non si aggiustano conteggi ufficiali per far funzionare il modello.
- L'esattezza vale alle granularità realmente osservate e verificate. Totali
  comunali esatti e sesso/età regionali esatti non dimostrano una congiunta
  sesso/età comunale esatta. Un'eventuale disaggregazione inferita va dichiarata.
- Ogni versione riporta, per proprietà, fonte/data/geografia, vincolo adottato,
  misura dello scostamento, assunzione e limite. Mancante, stimato, osservato
  e sintetico restano distinti; una cella soppressa non diventa uno zero.

## Un solo modello di riferimento per versione

Ogni versione adottata deve fissare input, algoritmo, regole, parametri e seed.
Può essere accompagnata da prove alternative, ma queste non sono popolazioni
di riferimento concorrenti e non si sceglie retroattivamente il risultato
che sembra più realistico senza un criterio dichiarato.

Per M3 il riferimento è **classe 6+ = 6 persone per famiglia, seed 1701**.
Sei è il minimo della classe pubblicata: evita di postulare componenti aggiuntivi
senza dati sulla coda della distribuzione. È un'ipotesi di lavoro semplice,
non una stima della dimensione media o una dichiarazione che non esistano
famiglie più grandi. Conserva un residuo esplicito di 929 adulti non assegnati;
non si riduce quel residuo scegliendo 7 o 8 per suggerire un adattamento migliore.
1701 è il primo seed già fissato nel contratto sperimentale, scelto per
continuità e riproducibilità, senza selezione in base alle statistiche familiari.

Gli altri seed e le dimensioni 7/8 misurano sensibilità. Identità, artefatti
e statistiche puntuali del riferimento v2 sono nella
[revisione M3](reviews/m3-human-review.md); quelli della nuova rappresentazione
v3 sono nella [revisione delle coorti](reviews/m3-birth-year-reference.md).
La CLI attuale continua a generare
l'esperimento completo: la scelta del riferimento è documentale e individua
esattamente una delle repliche conservate, senza modificare i report storici.

## Nascita stabile ed età derivata

L'[ADR 0011](adr/0011-stable-birth-cohorts.md) applica la prima priorità
alla rappresentazione temporale: l'età è derivata da una coorte sintetica
stabile, al 1° gennaio prima dei compleanni (`Y - birth_year - 1`). Tutte le
202 celle iniziali rimangono vincolanti; questa esattezza non si estende
automaticamente agli anni simulati successivi.

Per 100+ l'anno esatto resta nullo e si conserva soltanto l'ultimo anno
possibile (`birth_year_upper_bound`). Il limite inferiore dell'età avanza
nel tempo; non si sceglie una distribuzione non osservata della coda.
Schema, formula, riferimento e razionale sono nei metadati eseguibili v3.
Nuove evidenze sulle date di nascita o una simulazione infra-annuale
richiederanno una regola distinta e un confronto esplicito.

## Evoluzione

Ogni nuova assunzione deve dichiarare valore/regola unica, razionale, conseguenza
misurabile e quale evidenza ne permetterà il superamento. Cambi di priorità,
fonti o metodo richiedono motivazione e una versione distinta con confronto
alla precedente. Per cambiare la graduatoria si registra la decisione con
l'utente; non si riscrivono retroattivamente i criteri delle release passate.

Il rapporto di fedeltà e il riferimento unico dovranno essere rappresentati
anche nei metadati eseguibili di M4. Questa policy non dichiara già implementati
i controlli territoriali o gli attributi futuri. L'accettazione di un modello
di lavoro non equivale a una certificazione statistica o a un'autorizzazione
alla distribuzione dei microdati.

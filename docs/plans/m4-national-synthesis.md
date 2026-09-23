# M4 — geografia e scala nazionale 1:1

Stato: **pronto per l'avvio; implementazione M4 non ancora avviata**.
La [revisione umana M3](../reviews/m3-human-review.md) accetta il modello di
lavoro iniziale e le sue assunzioni. Il riferimento resta `m3-reference/1`;
il metodo futuro segue le [priorità di fedeltà](../model-fidelity.md).

## Verifica di prontezza

| Condizione | Evidenza / stato | Conseguenza |
|---|---|---|
| Modello iniziale esplicito e unico | Classe 6+ = 6, seed 1701, replica e checksum registrati | Soddisfatta per l'avvio |
| Fedeltà demografica pilota | 202 celle regionali esatte, 15 repliche, 3.030 confronti con il CSV ISTAT | Soddisfatta nel perimetro M3 |
| Integrità e riproducibilità | Audit indipendente, retry, quarantena, sorgenti/input immutabili; 160 test Python e CI passati su `ca8ac10` | Base tecnica disponibile |
| Revisione umana di progetto | Accettazione iniziale delle famiglie casuali e priorità concordate | M3 chiuso nel perimetro accettato |
| Integrazione della base di lavoro | PR M3 #14 su main; esito di merge da verificare all'apertura del lavoro M4 | Integrare M3 prima di creare il branch M4 da main; non è stata eseguita una fusione da questa revisione |
| Fonti aggiornate e geografia completa | Ultimo anno comune non ancora verificato; M3 non assegna comuni/province | Primo lavoro di M4, prima di una nuova sintesi territoriale |
| Scala nazionale | Limite attuale 200.000 residenti / 100.000 famiglie e una sola regione ammessa | Serve implementazione per batch; non basta aumentare i limiti |
| Revisione scientifica esterna e disclosure | Non svolte | Non bloccano lo sviluppo locale; restano condizioni per la distribuzione |

**Esito: si può iniziare M4.** Non si può ancora eseguire o dichiarare validata
una popolazione nazionale con il generatore M3 esistente.

## Risultato osservabile

Una versione di riferimento riproducibile, costruita in batch territoriali,
con input coerenti e copertura dichiarata. Conteggi sesso/età e geografici
osservati preservati, aggregazioni comune → provincia/UTS → regione → Italia
riconciliate e persone senza famiglia incluse nei totali territoriali.
Una famiglia assegnata appartiene a un solo comune e tutti i suoi componenti
allo stesso comune. Questo è un requisito M4, non una capacità già verificata.

La composizione familiare casuale vincolata resta la prima baseline; migliorarla
con ruoli o relazioni non è un prerequisito per i primi benchmark. Se diventa
incompatibile con vincoli locali osservati, quel batch fallisce: si documenta
una revisione della regola, senza alterare conteggi di età, sesso o geografia.

## Sequenza di lavoro e criteri di accettazione

1. **Fonti e riferimento temporale.** Inventario ristretto di sesso/età,
   popolazione territoriale e famiglie: anno, livello, categorie, stato,
   licenza, disponibilità di congiunte e totali. Verificare il più recente
   riferimento comune utilizzabile, non assumere che ogni tabella arrivi
   al 2024. Se serve conservare un periodo precedente, motivarlo esplicitamente.
   Uscita: contratto versionato e riconciliazioni su campione, copertura
   osservata distinta da stime o disaggregazioni ipotetiche. Niente download
   nazionale esplorativo senza aver controllato significati e fattibilità.
2. **Fedeltà geografica e riferimento eseguibile.** Collegare individui e
   famiglie a codici territoriali e snapshot coerenti; riusare le gerarchie
   M2 verificate, senza trasferire numeri tra confini diversi per sola etichetta.
   Conservare tutte le congiunte sesso/età disponibili e i totali dei livelli
   osservati. Se manca sesso/età comunale, non presentare una distribuzione
   inferita come osservata. Dichiarare priorità, regole familiari, 6+ = 6 e
   seed base 1701 in configurazione e manifest del riferimento; separare
   le prove di sensibilità. Uscita: piccolo campione multicomunale con audit
   per comune e riconciliazioni dei livelli superiori, anche sul residuo.
3. **Generazione per batch e recupero.** Identificativi univoci nel run,
   derivazione deterministica/versionata dei seed territoriali dal seed base,
   memoria limitata, checkpoint e ripresa dopo interruzione. L'ordine dei
   batch non deve cambiare i risultati; niente riutilizzo implicito dello
   stesso flusso casuale per territori diversi. Uscita: retry e ripresa
   identici, nessun doppione o perdita, fallimenti senza snapshot completo,
   audit locale e globale su file immutabili.
4. **Benchmark progressivi.** Prove a 1M, 10M e volume nazionale del periodo
   scelto. Prima di ogni prova fissare budget RAM/disco/tempo compatibili con
   l'ambiente, rendere visibili fase/conteggi/tempo e conservare i log.
   Misurare picco RAM del processo, disco, durata, throughput, costo di audit
   e ripresa; registrare hardware, versioni, dati e risultato. Distinguere
   fixture di carico da popolazioni calibrate. Uscita: misure ripetibili e
   rispetto dei budget; non estrapolare il tempo regionale alla scala nazionale.
5. **Valutazione e distribuzione.** Rapporto di fedeltà nell'ordine concordato,
   confronto con M3 e statistiche non usate in calibrazione quando disponibili.
   La loro assenza deve restare dichiarata. Per completare M4 servono inoltre
   valutazione statistica, analisi disclosure e formato/ambito di distribuzione
   concordati secondo roadmap e governance. Eventuali pubblicazioni richiedono
   i rispettivi esiti di revisione; benchmark riusciti non sono autorizzazione.

## Rischi e decisioni da verificare durante M4

- Differenze di periodo, universo statistico, confini o stato del dato
  possono impedire la riconciliazione; nessuna correzione silenziosa.
- Margini demografici regionali e totali comunali non determinano tutte le
  correlazioni locali: la fedeltà va riportata alla granularità disponibile.
- La classe 6+ = 6 è trasferibile come ipotesi iniziale, non come garanzia
  universale di fattibilità. Dimensioni e vincoli adulto/minore vanno testati
  su ogni territorio prima dell'allocazione.
- Una nuova fonte sulle famiglie può giustificare un nuovo riferimento;
  i conteggi prioritari e gli esperimenti precedenti restano preservati.
- Microservizi, nuove dipendenze o una proiezione nazionale PostgreSQL non
  sono prerequisiti automatici: valgono le condizioni misurate dell'architettura.

Questo piano definisce il lavoro successivo. La presente revisione aggiorna
documentazione e accettazione M3, senza eseguire benchmark o implementare M4.

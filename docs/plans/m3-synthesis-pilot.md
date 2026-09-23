# M3 — sintesi pilota

Stato: revisione implementata e verificata, calibrazione esatta sesso per singola età.
Nuovo algoritmo/input/report v2; 15 repliche, 3.030 confronti esatti con ISTAT,
160 test Python passati. Gli esperimenti v1 restano conservati. Risultati in
[validation.md](../validation.md#m3--sintesi-pilota).

## Risultato e perimetro

Pilota locale della Valle d'Aosta: popolazione al 1° gennaio 2022 e famiglie
al 31 dicembre 2021, originali ISTAT fissati per hash. I record generati sono
interamente virtuali. Nessuna pubblicazione di microdati nelle API o in Git.

## Decisioni

- Ricostruzione senza microcampione: margini demografici interi, allocazione
  casuale vincolata in famiglie; confronto IPF/IPU nell'ADR 0008.
- Tutte le 202 celle sesso/età (0–99 e 100+) sono vincoli esatti. Il seed
  modifica l'assegnazione familiare, senza modificare la congiunta demografica.
- La congiunta non è più un holdout. Assenza di statistiche esterne inutilizzate
  dichiarata nei report; zero errore di calibrazione non è validazione esterna.
- Classe 6+ esplorata con dimensioni ipotetiche 6, 7 e 8. Residuo esplicito
  non assegnato; non viene dichiarato popolazione in convivenze.
- Più seed, statistiche aggregate, intervalli empirici di variabilità;
  nessuna interpretazione come intervalli di confidenza della popolazione.
- Verificatore separato che rilegge i Parquet con SQL, senza importare il
  generatore. La revisione scientifica umana esterna resta distinta e dichiarata.
- Identità su input, contratto, codice, ambiente e parametri; scrittura atomica,
  retry verificato, quarantena in caso di errore. Nessuna nuova dipendenza o DB.

## Fasi e verifiche

1. Inventario ristretto, contratto, riconciliazione dei riferimenti temporali.
2. Modelli stretti, generatore deterministico, archivio Parquet e CLI.
3. Audit indipendente su tutte le celle sesso/età e sensibilità familiare.
4. Test che rilevano scambi di sesso con margini larghi invariati, conteggi
   estremi e zeri; rigenerazione ufficiale offline, confronto diretto con CSV
   ISTAT su ogni replica, retry e conservazione dei precedenti esperimenti.
5. Rebase su main aggiornato, commit su branch dedicato e PR.

## Limiti da rendere visibili

I margini non identificano le relazioni familiari. Nessun legame di parentela,
indirizzo, abitazione o identità reale viene inferito. 100+ rimane una categoria
aperta; il residuo e la composizione delle famiglie sono ipotesi del modello.
La verifica automatica indipendente non equivale a una revisione scientifica
esterna, né autorizza la distribuzione dei microdati. La scala nazionale è M4.

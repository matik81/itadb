# M3 — sintesi pilota

Stato: implementazione e verifiche locali completate il 23 settembre 2026;
consegna tramite branch e PR. Risultati e limiti effettivi in
[validation.md](../validation.md#m3--sintesi-pilota).

## Risultato e perimetro

Pilota locale della Valle d'Aosta: popolazione al 1° gennaio 2022 e famiglie
al 31 dicembre 2021, originali ISTAT fissati per hash. I record generati sono
interamente virtuali. Nessuna pubblicazione di microdati nelle API o in Git.

## Decisioni

- Ricostruzione senza microcampione: margini demografici interi, allocazione
  casuale vincolata in famiglie; confronto IPF/IPU nell'ADR 0008.
- Sesso per fascia ampia ed età marginale in calibrazione; tabella sesso/età
  puntuale esclusa dalla generazione e usata soltanto dalla validazione.
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
3. Verifica indipendente, metriche fuori calibrazione e sensibilità.
4. Test offline positivi/negativi, ripetibilità e corruzione; esecuzione ufficiale
   con avanzamento/log; controlli repository e documentazione dei risultati.
5. Rebase su main aggiornato, commit su branch dedicato e PR.

## Limiti da rendere visibili

I margini non identificano le relazioni familiari. Nessun legame di parentela,
indirizzo, abitazione o identità reale viene inferito. 100+ rimane una categoria
aperta; il residuo e la composizione delle famiglie sono ipotesi del modello.
La verifica automatica indipendente non equivale a una revisione scientifica
esterna, né autorizza la distribuzione dei microdati. La scala nazionale è M4.

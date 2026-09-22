# Roadmap verificabile

## M0 — fondazione riproducibile (questo scaffold)
Scopo: repository pubblico, istruzioni Codex, contratti e CI; percorso demo originale →
quality gate → DB → API → web. Uscita: retry senza doppioni, dati invalidi mai pubblicati,
query limitate, fonte/licenza/periodo visibili, avvio documentato.

## M1 — primo dataset ufficiale
Selezionare un dataflow ISTAT aggregato, un periodo e una granularità. Onboarding completo,
DSD/codelist conservate, licenza verificata, domini territoriali reali e riconciliazione con
totali upstream. Estendere catalogo per data di pubblicazione upstream e revisioni. Uscita:
risultati riproducibili e campione revisionato manualmente, con limiti documentati.

## M2 — copertura territoriale e demografica
Territori storicizzati, fusioni/scissioni e crosswalk, confini verificati, indicatori per
sesso/età, famiglie e abitazioni. Uscita: test di gerarchia e copertura, riconciliazioni tra
fonti e vintage, nessuna somma di categorie sovrapposte. Benchmark su volume rappresentativo.

## M3 — sintesi pilota
Area limitata, metodo esplicito (es. IPF/IPU o ricostruzione combinatoria da valutare), input
ammessi, seed e versioni riproducibili. Vincoli familiari e demografici, metriche fuori
calibrazione, incertezza e revisione indipendente. Nessuna persona virtuale associata a reale.

## M4 — scala nazionale 1:1
Batch territoriali, snapshot colonnari e output aggregati; prova a 1M, 10M e volume nazionale.
Uscita: budget misurati di RAM/disco/tempo, checkpoint e recupero, convalida statistica,
valutazione disclosure e formato di distribuzione concordato.

## M5 — lavoro, servizi e scenari
Collegamenti e dinamiche documentati, confronto baseline/intervento, sensibilità ai parametri
e comunicazione dei limiti causali. La complessità del modello cresce solo dopo validazione
del passo precedente. Non è previsto un agente LLM per ogni individuo.

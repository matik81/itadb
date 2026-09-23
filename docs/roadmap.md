# Roadmap verificabile

Per il modello sintetico vale la [graduatoria di fedeltà](model-fidelity.md):
età/sesso al primo posto, regioni/province/UTS/comuni al secondo e composizione
familiare al terzo.
L'ordine è evolutivo e ogni versione adottata deve avere un riferimento unico.

## M0 — fondazione riproducibile (questo scaffold)
Scopo: repository pubblico, istruzioni Codex, contratti e CI; percorso demo originale →
quality gate → DB → API → web. Uscita: retry senza doppioni, dati invalidi mai pubblicati,
query limitate, fonte/licenza/periodo visibili, avvio documentato.

## M1 — primo dataset ufficiale
Selezionare un dataflow ISTAT aggregato, un periodo e una granularità. Onboarding completo,
DSD/codelist conservate, licenza verificata, domini territoriali reali e riconciliazione con
totali upstream. Estendere catalogo per data di pubblicazione upstream e revisioni. Uscita:
risultati riproducibili e campione revisionato manualmente, con limiti documentati.

Primo incremento completato: [onboarding della popolazione regionale 2024](sources/istat-population.md),
contratto e controllo offline con 21 osservazioni ufficiali e riconciliazione esatta.
M1 completata per questo perimetro: pubblicazione DB/API v2/web, revisioni esplicite,
snapshot territoriali con integrità temporale e verifiche PostgreSQL eseguite.
La data di pubblicazione upstream resta non accertata e dichiarata null; non viene
dedotta da LAST_UPDATE. Storia territoriale, geometrie e ulteriori periodi restano in M2.

## M2 — copertura territoriale e demografica
Territori storicizzati, fusioni/scissioni e crosswalk, confini verificati, indicatori per
sesso/età, famiglie e abitazioni. Uscita: test di gerarchia e copertura, riconciliazioni tra
fonti e vintage, nessuna somma di categorie sovrapposte. Benchmark su volume rappresentativo.

M2 completata per il [perimetro ISTAT revisionato](sources/istat-m2.md): tre
snapshot geografici, otto eventi, 317 selezioni serie/periodo e 22.678 osservazioni.
Pubblicazione atomica, API e web, 2.815 riconciliazioni; benchmark PostgreSQL su
1.024.000 aggregati inventati. Storia continua, tutti gli anni e tutte le variabili
comunali non sono impliciti in questa copertura. [Verifiche](validation.md).

## M3 — sintesi pilota
Area limitata, metodo esplicito (es. IPF/IPU o ricostruzione combinatoria da valutare), input
ammessi, seed e versioni riproducibili. Vincoli familiari e demografici, metriche fuori
calibrazione quando disponibili (assenze dichiarate), incertezza e verifica indipendente.
Nessuna persona virtuale associata a reale.

Implementato e verificato il [pilota locale della Valle d'Aosta](synthesis-m3.md):
123.360 residenti virtuali e 60.468 famiglie per replica, 15 repliche, input
coerenti al confine 2021/2022, ricostruzione vincolata senza microcampione,
margini e congiunta sesso/età esatti rispetto ai conteggi ISTAT, sensibilità 6+.
La congiunta è ora interamente usata per calibrare: non è disponibile una
statistica osservata inutilizzata per validazione fuori calibrazione.
**M3 chiuso nel perimetro accettato dalla revisione umana di progetto**:
allocazione familiare casuale vincolata ammessa come prima versione, miglioramenti
successivi guidati dai dati. Riferimento unico: **6+ = 6 componenti, seed 1701**;
gli altri seed e le dimensioni 7/8 sono sensibilità. Sei è il minimo della
classe osservata, senza stimare la coda; resta esplicito il residuo di 929 adulti.
[Esito, razionale e replica adottata](reviews/m3-human-review.md).

La [revisione v3](adr/0011-stable-birth-cohorts.md) sostituisce l'età individuale
memorizzata con una coorte di nascita stabile e un calcolo annuale esplicito;
100+ resta una classe aperta. Conserva calibrazione e scelte del riferimento,
senza implementare dinamiche demografiche o modificare gli esperimenti v2.

La verifica indipendente implementata rilegge i Parquet con SQL separato.
La revisione scientifica esterna e l'analisi disclosure non sono state svolte:
restano condizioni per la distribuzione dei microdati, senza impedire lo
sviluppo locale M4. [Calibrazione esatta](adr/0009-exact-demographic-calibration.md)
e [decisione di progetto](adr/0010-model-fidelity-and-m3-reference.md).

## M4 — scala nazionale 1:1
Batch territoriali, snapshot colonnari e output aggregati; prova a 1M, 10M e volume nazionale.
Uscita: budget misurati di RAM/disco/tempo, checkpoint e recupero, convalida statistica,
valutazione disclosure e formato di distribuzione concordato.

**Implementata e verificata nel perimetro locale**: [M4](synthesis-m4.md) adotta
il riferimento 2024/2025 e genera 58.943.464 persone virtuali in 7.896 comuni,
107 province/UTS e 20 regioni. Le congiunte sesso/età e le classi familiari
comunali riconciliano con i livelli superiori. Checkpoint, ripresa, audit
indipendente e prove effettive 1M/10M/nazionale passano entro i budget.
[Misure, identità e test](validation.md#m4--scala-nazionale-11).

La [valutazione statistica e disclosure](reviews/m4-disclosure.md) documenta
rarità, ipotesi e limiti. Formati implementati: Parquet per microdati locali,
JSON per soli aggregati regionali; ambito e formato sono sottoposti alla
revisione della PR. Nessun dataset viene pubblicato da questa milestone.
La revisione scientifica esterna e la distribuzione pubblica dei microdati
rimangono condizioni separate, non dichiarate concluse dal completamento tecnico.

## M5 — lavoro, servizi e scenari
Collegamenti e dinamiche documentati, confronto baseline/intervento, sensibilità ai parametri
e comunicazione dei limiti causali. La complessità del modello cresce solo dopo validazione
del passo precedente. Non è previsto un agente LLM per ogni individuo.

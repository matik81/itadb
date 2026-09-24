# Popolazione — ordine eseguibile delle integrazioni

Stato: implementazione e verifiche locali completate, 24 settembre 2026.

## Problema e risultato

Le priorità v5 erano documentate, ma il riferimento eseguibile storico
assegnava ancora la cittadinanza dopo le famiglie. La richiesta dell'utente
è stata applicata ovunque: sesso/età → geografia → cittadinanza → famiglie.

Il nuovo riferimento `population-reference/1` genera direttamente dagli
input ammessi, senza uno snapshot familiare di partenza. Per ogni batch
conserva gli individui con cittadinanza prima della composizione delle
famiglie; un audit indipendente verifica che l'ultimo passaggio non cambi
alcun attributo dei primi tre. Le famiglie restano casuali e vincolate:
riordinare non introduce una calibrazione delle relazioni familiari.

## Ambito e decisioni

- Nuovi contratto, CLI corrente, generatore, runner riprendibile e audit.
- Riutilizzo delle ammissioni ISTAT, dei vincoli e dei budget già verificati.
- Comandi storici esplicitamente identificati; snapshot e verificatori
  precedenti conservati, senza riscriverne priorità o evidenze.
- Documento corrente, benchmark e consegna Git/PR allineati al nuovo riferimento.
- Nessuna modifica a DB/API/web, dipendenze o fonti esterne.

## Fasi e verifiche

1. Separati assegnazione della cittadinanza e composizione familiare;
   `individuals.parquet` viene scritto prima di qualunque famiglia nel batch.
2. Registrati ordine, riferimento e artefatto prima delle famiglie nell'identità.
3. Passati 284 test Python, lint e tipi Windows/Linux. Audit di invarianza,
   recupero fra fasi e batch, retry, corruzione e mancato completamento verificati.
4. Benchmark 1M, 10M e nazionale eseguiti entro i budget; audit separato passato.
   Riproduzione 10M: 11 file identici. Confronto nazionale: 214 Parquet finali
   identici allo storico; riferimenti precedenti verificati, retry nazionale passato.
5. Evidenze registrate nella [validazione](../validation.md#ordine-eseguibile-della-popolazione)
   e nelle [misure](../benchmarks/population-order-2026-09-24.json).
   Consegna sul branch dedicato M4, rebase su main e aggiornamento della PR;
   controlli CI sul commit finale.

Log locale conservato: `.tools/population-progress.log`. Snapshot corrente:
`24a56e3bdb58fb1af523ea1b6019e8de04292ecdf11105fc6885cacc4903b76c`.

Rischio esplicito: il nuovo ordine non rende plausibili o osservate le
relazioni di età/cittadinanza nella famiglia. Gli incroci non osservati
restano sintetici; la classe 6+ resta rappresentata con 6 componenti.

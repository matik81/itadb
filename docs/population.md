# Popolazione virtuale — integrazioni di dati esterni

Aggiornato al 24 settembre 2026. Questo documento riepiloga le integrazioni
di dati esterni per la popolazione virtuale, con il loro stato effettivo.

**Ordine di riferimento: 1. sesso ed età → 2. geografia amministrativa →
3. cittadinanza → 4. famiglie.**

**I primi tre passaggi sono esatti rispetto ai conteggi osservati disponibili.
Il quarto conserva i conteggi delle classi dimensionali delle famiglie, ma la
composizione per età e cittadinanza è ancora casuale e non calibrata.**
Questo è l'ordine delle [priorità di fedeltà, versione 5](model-fidelity.md),
concordato il 24 settembre 2026 e applicato alla pipeline corrente
`population-reference/1`. Le precedenti integrazioni restano documentate
come riferimenti storici.

| Passaggio | Dati esterni | Utilizzo nella sintesi | Fedeltà attuale |
|---|---|---|---|
| **1. Sesso ed età** | Conteggi ISTAT per comune, sesso e singola età al **1° gennaio 2025** | Determinano quanti individui virtuali generare in ciascuna cella comune–sesso–età | **Conteggi esatti**; 100+ resta una classe aperta |
| **2. Geografia amministrativa** | Codici e gerarchia ISTAT al **1° gennaio 2025** | Assegnano comune, provincia/UTS e regione agli individui virtuali | **Conteggi territoriali esatti e gerarchia coerente** |
| **3. Cittadinanza** | Fonti ISTAT **STR** e **RCS** al **1° gennaio 2025** | Assegnano una categoria di cittadinanza a ogni individuo, conservando i margini STR/RCS | **Conteggi STR/RCS esatti**; incrocio età–singola cittadinanza sintetico |
| **4. Famiglie** | Conteggi censuari ISTAT per comune e numero di componenti al **31 dicembre 2024** | Determinano numero di famiglie e classi dimensionali | **Composizione ancora grezza**: conteggi per classe esatti, componenti casuali rispetto a età e cittadinanza |

Sesso/età, geografia e conteggi familiari sono integrati nel riferimento
nazionale [M4](synthesis-m4.md), dopo il [pilota M3](synthesis-m3.md) in Valle d'Aosta.
Fonti, riferimenti e checksum M4 sono fissati nel
[contratto degli input](../contracts/istat-m4-national-v1.json).

Per la cittadinanza sono state integrate due fonti complementari:

- [STR — Popolazione straniera residente](https://demo.istat.it/app/?i=STR&a=2025&l=it):
  stranieri complessivi per comune, sesso ed età.
- [RCS — Popolazione residente per cittadinanza o paese di nascita](https://demo.istat.it/app/?i=RCS&a=2025&l=it):
  conteggi per comune, sesso e singola cittadinanza.

I file riconciliano esattamente con M4. La [nuova versione arricchita](citizenship.md)
assegna `citizenship_code` a tutti i **58.943.464 individui**: 53.572.213 nella
categoria italiana e 5.371.251 nella popolazione straniera, inclusi 525 apolidi.
La base M4 originale è conservata immutabile.
L'associazione tra età e specifica cittadinanza è sintetica e documentata:
questo incrocio non è osservato nelle tavole disponibili.

Per le famiglie, i componenti sono assegnati casualmente entro lo stesso
comune, con almeno un adulto per famiglia e assegnazione di tutti i minori.
Nel percorso corrente età e cittadinanza sono già fissate prima di formare
le famiglie. **Non sono calibrate né le relazioni di età
tra componenti né la composizione per cittadinanza**, incluse le frequenze
delle famiglie italiane, straniere e miste. Non sono integrate relazioni di
parentela osservate. La classe 6+ è rappresentata con 6 componenti;
560.159 adulti restano senza assegnazione familiare.
I conteggi dimensionali esatti non dimostrano la plausibilità della composizione.

La riconciliazione dei totali, gli audit e i test sono **verifiche trasversali**,
non ulteriori passaggi di integrazione. Infrastruttura e sviluppo software
supportano questi passaggi. L'anno di nascita sintetico è derivato dall'età
secondo la convenzione adottata, senza una fonte esterna aggiuntiva.

Le fonti forniscono evidenze aggregate: gli individui e le famiglie generati
restano sintetici e non sono associati a persone reali.

## Pipeline corrente

Il [contratto di riferimento](../contracts/population-reference-v1.json)
fissa ordine, seed 1701, classe 6+ = 6 e limiti di fedeltà. Il generatore
esegue i quattro passaggi in ordine per ciascun batch territoriale, fino a
5 milioni di individui. Non richiede uno snapshot familiare di partenza.

1. Espande i conteggi sesso/età e assegna identità stabili.
2. Associa comune, provincia/UTS e regione.
3. Assegna la cittadinanza con i vincoli STR/RCS e salva `individuals.parquet`,
   privo di appartenenze familiari.
4. Legge quegli individui e assegna famiglia e adulto di riferimento,
   producendo `persons.parquet` e `households.parquet`.

L'audit indipendente controlla margini demografici, gerarchia, STR/RCS,
classi dimensionali e integrità familiare. Confronta ogni attributo
individuale prima e dopo il quarto passaggio, inclusa la cittadinanza:
anche uno scambio che conservi i totali deve essere rifiutato.
Il riordino conserva la regola casuale familiare; non introduce correlazioni
familiari osservate. [Metodo e compatibilità](adr/0014-ordered-population.md).

Da root, con gli inventari archiviati da `fetch-m4` e `fetch-citizenship`:

```sh
uv run python scripts/run_logged.py --label "Popolazione ordinata" --log .tools/population-progress.log -- uv run itadb synthesize-population --inputs data/state/m4-official-inputs.json --citizenship-inputs data/state/citizenship-official-inputs.json
uv run python scripts/run_logged.py --label "Audit popolazione" --log .tools/population-progress.log -- uv run itadb verify-population --run data/curated/population/RUN_ID
```

Gli inventari indicati sono quelli locali conservati per il riferimento;
in una nuova acquisizione usare i percorsi effettivamente stampati dai comandi.
Seguire il log con `tail -n 30 -F .tools/population-progress.log`.
Le fonti vengono nuovamente ammesse prima della generazione. Gli snapshot
completati sono in `data/curated/population/`, i checkpoint in `data/state/`,
log e misure in `data/reports/population/`. Un retry verifica gli artefatti;
corruzioni o file inattesi bloccano il completamento e conservano le evidenze.

Il benchmark corrente è `scripts/benchmark_population.py --population
1000000` oppure `10000000`, con `--recovery` e `--reverse-order` per le prove
di ripresa e riproduzione. Sono fixture inventate, distinte dal run nazionale.
I comandi `synthesize-m4` e `synthesize-citizenship` e i rispettivi benchmark
riproducono i riferimenti storici. I loro verificatori restano disponibili.

Il run nazionale corrente è
`24a56e3bdb58fb1af523ea1b6019e8de04292ecdf11105fc6885cacc4903b76c`:
58.943.464 individui, 26.670.169 famiglie, 107 batch e 321 Parquet, inclusi
quelli prima delle famiglie. La generazione e l'audit inline hanno richiesto
267,99 s monitorati, con picco RSS 1,64 GiB; l'audit successivo 35,47 s.
I margini osservati hanno errore zero e la fase familiare conserva tutti
gli attributi precedenti. [Verifiche eseguite](validation.md#ordine-eseguibile-della-popolazione).


## Pubblicazione applicativa dello snapshot verificato

Il prodotto corrente aggiunge un passaggio esplicito dopo la generazione:

```sh
uv run python scripts/run_logged.py --label "Pubblicazione popolazione" --log .tools/population-publication.log -- uv run itadb publish-population --run data/curated/population/RUN_ID
```

Il comando verifica lo snapshot e i contratti delle fonti archiviati, carica
individui e famiglie completi in PostgreSQL e ne ricalcola le distribuzioni.
Solo la versione verificata diventa visibile nelle API v3 e nel frontend.
La pubblicazione è atomica e idempotente; il log e i rapporti sono conservati
in `data/reports/population-publication/`. Un errore produce rollback e
quarantena. L'importatore applicativo rifiuta le fixture inventate.

Gli snapshot Parquet e il loro campo storico `public_release=false` restano
immutabili. Il catalogo applicativo è una nuova evidenza di pubblicazione,
collegata a run ID e checksum. La richiesta dell'utente supera il precedente
perimetro «solo file locali»: [ADR 0015](adr/0015-population-product.md).

La mappa corrente usa la geografia 2025 degli stessi input, non le geometrie
M2 2020/2021/2024. I marcatori rappresentano comuni; nessuna coordinata di
residenza viene assegnata implicitamente ai singoli individui.

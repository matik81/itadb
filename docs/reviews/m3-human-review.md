# M3 — esito della revisione umana di progetto

Data: 23 settembre 2026. Origine: conclusioni esplicite dell'utente nella
revisione del pilota. **Esito: M3 accettato come modello di lavoro iniziale;
pronto per avviare M4 secondo il piano definito.**

Questa è accettazione umana del perimetro e delle assunzioni. Non è una
revisione scientifica esterna, non certifica la plausibilità delle famiglie
e non abilita la distribuzione pubblica dei microdati. I campi originali
`external_scientific_review=not_performed` e `public_release=false` restano veri.

## Conclusioni recepite

| Tema | Esito della revisione | Azione di progetto |
|---|---|---|
| Fedeltà età/sesso | Prima priorità; conteggi osservati vincolanti | Confermata la calibrazione esatta M3 v2 |
| Fedeltà geografica | Seconda priorità: regioni, province/UTS, comuni | Copertura e assegnazione da implementare in M4 |
| Composizione familiare | Terza priorità; allocazione casuale vincolata accettata inizialmente | Miglioramenti successivi guidati da fonti e verifiche, senza bloccare l'avvio di M4 |
| Classe 6+ | Ammessa un'ipotesi di lavoro unica, esplicita e motivata | Scelta attuativa: tutte da 6 persone; razionale e conseguenze sotto |
| Evoluzione | Graduatoria rivedibile, modello univoco per versione | Policy versionata e confronto tra successive versioni |

L'aggiornamento delle fonti, emerso nella discussione, resta un'attività aperta:
il 2021/2022 è il riferimento verificato del pilota, non una dichiarazione
che manchino dati più recenti. M4 inizierà verificando l'ultimo riferimento
comune utilizzabile, con copertura e definizioni coerenti.

## Riferimento unico adottato

Identificatore documentale: **`m3-reference/1`**.

| Elemento | Valore fissato |
|---|---|
| Territorio e periodo | Valle d'Aosta; popolazione 01/01/2022, famiglie 31/12/2021 |
| Algoritmo / audit | `constrained-reconstruction/2.0.0` / `parquet-independent-audit/2.0.0` |
| Input / rapporto | `m3-input/2` / `m3-report/2` |
| Famiglie 6+ | Tutte da **6** componenti |
| Seed | **1701** |
| Replica | `size-6-seed-1701` |
| Esperimento | `ee50a4c577b6462db82c909ea54b092ddc8346c4b8d6463286f848e55d3219a0` |
| Implementazione verificata | Commit `ca8ac10`; sorgenti e lockfile corrispondenti agli hash archiviati nel run |

Percorso locale: `data/curated/m3/ee50a4c577b6462db82c909ea54b092ddc8346c4b8d6463286f848e55d3219a0/size-6-seed-1701/`.
Il manifest nella directory superiore fissa input, codice, dipendenze, ambiente
e checksum. Questi ultimi identificano i file selezionati:

| File | SHA-256 |
|---|---|
| `persons.parquet` | `1ad8c33fa3cbea1d7973b2b9872f3aa2c67bc38ca6e135a49c83c218feae4f69` |
| `households.parquet` | `4bb5b29d63acf7dcef2aa36e447f3a274630c28503245698d7e8ec5d3d134eba` |

Sei è il limite inferiore della classe ISTAT 6+: usa il minor numero di
componenti compatibile con la categoria, senza inventare una media della
coda. Può sottorappresentare persone in famiglie più grandi: l'effetto resta
visibile nel residuo, non è nascosto alterando i residenti. Non è una stima
della vera distribuzione. 1701 è il primo seed già fissato, scelto per
continuità, non per preferire una composizione risultante.

Tutte le famiglie hanno almeno un adulto; tutti i minori sono assegnati.
Queste regole sono ipotesi operative accettate, non leggi universali sulle
famiglie reali. L'adulto di riferimento non è interpretato come genitore.
Parentela e coppie non vengono attribuite. Non si presume un indirizzo reale.

| Misura della replica adottata | Conteggio |
|---|---:|
| Persone virtuali | 123.360 |
| Famiglie virtuali | 60.468 |
| Persone assegnate alle famiglie | 122.431 |
| Adulti non assegnati | 929 |
| Famiglie con almeno un minore | 15.486 |
| Famiglie con tutti i componenti di almeno 65 anni | 8.927 |
| Famiglie con minori e persone di almeno 65 anni | 7.167 |
| Persone di almeno 65 anni sole | 7.827 |

Le ultime quattro categorie si sovrappongono. Sono risultati del modello,
non osservazioni ISTAT della composizione familiare. Il residuo non è
identificato con la popolazione osservata in convivenze.

## Verifica e passaggio a M4

La [verifica tecnica](../validation.md#m3--sintesi-pilota) conserva i 160 test
Python, i 3.030 confronti esatti con ISTAT e il retry invariato. Per questa
chiusura documentale è stata ripetuta la verifica completa del run, con
rilettura SQL delle 15 repliche e controllo dei checksum della replica scelta.
Non è stata necessaria una nuova generazione o modifica degli artefatti.

Il modello di riferimento è unico; le altre 14 repliche rimangono analisi
di sensibilità. La CLI continua a generarle tutte e i vecchi report non
contengono questa decisione successiva: la selezione è registrata qui.

Il [piano M4](../plans/m4-national-synthesis.md) distingue condizioni di avvio,
lavoro da implementare e requisiti di uscita. La mancanza di validazione
scientifica esterna e disclosure non impedisce lo sviluppo locale M4;
restano condizioni per la distribuzione. Il passaggio non attesta che
geografia comunale o prestazioni nazionali siano già implementate.

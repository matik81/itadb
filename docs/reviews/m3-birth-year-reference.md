# M3 — riferimento v3 con coorti di nascita stabili

Data: 23 settembre 2026. Origine: richiesta e autorizzazione dell'utente
a sostituire l'età individuale memorizzata con un riferimento di nascita
stabile. Metodo nell'[ADR 0011](../adr/0011-stable-birth-cohorts.md).
Questo documento registra l'adeguamento tecnico del riferimento precedente,
non una nuova revisione scientifica esterna.

## Riferimento unico adottato

Identificatore documentale: **`m3-reference/2`**. Succede a
[`m3-reference/1`](m3-human-review.md), che rimane immutato e storico.
Conserva gli stessi input, seed e ipotesi familiari; cambia la rappresentazione
della nascita, con i metadati eseguibili `person_model` nel manifest e nel report.

| Elemento | Valore fissato |
|---|---|
| Territorio e periodo | Valle d'Aosta; popolazione 01/01/2022, famiglie 31/12/2021 |
| Algoritmo / audit | `constrained-reconstruction/3.0.0` / `parquet-independent-audit/3.0.0` |
| Input / rapporto / persone | `m3-input/2` / `m3-report/3` / `m3-persons/3` |
| Regola temporale | `year-start-cohort/1`: al 1° gennaio Y prima dei compleanni, età = Y − nascita − 1 |
| Classe iniziale 100+ | `birth_year=null`, `birth_year_upper_bound=1921` |
| Famiglie 6+ / seed | **6** componenti / **1701** |
| Replica | `size-6-seed-1701` |
| Esperimento | `7ffa65715dd035357e71f33feed373528b2cfe490393be318cb898e841dc98ce` |

Percorso locale:
`data/curated/m3/7ffa65715dd035357e71f33feed373528b2cfe490393be318cb898e841dc98ce/size-6-seed-1701/`.
Il manifest registra hash dei sorgenti effettivi, ambiente, lockfile e
working tree dirty: la verifica precede il commit della modifica.

| File | SHA-256 |
|---|---|
| `persons.parquet` | `8fea1b9c4a82b5d88c9dd4d3fcdcc7a3a2b9af64f0de8577406012bc12922525` |
| `households.parquet` | `4bb5b29d63acf7dcef2aa36e447f3a274630c28503245698d7e8ec5d3d134eba` |

La replica contiene **123.360 persone virtuali**, **60.468 famiglie** e
**929 adulti non assegnati**. Gli anni sintetici puntuali sono 123.327;
33 persone hanno solo il limite di nascita (6 maschi e 27 femmine).
Appartenenze, sesso e adulto di riferimento di tutte le persone coincidono
con la replica v2. Il Parquet delle famiglie è identico anche per checksum.

## Verifiche e limiti

Tutte le 15 repliche v3 sono state generate offline dagli originali ISTAT
archiviati. I 3.030 confronti sesso/età con il CSV ufficiale sono esatti,
ricostruendo l'età dalla nascita al riferimento iniziale. Rilettura indipendente
e retry sono passati; i 34 file del nuovo esperimento e i 136 file storici
sono rimasti invariati durante i controlli. [Registro](../validation.md).

Le altre 14 repliche restano analisi di sensibilità, non riferimenti
concorrenti. La regola non inventa compleanni o una distribuzione dei 100+;
il limite inferiore dell'età avanza di un anno a ogni passo. Non vengono
implementate mortalità, nascite, migrazioni o evoluzioni familiari.
L'esattezza iniziale non attesta l'aderenza a osservazioni successive.

Restano validi i limiti della revisione precedente: nessuna validazione
fuori calibrazione disponibile, nessuna revisione scientifica esterna o
valutazione disclosure completata, `public_release=false`.

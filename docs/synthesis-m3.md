# M3 — pilota di sintesi della Valle d'Aosta

Il pilota genera **123.360 persone virtuali per replica**, con **60.468 famiglie
virtuali** e un residuo esplicito non assegnato a famiglie. Nessuna persona
virtuale è associata a un individuo reale. È una baseline sperimentale locale,
non un prodotto statistico certificato, una previsione o un modello causale.

## Input ammessi e riferimenti

Il contratto [`istat-m3-valle-aosta-v1.json`](../contracts/istat-m3-valle-aosta-v1.json)
fissa URL, SHA-256, dimensioni, intestazioni, domini, flag e note di otto originali.
Ogni fonte e manifest viene archiviato e verificato prima della trasformazione.
Metadati DSD/codelist, dataflow e licenza sono originali già revisionati in M2;
il nuovo campione usa gli stessi significati e la stessa versione 1.0 del dataflow.
La richiesta popolazione è stata acquisita con versione URL `1`; intestazione
SDMX e dataflow archiviato dichiarano `1.0`, entrambi fissati nel contratto.

| Evidenza ISTAT | Riferimento | Utilizzo |
|---|---|---|
| Popolazione ITC2, `22_289_DF_DCIS_POPRES1_1` | 01/01/2022 | Margini d'età, sesso per fascia e congiunta fuori calibrazione |
| Famiglie ITC2, `DF_DCSS_FAMIGLIE_TV_1` | 31/12/2021 | Conteggi 1, 2, 3, 4, 5, 6+ componenti |
| Geografia censuaria M2, POP21/FAM21 | 31/12/2021 | Identità territoriale e riconciliazione dei totali |
| DSD, codelist, dataflow e licenza | Acquisizioni archiviate | Significati, attribuzione e tracciabilità |

Il campione nuovo contiene 306 celle, 26.579 byte. Gli altri originali sono
riusati dall'archivio M2. Totali verificati: 123.360 residenti e 60.468 famiglie.
L'uguaglianza al confine d'anno non autorizza a combinare arbitrariamente vintage
diversi. Le date di pubblicazione upstream non vengono inferite dalla data
di acquisizione. Fonte: ISTAT, [IstatData](https://esploradati.istat.it/) e
[Open Data, CC BY 4.0](https://www.istat.it/dati/open-data/).

Le famiglie 1–5 hanno rispettivamente 26.581, 16.689, 8.706, 6.532, 1.534 unità;
quelle 6+ sono 426. Nessun microdato, indirizzo, identificativo personale,
record soppresso o stimato è ammesso. La fixture `m3-invented.json` è separata,
inventata e CC0: non alimenta la CLI ufficiale.

## Metodo, controlli e limiti

Vedere [ADR 0008](adr/0008-synthesis-pilot.md) per formula e alternative valutate.
Il generatore calibra età marginale e sesso nelle fasce 0–17, 18–64, 65+;
assume indipendenza sesso/età all'interno di ogni fascia. La congiunta per
anno singolo, 202 celle, viene usata solo dopo la generazione.
`age=100` significa **100+**, non un'età puntuale.

Ogni famiglia ha la cardinalità dichiarata e un adulto di riferimento;
tutti i minori sono assegnati a una famiglia con almeno un adulto.
L'appartenenza è casuale. Non vengono inferiti parentela, coppie, occupazione,
abitazioni o collegamenti a persone reali. Il residuo con `household_id=null`
è adulto per costruzione: non è una stima della popolazione in convivenze.

I tre scenari assumono che ogni famiglia 6+ abbia 6, 7 oppure 8 componenti.
I cinque seed sono fissati in [`m3-experiment-v1.json`](../contracts/m3-experiment-v1.json).
Vengono conservate tutte le 15 repliche. Nessuno scenario è indicato come
più vero o scelto perché si adatta meglio ai dati di validazione.

Il verificatore SQL indipendente rilegge i Parquet: schema consentito, domini,
unicità degli ID, integrità dei riferimenti, cardinalità, adulto per famiglia,
assegnazione minori, margini e residuo. La verifica non importa il generatore.
Test di perturbazione provano che modificare la congiunta di validazione a
margini invariati cambia il rapporto, senza cambiare i record generati.

La distanza di variazione totale è `sum(abs(sintetico-osservato))/(2*N)`
sulle 202 celle. Vengono conservati anche errore medio assoluto, massimo ed
errori firmati per cella. Non si divide per singole celle osservate pari a zero.
Questa è validazione fuori calibrazione, **dalla stessa fonte**, non un
campione osservato indipendente. Le statistiche familiari del modello non
dispongono di una congiunta osservata di confronto: non sono validate.

I risultati hanno stato `completed_experiment`, `synthetic`, `public_release=false`
e `statistical_acceptance=experimental_not_certified`. La revisione scientifica
umana esterna **non è stata svolta**. La revisione indipendente implementata è
un controllo software degli artefatti. Distribuzione di microdati e integrazione
nelle API restano bloccate in attesa di revisione scientifica e disclosure.

## Esecuzione riproducibile

Comandi dalla root, dopo `uv sync --locked`:

```sh
uv run python scripts/run_logged.py --label "Inventario M3" --log .tools/m3-progress.log -- uv run itadb fetch-m3
# Riutilizzare il percorso stampato dal comando precedente:
uv run python scripts/run_logged.py --label "Sintesi M3" --log .tools/m3-progress.log -- uv run itadb synthesize-m3 --inputs data/state/m3-inputs-UUID.json
# Riutilizzare il percorso dell'esperimento stampato dalla sintesi:
uv run python scripts/run_logged.py --label "Verifica M3" --log .tools/m3-progress.log -- uv run itadb verify-m3 --run data/curated/m3/HASH
```

L'acquisizione è limitata al contratto e riusa originali verificati; un cambio
upstream viene archiviato e bloccato. Sintesi e verifica non accedono alla rete.
Non richiedono PostgreSQL o Docker. L'immagine applicativa conserva `uv.lock`
per registrare l'ambiente anche eseguendo `itadb` nel servizio `pipeline`;
il percorso statistico qui verificato è quello locale dalla root.

`synthesize-m3` accetta `--contract` e `--experiment` espliciti. Il limite è
200.000 residenti, 100.000 famiglie, 10 seed e tre scenari. Parametri impossibili
falliscono prima della generazione; non si correggono silenziosamente margini.
Ogni tentativo scrive un log in `data/reports/m3/`, con fase, conteggi, tempo
trascorso ed esito, senza credenziali o dati personali.

La directory completata contiene `manifest.json`, `input.json`, `report.json`,
README e due Parquet per replica. L'identità comprende input e provenienza,
contratto, versione algoritmo/verificatore, sorgenti Python, lockfile, ambiente,
seed e parametri. Il commit e lo stato dirty sono registrati nel manifest;
gli hash dei sorgenti descrivono anche esecuzioni precedenti al commit.
Le revisioni producono un nuovo hash, senza sovrascrivere esperimenti.

Un lock serializza i retry sullo stesso host; il rename della directory sullo
stesso filesystem rende visibile l'esperimento completo. Non è un protocollo
di pubblicazione distribuito. I tentativi interrotti restano in `data/state/`;
gli errori gestiti producono quarantena. Un retry completato verifica checksum
e ricalcola gli audit: artefatti mancanti o alterati vengono rifiutati.
Non riparare un esperimento sovrascrivendolo; conservare l'evidenza e usare un
nuovo archivio per riprodurlo. Parquet, originali, log e report locali sono esclusi da Git.

## Risultati e lavoro successivo

Le [verifiche M3](validation.md#m3--sintesi-pilota) riportano esecuzione, scostamenti,
sensibilità e test realmente eseguiti. Gli intervalli tra seed sono empirici,
non intervalli di confidenza. Una variabilità nulla della metrica demografica
indica arrotondamento stabile: non assenza di errore o incertezza del modello.

Servono ancora dati sulla composizione familiare e sulle convivenze, verifica
scientifica esterna e analisi disclosure per un rilascio dei microdati. La
scala nazionale 1:1 è M4: nessuna estrapolazione del tempo del pilota la dimostra.

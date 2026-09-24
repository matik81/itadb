# M3 — pilota di sintesi della Valle d'Aosta

Il pilota genera **123.360 persone virtuali per replica**, con **60.468 famiglie
virtuali** e un residuo esplicito non assegnato a famiglie. Nessuna persona
virtuale è associata a un individuo reale. È una baseline sperimentale locale,
non un prodotto statistico certificato, una previsione o un modello causale.

La [revisione umana di progetto](reviews/m3-human-review.md) accetta questa
prima versione e consente l'avvio di M4. Il riferimento unico è
**classe 6+ = 6, seed 1701**; le altre repliche sono
sensibilità. La [graduatoria di fedeltà](model-fidelity.md) adottata per questo
pilota storico era età/sesso, geografia, poi composizione familiare.
La revisione v3 conserva queste scelte e introduce coorti di nascita stabili
([ADR 0011](adr/0011-stable-birth-cohorts.md)). Il riferimento v2
`m3-reference/1` rimane storico; il riferimento v3 è registrato
[separatamente](reviews/m3-birth-year-reference.md).

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
| Popolazione ITC2, `22_289_DF_DCIS_POPRES1_1` | 01/01/2022 | Conteggi esatti per sesso e singola età: 202 celle |
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

Vedere [ADR 0009](adr/0009-exact-demographic-calibration.md) per la calibrazione
esatta e [ADR 0008](adr/0008-synthesis-pilot.md) per l'allocazione familiare.
Il generatore crea esattamente tanti record quanti indicati da ISTAT in ogni
combinazione sesso/età: 2 sessi × 101 classi = **202 conteggi interi vincolanti**.
L'input conserva totale e maschi per età; le femmine sono la differenza,
dopo aver verificato sul CSV originale che maschi + femmine = totale.
Non serve arrotondare né stimare la distribuzione sesso/età. Ogni aggregazione
successiva in fasce d'età conserva la stessa uguaglianza con ISTAT.
La cella di calibrazione 100 significa **100+**, non un'età puntuale.

### Proprietà individuali e anno di nascita

Il Parquet v3 conserva sette campi:

| Campo | Tipo | Significato |
|---|---|---|
| `person_id` | BIGINT | Identificativo univoco all'interno della replica |
| `household_id` | BIGINT, nullable | Famiglia virtuale; null per il residuo non assegnato |
| `birth_year` | SMALLINT, nullable | Anno di nascita sintetico per le classi iniziali 0–99 |
| `birth_year_upper_bound` | SMALLINT, nullable | Ultimo anno di nascita possibile per la classe iniziale 100+ |
| `sex` | VARCHAR | M/F, secondo le categorie di calibrazione |
| `reference_adult` | BOOLEAN | Un adulto di riferimento per famiglia, senza ruolo di parentela |
| `data_kind` | VARCHAR | Sempre `synthetic` |

Esattamente uno dei due campi di nascita è valorizzato; entrambi restano
stabili. L'età non viene memorizzata: al 1° gennaio Y, **prima dei compleanni
dell'anno**, si calcola `Y - birth_year - 1`. È la convenzione annuale
`year-start-cohort/1`, non una ricostruzione di compleanni osservati.
Al riferimento 2022: età 0 → nascita 2021, età 30 → 1991, età 99 → 1922.
Per 100+: nascita esatta null, limite superiore 1921.

```python
from itadb.synthesis.demography import age_at_year_start

age_at_year_start(2022, birth_year=1991)  # AnnualAge(30, False)
age_at_year_start(2023, birth_year=1991)  # AnnualAge(31, False)
age_at_year_start(2023, birth_year=None, birth_year_upper_bound=1921)
# AnnualAge(101, True): almeno 101 anni, senza età puntuale inventata
```

`years` è l'età secondo la convenzione; quando `is_lower_bound=True` è solo
un limite inferiore. Un individuo inizialmente di 99 anni diventa di 100
anni esatti secondo questa regola, distinto dalla classe che avanza a 101+.
Il calcolo non modifica i record, non assegna compleanni infra-annuali e
non simula sopravvivenza, nuovi nati o cambiamenti delle famiglie. I conteggi
degli anni successivi non sono calibrazioni su nuove osservazioni.

Manifest e report contengono `person_model`: versione dello schema, regola,
formula, data iniziale, classe aperta, natura sintetica e razionale.
Il verificatore controlla i due campi e ricostruisce indipendentemente l'età
alla data iniziale per riconciliare gli stessi conteggi ISTAT dell'input.

### Assegnazione familiare e controlli

Ogni famiglia ha la cardinalità dichiarata e un adulto di riferimento;
tutti i minori sono assegnati a una famiglia con almeno un adulto.
L'appartenenza è casuale. Non vengono inferiti parentela, coppie, occupazione,
abitazioni o collegamenti a persone reali. Il residuo con `household_id=null`
è adulto per costruzione: non è una stima della popolazione in convivenze.

Il modello di riferimento assume che **ogni famiglia 6+ abbia 6 componenti**:
è il minimo della categoria osservata, scelto senza ipotizzare una media
della coda. Non stima la vera distribuzione delle famiglie numerose. Il
residuo di 929 adulti rimane visibile e non viene assorbito artificiosamente.
Il seed di riferimento **1701** è il primo già fissato, senza selezione in
base ai risultati. Razionale, identità e checksum sono nella revisione umana.

Gli scenari 7 e 8 componenti e gli altri seed sono analisi di sensibilità.
I cinque seed sono fissati in [`m3-experiment-v1.json`](../contracts/m3-experiment-v1.json).
Vengono conservate tutte le 15 repliche. Il seed cambia l'assegnazione alle
famiglie e l'ordine dei record, mantenendo identica la congiunta demografica.
La CLI continua a produrre le 15 repliche: per il riferimento si usa soltanto
`size-6-seed-1701` del run identificato nella revisione della rispettiva versione.
Nessuna alternativa
è adottata implicitamente e nessuna scelta è dichiarata più vera statisticamente.

M3 fissa la regione nell'input, ma i Parquet non assegnano province o comuni
alle persone o alle famiglie. La seconda priorità della graduatoria richiede
quindi input e controlli territoriali aggiuntivi in M4.

Il verificatore SQL indipendente rilegge i Parquet: schema consentito, domini,
unicità degli ID, integrità dei riferimenti, cardinalità, adulto per famiglia,
assegnazione minori, margini, tutte le 202 celle sesso/età e residuo.
La verifica non importa il generatore. Una differenza anche di una sola
persona per cella blocca il completamento dell'esperimento. Un test scambia
il sesso tra due età mantenendo i vecchi margini per fascia: l'audit lo rifiuta.

La distanza di variazione totale è `sum(abs(sintetico-osservato))/(2*N)`
sulle 202 celle. Vengono conservati anche errore medio assoluto, massimo ed
errori firmati per cella. Non si divide per singole celle osservate pari a zero.
Queste metriche sono registrate in `calibration_joint` e devono essere tutte
zero: misurano il rispetto dei vincoli. **Non sono validazione fuori calibrazione**.
Il rapporto dichiara `out_of_calibration_validation=not_available`: tutte le
celle demografiche disponibili sono già usate. Le statistiche familiari del
modello non dispongono di una congiunta osservata di confronto: non sono validate.

I risultati hanno stato `completed_experiment`, `synthetic`, `public_release=false`
e `statistical_acceptance=experimental_not_certified`. La revisione umana di
progetto è conclusa con accettazione iniziale; la revisione scientifica
esterna **non è stata svolta**. La revisione indipendente implementata è
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

Questa revisione usa input `m3-input/2`, schema persone `m3-persons/3`,
rapporto `m3-report/3`, algoritmo `constrained-reconstruction/3.0.0` e
audit `parquet-independent-audit/3.0.0`.
Il contratto delle fonti e quello dei seed restano v1: gli originali e i parametri
non cambiano. Gli esperimenti v1 con congiunta fuori calibrazione e quelli
v2 con `age` materializzato restano storici immutabili; per verificarli
serve l'implementazione registrata (ultimo v1: commit `a722563`; riferimento
v2: commit `ca8ac10`). La CLI v3 rifiuta versioni incompatibili
con un messaggio esplicito; una nuova sintesi crea una directory distinta.

Un lock serializza i retry sullo stesso host; il rename della directory sullo
stesso filesystem rende visibile l'esperimento completo. Non è un protocollo
di pubblicazione distribuito. I tentativi interrotti restano in `data/state/`;
la directory di un nuovo tentativo viene creata soltanto sotto lock, dopo
aver escluso il riuso di un esperimento completato. I retry riusciti non
accumulano directory di staging; i log per tentativo restano conservati.
Gli errori gestiti producono quarantena. Un retry completato verifica checksum
e ricalcola gli audit: artefatti mancanti o alterati vengono rifiutati.
Non riparare un esperimento sovrascrivendolo; conservare l'evidenza e usare un
nuovo archivio per riprodurlo. Parquet, originali, log e report locali sono esclusi da Git.

## Risultati e lavoro successivo

Le [verifiche M3](validation.md#m3--sintesi-pilota) riportano esecuzione, uguaglianza,
sensibilità e test realmente eseguiti. Gli intervalli tra seed sono empirici,
non intervalli di confidenza. La congiunta sesso/età è fissa in tutte le
repliche; la sensibilità riguarda l'allocazione familiare. La corrispondenza
1:1 vale per i conteggi osservati, senza identificare persone reali o
certificare le altre caratteristiche del modello.

Servono ancora dati sulla composizione familiare e sulle convivenze, verifica
scientifica esterna e analisi disclosure per un rilascio dei microdati. La
scala nazionale 1:1 è M4: nessuna estrapolazione del tempo del pilota la dimostra.
L'allocazione familiare attuale è accettata per l'avvio di M4; il suo miglioramento
non è un prerequisito per iniziare quel lavoro. Il [piano M4](plans/m4-national-synthesis.md)
prevede prima la verifica delle fonti più recenti compatibili e la distribuzione
geografica; il riferimento 2021/2022 rimane quello storico verificato di M3.

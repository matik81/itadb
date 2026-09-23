# Primo campione ISTAT: popolazione residente regionale

Verifica del 23 settembre 2026, fuso Europe/Rome (acquisizioni il 22 settembre in UTC).
Stato: **pubblicato nello stack locale**, consultabile via API v2 e web app.
Contratto: [istat-population-regions-v1.json](../../contracts/istat-population-regions-v1.json).
Contratto di pubblicazione: [istat-population-publication-v1.json](../../contracts/istat-population-publication-v1.json).
Piani: [onboarding](../plans/m1-istat-population.md) e [pubblicazione](../plans/m1-publication.md).

## Fonte, significato e perimetro

[IstatData, Italia, regioni, province](https://esploradati.istat.it/databrowser/#/it/dw/categories/IT1,POP,1.0/POP_POPULATION/DCIS_POPRES1/IT1,22_289_DF_DCIS_POPRES1_1,1.0),
popolazione residente al 1° gennaio. Dataflow `IT1,22_289_DF_DCIS_POPRES1_1,1.0`,
DSD `IT1,DCIS_POPRES1,1.0`. Selezione deliberatamente piccola: un anno, 20 regioni
amministrative e il totale nazionale, senza dati personali o record individuali.

Ordine delle dimensioni verificato nella DSD:

| Posizione | Dimensione | Selezione | Codelist IT1, versione 1.0 |
|---|---|---|---|
| 1 | `FREQ` | `A`, annuale | `CL_FREQ` |
| 2 | `REF_AREA` | Italia e 20 codici espliciti nel contratto | `CL_ITTER107` |
| 3 | `DATA_TYPE` | `JAN`, popolazione al 1° gennaio | `CL_TIPO_DATO15` |
| 4 | `SEX` | `9`, totale | `CL_SEXISTAT1` |
| 5 | `AGE` | `TOTAL` | `CL_ETA1` |
| 6 | `MARITAL_STATUS` | `99`, totale | `CL_STATCIV2` |
| 7 | `TIME_PERIOD` | `2024` | dimensione temporale, fuori dalla chiave REST |

I codici sono quelli della codelist ISTAT del dataflow, non codici NUTS ricostruiti
o codici amministrativi dedotti. `ITDA` rappresenta Trentino-Alto Adige/Südtirol:
la selezione esclude `ITD1` e `ITD2` per evitare di contare due volte le province
autonome. Italia è un controllo, non una ventunesima regione da sommare.

Il valore è un conteggio di persone, senza moltiplicazione. Nel campione
`UNIT_MEAS` e `UNIT_MULT` sono vuoti: l'unità deriva dalla misura `JAN` revisionata
nel contratto, non da un attributo presente nel CSV. Sono ammessi anche i codici
espliciti `PERS` e `0`, verificati nelle rispettive codelist.

## Acquisizione e controlli realmente eseguiti

Il CSV ufficiale contiene **21 righe**, 2.098 byte. La somma delle 20 regioni è
**58.971.230**, uguale al totale Italia, con differenza e tolleranza pari a zero.
La revisione delle righe include Italia, Piemonte (4.251.623), Trentino-Alto Adige
(1.082.702) e Sardegna (1.570.453), confrontate tra CSV e rapporto normalizzato.
È un controllo della trasformazione sullo stesso upstream, non una validazione
statistica indipendente con un'altra fonte.

Tutti i valori del campione sono senza `OBS_STATUS`. Il rapporto li identifica
come `unflagged_upstream`: l'assenza di un flag non dimostra che il dato derivi
esclusivamente da osservazione diretta. Flag di stima, provvisorietà, segreto o
altri stati fanno fallire questo primo contratto; non vengono cancellati né
convertiti in valori osservati. Il supporto a tali stati richiede una revisione.
Anche valori mancanti o soppressi vengono bloccati, mai trasformati in zero.

Le note territoriali `FILTER__...`, etichettate “Filtro” nella codelist, restano
nel rapporto. Altre note non revisionate bloccano il controllo. La validazione
confronta identità e ordine DSD, riferimenti e significati dei codici selezionati,
intestazioni, domini, periodo, chiave unica, conteggi interi non negativi entro
int64, copertura esatta e totale nazionale. Non interpreta contratti arbitrari.

Una richiesta esplorativa con `startPeriod=2024&endPeriod=2024` ha restituito
anche `TIME_PERIOD=2025`. La richiesta definitiva usa entrambi gli estremi
**`2024-01-01`** e contiene solo il 2024. Il gate verifica comunque il periodo;
non scarta silenziosamente righe aggiuntive.

L'annotazione `LAST_UPDATE` del dataflow è `2026-03-31T08:03:43.724Z`.
È conservata come `upstream_last_update`; **`upstream_published_at` resta null**:
non è stata accertata la data di pubblicazione delle singole osservazioni.

## Licenza e provenienza

Fonte e attribuzione: Istat, Popolazione residente al 1° gennaio, Italia, regioni,
province. Selezione e controlli: Itadb.
La [pagina Open Data ISTAT](https://www.istat.it/dati/open-data/) associa i dati
del sito e delle banche dati di diffusione alla
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
La pagina è stata acquisita e il riferimento applicato a questo campione;
il contratto registra data di verifica, attribuzione e hash dell'evidenza.
La licenza del codice Itadb resta distinta dalla licenza dei dati e dei metadati.

Originali conservati localmente, esclusi da Git:

| Artefatto | Byte | SHA-256 |
|---|---:|---|
| Dataflow | 3.641 | `64cd45fd4f96fd65577c6c9cebcf61d05c672eea5ed743cb63e02b67233e9b96` |
| DSD e codelist complete | 10.214.619 | `ae72237a7de006839e90f1c7024a5347725e1572dcdc50c199ccb63f15950007` |
| CSV regionale 2024 | 2.098 | `3fda1534b2af47487d2cffa6dd468997a4ae375651c8eef8f80eeca2ee40f32b` |
| Pagina licenza | 123.862 | `5104ea81de8b249fb2cd2f873e5d931e39337ebc3f105cd66bebda20daf8b515` |

Ogni originale è in `data/raw/<prime-due-cifre>/<sha256>/payload`, con manifest
che registra URL, acquisizione e checksum. DSD completa e codelist occupano
circa 10 MB perché la lista territoriale include codici fuori dal campione:
non sono stati scaricati i relativi dati statistici. Le acquisizioni esplorative
sono state limitate a 20 MB per metadati e 100 kB per dati. Gli estratti XML nei
test sono derivati, con licenza e modifiche dichiarate; i conteggi della fixture
CSV sono inventati e diversi dai dati ufficiali.

## Riprodurre da PowerShell

Questi comandi effettuano tre richieste live esplicite: metadati del dataflow,
DSD con codelist e campione filtrato. Il connettore condivide il limite locale
di una richiesta ogni 15 secondi, inferiore alle
[5 richieste/minuto dichiarate da ISTAT](https://www.istat.it/classificazioni-e-strumenti/web-services-sdmx/).
Non rilanciare le acquisizioni per rieseguire il controllo offline.

```powershell
$uvPath = if (Get-Command uv -ErrorAction SilentlyContinue) { 'uv' } else { '.tools/uv/uv.exe' }
$flow = & $uvPath run itadb fetch-structure istat --resource dataflow --agency IT1 --identifier 22_289_DF_DCIS_POPRES1_1 --version 1.0 --references none | ConvertFrom-Json
$dsd = & $uvPath run itadb fetch-structure istat --resource datastructure --agency IT1 --identifier DCIS_POPRES1 --version 1.0 --references all | ConvertFrom-Json
$contract = Get-Content -Raw -Encoding utf8 contracts/istat-population-regions-v1.json | ConvertFrom-Json
$areas = $contract.territories.PSObject.Properties.Name -join '+'
$sample = & $uvPath run itadb fetch istat --flow IT1,22_289_DF_DCIS_POPRES1_1,1.0 --key "A.$areas.JAN.9.TOTAL.99" --start-period 2024-01-01 --end-period 2024-01-01 | ConvertFrom-Json
& $uvPath run itadb check-istat-population --acquisition $sample.manifest --structure $dsd.manifest --dataflow $flow.manifest
```

L'ultimo comando lavora senza rete né PostgreSQL. I tre argomenti indicano i
**manifest**, non i payload. Il report di successo è in `data/reports/`;
la sua identità dipende da originali, manifest, contratto e versione del controllo.
Una ripetizione con gli stessi input verifica e riusa lo stesso file senza
riscriverlo. Una nuova acquisizione o revisione produce una nuova evidenza.
Un errore di qualità o provenienza conserva un report in `data/quarantine/` e
non produce un report di successo. Nessuno di questi comandi pubblica nel DB.

Il comando generico `fetch` conserva il limite di 100 MB dello scaffold;
la query qui documentata è selettiva e il gate accetta al massimo 100 kB e 21 righe.
Le nuove acquisizioni potrebbero avere hash diversi per aggiornamenti upstream o
timestamp dei metadati: verificare la nuova evidenza senza sostituire la precedente.

## Pubblicazione in DB/API/web

Dopo migrazioni e configurazione del ruolo reader, usare gli stessi manifest e
l'originale della pagina di licenza, conservato durante la verifica:

```powershell
& $uvPath run itadb ingest-istat-population --acquisition $sample.manifest --structure $dsd.manifest --dataflow $flow.manifest --license-evidence PERCORSO_HTML_LICENZA
```

Nel Compose eseguire il comando con `docker compose run --rm pipeline itadb ...`
e percorsi interni all'archivio `/app/data`. Gli originali acquisiti sul filesystem
Windows vanno prima trasferiti nell'archivio del worker, conservando bytes, hash
e manifest. Tutti i worker di uno stesso catalogo devono condividere l'archivio.
La copia già presente in questa installazione è nel volume `itadb_evidence`;
gli input sono registrati in `/app/data/state/m1-official-inputs.json`.

Il contratto verifica il checksum della pagina licenza già revisionata. Una nuova
pagina scaricata può avere bytes differenti: non aggiornare il checksum alla cieca;
revisionare l'evidenza e versionare i contratti prima della pubblicazione.

La pipeline ricalcola i gate sugli originali, crea Parquet/Zstandard e carica
21 righe via COPY. Controlla nuovamente somma e conteggio in PostgreSQL, registra
12 artefatti e pubblica in transazione. Retry identici riusano la stessa release.
Un errore conserva run e quarantena senza pubblicare dati parziali.
Le API v2 preservano `unflagged_upstream` e mostrano il livello territoriale;
la web app esplicita la sovrapposizione tra regioni e controllo nazionale.

Per dati o metadati cambiati, indicare `--supersedes UUID_CORRENTE` e
`--revision-reason "Motivazione revisionata"`. Un predecessore obsoleto viene
rifiutato. La release precedente resta immutabile e consultabile. L'identità
ignora il solo Header di risposta SDMX, non gli aggiornamenti semantici.

I contratti nel repository usano terminatori LF. La versione 1.0.1 del contratto
di pubblicazione fissa il checksum portabile dell'onboarding; l'adeguamento
rispetto alla prima pubblicazione Windows è registrato come revisione con
valori invariati. Gli originali dei contratti precedenti restano tra gli artefatti.

La release corrente verificata nello stack locale è
[`eaef6df9-96db-58bd-9b9d-9e203d89d030`](http://localhost:8080/api/v2/releases/eaef6df9-96db-58bd-9b9d-9e203d89d030),
successiva a `4d602369-9057-57a0-9942-9d0ac9bcb91e`. Tutti i 21 valori e gli
attributi upstream sono stati confrontati tra API e CSV originale; i 72 controlli
qualità sono passati. [Registro della verifica](../validation.md#pubblicazione-istat-locale-23-settembre-2026).

## Limiti del perimetro M1

La validità territoriale attestata è solo `[2024-01-01,2024-01-02)`, con gerarchia
Italia/regioni e namespace versionato. Il DB impedisce sovrapposizioni e date
fuori validità. Confini, crosswalk e fusioni/scissioni su altri periodi restano
in M2; non sono dedotti da questa selezione. La data di pubblicazione upstream
rimane non accertata. Nessuna prova di prestazioni su scala nazionale o di
popolazione sintetica è stata eseguita.

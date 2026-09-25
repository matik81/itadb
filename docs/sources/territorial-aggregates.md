# Copertura territoriale e demografica ISTAT

Perimetro revisionato il 23 settembre 2026. Il contratto
[`istat-territorial-aggregates-v1.json`](../../contracts/istat-territorial-aggregates-v1.json) fissa 14 originali con URL,
SHA-256, byte, intestazioni e domini ammessi. I file originali e i manifest sono
nell'archivio locale, esclusi da Git. Nuovi contenuti upstream richiedono una
revisione esplicita del contratto, non un aggiornamento silenzioso.

## Copertura effettiva

| Evidenza | Riferimento | Copertura |
|---|---|---|
| Geografie amministrative | 01/01/2020 | Italia, 20 regioni, 107 unità territoriali sovracomunali, 7.904 comuni |
| Geografie censuarie | 31/12/2021 | Italia, 20 regioni, 107 UTS, 7.904 comuni |
| Geografie amministrative | 01/01/2024 | Italia, 20 regioni, 107 UTS, 7.899 comuni |
| Popolazione censuaria, attributo POP21 | 31/12/2021 | Comuni, UTS e regioni; nessun totale Italia inventato |
| Popolazione per sesso ed età | 01/01/2024 | 20 regioni e Italia; M, F, totale; anni singoli 0–99, 100+, totale |
| Famiglie, FAM21 e SDMX | 31/12/2021 | Totali comunali, UTS, regionali; SDMX regionale e Italia per 1, 2, 3, 4, 5, 6+ componenti e totale |
| Abitazioni | 31/12/2021 | 20 regioni e Italia; totali, occupate e non occupate |

Risultato: **22.678 osservazioni, 317 selezioni serie/periodo, 24.091 versioni
territoriali e 2.815 equazioni verificate**. Totali e dettagli coesistono come
serie separate: non sono righe da sommare indiscriminatamente. Le serie hanno
unità persone, famiglie o abitazioni. Il conteggio delle famiglie non è quello
delle persone; le abitazioni non coincidono con gli edifici.

Fonti: [confini ISTAT](https://www.istat.it/notizia/confini-delle-unita-amministrative-a-fini-statistici-al-1-gennaio-2018-2/),
[codici e variazioni](https://www.istat.it/classificazione/codici-dei-comuni-delle-province-e-delle-regioni/),
[IstatData](https://esploradati.istat.it/),
[licenza e open data](https://www.istat.it/dati/open-data/), CC BY 4.0.
I dataflow sono `22_289_DF_DCIS_POPRES1_1`, `DF_DCSS_FAMIGLIE_TV_1` e
`DF_DCSS_ABITAZIONI_TV_1`, tutti IT1/versione 1.0. DSD/codelist e dataflow sono
archiviati integralmente con i dati selezionati. I parametri di query SDMX per il
censimento usano l'anno 2021; il riferimento statistico normalizzato è il 31 dicembre.
Le date di pubblicazione upstream non accertate restano null.

## Storia e riconciliazione

Otto eventi dal prospetto ufficiale
[Novità 2017–2026](https://www.istat.it/wp-content/uploads/2026/02/Novita-2026-2017-26febbraio2026.pdf):
incorporazione di Monteciccardo in Pesaro; scissione Trapani/Misiliscemi;
trasferimenti Montecopiolo e Sassofeltrio; fusioni Moransengo-Tonengo,
Bardello con Malgesso e Bregano, Campospinoso Albaredo, Uggiate con Ronago.
Le decorrenze e i codici sono fissati nel contratto dopo lettura del prospetto.
La pipeline riconcilia tutti i codici comunali introdotti/soppressi tra i tre
snapshot con questi eventi. Non ricostruisce rinominazioni, ogni trasferimento
di superficie o la validità amministrativa continua tra le date.

Le fusioni complete hanno peso esatto 1 per ciascun predecessore; scissioni e
trasferimenti sono collegamenti strutturali con peso null. `reaggregate_exact`
rifiuta copertura incompleta, sovrapposizioni e scissioni senza pesi. Non vengono
interpolate popolazioni tra 2021 e 2024, né inferiti pesi dall'area dei poligoni.
Le 20 uguaglianze FAM21 = totale famiglie SDMX sono esatte: sono prodotti della
stessa fonte, non due stime statisticamente indipendenti. I totali coincidenti
vengono pubblicati una sola volta.

## Confini verificati e derivazioni

Gli originali SHP/DBF/PRJ sono letti senza estrarre percorsi ZIP. Il sistema
verifica budget, livelli, codici e CRS WGS84/UTM32N, quindi trasforma in EPSG:4326.
Il namespace include data e checksum geografico. La validità di un giorno
attesta lo snapshot; non pretende di descrivere il periodo tra due acquisizioni.

L'audit ha trovato 25 auto-intersezioni degli anelli, elencate nel contratto.
Solo questi casi possono passare attraverso `ST_MakeValid`: la variazione relativa
d'area deve essere ≤ 10⁻¹⁰ (misurata tra circa 10⁻¹⁶ e 4,1×10⁻¹⁵). Originali,
motivo e variazione misurata sono conservati. Casi nuovi bloccano la pubblicazione.

I poligoni fonte ai diversi livelli non sono perfettamente annidati: lo
scostamento massimo misurato è il 13,5301% dell'area di Camparada nel 2021.
Per pubblicare una gerarchia coerente, i confini UTS sono **derivati dall'unione
dei comuni** e quelli regionali dall'unione delle UTS. Il rapporto registra
lo scostamento originale e la derivazione; il gate verifica validità e
contenimento dopo l'unione. Nessun conteggio demografico viene modificato.
I GeoJSON API sono semplificati a 0,001 gradi, massimo 20.000 vertici: servono alla
consultazione, non a misure catastali o attribuzione di indirizzi.

## Procedura riproducibile

```sh
uv run python scripts/run_logged.py --label "Acquisizione aggregati" -- uv run itadb fetch-territorial-aggregates
# Il comando stampa il percorso del nuovo inventario; riusarlo nei due passi seguenti.
uv run itadb check-territorial-aggregates --inputs PERCORSO_INVENTARIO
uv run python scripts/run_logged.py --label "Pubblicazione aggregati" -- uv run itadb ingest-territorial-aggregates --inputs PERCORSO_INVENTARIO
```

`fetch-territorial-aggregates` riusa gli originali il cui hash è verificato, altrimenti acquisisce
soltanto l'inventario contrattuale, con limite dimensionale e intervallo ISTAT
di 15 secondi. Modifiche della fonte vengono archiviate e bloccate per revisione.
I controlli e l'importazione successivi non accedono alla rete. Per Docker usare
gli stessi comandi dentro `docker compose --profile offline run --rm pipeline`, così originali,
manifest e artefatti restano nel volume condiviso `itadb_evidence`.

Retry sullo stesso inventario restituisce lo stesso UUID. Una nuova acquisizione
con manifest diverso è nuova evidenza di provenienza e richiede
`--supersedes UUID --revision-reason "Motivazione"`. Identità della release:
bundle normalizzato, contratto, inventario delle evidenze e trasformazione.
Revisioni concorrenti sono serializzate; i file conservati sono protetti anche
dalla contesa tra processi. Errori lasciano run fallito e quarantena, senza
release parzialmente visibili.

Questa pipeline pubblica aggregati statistici. Per generare individui e famiglie
sintetiche seguire il [workflow della popolazione](../population.md).

Dopo la pubblicazione locale, esportare e attivare una nuova release DuckDB
per aggiornare le API online. [Procedura](../deployment.md).

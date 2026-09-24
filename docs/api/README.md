# API della popolazione e delle evidenze

## v3 — popolazione sintetica

Tutti i percorsi seguenti sono GET. Dietro il proxy locale hanno prefisso `/api`.

| Percorso | Contenuto |
|---|---|
| `/v3/populations` | Snapshot pubblicati, conteggi e natura sintetica |
| `/v3/populations/{id}` | Riferimento, fonti, modello, rapporto e controlli DB |
| `/v3/populations/{id}/map` | Confini di regioni, province/UTS e comuni, con marcatori comunali |
| `/v3/populations/{id}/municipalities` | Ricerca nome/codice, regione e cursore |
| `/v3/populations/{id}/persons` | Individui filtrati per comune, sesso, età e cittadinanza |
| `/v3/populations/{id}/persons/{person_id}` | Individuo della versione selezionata |
| `/v3/populations/{id}/households` | Famiglie per comune e dimensione |
| `/v3/populations/{id}/households/{household_id}` | Famiglia e tutti i componenti |
| `/v3/populations/{id}/distributions` | Istogrammi sesso/età con filtri territoriali e individuali |
| `/v3/populations/{id}/validation` | Conteggi confrontati, celle discordanti e scostamento massimo |
| `/v3/populations/{id}/comparison` | Singoli vincoli di un comune e conteggi sintetici corrispondenti |

Le liste di persone e famiglie richiedono `municipality_code` a sei cifre;
`limit` è al massimo 500 e `next_cursor` va passato come `after`. Mantenere
snapshot, filtri, `sort_by` e `direction` invariati tra pagine. Cambiare una
selezione azzera il cursore. Gli ID individuali sono locali allo snapshot.
Età 100 con `age_is_lower_bound=true` significa 100+. L'API corrente non
contiene latitudine/longitudine individuali: `/map` dichiara espressamente
`representation=municipality_aggregates`.

La mappa restituisce `regions`, `provinces`, `municipality_boundaries` e
`municipalities`. I confini sono GeoJSON semplificati per visualizzazione;
non sono geometrie catastali. `region_code` filtra province, confini e marker
comunali, mantenendo le regioni come contesto nazionale. Le liste geografiche
sono limitate a 1.000 province e 10.000 comuni per snapshot. Le province
degli snapshot precedenti alla migrazione cartografica vanno caricate con
`publish-population-boundaries`; fino ad allora la relativa lista è vuota.

La web app aggrega i conteggi comunali per le modalità Regioni e Province e
mostra i confini del livello scelto e dei livelli superiori. Cambiando modalità
conserva i genitori selezionati e azzera selezioni figlie, ricerca ed elenco.
Dalle schede regionali si passa alle province, dalle province ai comuni;
i record individuali restano consultabili per comune. I totali cartografici
includono anche i comuni senza coordinate.

Le distribuzioni derivano dai record importati. `/distributions` accetta
`region_code` a due cifre, `province_code` a tre e `municipality_code` a sei,
oltre a sesso, cittadinanza ed età. I filtri si intersecano e restituiscono
al massimo 202 celle sesso/età; territori incompatibili producono una lista
vuota. I filtri individuali aggiornano l'istogramma e l'elenco, mentre cerchi
e schede territoriali riportano i totali senza filtri individuali.
`/comparison` richiede un
comune e il tipo `sex_age`, `foreign_age`, `citizenship` o `household_size`.
Il rapporto originale della generazione mantiene il proprio storico
`public_release=false`; la pubblicazione applicativa ha una propria identità
e controlli distinti, descritti nell'[ADR 0015](../adr/0015-population-product.md).

## API degli aggregati v1 e v2


FastAPI espone OpenAPI 3.1 a `/openapi.json`, Swagger a `/docs`, ReDoc a `/redoc`.
Nel Compose il prefisso esterno è `/api`: <http://localhost:8080/api/docs>.
Il file [openapi.json](openapi.json) è generato e versionato; i tipi del frontend derivano
da esso. La CI rileva differenze non committate e test del contratto divergenti.

| Endpoint GET | Significato |
|---|---|
| `/health/live` | Processo disponibile; nessun accesso DB |
| `/health/ready` | Pool e schema API disponibili |
| `/v1/sources` | Fonti registrate, anche se non ancora importate |
| `/v1/releases?limit=50` | Ultime release pubblicate (massimo 100) |
| `/v1/releases/{uuid}` | Provenienza, periodo, limiti, licenza e checksum |
| `/v1/releases/{uuid}/quality` | Risultati dei gate pubblicati |
| `/v1/observations` | Misure territoriali paginate, con filtri obbligatori |

```sh
curl http://localhost:8080/api/v1/releases
# Inserire l'UUID restituito; nessun valore reale è hardcoded:
curl 'http://localhost:8080/api/v1/observations?release_id=UUID&period=2025-01-01&series=population_total&limit=100'
```

`release_id` e `period` sono obbligatori; `series` vale inizialmente `population_total`.
`after` è un ID territoriale bigint >=0; `limit` è tra 1 e 500. Usare `next_cursor` come
`after`, mantenendo tutti gli altri filtri. `null` indica fine elenco. Nessun totale
calcolato a ogni pagina. Un dataset incompleto non consente di inferire un totale nazionale.

Esempio di forma della risposta, con dati esclusivamente dimostrativi:

```json
{
  "items": [{
    "release_id": "11111111-1111-4111-8111-111111111111",
    "series_code": "population_total", "unit": "persons",
    "territory_id": 1, "territory_code": "DEMO001",
    "territory_name": "Territorio Alfa", "scheme": "ITADB_DEMO",
    "period": "2025-01-01", "value": "1200.000000", "status": "demo"
  }],
  "next_cursor": null
}
```

I Decimal sono stringhe per preservare precisione nei client; `null` è distinto da zero.
Il frontend converte in Number solo per presentare questi conteggi; client analitici devono
usare Decimal. Gli ID bigint futuri oltre 2^53 richiederanno un contratto stringa dedicato;
la v0.1 espone solo dimensioni territoriali piccole, non identificativi di agenti.

Query non valide: 422. Release assente/non pubblicata: 404. Serie/periodo assenti nella
release: pagina vuota. DB indisponibile o timeout: 503. Gli errori gestiti seguono la forma
`application/problem+json` con request_id. Il gateway può emettere 429; il suo corpo è
quello di Nginx. La risposta contiene sempre un nuovo X-Request-ID generato dall'app.

Le API v1/v2 non espongono individui. Nessuna API accetta scritture, SQL arbitrario
o download individuali nazionali illimitati tramite una singola richiesta.
Le API pubbliche di lettura non richiedono login nella v0.1. Prima della produzione definire
fair-use, caching, budget di risorse e monitoraggio. Export grandi saranno job asincroni
con manifest e URL firmati, non una pagina JSON senza limite.

## v2 — evidenze ufficiali e revisioni

La web app usa v2. Le route e gli schemi di risposta v1 restano invariati e
servono solo release compatibili con gli stati v1; una release ISTAT v2 richiesta
tramite v1 restituisce 404. Il catalogo v2 include anche la demo.

| Endpoint GET | Significato |
|---|---|
| `/v2/sources` | Fonti registrate |
| `/v2/releases?limit=50` | Ultime release, comprese quelle sostituite |
| `/v2/releases/{uuid}` | Provenienza, serie, snapshot territoriale e revisione |
| `/v2/releases/{uuid}/quality` | Gate, riconciliazione e differenze tra revisioni |
| `/v2/releases/{uuid}/artifacts` | Tipo, SHA-256 e dimensione degli artefatti |
| `/v2/observations` | Release, serie e periodo obbligatori; pagine da 1 a 500 righe |

Usare `series_code` restituito dalla release: `population_total` per la demo,
`resident_population_jan1` per ISTAT. Esempio sullo stack locale:

```sh
curl http://localhost:8080/api/v2/releases
curl 'http://localhost:8080/api/v2/observations?release_id=UUID&series=resident_population_jan1&period=2024-01-01&limit=100'
```

`unflagged_upstream` significa che la fonte non ha fornito un flag; non viene
convertito in `observed`. La web app lo mostra come «—» in tabelle, filtri e schede;
il valore numerico rimane visibile. Le osservazioni v2 aggiungono livello territoriale,
codice del padre e attributi upstream. `country` e `region` si sovrappongono:
il totale Italia non deve essere sommato alle regioni. La paginazione resta
keyset con `next_cursor`, mantenendo release, serie e periodo costanti.

Le release aggiungono `metadata_sha256`, `series_code`, `territory_snapshot`,
`upstream_last_update`, `upstream_published_at`, `supersedes_release_id`,
`revision_reason` e `attribution`. Le date upstream possono essere null e non
coincidono con acquisizione o pubblicazione Itadb. Una release sostituita rimane
leggibile al proprio UUID; il client può seguire il predecessore dichiarato.

Gli artefatti sono un inventario di provenienza; l'API non espone percorsi del
filesystem né serve download arbitrari. Le viste v2 e il ruolo reader escludono
sempre draft, artefatti e verifiche non pubblicati. La readiness verifica anche
la presenza e i permessi reader su tutte le viste v2, incluse copertura,
territori, crosswalk e confini, senza scandire dati. Uno schema privo delle viste di copertura
o una vista mancante produce 503 su `/health/ready`; `/health/live` resta indipendente.

## Copertura e geografie

| Endpoint GET | Filtri e limiti |
|---|---|
| `/v2/releases/{uuid}/coverage` | Massimo 500 selezioni pubblicate: serie, unità, dimensioni, periodo, schema, snapshot e conteggio |
| `/v2/observations` | Aggiunge `level=country|region|province|municipality`; conservare anche questo filtro tra pagine |
| `/v2/territories` | `release_id`, `snapshot`, `level` obbligatori; `after`, `limit` da 1 a 500 |
| `/v2/crosswalks` | `release_id` obbligatorio; `after`, `limit` da 1 a 500; fonte, decorrenza, codici e peso |
| `/v2/releases/{uuid}/territories/{id}/boundary` | Un MultiPolygon GeoJSON semplificato, 0,001 gradi e massimo 20.000 vertici |

Nelle pubblicazioni multiserie, serie e periodo della release sono la selezione iniziale: leggere `coverage`
per tutte le combinazioni disponibili. Il conteggio copre tutti i livelli della
selezione, non solo quello della pagina. Un livello non coperto restituisce una
pagina vuota; non significa popolazione zero. Totali territoriali e categorie
totali non vanno sommati ai rispettivi dettagli. Il filtro livello è opzionale
per compatibilità; l’esploratore degli aggregati lo imposta sempre.

### Ordinamento e filtri delle tabelle

`/v2/observations` accetta `sort_by=territory_id|name|code|value|status` e
`direction=asc|desc` (default `territory_id`, `asc`). Filtri opzionali:
`search` (1–100 caratteri, sottostringa letterale di nome o codice senza distinzione
maiuscole/minuscole), `parent_code` (codice del padre immediato nello snapshot),
`status=observed|estimated|missing|suppressed|demo|unflagged_upstream`.
L'ordinamento dello stato segue le etichette italiane della web app.

`/v2/crosswalks` accetta `sort_by=id|date|description|from_code|to_code|usage` e
`direction=asc|desc` (default `id`, `asc`), con filtri
`kind=merger|split|recode|transfer` e `weight_basis=exact|structural`.

Filtri e ordinamento sono applicati nel database **prima** della paginazione.
I valori numerici sono ordinati come numeri; i null restano in fondo in entrambe
le direzioni. A parità di valore, l'ID è crescente e rende stabile il cursore.
Mantenere tutti i parametri invariati tra pagine; a ogni modifica ricominciare
con `after=0`. Un cursore fuori dalla selezione restituisce una pagina vuota.
La dimensione massima resta 500 righe. Nessuna modifica alle route v1.

Confine assente o oltre il budget: 404. La forma GeoJSON può essere usata per
consultazione, non per misure catastali. Crosswalk `structural` ha peso null:
non autorizza a distribuire i valori dei predecessori. Snapshot e codice da soli
non sostituiscono lo schema territoriale versionato. [Copertura e derivazioni](../sources/territorial-aggregates.md).

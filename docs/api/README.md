# API pubbliche v1 e v2

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

Nessuna scrittura, SQL arbitrario, ricerca individuale o download massivo via API sincrona.
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
convertito in `observed`. Le osservazioni v2 aggiungono livello territoriale,
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
la presenza dello schema v2.

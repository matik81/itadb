# API pubbliche v1

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


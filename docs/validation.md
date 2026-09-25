# Verifiche della versione corrente

Controlli locali eseguiti il 25 settembre 2026. La preparazione e il servizio usano
DuckDB; Compose contiene soltanto API e web. Il deployment cloud non è stato eseguito.

## Archivio nazionale

La pubblicazione diretta dei 107 batch Parquet ha ripetuto l'audit indipendente,
importato tutti i record e ricalcolato i vincoli prima dell'attivazione.

| Contenuto | Quantità verificata |
|---|---:|
| Individui sintetici | 58.943.464 |
| Famiglie sintetiche | 26.670.169 |
| Comuni / province / regioni | 7.896 / 107 / 20 |
| Celle demografiche | 3.943.689 |
| Confronti con i vincoli ammessi | 3.733.338, tutti con errore zero |
| Release di aggregati v2 / osservazioni | 4 / 22.723 |

Conteggi e impronte delle righe sono stati confrontati sull'intero archivio:
attributi individuali, famiglie, distribuzioni, metadati territoriali e aggregati
corrispondono. Report e provenienza coincidono come oggetti JSON. I dati non
corrispondono a persone reali.

I confini sono ricalcolati dalle fonti: tutti gli 8.023 poligoni visualizzati sono
validi. La differenza simmetrica rispetto alle fonti rimane sotto l'1% dell'area;
le semplificazioni eccessive vengono scartate. Le geometrie visualizzate possono
quindi differire dalla copia precedente, soprattutto nei comuni piccoli.
I punti territoriali differiscono al massimo di circa `1,51e-13` gradi.
Data di pubblicazione, rapporto dei controlli e ranghi testuali sono propri
del nuovo archivio; non si dichiara uguaglianza binaria dei due pacchetti.

Il file corrente misura 396.111.872 byte. SHA-256:
`59624e74ebfc797ad9794d738aa9d6560dcda2f53cf2f75b13ee385dcd8c832f`.
È installato in `data/published` e `data/serving`; la copia precedente è conservata.
Un retry nazionale ha restituito lo stesso snapshot e lo stesso checksum.
Sono stati eseguiti anche `EXPLAIN ANALYZE` su individui, famiglie e distribuzioni
nazionali: i piani applicano i filtri e i limiti delle query.

## Software e distribuzione locale

- **263 test Python passati**, inclusi 24 test di integrazione, nessuno saltato.
  Coprono pubblicazione, retry, concorrenza, revisioni, quarantena, integrità,
  cartografia, esportazione, ripristino, paginazione e indisponibilità dell'archivio.
  Rimangono due avvisi di deprecazione nelle dipendenze del client di test.
- **43 test frontend passati**; typecheck, formattazione e build riusciti.
- Ruff, mypy e verifica dei link di 32 documenti passati.
- OpenAPI e tipi TypeScript rigenerati senza cambiamenti del contratto.
- **404 risposte API verificate** sull'archivio aggiornato e ripetute via HTTP
  nell'immagine applicativa, con otto client, una CPU, limite 512 MiB, filesystem
  in sola lettura, utente 10001 e rete esterna disabilitata. Nessun OOM, ma il
  cgroup ha raggiunto il limite con recupero di memoria: 512 MiB non danno margine.
- Immagini API/web costruite; Compose riavviato sull'archivio corrente.
  Verificati readiness, CORS e installazione del pacchetto tramite CLI nel container.
- Build con configurazione Vercel riuscita con URL API HTTPS; l'assenza dell'URL
  blocca correttamente la build.

I log dettagliati restano locali in `.tools/`: `clean-final-tests.log`,
`clean-frontend.log`, `national-duckdb-final.log`, `national-comparison-final.log`,
`national-retry.log`, `production-final.log`, `vercel-build.log` e `compose-final.log`.
I risultati dell'audit nazionale e i piani sono in `.tools/national-duckdb-final/`.

## Prontezza al deployment

Codice, pacchetto dati e configurazione sono pronti per un primo deployment
Vercel/Railway seguendo la [procedura](deployment.md). Restano da eseguire sul
provider il caricamento sul volume, la configurazione di domini e CORS, il backup
esterno e una prova di ripristino. Prestazioni e consumo sotto carico vanno
verificati in quell'ambiente: le prove locali non sono promesse prestazionali.

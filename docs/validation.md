# Verifiche della versione corrente

Controlli locali e primo deployment cloud eseguiti il 25 settembre 2026.
La preparazione e il servizio usano DuckDB; Compose contiene soltanto API e web.

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

Il 25 settembre 2026 sono state installate e verificate Railway CLI **5.62.1** e
Vercel CLI **60.0.1**. Su entrambe sono riusciti il login, il controllo della
sessione e la lettura dei progetti accessibili. Identità, credenziali e inventario
degli account restano fuori dalla documentazione.

I progetti sono stati creati e configurati tramite CLI. Sono state eseguite:

- **Railway:** build dal repository GitHub, volume da 5 GB in Europa montato a
  `/app/serving`, una replica con limite di 1 GB e una CPU. Il database di
  396.111.872 byte e il manifest sono stati trasferiti, verificati e installati;
  la release attiva coincide con il checksum nazionale riportato sopra.
- **Processo API:** Uvicorn come PID 1 con UID/GID 10001, un worker, porta 8000,
  healthcheck `/health/ready` e dominio HTTPS. Rimosso l'override root usato durante
  l'installazione. La shell SSH usa root, ma il processo applicativo è non privilegiato.
- **Vercel:** build Production completata con Node.js 24, root `apps/web`, Vite e
  URL HTTPS dell'API. Il filtro `.vercelignore` è stato verificato con `--dry`:
  37 file frontend per 358.029 byte; esclusi dati, file ambiente e dipendenze locali.
  Un primo invio che includeva directory di dati è stato interrotto prima del
  completamento del deployment e sostituito dall'invio filtrato.
- **HTTP:** 17 richieste API con risposta 200 e CORS corretto, inclusi readiness,
  conteggi nazionali, evidenze, mappa regionale, paginazione senza duplicati,
  individuo, famiglia con componenti, distribuzioni, vincoli senza discordanze e
  cataloghi v1/v2. Verificata l'assenza di autorizzazione CORS per un'origine estranea.
  Homepage e due asset frontend rispondono 200; il bundle contiene l'URL API corretto.
- **GitHub/Railway:** trigger su `main` con `checkSuites: true`; sorgente GitHub e
  configurazione remota controllate. La build iniziale da GitHub è riuscita.

Il **26 settembre 2026**, dopo l'autorizzazione della GitHub App, è riuscito
`vercel git connect --yes`. La lettura della configurazione remota conferma
provider GitHub, `productionBranch: main` e
`gitProviderOptions.createDeployments: enabled`, senza comando di esclusione
della build. Confermato anche il trigger Railway su `main` con attesa della CI.
Il primo deployment Vercel è stato eseguito tramite upload CLI. Il collegamento
non ha richiesto nuovi commit o push; l'aggiornamento automatico successivo è
stato verificato il 27 settembre, come riportato sotto.

## Consolidamento del 26 settembre 2026

- Attivati quattro deployment check Vercel collegati ai job CI, con blocco
  dell'assegnazione del dominio di produzione e timeout di 30 minuti.
- Importate e applicate le impostazioni Railway tramite IaC; API e volume sono
  assegnati al partial `itadb`. `config plan --detailed-exit-code` non rileva
  differenze. Confermati via API riavvio `ON_FAILURE` con tre tentativi,
  `sleepApplication=false`, healthcheck e assenza del file legacy remoto.
  La CLI omette i due valori di default in lettura: nel file sono documentati
  invece di produrre una differenza permanente a ogni piano.
- Verificato il monitor su frontend, JavaScript, readiness, catalogo e CORS.
  Impostate le variabili GitHub per i due domini; il workflow ogni 15 minuti
  è stato poi attivato con la pubblicazione su `main` del 27 settembre. Dodici test del
  monitor passano, inclusi indisponibilità, contenuti errati e retry esauriti.
- Riprodotte **160 richieste con quattro client**, confrontando lo SHA-256 delle
  risposte con la prova locale sullo stesso archivio: 160 corrispondenze, nessun
  errore, durata 10,7 secondi. Latenze dal client: mediana 162 ms, p95 462 ms,
  massimo 5.309 ms. La finestra comprende un deployment avviato dalla modifica
  IaC: è una prova limitata, non un benchmark di capacità sostenuta.
- Le metriche Railway della finestra di 15 minuti riportano 170 risposte 2xx,
  nessun 4xx/5xx e memoria massima campionata di circa 469 MB. I campioni del
  provider non dimostrano il picco istantaneo. Le metriche cgroup del processo
  che esegue lo script locale non vengono attribuite al container cloud.

Il backup cloud è escluso per scelta progettuale: i dati sono generati localmente
con metodo versionato. Il recupero ricopia un pacchetto locale verificato o
esegue nuovamente preparazione e pubblicazione. Restano fuori da questa verifica
l'interazione completa nel browser e un test di carico prolungato.

Log aggiuntivi locali: `.tools/cloud-load.log`, `.tools/cloud-load-results.json`,
`.tools/cloud-metrics-after.json` e `.tools/railway-apply.json`.

## Verifica automatismi del 27 settembre 2026

La PR di configurazione è entrata in `main` con commit `7a8de49b0e89` dopo
il superamento dei quattro job CI e dell'audit delle dipendenze. Sono passati
251 test Python non di integrazione, 24 di integrazione e 43 frontend, oltre
a Ruff, mypy, contratti, build e smoke Compose. Nessun test saltato; i 24 test
esclusi dalla prova locale non di integrazione sono stati eseguiti dal job dedicato.

Entrambi i provider hanno avviato automaticamente il rilascio dello stesso commit.
Vercel ha mantenuto il dominio sulla versione precedente mentre un controllo era
ancora in corso, poi lo ha assegnato alla nuova build dopo i quattro esiti positivi.
Railway ha atteso la CI, completato il deployment e superato il healthcheck.
La lettura finale conferma `READY` con alias assegnato su Vercel e `SUCCESS`
su Railway, entrambi sul commit indicato. Nessuna modifica Railway è rimasta
in staging; il piano IaC non rileva differenze.

Il workflow di disponibilità è attivo su `main`; l'esecuzione manuale su
GitHub Actions ha verificato con successo API, catalogo, CORS, homepage e asset.
Ripetuta anche la verifica HTTP pubblica dopo il rilascio. La consegna di
notifiche email e l'esecuzione di ogni futura scadenza non sono oggetto della prova.
Gli identificativi cloud e i dettagli del confronto restano in
`.tools/cloud-release-final.json`, escluso da Git.

Evidenze locali, escluse da Git: `.tools/deploy-archive-verify.log`,
`.tools/deploy-data-upload.log`, `.tools/deploy-data-install.log`,
`.tools/deploy-api-build.log`, `.tools/deploy-api-start.log`,
`.tools/deploy-web-production.log`, `.tools/deploy-http-checks.log` e
`.tools/deploy-provider-checks.json`.

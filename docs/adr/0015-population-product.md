# ADR 0015 — popolazione interrogabile come prodotto

Data: 24 settembre 2026. Stato: adottata su richiesta esplicita dell'utente.

## Decisione

La popolazione sintetica è il contenuto principale del database applicativo,
delle API e dei frontend. La generazione resta un workflow separato, eseguito
da CLI e consultabile nel repository e nella documentazione. L'applicazione
non esegue sintesi durante le richieste HTTP.

Questa decisione supera per il percorso corrente il vincolo «nessuna tabella,
API o frontend» delle ADR 0012–0014. Non modifica il modello statistico, gli
snapshot preesistenti o il loro campo storico `public_release=false`. Una
pubblicazione applicativa distinta identifica lo snapshot verificato mediante
run ID e checksum del manifest. L'esposizione pubblica e la configurazione del
deployment saranno passi successivi espliciti, come richiesto dall'utente.

## Memorizzazione e interrogazione

PostgreSQL conserva tutti gli individui e le famiglie, con attributi tipizzati
e partizioni per snapshot. Parquet resta l'archivio della generazione. Il
caricamento usa COPY e controlli per insiemi, evitando query e trigger di
verifica per ciascun individuo. Le partizioni pubblicate diventano immutabili;
le viste API escludono gli snapshot incompleti. Le distribuzioni derivate
dai record importati accelerano mappe e istogrammi e vengono confrontate con
i vincoli di origine. Le misure nazionali effettive sono registrate a parte.

Le API v3 espongono popolazione, famiglie, territori, distribuzioni, provenienza
e verifiche. Le API storiche restano compatibili, ma il frontend principale
non richiede una release M2 per esplorare la popolazione. Nessun endpoint
accetta SQL libero o un percorso locale fornito dal client.

## Esperienza e geografia

La web app presenta una mappa scura a pieno schermo con pannelli di filtro,
istogrammi e navigazione dei record. «Metodo e verifiche» mostra la sequenza
effettiva, le fonti degli input dello snapshot, le assunzioni e il confronto
tra vincoli e popolazione generata. I territori usano la geografia del medesimo
riferimento, senza riutilizzare implicitamente confini M2 di anni diversi.

Le coordinate individuali non esistono nel riferimento corrente. I simboli
comunali sono dichiarati aggregati e non sono posizioni di persone. Una futura
integrazione di densità e residenza dovrà produrre un nuovo snapshot; la
mappa servirà i punti dell'area visibile, con aggregazione quando necessario.

## Destinazione del deployment

Frontend statico e API configurabile tramite URL; backend stateless con
connessioni PostgreSQL limitate e nessun accesso ai file della generazione.
Questi confini consentono servizi gestiti quali Vercel, Neon, Railway e
Cloudflare senza adottare ora un provider. Nessun deployment, account,
servizio di email o nuova dipendenza è necessario per questo cambiamento.

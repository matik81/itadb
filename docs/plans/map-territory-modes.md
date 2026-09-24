# Modalità territoriali della mappa

## Risultato e ambito

Aggiungere Regioni e Province alla modalità Comuni di Esplora. Il livello
determina confini, aggregati, ricerca, filtri territoriali e scheda selezionata.
Conservare i filtri individuali e consentire il passaggio ai territori figli.

## Decisioni

- Aggregare individui e famiglie dai conteggi comunali dello snapshot, anche
  quando mancano coordinate o confini. Nessuna nuova dipendenza o migrazione.
- Posizionare ciascun aggregato sul punto comunale più vicino al baricentro
  dei punti disponibili, pesato per individui. Non sono residenze individuali.
- Mostrare i confini del livello attivo e dei livelli superiori.
- Conservare zoom e posizione della mappa quando cambia il livello, senza
  ricreare il canvas né ricentrare la selezione ereditata. Aggiornare i cerchi
  prima del rendering a schermo, insieme ai confini.
- Conservare i genitori selezionati cambiando livello; azzerare i figli non
  pertinenti, la ricerca e l'elenco record. I record restano consultabili per comune.
- Aggiungere il filtro provinciale alle distribuzioni v3, con query parametrizzata
  sulle viste esistenti; rigenerare contratto e tipi client.
- I cerchi e le schede riportano totali territoriali; sesso, età e cittadinanza
  filtrano istogramma ed elenco, come nella modalità comunale precedente.

## Fasi e verifiche

1. Aggregazioni e interazione cartografica per i tre livelli.
2. Filtri, selezione gerarchica e istogramma provinciale.
3. Test di aggregazione, confini, cambi di livello e contratto API; typecheck,
   test e build frontend, controlli Python proporzionati, documentazione.

## Limiti

Confini assenti negli snapshot restano assenti. Gli aggregati senza coordinate
restano ricercabili nel pannello. Nessuna promessa di prestazioni senza benchmark.

## Stato

Completato il 24 settembre 2026. Verifiche eseguite:

- Frontend: typecheck, formato, 43 test e build superati.
- API: 7 test mirati superati; Ruff, formato Python e mypy superati.
- Contratto OpenAPI e tipi TypeScript rigenerati; controllo documentazione superato.
- Chromium desktop (1440×1000) e mobile (390×844), con fixture inventata:
  livelli, confini, selezione, totali dell'istogramma e tastiera verificati.
  Log in `.tools/frontend-map-checks.log` e `.tools/frontend-map-browser.log`.
- Cambio modalità senza salti: verificati in Chromium canvas persistente e
  inquadramento identico per cinque frame dopo ogni cambio, con e senza
  selezione, usando il database locale. Log in `.tools/map-camera-checks.log`.
- Sei test di integrazione PostgreSQL saltati: URL di test espliciti assenti.
  Aggiunte asserzioni sul filtro provinciale nel test di pubblicazione esistente;
  la verifica su database reale resta da eseguire in un ambiente configurato.

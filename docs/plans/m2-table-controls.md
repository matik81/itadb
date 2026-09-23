# M2 — tabelle esplorabili e icone

## Risultato richiesto

Entrambe le tabelle hanno comandi crescenti/decrescenti e filtri pertinenti.
Le osservazioni usano ricerca nome/codice, selezione del territorio padre e
stato; lo storico seleziona tipo di variazione e utilizzo. I controlli lavorano
sull'intera selezione, prima della paginazione, e azzerano il cursore.
Il tipo territoriale è un'icona accessibile accanto al nome. I numeri delle
schede hanno icone distinte per persone, famiglie e abitazioni.

## Fasi

1. Estendere le query v2 con parametri enumerati, filtri parametrizzati e keyset
   stabile anche per valori uguali o nulli. Conservare i default preesistenti.
2. Controlli tabella accessibili, icone SVG locali e layout responsivo, senza
   nuove dipendenze. Conservare provenienza, stati vuoti/errori e schede mappa.
3. Test backend e frontend, confronto ordinamento su più pagine con PostgreSQL,
   OpenAPI/tipi client rigenerati, Playwright su dati ufficiali e viewport mobili.
4. Documentazione, commit sul branch dedicato, rebase e aggiornamento PR.

Stato: implementazione e verifiche completate. Nessuna modifica a dati o migrazioni
applicate e nessuna nuova dipendenza. 104 test offline, 25 di integrazione e
17 web superati; 16 controlli Playwright su Chrome. Entrambi gli ordinamenti
numerici confrontati su tutti i 7.904 comuni del 2021 con una query indipendente;
quattro piani PostgreSQL conservati. Dettagli nel registro delle verifiche.

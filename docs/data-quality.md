# Qualità, riproducibilità e limiti

## Gate implementati sul dataset demo

Intestazione esatta; almeno una riga; codici nel namespace demo; nomi non vuoti; data ISO
valida e compatibile con il vintage demo; conteggi interi non negativi entro int64;
chiave territorio/periodo unica; un solo periodo. DuckDB normalizza in Parquet con tipi
espliciti. Dopo COPY il numero di osservazioni deve coincidere con quello validato.
I gate sono implementati dall'adapter demo, non da un motore generico che interpreti
qualsiasi JSON. Il contratto è versionato e incluso nell'identità della release.

Gli errori bloccano la pubblicazione; un QualityError produce report di quarantena e run
fallito. Errori tecnici conservano il codice del tipo di eccezione nel run. La transazione
fa rollback di tutti i dati di servizio della release. Un file Parquet eventualmente
prodotto prima del rollback è un artefatto orfano, mai una release pubblicata.

L'identità è deterministica su dataset + SHA-256 originale + versione trasformazione +
SHA-256 contratto. Retry identici non duplicano osservazioni; ogni tentativo ha run distinto.
Lock di file protegge i file sullo stesso host, advisory lock transazionale protegge la
pubblicazione tra host. La v0.1 presuppone che le definizioni di dimensione siano curate
da un solo flusso amministrativo; onboarding parallelo richiederà lock anche sulle dimensioni.

Un crash di processo può lasciare un run `running`: un reconciler operativo, non ancora
implementato, dovrà identificarlo tramite timeout e verificare transazione/artefatti.
Non promettiamo exactly-once su sistemi distribuiti: la pubblicazione DB è atomica e
idempotente, il filesystem non partecipa alla transazione PostgreSQL.

## Gate richiesti per dati reali

- Schema e DSD; domini e codelist; copertura territoriale e temporale attesa.
- Unità e scale, valute/prezzi correnti o costanti, definizioni delle categorie.
- Riconciliazione con totali ufficiali, disaggregazioni, tolleranze documentate.
- Variazioni anomale tra release e revisione delle differenze, senza correggere automaticamente.
- Distinzione tra osservato, stimato, mancante e soppresso; preservare i flag upstream.
- Geometrie valide, SRID, copertura e versione dei confini.

### Primo gate reale implementato: campione regionale ISTAT

`itadb check-istat-population` verifica offline il contratto
`contracts/istat-population-regions-v1.json`: provenienza e hash di dati/metadati,
DSD e codelist, codici e significati selezionati, intestazioni esatte, anno 2024,
chiave unica, 20 regioni più Italia, conteggi int64 non negativi e somma regionale
uguale al totale upstream. Flag e note non revisionati bloccano il controllo;
gli attributi accettati sono conservati nel rapporto. Zero resta un valore valido.

Originali e manifest sono archiviati prima della verifica. Il rapporto locale
`validated_sample` non è una release e non è esposto dalle API. Input identici
riusano il rapporto verificandone il contenuto, senza overwrite; input nuovi
producono un nuovo rapporto. Errori di qualità/provenienza finiscono in quarantena.
Il successivo comando `ingest-istat-population` applica anche il contratto
`istat-population-publication-v1.json`: corrispondenza dei contratti e della licenza,
limite Numeric(20,6), snapshot giornaliero, COPY da Parquet e verifica del conteggio
e del totale dopo caricamento. Pubblicazione, osservazioni, artefatti e quality sono
in una sola transazione. Il run fallito e la quarantena restano dopo il rollback.
Anche il DB rifiuta pubblicazione v2 con righe mancanti, gate falliti o artefatti incompleti.

L'identità della release ISTAT comprende raw, contratto di pubblicazione (che fissa
l'hash del contratto onboarding), trasformazione e XML canonici privati del solo Header SDMX.
Una nuova acquisizione identica non produce doppioni. Cambiamenti richiedono
`--supersedes` con il predecessore corrente e `--revision-reason`; il report registra
le differenze numeriche. Due revisioni concorrenti non possono creare rami.
È una revisione umana esplicita, non un rilevatore statistico di anomalie.
Storia territoriale e crosswalk sono implementati nel perimetro M2.
Vedere [evidenze e limiti](sources/istat-population.md).

M2 aggiunge copertura esatta per serie/periodo/vintage, gerarchie temporali,
partizioni disgiunte per sesso, età, dimensione familiare e occupazione delle
abitazioni. Intervalli di età sono semiaperti; 100+ usa il limite convenzionale
1000, senza inferire un'età reale massima. Sono vietati totali inclusi tra le
parti e somme di unità, periodi o vintage diversi. Il gate geometrico conserva
originali e riparazioni revisionate; la pubblicazione confronta integralmente
Parquet e DB, compresi stato e attributi upstream. Vedi [M2](sources/istat-m2.md).

## Gate richiesti per la sintesi

Margini territoriali, distribuzioni congiunte, composizione familiare, vincoli logici e
copertura. Validazione su statistiche non usate nella calibrazione; confronto tra seed e
quantificazione dell'incertezza. I margini non determinano univocamente le correlazioni:
ipotesi modellistiche, errori e bias vanno pubblicati insieme ai risultati.
La coerenza statistica non rende uno scenario una previsione certa o una stima causale.
Prima di rilasciare microdati sintetici servono valutazioni di rischio di re-identificazione
e di disclosure, anche in assenza di corrispondenza intenzionale con individui reali.

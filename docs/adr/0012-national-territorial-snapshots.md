# ADR 0012 — snapshot nazionali territoriali riprendibili

Data: 24 settembre 2026. Stato: adottata per lo sviluppo locale M4.

## Problema

Il generatore M3 conserva residenti e posti familiari in liste Python e non
assegna comuni. Aumentare il limite di 200.000 residenti non dimostra capacità
nazionale né coerenza territoriale. Occorrono anche checkpoint verificabili,
misure effettive e un confine esplicito per la distribuzione.

## Decisione

Riferimento unico `m4-reference/1`: popolazione al 1° gennaio 2025, famiglie
al 31 dicembre 2024, geografia al 1° gennaio 2025; seed 1701 e 6 componenti
per la classe 6+. Priorità: sesso/età, geografia, composizione familiare.
Le famiglie 2024 sono l'ultimo riferimento disponibile nell'inventario
2021–2025 interrogato. La popolazione 2026 è indicata da ISTAT come stima:
non sostituisce il riferimento comune verificato.

Si riusano archivio, lettore geografico, connettori limitati, DuckDB e Parquet.
Nessuna nuova dipendenza, tabella DB, API o servizio. POSAS ZIP fornisce le
congiunte comunali e provinciali; SDMX quelle regionali/nazionali e le
famiglie. Il campione POSAS/SDMX coincide su 612 celle. Gli endpoint regionali
SDMX nascosti e le richieste comunali troppo lunghe non sono usati dal contratto.

L'espansione delle celle avviene in DuckDB. I batch raggruppano comuni della
stessa provincia/UTS, fino a 5 milioni di residenti; un comune non viene
spezzato. Una località oltre questo limite viene rifiutata. Il riferimento
misurato produce 107 batch e 214 Parquet. Il limite DuckDB è 2 GiB, due thread;
un monitor rileva picco RSS del processo, disco campionato e tempo. Il run
non può completarsi se supera i budget registrati. I controlli tra fasi non
sono un limite RAM imposto dal sistema operativo.

Si deriva un seed comunale dai primi 64 bit di
`SHA256("itadb:m4:territorial-seed:1:1701:" + codice_comune)`.
L'ordine pseudocasuale usa `hash` di DuckDB e chiavi di spareggio esplicite;
la versione DuckDB, l'ambiente e il lockfile fanno parte dell'identità.
La stabilità tra versioni diverse del motore non è presunta.
Identificativi int64 densi derivano dall'ordine provincia/comune/cella;
l'ordine di esecuzione dei batch non cambia gli artefatti.

Per comune si riserva un adulto per famiglia, poi si assegnano tutti i
minori e infine gli altri adulti ai posti residui. Il residuo non assegnato
resta adulto. Non si inferiscono parentela, convivenze, indirizzi o identità
reali. La nascita usa `year-start-cohort/1` dell'ADR 0011; 100+ rimane aperto.

Un audit SQL separato dal generatore rilegge ogni batch: schema, ID, coorti,
domini, famiglie, riferimenti, geografia e 202 celle per comune. Intervalli
ID densi e disgiunti provano l'unicità globale senza un DISTINCT nazionale.
Le somme comunali vengono riconciliate in ammissione con tutte le congiunte
provinciali, regionali e nazionali e con le classi familiari provinciali,
regionali e nazionali. I codici UTS non vengono confusi con i codici provincia:
si usano gli attributi della geografia e i legami padre della codelist ISTAT.

Il checkpoint contiene checksum e audit; solo dopo la verifica il batch
viene rinominato nella directory di lavoro. La ripresa rilegge e verifica
anche i batch già completati. I tentativi parziali restano conservati nello
stato, separati dallo snapshot; un file corrotto non viene riparato in-place.
Un lock locale serializza i retry. Un rename sullo stesso filesystem completa
lo snapshot solo dopo gli audit e il controllo dei budget. Non è un protocollo
di commit distribuito o una garanzia contro la perdita fisica del disco.

## Distribuzione e conseguenze

Microdati esclusivamente locali, `public_release=false`. Il formato preparato
per gli aggregati è JSON versionato: regione, sesso, classi decennali con 90+
raggruppato, attribuzione, periodo e limiti. Nessuna relazione familiare o ID
individuale. Se esiste una cella sotto 10, l'intera tabella viene trattenuta:
non si usa soppressione selettiva ricostruibile tramite i totali.

La [valutazione disclosure](../reviews/m4-disclosure.md) è una valutazione
tecnica del prodotto locale e dell'output aggregato. Non certifica anonimato
dei microdati. Revisione scientifica esterna e autorizzazione alla distribuzione
dei microdati restano escluse dall'esito tecnico. La PR rende verificabili
formato e ambito; nessun artefatto viene pubblicato automaticamente.

Prestazioni e fedeltà devono essere lette nelle [misure M4](../synthesis-m4.md),
distinguendo prove inventate a 1M/10M e popolazione nazionale calibrata.

# Fonti e connettori

## Fonti selezionate

| Fonte | Interfaccia | Stato nello scaffold |
|---|---|---|
| ISTAT IstatData | SDMX REST, `https://esploradati.istat.it/SDMXWS/rest` | Campione regionale 2024 acquisito, verificato e pubblicabile in DB/API v2/web |
| Eurostat | SDMX 2.1, `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1` | Stessa interfaccia di acquisizione; mapping da implementare |
| Fixture Itadb | CSV versionato nel repository | Percorso completo verificabile con dati inventati |

La demo usa gli identificativi `urn:itadb:demo` per la fonte e
`urn:itadb:fixture:population-demo` per la fixture
`tests/fixtures/population-demo.csv`. Sono riferimenti interni al progetto,
non pagine web; la UI presenta la fonte demo come testo.

Fonti candidate successive: confini e variazioni territoriali ISTAT, dati aggregati INPS,
MEF, Banca d'Italia e amministrazioni. Non sono connettori implementati né banche dati già
collegate. Valutare disponibilità, licenza, granularità e coerenza prima di selezionarle.
Non assumere che una banca dati consenta una connessione SQL diretta; usare le interfacce
pubbliche supportate. Un adapter SQL futuro deve usare credenziali read-only, viste curate,
watermark e query parametrizzate, senza esporre DSN o SQL nell'API pubblica.

Primo contratto reale: [popolazione residente regionale ISTAT](sources/istat-population.md).
La pagina contiene selezione esatta, licenza, evidenze e comandi riproducibili.

## Contratto del connettore

`SourceConnector.fetch(flow, key, start, end)` restituisce percorso, checksum e manifest.
L'implementazione `SdmxConnector` preserva la risposta originale e provenienza, richiede un
range temporale, rifiuta redirect, formato inatteso, risposte vuote o oltre 100 MB.
Tre tentativi massimi per problemi transitori; `Retry-After` lungo interrompe il task.
Non pubblica dati e non converte alla cieca SDMX in osservazioni.

`fetch_structure(resource, agency, identifier, version, references)` archivia un singolo
dataflow o una DSD esplicitamente versionata, con riferimenti `none` oppure `all`.
La CLI `fetch-structure` impone un massimo di 20 MB e riusa rate limit e provenienza.
Il contenuto XML è validato semanticamente dal gate specifico, non dall'acquisizione.

Esempio di sintassi, con valori da ricavare dalla DSD del dataset scelto:

```sh
uv run itadb sources
uv run itadb fetch istat --flow AGENCY,FLOW,VERSION --key DIM1.DIM2 \
  --start-period 2025 --end-period 2025
```

Questo esempio contiene segnaposto, non una query ISTAT certificata. I test del connettore
sono offline. È stato acquisito un campione di 21 totali regionali/nazionali per un anno,
documentato sopra; nessun download esteso a comuni, età o serie storiche.

ISTAT dichiara 5 query/minuto per IP e blocchi in caso di superamento. Lo scaffold usa
15 secondi tra richieste e un file lock condiviso dai processi sullo stesso archivio.
Dietro un IP comune, worker su host diversi devono usare un limiter centralizzato o un
singolo worker di acquisizione. Il lock locale non garantisce una quota globale di rete.

## Onboarding obbligatorio prima della pubblicazione reale

1. Identificare ente, dataset/dataflow, versione DSD, ordine delle dimensioni e codelist.
2. Conservare riferimenti della licenza applicabile alla specifica release, attribuzione,
   limiti di redistribuzione e timestamp della verifica. I link generali in catalogo non
   equivalgono ad approvazione legale di ogni dataset.
3. Definire unità, frequenza, tempo di riferimento, data di rilascio upstream (distinta
   dall'acquisizione), territorio/versione, categorie e marcatori missing/suppressed.
4. Scrivere contratto machine-readable e adapter specifico; non sommare categorie
   sovrapposte, totali e dettagli o vintage territoriali incompatibili.
5. Creare fixture ridotta, consentita o inventata, con casi reali di schema e stato.
6. Acquisire un campione selettivo; validare schema, domini, copertura e riconciliazione
   con i totali ufficiali. Documentare le discrepanze e le tolleranze.
7. Pubblicare in transazione soltanto dopo i gate; conservare originali, metadati e report.
   Correzioni e revisioni producono nuove release. Collegare la precedente esplicitamente.

## Riferimenti ufficiali verificati il 23 settembre 2026

- [ISTAT: SDMX e limiti](https://www.istat.it/classificazioni-e-strumenti/web-services-sdmx/)
- [ISTAT: endpoint](https://esploradati.istat.it/SDMXWS/)
- [Eurostat: query SDMX 2.1](https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/sdmx2-1/data-query)

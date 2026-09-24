# Fonti e connettori

## Fonti integrate

| Perimetro | Input ammesso | Uso |
|---|---|---|
| Popolazione corrente | ISTAT 2025 per comune/sesso/età, geografia 2025 e famiglie a fine 2024 | Generazione nazionale, [workflow](population.md) |
| Cittadinanza corrente | ISTAT STR/RCS 2025 | Vincoli individuali prima delle famiglie |
| Aggregati territoriali | Inventario ISTAT multi-periodo revisionato | [Copertura e API v2](sources/territorial-aggregates.md) |
| Popolazione regionale 2024 | Campione ISTAT di 21 osservazioni | [Ammissione e pubblicazione](sources/istat-population.md) |
| Fixture inventate | CSV/JSON ridotti e vincoli di carico | Test offline, mai sostituti dei dati osservati |

I [contratti versionati](../contracts/README.md) fissano inventari, checksum,
periodi, geografia e licenze. Gli originali sono conservati prima della
trasformazione; il [catalogo dei dati](../data/README.md) ne descrive i percorsi.
`fetch-national-inputs` acquisisce il solo inventario nazionale revisionato;
`fetch-citizenship` acquisisce STR/RCS. Riusano gli originali verificati.

Il connettore SDMX supporta ISTAT ed Eurostat; per Eurostat non esiste ancora
un adapter di pubblicazione revisionato. INPS, MEF e Banca d'Italia restano fonti
candidate, da ammettere con contratto e verifiche prima dell'integrazione.

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

Questo esempio contiene segnaposto, non una query ISTAT certificata. I test del
connettore sono offline. Le acquisizioni effettive sono quelle degli inventari
versionati: il campione regionale iniziale è distinto dagli input nazionali correnti.

La verifica documentata il 23 settembre 2026 riportava un limite ISTAT di
5 query/minuto per IP e blocchi in caso di superamento. Il connettore usa
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

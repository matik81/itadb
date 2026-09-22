# Fonti e connettori

## Fonti selezionate

| Fonte | Interfaccia | Stato nello scaffold |
|---|---|---|
| ISTAT IstatData | SDMX REST, `https://esploradati.istat.it/SDMXWS/rest` | Acquisizione SDMX-CSV limitata; mapping dataset da implementare |
| Eurostat | SDMX 2.1, `https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1` | Stessa interfaccia di acquisizione; mapping da implementare |
| Fixture Itadb | CSV versionato nel repository | Percorso completo verificabile con dati inventati |

Fonti candidate successive: confini e variazioni territoriali ISTAT, dati aggregati INPS,
MEF, Banca d'Italia e amministrazioni. Non sono connettori implementati né banche dati già
collegate. Valutare disponibilità, licenza, granularità e coerenza prima di selezionarle.
Non assumere che una banca dati consenta una connessione SQL diretta; usare le interfacce
pubbliche supportate. Un adapter SQL futuro deve usare credenziali read-only, viste curate,
watermark e query parametrizzate, senza esporre DSN o SQL nell'API pubblica.

## Contratto del connettore

`SourceConnector.fetch(flow, key, start, end)` restituisce percorso, checksum e manifest.
L'implementazione `SdmxConnector` preserva la risposta originale e provenienza, richiede un
range temporale, rifiuta redirect, formato inatteso, risposte vuote o oltre 100 MB.
Tre tentativi massimi per problemi transitori; `Retry-After` lungo interrompe il task.
Non pubblica dati e non converte alla cieca SDMX in osservazioni.

Esempio di sintassi, con valori da ricavare dalla DSD del dataset scelto:

```sh
uv run itadb sources
uv run itadb fetch istat --flow AGENCY,FLOW,VERSION --key DIM1.DIM2 \
  --start-period 2025 --end-period 2025
```

Questo esempio contiene segnaposto, non una query ISTAT certificata. I test del connettore
sono offline. Non è stato eseguito uno scaricamento nazionale.

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


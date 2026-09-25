# Operazioni

## Preparazione

Seguire il [workflow della popolazione](population.md). Gli input originali e
i contratti restano archiviati per checksum. La generazione conserva checkpoint
e report; un retry verifica i file prima di riusarli. Corruzioni e input incompatibili
bloccano il run e non autorizzano a sovrascrivere le evidenze.

Prima dei comandi lunghi usare `scripts/run_logged.py`: mostra fase, avanzamento,
tempo trascorso ed esito, conservando il log. Non stampare credenziali o record
individuali. Non avviare più pubblicazioni sullo stesso archivio da host diversi.

## Pubblicazione

`publish-population` e i comandi degli aggregati costruiscono un nuovo archivio
in `data/published/attempts`. Un lock locale serializza i tentativi. Le versioni
verificate entrano in `releases/SHA256`; `current` indica l'ultima pubblicata.
Una pubblicazione già completata viene riconosciuta dal suo identificativo.

In caso di errore, leggere il log e `data/quarantine/publication-*.json`.
`published=false` significa che il puntatore non è stato aggiornato. Se la
scrittura del rapporto fallisce dopo l'attivazione, il tentativo riporta
`published=true`: verificare `current` prima di ripetere. Il retry non duplica i dati.
I tentativi parziali non sono pacchetti da distribuire.

La pubblicazione parte dall'archivio di preparazione corrente. Se manca, usa
quello installato nel servizio per conservare tutte le release esistenti.
Prima di preparare su un nuovo computer, installare quindi il pacchetto completo.
Un archivio esistente ma corrotto provoca errore; non viene ignorato.

## Distribuzione e recupero

`export-serving` copia l'archivio pubblicato dopo la verifica. Installazione,
attivazione, riavvio e ripristino sono descritti in [deployment.md](deployment.md).
Conservare un backup esterno di database e manifest, oltre agli input originali.
Una nuova pubblicazione richiede spazio per archivio precedente, candidato e copia
installata. Il servizio online non genera dati e non modifica l'archivio.

# Integrazione della cittadinanza — piano di lavoro

Stato: implementazione e verifiche locali completate, 24 settembre 2026.

## Risultato e ambito

Assegnare una cittadinanza sintetica a ogni individuo del riferimento M4
2025, conservando identità, sesso, coorte, territorio e famiglia. Nuova
versione immutabile; nessuna riscrittura delle evidenze M4 esistenti.

STR vincola stranieri per comune/sesso/età; RCS vincola le singole
cittadinanze per comune/sesso. L'incrocio età–singola cittadinanza non è
osservato: occorre una regola unica, deterministica e documentata. Nessuna
inferenza di cittadinanza dai legami familiari o dal paese di nascita.

## Fasi e controlli

1. Acquisiti selettivamente sei originali e il campione STR Valle d'Aosta;
   fissati schema, 196 categorie, periodo, licenza e checksum nel contratto.
2. Riconciliati STR/RCS con 7.896 comuni M4 e tutti i livelli superiori;
   nessun aggiustamento dei conteggi ufficiali. Zeri RCS derivati soltanto
   dopo riconciliazione esaustiva delle partizioni non negative.
3. Implementati nuovi CLI, arricchimento immutabile, riferimento unico,
   checkpoint e audit SQL separato. Tutti gli attributi M4 conservati.
4. Passati 266 test Python, prove a 1M, 10M con interruzione/ripresa e
   58.943.464 individui. Ordine invertito a 10M: nove file identici.
   Audit nazionale successivo e retry passati; budget rispettati.
5. Aggiornati contratto, metodo, priorità v4, diagnostica disclosure e
   riepilogo dedicato delle quattro integrazioni completate.

## Decisioni e limiti

La cittadinanza segue i tre gruppi di attributi già integrati, come richiesto
dall'utente; non può allentarne i vincoli. Microdati locali e nessuna
pubblicazione automatica. `100` Italia, `999` apolidia, non valore mancante.
Il run assegna 53.572.213 individui alla categoria italiana e 5.371.251 alla
popolazione straniera, inclusi 525 apolidi. La congiunta età–singola
cittadinanza e le relazioni di cittadinanza nella famiglia restano sintetiche
e non validate esternamente. [ADR](../adr/0013-citizenship-enrichment.md),
[metodo](../citizenship.md), [misure](../benchmarks/citizenship-2026-09-24.json).

Log locale dedicato: `.tools/citizenship-progress.log`, con fasi, conteggi,
tempo trascorso ed esito. Fonti e artefatti restano esclusi da Git.

Consegna: commit sul branch dedicato M4, rebase su main e aggiornamento
della PR con l'integrazione aggiuntiva; verifica della CI della PR.

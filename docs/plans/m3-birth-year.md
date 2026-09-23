# M3 — anno di nascita stabile

Stato: completato e verificato, autorizzato dall'utente il 23 settembre 2026.

## Risultato e ambito

Sostituire l'età materializzata delle persone virtuali con una coorte di
nascita stabile; ricavare l'età ai successivi inizi d'anno. Conservare le
202 celle sesso/età iniziali, i legami familiari e gli esperimenti storici.
Il cambiamento riguarda generatore, audit, metadati, test e documentazione;
non introduce dinamiche di mortalità, nascite, famiglie o API.

## Decisioni

- Al 1° gennaio Y, prima dei compleanni dell'anno, età = Y − nascita − 1.
  Per le classi 0–99: `birth_year = Y − età − 1`, anno sintetico.
- Per 100+: `birth_year = null`, `birth_year_upper_bound = Y − 101`.
  L'anno esatto resta ignoto; negli anni successivi avanza il limite inferiore
  dell'età, senza assumere una distribuzione della coda.
- Un solo campo di nascita valorizzato per record. Nessun mese/giorno inventato.
  Input aggregati v2 invariati; schema persone, algoritmo, audit e rapporto v3.
- Nuovi output immutabili, con regola e razionale nei metadati; nessuna
  riscrittura o reinterpretazione degli esperimenti v1/v2.

## Passi e verifiche

1. Implementare rappresentazione, calcolo annuale, audit SQL indipendente e
   versionamento; registrare la scelta nell'ADR 0011.
2. Verificare neonati, soglia 18/65, 99 e 100+, avanzamento annuale, domini,
   corruzione, calibrazione, determinismo, retry e fallimenti senza completamento.
3. Eseguire Ruff, mypy e suite Python non integration con log seguito dal terminale.
4. Generare offline una nuova versione dalle evidenze locali, confrontarla
   con il riferimento v2 e verificare checksum storici e idempotenza.
5. Aggiornare documentazione e registro con gli esiti realmente ottenuti.

Passi completati: 189 test Python non integration, Ruff e mypy passati;
15 repliche ufficiali v3, 3.030 celle ISTAT esatte, appartenenze v2 identiche,
retry invariato e 136 file storici conservati. Il riferimento aggiornato
è [m3-reference/2](../reviews/m3-birth-year-reference.md); dettagli, log e
controlli esclusi nel [registro](../validation.md).

## Limiti

Una coorte annuale è una convenzione temporale, non una data di nascita osservata.
La classe aperta non permette età puntuali. Un calendario infra-annuale o dati
sulla coda richiederanno un'altra regola versionata, senza cambiare i vincoli
iniziali o scegliere un diverso seed sulla base dei risultati.

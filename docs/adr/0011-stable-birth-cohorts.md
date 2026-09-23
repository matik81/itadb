# ADR 0011 — coorti di nascita stabili e tempo annuale

Stato: adottato su richiesta dell'utente il 23 settembre 2026.
Integra gli ADR 0009/0010 e sostituisce la rappresentazione individuale
dell'età nei nuovi esperimenti, conservando le versioni precedenti.

## Contesto

L'età materializzata in M3 v2 descrive solo il riferimento iniziale. Per
avanzare nel tempo l'utente richiede un anno di nascita che resti stabile.
Le fonti ammesse contengono conteggi per età, non compleanni individuali;
la classe 100+ non identifica un anno di nascita puntuale.

## Scelta

La regola unica `year-start-cohort/1` usa il confine annuale al 1° gennaio,
prima dei compleanni dell'anno entrante. Per l'anno Y:

`age = Y - birth_year - 1`

Nel pilota, 0 anni al 01/01/2022 diventano `birth_year=2021`, 30 anni
diventano 1991, 99 anni diventano 1922. Sono coorti sintetiche assegnate
secondo una convenzione, non anni individuali osservati. Non si postulano
mese e giorno, né si pretende di risolvere il caso del compleanno al 1° gennaio.

Per la classe 100+, `birth_year=null` e `birth_year_upper_bound=1921`:
«nato entro il 1921». Esattamente uno dei due campi è valorizzato.
Il limite inferiore dell'età avanza a 101+ nel 2023, 102+ nel 2024, ecc.
Un individuo inizialmente di 99 anni diventa invece esattamente di 100
secondo la convenzione annuale: non viene confuso con la classe aperta.

L'helper `age_at_year_start` restituisce `AnnualAge(years, is_lower_bound)`
e rifiuta campi ambigui, anni non interi e riferimenti anteriori alla coorte.
Il generatore non conserva più `age` nel Parquet. I conteggi di calibrazione
restano quelli dell'input v2, e l'audit SQL indipendente ricostruisce l'età
alla data iniziale per controllare tutte le 202 celle e i vincoli familiari.

Schema persone `m3-persons/3`, algoritmo/audit `3.0.0`, rapporto `m3-report/3`.
Manifest e rapporto registrano regola, formula, riferimento, classe aperta,
natura sintetica e razionale. Il verificatore rifiuta metadati incompatibili
anche se il rapporto è stato nuovamente hashato. Input e contratti delle
fonti/seed restano invariati; nessuna nuova dipendenza, migrazione o API.

## Alternative e conseguenze

- Conservare anche un'età modificabile creerebbe due valori potenzialmente
  discordanti. L'età è quindi solo derivata; i dati originali di calibrazione
  conservano le classi osservate.
- Usare `Y - birth_year` senza convenzione sposterebbe le coorti di un anno
  rispetto al confine precedente i compleanni. La regola adottata è esplicita
  e coperta da esempi e test, inclusa l'età zero.
- Scegliere un compleanno convenzionale o casuale aggiungerebbe dettaglio
  privo di evidenza e un calendario non richiesto dalla simulazione annuale.
- Assegnare a tutti i 100+ una nascita nel 1921 trasformerebbe un limite in
  un dato puntuale; campionare anni più antichi richiederebbe una distribuzione
  della coda non disponibile. Conserviamo quindi l'informazione censurata.

La conversione non consuma numeri casuali: a parità di input, seed e ipotesi
familiare, identità, sesso e appartenenza restano gli stessi. Nuovi esperimenti
hanno identità distinta e conservano gli output v1/v2, verificabili con il
codice registrato. Si mantiene il riferimento 6+ = 6 e seed 1701, senza
scegliere nuove repliche sulla base dei risultati.

Il calcolo temporale non implementa mortalità, nuove nascite, migrazioni o
dinamiche familiari, e non attesta conteggi osservati negli anni successivi.
Evidenze sui compleanni o sulla coda 100+, oppure un'esigenza infra-annuale,
richiederanno una nuova policy con confronto al riferimento precedente.

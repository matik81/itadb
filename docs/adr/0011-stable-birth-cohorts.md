# ADR 0011 — coorti di nascita stabili e tempo annuale

Stato: adottata. Data: 23 settembre 2026.

## Contesto

Le fonti contengono conteggi per età, senza compleanni individuali. Una coorte
di nascita stabile consente di derivare l'età a un riferimento annuale esplicito.
La classe 100+ non identifica un anno di nascita puntuale.

## Decisione

La regola `year-start-cohort/1` usa il 1° gennaio prima dei compleanni:
`age = Y - birth_year - 1`. Al 1° gennaio 2025, 0 anni corrispondono alla
coorte 2024, 30 anni alla coorte 1994 e 99 anni alla coorte 1925.
Sono coorti sintetiche convenzionali, non anni individuali osservati.

Per 100+, `birth_year=null` e `birth_year_upper_bound=1924`: nato entro il
1924. Esattamente uno dei due campi è valorizzato. Il limite inferiore dell'età
avanza nel tempo; non diventa un'età esatta. Un individuo inizialmente di 99
anni diventa invece di 100 anni secondo la convenzione annuale.

`age_at_year_start` restituisce `AnnualAge(years, is_lower_bound)` e rifiuta
campi ambigui, anni non interi e riferimenti anteriori alla coorte. I Parquet
conservano la coorte; l'audit SQL ricostruisce l'età alla data di riferimento
e verifica tutte le celle ammesse e i vincoli familiari. Il database serve
l'età dello snapshot senza interpretarla come un attributo osservato individuale.

Manifest e rapporto registrano formula, riferimento, classe aperta e natura
sintetica. Il verificatore rifiuta metadati incompatibili. La conversione non
consuma numeri casuali e conserva gli altri attributi individuali.

## Alternative e conseguenze

Un'età modificabile insieme alla coorte introdurrebbe valori potenzialmente
discordanti. Assegnare compleanni convenzionali aggiungerebbe dettaglio privo
di evidenza. Trattare tutti i 100+ come centenari esatti perderebbe l'informazione
censurata; una distribuzione della coda richiederebbe dati aggiuntivi.

Il calcolo temporale non implementa mortalità, nascite, migrazioni o dinamiche
familiari e non attesta conteggi osservati negli anni successivi. Nuove evidenze
sui compleanni o esigenze infra-annuali richiedono una nuova regola e un confronto
con il [riferimento del modello](../model-fidelity.md).

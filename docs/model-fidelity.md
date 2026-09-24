# Priorità di fedeltà del modello

Versione 5, adottata il 24 settembre 2026. Riferimento corrente unico:
`population-reference/1`. Ordine: **sesso/età → geografia → cittadinanza → famiglie**.
[Decisione eseguibile](adr/0014-ordered-population.md).

| Priorità | Proprietà | Fedeltà verificata | Limite |
|---|---|---|---|
| 1 | Sesso ed età | Conteggi esatti per comune/sesso/età al 1° gennaio 2025 | 100+ è una classe aperta; la coorte di nascita è sintetica |
| 2 | Geografia amministrativa | Conteggi territoriali esatti e gerarchia comune–provincia/UTS–regione coerente | Appartenenza comunale, senza localizzazione individuale interna |
| 3 | Cittadinanza | STR: stranieri per comune/sesso/età; RCS: singole cittadinanze per comune/sesso; entrambi esatti | Incrocio età–singola cittadinanza sintetico |
| 4 | Famiglie | Numero e classi dimensionali comunali esatti | Composizione casuale vincolata, senza calibrazione delle relazioni per età e cittadinanza |

## Regole per nuove versioni

- Conservare tutti i vincoli adottati. Un miglioramento familiare non può
  modificare sesso, età, territorio, cittadinanza o classi dimensionali.
- Confrontare lo stesso universo, periodo e definizione territoriale. Fonti
  incompatibili bloccano la versione; conservare l'evidenza senza aggiustare i conteggi.
- Dichiarare per ogni proprietà fonte/data/geografia, vincolo, errore, assunzione
  e limite. Mancante, stimato, osservato e sintetico restano distinti.
- Fissare un solo riferimento per versione: input, algoritmo, regole, parametri
  e seed. Le prove alternative sono sensibilità; non scegliere retroattivamente
  la replica che sembra più realistica senza un criterio dichiarato.
- Registrare con l'utente le modifiche alla graduatoria. Nuove fonti, ipotesi o
  metodi richiedono razionale, versione e confronto con il riferimento precedente.

L'esattezza riguarda le celle osservate e ammesse. Non implica validazione
esterna delle combinazioni individuali o delle relazioni familiari. La mancanza
di statistiche osservate fuori calibrazione va dichiarata.

## Assunzioni del riferimento

Seed 1701; classe familiare 6+ rappresentata da 6 componenti, minimo osservato
senza stimare una coda ignota. Ogni famiglia ha almeno un adulto, tutti i minori
sono assegnati e i componenti appartengono allo stesso comune. Il residuo nazionale
è di 560.159 adulti senza famiglia assegnata. Questi criteri non attestano
fedeltà delle relazioni tra i componenti.

La cittadinanza specifica è scambiabile entro comune e sesso tra gli stranieri
selezionati per età. Tale assunzione conserva STR/RCS senza inventare una
correlazione osservata tra età e singola cittadinanza. La pipeline salva gli
individui prima delle famiglie e verifica l'invarianza di tutti gli attributi
precedenti dopo il raggruppamento.

L'età al 1° gennaio precede i compleanni: `Y - birth_year - 1`. Per 100+ l'anno
esatto è nullo e `birth_year_upper_bound` conserva l'ultimo anno possibile.
La coorte resta stabile; non vengono implementate dinamiche demografiche né
una distribuzione non osservata della coda. [ADR 0011](adr/0011-stable-birth-cohorts.md).

Ogni assunzione nuova deve indicare la conseguenza misurabile e quale evidenza
permetterebbe di superarla. Lavoro, istruzione e abitazione non hanno ancora una
posizione concordata. [Fonti e workflow](population.md).

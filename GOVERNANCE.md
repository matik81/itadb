# Governance iniziale

I maintainer gestiscono revisioni e rilasci. Le decisioni tecniche durevoli si registrano come ADR.
Le proposte pubbliche vengono discusse in issue/PR; una modifica delle finalità del
progetto richiede discussione esplicita, non una modifica silenziosa del codice.

Per la fase iniziale non sono dichiarati un comitato scientifico, partnership, SLA o
certificazioni inesistenti. La validazione scientifica resta distinta dalla verifica software e dalla
calibrazione. Su richiesta dell'utente, l'ADR 0015 porta la popolazione
sintetica verificata nel database, nelle API e nel frontend, con ipotesi e
limiti espliciti. Questo sviluppo non dichiara una certificazione scientifica.
La scelta dei servizi gestiti e il deployment pubblico saranno passi successivi.

La revisione umana di progetto può accettare un modello di lavoro con limiti
espliciti e consentire lo sviluppo successivo. È distinta dalla revisione
scientifica esterna e dalle condizioni di distribuzione dei microdati.
L'[esito M3](docs/reviews/m3-human-review.md) chiude questa revisione iniziale
con accettazione dell'allocazione familiare casuale vincolata e avvio M4.

La [graduatoria di fedeltà](docs/model-fidelity.md) è evolutiva: età/sesso,
distribuzione geografica, composizione familiare sono le priorità iniziali.
Le revisioni della graduatoria si concordano con l'utente e si motivano in un
ADR. Ogni versione adottata ha un riferimento unico e assunzioni esplicite;
analisi di sensibilità e modelli futuri non sostituiscono implicitamente quel
riferimento. Fonti e artefatti delle versioni precedenti restano conservati.

Prima della collaborazione regolare: proteggere main, richiedere la CI e revisione,
abilitare segnalazioni private di vulnerabilità e nominare ulteriori maintainer.

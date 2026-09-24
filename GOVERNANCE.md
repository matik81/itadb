# Governance

I maintainer gestiscono revisioni e rilasci. Le decisioni tecniche durevoli
si registrano come ADR. Le proposte pubbliche vengono discusse in issue/PR;
un cambiamento delle finalità del progetto richiede una decisione esplicita.

La popolazione sintetica verificata è servita dal database, dalle API e dal
frontend, con ipotesi e limiti visibili. La verifica del software e la calibrazione
non equivalgono a validazione scientifica esterna o certificazione del modello.
Non sono dichiarati comitati scientifici, partnership o SLA non istituiti.
Il deployment pubblico e la scelta dei servizi gestiti restano obiettivi futuri.

La [graduatoria di fedeltà](docs/model-fidelity.md) stabilisce l'ordine:
**sesso/età → geografia → cittadinanza → famiglie**. Le revisioni si concordano
con l'utente e si motivano in un ADR. Ogni versione adottata ha un riferimento
unico, con fonti, parametri, seed, assunzioni e limiti espliciti. Le analisi di
sensibilità non sostituiscono implicitamente quel riferimento.

Gli artefatti pubblicati sono immutabili. Le correzioni producono nuove versioni,
confrontate con le precedenti; nessun individuo sintetico viene associato a una
persona reale. La composizione familiare resta una proprietà del modello.

Prima della collaborazione regolare: proteggere main, richiedere CI e revisione,
abilitare segnalazioni private di vulnerabilità e nominare ulteriori maintainer.

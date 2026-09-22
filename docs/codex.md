# Uso di Codex nel repository

Codex legge `AGENTS.md` alla root e istruzioni più specifiche lungo il percorso di lavoro.
I file locali in api, pipeline, connectors, migrations e web definiscono i confini dei
componenti. `.codex/config.toml` contiene solo il budget delle istruzioni di progetto:
non impone modello, permessi, approvazioni, credenziali o server personali.

Aprire il repository in Codex e assegnare obiettivi verificabili. Esempi:

- «Esegui i controlli del README e correggi i difetti senza modificare il contratto API.»
- «Implementa l'onboarding del dataflow ISTAT selezionato seguendo docs/sources.md;
  prepara fixture, DSD, contratto, gate e una PR con evidenze.»
- «Misura EXPLAIN (ANALYZE, BUFFERS) su un campione rappresentativo e proponi un ADR
  sugli indici, senza cambiare la produzione.»

Per lavori lunghi seguire PLANS.md; per scelte durevoli aggiornare gli ADR. Non introdurre
file chiamati CODEX.md supponendo che vengano caricati automaticamente. Le personalizzazioni
dell'utente restano nella sua configurazione, non nel repository pubblico.

Documentazione ufficiale consultata il 23 settembre 2026:
[istruzioni AGENTS.md](https://developers.openai.com/codex/guides/agents-md),
[configurazione](https://developers.openai.com/codex/config-reference/).

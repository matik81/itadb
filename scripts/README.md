# Strumenti dalla root del repository

Usare Bash, `uv` e `npm` nel PATH. Gli script non richiedono di cambiare directory.

| Operazione | Comando |
|---|---|
| Controllo ambiente, senza modifiche | `bash scripts/doctor.sh` |
| Migrazioni e ruolo reader | `uv run python scripts/migrate.py` |
| Avanzamento e log persistente | `uv run python scripts/run_logged.py --label "Fase" -- COMANDO` |
| Parità nazionale API PostgreSQL/DuckDB | `uv run python scripts/verify_serving.py --help` |
| Replay HTTP senza PostgreSQL | `uv run python scripts/smoke_serving.py --help` |
| Coerenza dei link locali Markdown | `uv run python scripts/check_docs.py` |
| Carico della popolazione corrente | `uv run python -m scripts.benchmarks.population --help` |
| Query della popolazione pubblicata | `uv run python -m scripts.benchmarks.population_api --help` |
| Capacità colonnare, dati inventati | `uv run python -m scripts.benchmarks.columnar --help` |
| Aggregati inventati su DB di test vuoto | `uv run python -m scripts.benchmarks.aggregate_storage --help` |
| Sintesi nazionale senza cittadinanza | `uv run python -m scripts.benchmarks.national --help` |
| Cittadinanza su uno snapshot esistente | `uv run python -m scripts.benchmarks.citizenship --help` |

I benchmark di sintesi condividono le fixture in `benchmarks/fixtures.py`.
I carichi da 1M/10M sono attività esplicite, da eseguire con `run_logged.py`,
root dedicata e budget disponibili. Non sono necessari per provare un import.
Il benchmark degli aggregati richiede `ITADB_TEST_DATABASE_URL`, schema migrato
e catalogo vuoto. Il benchmark API è di sola lettura e rifiuta rapporti già esistenti.
Il log predefinito è `.tools/task-progress.log`; usare `--log` per un nome dedicato.

## Workflow CLI

`uv run itadb --help` elenca i comandi e `uv run itadb COMANDO --help` ne descrive
i parametri. Il workflow del prodotto è:

1. `fetch-national-inputs` e `fetch-citizenship`: acquisizione degli inventari ammessi.
2. `synthesize-population`: generazione dei quattro passaggi del modello.
3. `verify-population`: audit indipendente dello snapshot.
4. `publish-population`: pubblicazione nel PostgreSQL locale di preparazione.

Per gli aggregati statistici usare `fetch-territorial-aggregates`,
`check-territorial-aggregates` e `ingest-territorial-aggregates`.
Gli esperimenti regionali usano `fetch-pilot-inputs`, `synthesize-pilot` e
`verify-pilot`; la sintesi nazionale senza cittadinanza usa `synthesize-national`
e `verify-national`. Questi strumenti non sostituiscono il riferimento del prodotto.

I contratti sono nell'[indice per funzione](../contracts/README.md); la procedura
completa è nella [guida della popolazione](../docs/population.md).

Per distribuire il risultato usare `itadb export-serving`, `verify-serving`,
`install-serving --activate` e `activate-serving` per il ripristino. Questi comandi
esportano l'intera applicazione v1/v2/v3. [Procedura](../docs/deployment.md).

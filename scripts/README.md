# Strumenti

| Comando | Uso |
|---|---|
| `bash scripts/doctor.sh` | Verifica degli strumenti locali |
| `uv run python scripts/check_docs.py` | Link e ancore Markdown |
| `uv run python scripts/run_logged.py --label NOME --log .tools/task.log -- COMANDO` | Esecuzione con log e avanzamento |
| `uv run python scripts/smoke_serving.py --help` | Confronto HTTP con risposte verificate |

La CLI principale è `uv run itadb --help`. Per il prodotto corrente:
acquisizione → `synthesize-population` → `verify-population` → `publish-population`
→ `export-serving` → `install-serving --activate` → riavvio API.

[Preparazione](../docs/population.md), [deployment](../docs/deployment.md),
[verifiche](../docs/validation.md). I log e i file di dati restano fuori Git.

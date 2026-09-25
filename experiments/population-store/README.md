# Esperimento: archivio della popolazione

Prototipo di sola consultazione, separato dall'API. Decisione e ambito:
[ADR 0016](../../docs/adr/0016-storage-comparison-experiment.md).
Non è un database generalista né una migrazione del prodotto.

## Formato e vincoli

Il formato `itadb-consultation/1` conserva lo snapshot al 1° gennaio 2025.
Gli identificativi devono essere univoci, densi, partire da 1 e rientrare in
32 bit; i record di ogni comune devono essere contigui. Il builder verifica
queste condizioni e le relazioni familiari e rifiuta input incompatibili.
Nessuna persona viene generata durante le richieste.

| File | Rappresentazione |
|---|---|
| `persons.bin` | 12 byte per individuo: famiglia u32, comune u32, cittadinanza u16, classe di età u8, sesso e adulto di riferimento in due bit |
| `households.bin` | 12 byte per famiglia: offset componenti u32, comune u32, dimensione u8 e tre byte riservati |
| `members.bin` | Identificativi u32 dei componenti, ordinati per famiglia e identificativo |
| `age-index.bin` | Permutazione degli identificativi u32, comune/età decrescente/id crescente |
| `cells.bin` | 12 byte per cella aggregata: comune u32, conteggio u32, cittadinanza u16, età u8, sesso u8 |
| `manifest.json` | Versione, riferimento, conteggi, intervalli comunali, provenienza e SHA256 dei file |

Tutti i numeri sono little-endian; non si serializzano strutture Rust dipendenti
dall'ABI. L'ID è dato dalla posizione, con verifica esplicita durante la build.
Famiglia zero rappresenta il nullo. Classe 100 significa anno di nascita nullo
e limite superiore 1924; per le altre classi l'anno è `2024 - classe`.
La verifica sui Parquet richiede che questa trasformazione sia reversibile.

Gli intervalli e l'indice per età accelerano le pagine più frequenti. Gli altri
ordinamenti selezionano i primi K elementi e ordinano solo la pagina; possono
comunque scandire tutto il comune. Le distribuzioni leggono le stesse celle
aggregate usate dagli altri motori. Non c'è cache delle risposte.

## Uso sperimentale

Dalla root, con Python del progetto e toolchain Rust nel PATH:

```sh
cargo build --release --locked --manifest-path experiments/population-store/Cargo.toml
cargo test --locked --manifest-path experiments/population-store/Cargo.toml
cargo clippy --locked --manifest-path experiments/population-store/Cargo.toml --all-targets -- -D warnings
```

Usare una directory nuova per ogni esperimento. Nei comandi seguenti `RUN` e
`OUT` sono variabili Bash scelte dall'operatore, senza credenziali:

```sh
RUN=data/curated/population/24a56e3bdb58fb1af523ea1b6019e8de04292ecdf11105fc6885cacc4903b76c
OUT=.tools/storage-comparison/nuovo-esperimento
uv run python scripts/run_logged.py --label "Audit input" --log .tools/storage-input.log -- uv run itadb verify-population --run "$RUN"
uv run python scripts/run_logged.py --label "DuckDB e export" --log .tools/storage-build.log -- uv run python scripts/benchmarks/storage_prepare.py --source "$RUN" --output "$OUT" --phase duckdb
uv run python scripts/run_logged.py --label "PostgreSQL compatto" --log .tools/storage-build.log -- uv run python scripts/benchmarks/storage_prepare.py --source "$RUN" --output "$OUT" --phase postgres --database itadb_storage_nuovo_esperimento
uv run python scripts/run_logged.py --label "Rust" --log .tools/storage-build.log -- experiments/population-store/target/release/build-store "$OUT" "$OUT/rust"
uv run python scripts/benchmarks/storage_compare.py --root "$OUT" --make-workload
```

La baseline PostgreSQL richiede lo snapshot nazionale pubblicato come ID 1,
accessibile con la configurazione locale del progetto. Il database ottimizzato
ha un nome distinto; il preparatore rifiuta nomi o archivi già esistenti.
Non cancellare database o directory per aggirare il controllo: scegliere un
nuovo nome. I CSV sono intermedi locali, esclusi da Git e dal volume di serving.

Per replicare i limiti della misura su WSL2, creare come amministratore Linux il
cgroup `/sys/fs/cgroup/itadb-storage-benchmark`, impostando `cpu.max` a
`200000 100000`, `memory.max` a `4294967296`, `memory.swap.max` a `0`.
L'opzione `--cgroup` sposta solo il processo di benchmark nel gruppo usando
`wsl.exe -d Ubuntu -u root`; richiede WSL e quel gruppo già configurato.
Su altri Linux applicare limiti equivalenti con il gestore dei servizi/cgroup
e adattare il piccolo helper, oppure omettere l'opzione dichiarando l'assenza
del vincolo. Non confrontare risultati con limiti diversi senza esplicitarlo.

Il server PostgreSQL della prova è il container `itadb-db-1`, con 2 CPU e 4 GiB,
oltre al piccolo client Python. Annotare i limiti preesistenti, applicare quelli
del test con `docker update`, quindi ripristinarli. I benchmark devono essere
sequenziali, con gli altri carichi pesanti fermi.

```sh
uv run python scripts/run_logged.py --label "Baseline" --log .tools/storage-bench.log -- uv run python scripts/benchmarks/storage_compare.py --root "$OUT" --engine postgres --output "$OUT/benchmark-postgres.json" --cgroup
uv run python scripts/run_logged.py --label "PostgreSQL compatto" --log .tools/storage-bench.log -- uv run python scripts/benchmarks/storage_compare.py --root "$OUT" --engine postgres_compact --output "$OUT/benchmark-postgres_compact-final.json" --cgroup
uv run python scripts/run_logged.py --label "DuckDB" --log .tools/storage-bench.log -- uv run python scripts/benchmarks/storage_compare.py --root "$OUT" --engine duckdb --output "$OUT/benchmark-duckdb-final.json" --cgroup
uv run python scripts/run_logged.py --label "Rust" --log .tools/storage-bench.log -- uv run python scripts/benchmarks/storage_compare.py --root "$OUT" --engine rust --output "$OUT/benchmark-rust-final.json" --cgroup
uv run python scripts/run_logged.py --label "Parità estesa" --log .tools/storage-audit.log -- uv run python scripts/benchmarks/storage_verify.py --root "$OUT"
uv run python scripts/run_logged.py --label "Parità integrale SQL" --log .tools/storage-audit.log -- uv run python scripts/benchmarks/storage_audit.py --root "$OUT"
uv run python scripts/benchmarks/storage_report.py --root "$OUT" --output "$OUT/report-aggregato.json"
```

I timer includono query, conversione in oggetti Python e serializzazione JSON
canonica, senza HTTP/FastAPI/rete cloud. La concorrenza usa client a ciclo chiuso
per almeno 10 secondi e completa l'ultimo blocco del mix; il p95 è campionario.
L'avvio Rust verifica tutti i checksum: riscalda la cache prima delle query.
`POSIX_FADV_DONTNEED` è consultivo; non costituisce un test di storage a freddo.
La memoria viene riportata come RSS/PSS, cgroup e cache, senza equipararla
automaticamente alla metrica fatturata dal provider.

Il generatore del report include, quando presenti, `environment.json`,
`audit-rebuild.json` e `rust-rebuild-resources.txt`. Nel run documentato sono
stati raccolti durante la seconda build nazionale; se non forniti, il nuovo
report dichiara la ricostruzione non verificata. Per ripeterla, costruire in una
seconda directory nuova e confrontare la mappa `files` dei due manifest: i
checksum dei dati devono coincidere; il tempo nel manifest può differire.

## Integrità e confine del prototipo

Il manifest è pubblicato per ultimo tramite rename nella stessa directory,
dopo sincronizzazione dei file. Un fallimento lascia una directory incompleta
non apribile dal reader; una seconda build sullo stesso percorso viene rifiutata.
L'audit integrale ricostruisce il flusso CSV canonico da ogni record e confronta
SHA256, senza stampare i record. I test comprendono nulli, 100+, cursori filtrati,
tie-break, checksum errato, input incompleto e rifiuto dell'overwrite.

Il reader usa mmap di sola lettura; i file devono restare immutabili per tutta
la vita del mapping. La piccola interfaccia C viene chiamata da `ctypes.CDLL`
nello stesso processo Python, che rilascia il GIL durante la chiamata nativa.
È un'alternativa minima a PyO3 per misurare il confine Python/Rust senza un
secondo servizio. L'ABI richiede handle validi, chiusura unica e assenza di query
durante la chiusura. Compilare nel sistema operativo/base image di destinazione;
il binario locale non è un artefatto portabile di deployment.

Restano fuori dal prototipo: integrazione FastAPI, OpenAPI, v1/v2, provenienza e
validazioni HTTP, mappe/PostGIS, distribuzioni per provincia/regione, gestione
operativa di più snapshot, switch atomico fra release e backup remoto. Tali
funzioni restano nel PostgreSQL applicativo. Non pubblicare il prototipo come
sostituto completo prima di completare quel lavoro e i relativi test.

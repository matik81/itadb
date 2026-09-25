import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
import uvicorn

from itadb.api.app import create_app
from itadb.config import Settings
from itadb.connectors.inventory import acquire_inventory, acquire_territorial_aggregates
from itadb.connectors.sdmx import SOURCES, SdmxConnector
from itadb.pipeline.istat_population import check_population_sample
from itadb.pipeline.publish_coverage import publish_coverage
from itadb.pipeline.publish_istat import ingest_istat_population
from itadb.pipeline.runner import ingest_demo
from itadb.pipeline.territorial_aggregates import build_territorial_aggregates
from itadb.synthesis.citizenship_inputs import prepare_citizenship_inputs
from itadb.synthesis.citizenship_models import CitizenshipReference
from itadb.synthesis.citizenship_runner import run_citizenship, verify_citizenship
from itadb.synthesis.inputs import prepare_inputs
from itadb.synthesis.models import Experiment
from itadb.synthesis.national_inputs import prepare_national_inputs
from itadb.synthesis.national_models import NationalInput, NationalReference, ResourceBudget
from itadb.synthesis.national_runner import run_national, verify_national
from itadb.synthesis.population_models import PopulationInput, PopulationReference
from itadb.synthesis.population_runner import run_population, verify_population
from itadb.synthesis.runner import run_pilot, verify_run

app = typer.Typer(
    no_args_is_help=True, help="Operazioni Itadb. Eseguire dalla root del repository."
)


@app.command()
def sources() -> None:
    """List configured machine-to-machine source interfaces."""
    for source in SOURCES.values():
        typer.echo(f"{source.id}: {source.base_url} ({source.interval_seconds}s between requests)")


@app.command()
def fetch(
    source: str,
    flow: Annotated[str, typer.Option()],
    key: Annotated[str, typer.Option()],
    start_period: Annotated[str, typer.Option()],
    end_period: Annotated[str, typer.Option()],
) -> None:
    """Archive a bounded SDMX-CSV response; does not publish unreviewed data."""
    if source not in SOURCES:
        raise typer.BadParameter("Choose istat or eurostat")
    artifact = SdmxConnector(SOURCES[source], Settings().data_dir).fetch(
        flow, key, start_period, end_period
    )
    typer.echo(json.dumps({"sha256": artifact.sha256, "manifest": str(artifact.manifest_path)}))


@app.command("fetch-structure")
def fetch_structure(
    source: str,
    resource: Annotated[str, typer.Option()],
    agency: Annotated[str, typer.Option()],
    identifier: Annotated[str, typer.Option()],
    version: Annotated[str, typer.Option()],
    references: Annotated[str, typer.Option()] = "none",
) -> None:
    """Archivia un dataflow o una DSD identificata, senza pubblicare dati."""
    if source not in SOURCES:
        raise typer.BadParameter("Choose istat or eurostat")
    artifact = SdmxConnector(SOURCES[source], Settings().data_dir, max_bytes=20_000_000)
    result = artifact.fetch_structure(resource, agency, identifier, version, references)
    typer.echo(json.dumps({"sha256": result.sha256, "manifest": str(result.manifest_path)}))


@app.command("check-istat-population")
def check_istat_population(
    acquisition: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    structure: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    dataflow: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-population-regions-v1.json"
    ),
) -> None:
    """Verifica offline il campione ISTAT e la provenienza; non pubblica nel DB."""
    report = check_population_sample(
        Settings().data_dir, acquisition, structure, dataflow, contract
    )
    typer.echo(
        json.dumps({"status": "validated_sample", "report": str(report), "published": False})
    )


@app.command("ingest-demo")
def demo() -> None:
    """Publish the explicitly fictional fixture through all quality gates."""
    typer.echo(
        str(
            ingest_demo(
                Settings(),
                Path("tests/fixtures/population-demo.csv"),
                Path("contracts/population-demo-v1.json"),
            )
        )
    )


@app.command("ingest-istat-population")
def publish_istat(
    acquisition: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    structure: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    dataflow: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    license_evidence: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    onboarding_contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-population-regions-v1.json"
    ),
    publication_contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-population-publication-v1.json"
    ),
    supersedes: Annotated[UUID | None, typer.Option()] = None,
    revision_reason: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Pubblica il campione verificato; nuove revisioni richiedono predecessore e motivo."""
    release = ingest_istat_population(
        Settings(),
        acquisition,
        structure,
        dataflow,
        onboarding_contract,
        publication_contract,
        license_evidence,
        supersedes,
        revision_reason,
    )
    typer.echo(json.dumps({"release_id": str(release)}))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the public API locally."""
    uvicorn.run("itadb.api.app:app", host=host, port=port, access_log=False)


@app.command("check-territorial-aggregates", rich_help_panel="Aggregati")
def check_territorial_aggregates(
    inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-territorial-aggregates-v1.json"
    ),
) -> None:
    """Verifica offline copertura, partizioni e riconciliazioni territoriali, senza pubblicare."""
    build_territorial_aggregates(Settings().data_dir, inputs, contract)


@app.command("fetch-territorial-aggregates", rich_help_panel="Acquisizione")
def fetch_territorial_aggregates(
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-territorial-aggregates-v1.json"
    ),
) -> None:
    """Acquisisce il solo inventario territoriale revisionato, riusando gli originali verificati."""
    typer.echo(str(acquire_territorial_aggregates(Settings().data_dir, contract)))


@app.command("ingest-territorial-aggregates", rich_help_panel="Aggregati")
def ingest_territorial_aggregates(
    inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-territorial-aggregates-v1.json"
    ),
    supersedes: Annotated[UUID | None, typer.Option()] = None,
    revision_reason: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Verifica e pubblica gli aggregati atomicamente, con avanzamento nel terminale."""
    settings = Settings()
    bundle = build_territorial_aggregates(settings.data_dir, inputs, contract)
    release = publish_coverage(settings, bundle, contract, supersedes, revision_reason)
    typer.echo(json.dumps({"release_id": str(release)}))


@app.command()
def export_openapi(output: Path = Path("docs/api/openapi.json")) -> None:
    """Export the API contract without a database connection."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


@app.command("fetch-pilot-inputs", rich_help_panel="Acquisizione")
def fetch_pilot_inputs(
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-pilot-valle-aosta-v1.json"
    ),
) -> None:
    """Acquisisce il solo inventario aggregato revisionato per la sintesi regionale."""
    typer.echo(str(acquire_inventory(Settings().data_dir, contract, "istat-m3-valle-aosta", "m3")))


@app.command("synthesize-pilot", rich_help_panel="Strumenti di sintesi")
def synthesize_pilot(
    inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-pilot-valle-aosta-v1.json"
    ),
    experiment: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/pilot-experiment-v1.json"
    ),
) -> None:
    """Genera e verifica un esperimento locale sintetico; non pubblica microdati."""
    root = Settings().data_dir
    config = Experiment.model_validate_json(experiment.read_bytes())
    result = run_pilot(root, prepare_inputs(root, inputs, contract), config)
    typer.echo(
        json.dumps({"experiment": str(result), "data_kind": "synthetic", "public_release": False})
    )


@app.command("verify-pilot", rich_help_panel="Strumenti di sintesi")
def verify_pilot(run: Annotated[Path, typer.Option(exists=True, file_okay=False)]) -> None:
    """Rilegge i Parquet e ricalcola tutti i gate e i rapporti indipendenti del pilota."""
    result = verify_run(run)
    typer.echo(json.dumps({"run_id": result["run_id"], "verified": True, "public_release": False}))


@app.command("fetch-national-inputs", rich_help_panel="Acquisizione")
def fetch_national_inputs(
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-national-v1.json"
    ),
) -> None:
    """Acquisisce gli originali nazionali fissati, con riuso e controllo checksum."""
    typer.echo(str(acquire_inventory(Settings().data_dir, contract, "istat-m4-national", "m4")))


@app.command("synthesize-national", rich_help_panel="Strumenti di sintesi")
def synthesize_national(
    inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-national-v1.json"
    ),
    reference: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/national-reference-v1.json"
    ),
    budget: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/national-budget-v1.json"
    ),
) -> None:
    """Sintesi nazionale senza cittadinanza; per il corrente usare synthesize-population."""
    root = Settings().data_dir
    directory = run_national(
        root,
        prepare_national_inputs(root, inputs, contract),
        NationalReference.model_validate_json(reference.read_bytes()),
        ResourceBudget.model_validate_json(budget.read_bytes()),
    )
    typer.echo(
        json.dumps({"snapshot": str(directory), "data_kind": "synthetic", "public_release": False})
    )


@app.command("verify-national", rich_help_panel="Strumenti di sintesi")
def verify_national_command(
    run: Annotated[Path, typer.Option(exists=True, file_okay=False)],
) -> None:
    """Verifica integrità, vincoli comunali e rapporto statistico/disclosure nazionale."""
    result = verify_national(run)
    typer.echo(json.dumps({"run_id": result["run_id"], "verified": True, "public_release": False}))


@app.command("fetch-citizenship")
def fetch_citizenship(
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-citizenship-v1.json"
    ),
) -> None:
    """Acquisisce gli originali STR/RCS fissati, con riuso e controllo checksum."""
    typer.echo(
        str(acquire_inventory(Settings().data_dir, contract, "istat-citizenship", "citizenship"))
    )


@app.command("synthesize-citizenship", rich_help_panel="Strumenti di sintesi")
def synthesize_citizenship(
    base_run: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-citizenship-v1.json"
    ),
    reference: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/citizenship-reference-v1.json"
    ),
    budget: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/national-budget-v1.json"
    ),
) -> None:
    """Cittadinanza su uno snapshot esistente; per il prodotto usare synthesize-population."""
    root = Settings().data_dir
    base = NationalInput.model_validate_json((base_run / "input.json").read_bytes())
    directory = run_citizenship(
        root,
        base_run,
        prepare_citizenship_inputs(root, inputs, contract, base),
        CitizenshipReference.model_validate_json(reference.read_bytes()),
        ResourceBudget.model_validate_json(budget.read_bytes()),
    )
    typer.echo(
        json.dumps({"snapshot": str(directory), "data_kind": "synthetic", "public_release": False})
    )


@app.command("verify-citizenship", rich_help_panel="Strumenti di sintesi")
def verify_citizenship_command(
    run: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    base_run: Annotated[Path, typer.Option(exists=True, file_okay=False)],
) -> None:
    """Rilegge base e nuova versione, verificando cittadinanza e attributi immutati."""
    result = verify_citizenship(run, base_run)
    typer.echo(json.dumps({"run_id": result["run_id"], "verified": True, "public_release": False}))


@app.command("synthesize-population")
def synthesize_population(
    inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    citizenship_inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-national-v1.json"
    ),
    citizenship_contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-citizenship-v1.json"
    ),
    reference: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/population-reference-v1.json"
    ),
    budget: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/national-budget-v1.json"
    ),
) -> None:
    """Riferimento corrente: sesso/età, geografia, cittadinanza, poi famiglie."""
    root = Settings().data_dir
    national = prepare_national_inputs(root, inputs, contract)
    citizenship = prepare_citizenship_inputs(
        root, citizenship_inputs, citizenship_contract, national
    )
    directory = run_population(
        root,
        PopulationInput(national=national, citizenship=citizenship),
        PopulationReference.model_validate_json(reference.read_bytes()),
        ResourceBudget.model_validate_json(budget.read_bytes()),
    )
    typer.echo(
        json.dumps(
            {
                "snapshot": str(directory),
                "data_kind": "synthetic",
                "public_release": False,
            }
        )
    )


@app.command("verify-population")
def verify_population_command(
    run: Annotated[Path, typer.Option(exists=True, file_okay=False)],
) -> None:
    """Verifica lo snapshot corrente e gli attributi fissati prima delle famiglie."""
    result = verify_population(run)
    typer.echo(json.dumps({"run_id": result["run_id"], "verified": True, "public_release": False}))


@app.command("publish-population")
def publish_population_command(
    run: Annotated[Path, typer.Option(exists=True, file_okay=False)],
) -> None:
    """Pubblica nel database applicativo una popolazione già generata e verificata."""
    from itadb.population.publish import publish_population

    snapshot_id = publish_population(Settings(), run)
    typer.echo(json.dumps({"snapshot_id": snapshot_id, "data_kind": "synthetic"}))


@app.command("publish-population-boundaries")
def publish_population_boundaries_command(
    snapshot_id: Annotated[int, typer.Option(min=1)],
) -> None:
    """Aggiunge i confini provinciali dalla fonte geografica già archiviata dello snapshot."""
    from itadb.population.cartography import publish_boundaries

    count = publish_boundaries(Settings(), snapshot_id)
    typer.echo(json.dumps({"snapshot_id": snapshot_id, "provinces": count}))


@app.command("export-serving")
def export_serving(
    output: Annotated[Path, typer.Option()],
    evidence: Annotated[Path, typer.Option()],
) -> None:
    """Esporta tutte le API pubblicate dal PostgreSQL locale; non attiva la release."""
    from itadb.serving.export import export_archive

    export_archive(Settings(), output, evidence)
    typer.echo(json.dumps({"archive": str(output), "verified": True}))


@app.command("verify-serving")
def verify_serving(archive: Annotated[Path, typer.Option(exists=True, file_okay=False)]) -> None:
    """Verifica checksum, schema e conteggi dell'intero archivio."""
    from itadb.serving.archive import verify_archive

    manifest = verify_archive(archive)
    typer.echo(json.dumps({"verified": True, "database": manifest["database"]}))


@app.command("install-serving")
def install_serving(
    archive: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    activate: Annotated[bool, typer.Option()] = False,
) -> None:
    """Installa una copia verificata; --activate aggiorna current. Riavviare l'API."""
    from itadb.serving.archive import activate_archive, install_archive

    root = Settings().serving_dir
    installed = install_archive(archive, root)
    if activate:
        activate_archive(root, installed)
    typer.echo(json.dumps({"release": installed.name, "activated": activate}))


@app.command("activate-serving")
def activate_serving(release: Annotated[str, typer.Option()]) -> None:
    """Attiva o ripristina una release installata, senza cancellarne altre."""
    from itadb.serving.archive import activate_archive

    root = Settings().serving_dir
    activate_archive(root, root / "releases" / release)
    typer.echo(json.dumps({"release": release, "restart_required": True}))


@app.command("init-serving")
def init_serving() -> None:
    """Crea un catalogo vuoto esplicito solo su una nuova installazione."""
    from uuid import uuid4

    from itadb.serving.archive import activate_archive, empty_archive, install_archive

    root = Settings().serving_dir
    if (root / "current").is_symlink() or (root / "current").exists():
        raise typer.BadParameter("An archive is already active")
    archive = empty_archive(root / ("empty-" + uuid4().hex))
    installed = install_archive(archive, root)
    activate_archive(root, installed)
    typer.echo(json.dumps({"release": installed.name, "empty": True}))

import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

import typer
import uvicorn

from itadb.api.app import create_app
from itadb.config import Settings
from itadb.connectors.m2 import acquire_m2
from itadb.connectors.sdmx import SOURCES, SdmxConnector
from itadb.pipeline.istat_m2 import build_istat_m2
from itadb.pipeline.istat_population import check_population_sample
from itadb.pipeline.publish_coverage import publish_coverage
from itadb.pipeline.publish_istat import ingest_istat_population
from itadb.pipeline.runner import ingest_demo

app = typer.Typer(no_args_is_help=True, help="Itadb data operations. Run from the repository root.")


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


@app.command("check-m2")
def check_m2(
    inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-m2-v1.json"
    ),
) -> None:
    """Verifica offline copertura, partizioni e riconciliazioni M2, senza pubblicare."""
    build_istat_m2(Settings().data_dir, inputs, contract)


@app.command("fetch-m2")
def fetch_m2(
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-m2-v1.json"
    ),
) -> None:
    """Acquisisce il solo inventario M2 revisionato, riusando gli originali verificati."""
    typer.echo(str(acquire_m2(Settings().data_dir, contract)))


@app.command("ingest-m2")
def ingest_m2(
    inputs: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    contract: Annotated[Path, typer.Option(exists=True, dir_okay=False)] = Path(
        "contracts/istat-m2-v1.json"
    ),
    supersedes: Annotated[UUID | None, typer.Option()] = None,
    revision_reason: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Verifica e pubblica M2 atomicamente, con avanzamento nel terminale."""
    settings = Settings()
    bundle = build_istat_m2(settings.data_dir, inputs, contract)
    release = publish_coverage(settings, bundle, contract, supersedes, revision_reason)
    typer.echo(json.dumps({"release_id": str(release)}))


@app.command()
def export_openapi(output: Path = Path("docs/api/openapi.json")) -> None:
    """Export the API contract without a database connection."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

import json
from pathlib import Path

import httpx
import pytest

from itadb.connectors.sdmx import SdmxConnector, SourceDefinition

SOURCE = SourceDefinition("test", "https://provider.example/rest", 0, "https://provider.example")


def test_fetch_archives_provenance_and_filters(tmp_path: Path) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url.params["startPeriod"] == "2025"
        assert request.url.params["endPeriod"] == "2025"
        assert request.url.host == "provider.example"
        return httpx.Response(
            200,
            headers={"content-type": "text/csv", "etag": '"v1"'},
            content=b"TIME_PERIOD,OBS_VALUE\n2025,3\n",
        )

    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        artifact = SdmxConnector(SOURCE, tmp_path, client).fetch("FLOW", "IT.TOTAL", "2025", "2025")
    manifest = json.loads(artifact.manifest_path.read_text())
    assert manifest["status"] == "raw_only"
    assert manifest["license_review"] == "required_before_publication"
    assert manifest["etag"] == '"v1"'
    assert len(artifact.sha256) == 64


@pytest.mark.parametrize(
    "content_type,content,limit",
    [
        ("text/html", b"<html>error</html>", 100),
        ("text/csv", b"column\n12345\n", 4),
        ("text/csv", b"", 100),
    ],
)
def test_rejects_wrong_format_empty_and_oversized_responses(
    tmp_path: Path,
    content_type: str,
    content: bytes,
    limit: int,
) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, headers={"content-type": content_type}, content=content)
    )
    with httpx.Client(transport=transport) as client, pytest.raises(ValueError):
        SdmxConnector(SOURCE, tmp_path, client, limit).fetch("FLOW", "IT", "2025", "2025")
    assert not list(tmp_path.rglob("payload"))
    assert not list(tmp_path.rglob("*.download"))


def test_does_not_follow_untrusted_redirects(tmp_path: Path) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(302, headers={"location": "http://localhost"})
    )
    with httpx.Client(transport=transport) as client, pytest.raises(httpx.HTTPStatusError):
        SdmxConnector(SOURCE, tmp_path, client).fetch("FLOW", "IT", "2025", "2025")


def test_fetch_structure_archives_explicit_version_and_codelists(tmp_path: Path) -> None:
    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rest/datastructure/IT1/DCIS_POPRES1/1.0"
        assert request.url.params["references"] == "all"
        assert request.headers["Accept"] == "application/vnd.sdmx.structure+xml;version=2.1"
        return httpx.Response(
            200, headers={"content-type": "application/xml"}, content=b"<Structure/>"
        )

    with httpx.Client(transport=httpx.MockTransport(upstream)) as client:
        artifact = SdmxConnector(SOURCE, tmp_path, client).fetch_structure(
            "datastructure", "IT1", "DCIS_POPRES1", "1.0", "all"
        )
    assert artifact.path.read_bytes() == b"<Structure/>"
    assert json.loads(artifact.manifest_path.read_text())["status"] == "raw_only"


@pytest.mark.parametrize(
    "resource,agency,identifier,version,references",
    [
        ("dataflow", "IT1", "all", "1.0", "none"),
        ("dataflow", "IT1", "ALL", "1.0", "none"),
        ("dataflow", "IT1", "FLOW+OTHER", "1.0", "none"),
        ("datastructure", "IT1", "DSD", "latest", "all"),
        ("dataflow", "", "FLOW", "1.0", "none"),
        ("data", "IT1", "FLOW", "1.0", "none"),
        ("dataflow", "IT1", "FLOW", "1.0", "descendants"),
    ],
)
def test_structure_requires_bounded_identity(
    tmp_path: Path, resource: str, agency: str, identifier: str, version: str, references: str
) -> None:
    with pytest.raises(ValueError):
        SdmxConnector(SOURCE, tmp_path).fetch_structure(
            resource, agency, identifier, version, references
        )


def test_structure_respects_byte_limit(tmp_path: Path) -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, headers={"content-type": "application/xml"}, content=b"<data/>"
        )
    )
    with httpx.Client(transport=transport) as client, pytest.raises(ValueError, match="byte limit"):
        SdmxConnector(SOURCE, tmp_path, client, max_bytes=3).fetch_structure(
            "dataflow", "IT1", "FLOW", "1.0"
        )
    assert not list(tmp_path.rglob("payload"))

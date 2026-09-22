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

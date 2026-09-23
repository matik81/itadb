import json
from pathlib import Path

import httpx
import pytest

from itadb.connectors.m2 import acquire_m2
from itadb.connectors.sdmx import SdmxConnector
from itadb.connectors.static import fetch_static
from itadb.pipeline.istat_m2 import build_istat_m2
from itadb.pipeline.storage import atomic_json


@pytest.mark.parametrize(
    "url",
    [
        "http://www.istat.it/a",
        "https://example.org/a",
        "https://user@www.istat.it/a",
        "https://www.istat.it:8443/a",
    ],
)
def test_static_rejects_unreviewed_hosts(tmp_path: Path, url: str) -> None:
    with pytest.raises(ValueError):
        fetch_static(tmp_path, url, 100)


def test_bounded_acquisition_cache_and_contract_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SdmxConnector, "_wait_turn", lambda _: None)
    url = "https://www.istat.it/reviewed-fixture"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=b"invented", headers={"content-type": "text/plain"}
            )
        )
    ) as client:
        result = fetch_static(tmp_path, url, 100, client)
        with pytest.raises(ValueError, match="budget"):
            fetch_static(tmp_path, url, 2, client)
    contract = tmp_path / "contract.json"
    meta = json.loads(result.manifest_path.read_text())
    spec = {
        "name": "istat-m2",
        "version": "1.0.0",
        "sources": {"fixture": {k: meta[k] for k in ("sha256", "url", "bytes")}},
    }
    atomic_json(contract, spec)
    monkeypatch.setattr(
        "itadb.connectors.m2.fetch_static",
        lambda *a, **kw: pytest.fail("Cache hit must not access the network"),
    )
    inputs = acquire_m2(tmp_path, contract)
    assert json.loads(inputs.read_text())["fixture"] == str(result.manifest_path)
    spec["sources"]["fixture"]["bytes"] += 1
    atomic_json(contract, spec)
    with pytest.raises(ValueError, match="Unreviewed source manifest"):
        build_istat_m2(tmp_path, inputs, contract)
    assert list((tmp_path / "quarantine").glob("m2-onboarding-*.json"))


def test_download_does_not_follow_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SdmxConnector, "_wait_turn", lambda _: None)
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    302, headers={"location": "https://example.org/unreviewed"}
                )
            )
        ) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        fetch_static(tmp_path, "https://www.istat.it/a", 100, client)
    assert not list((tmp_path / "raw").glob(".*.download"))

"""Exercise availability failures without making network requests."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

SPEC = importlib.util.spec_from_file_location(
    "deployment_monitor", Path(__file__).resolve().parents[1] / "scripts/check_deployment.py"
)
assert SPEC is not None and SPEC.loader is not None
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)

RESPONSES = [
    (b'{"status":"ready"}', "application/json"),
    (b'[{"id":1}]', "application/json"),
    (b'<div id="root"></div><script src="/assets/index.js"></script>', "text/html"),
    (b"console.log('app')", "application/javascript"),
]


def test_complete_deployment() -> None:
    with patch.object(monitor, "fetch", side_effect=RESPONSES) as fetch:
        monitor.check("https://api.example.test", "https://web.example.test")
    assert fetch.call_args_list[0].args[1] == "https://web.example.test"
    assert fetch.call_args_list[-1].args == ("https://web.example.test/assets/index.js",)


@pytest.mark.parametrize(
    ("index", "replacement"),
    [
        (0, (b'{"status":"unavailable"}', "application/json")),
        (1, (b"[]", "application/json")),
        (1, (b"null", "application/json")),
        (2, (b"<html>Maintenance</html>", "text/html")),
        (
            2,
            (
                b'<div id="root"></div><script src="https://elsewhere.test/a.js"></script>',
                "text/html",
            ),
        ),
        (3, (b"<html>Not found</html>", "text/html")),
    ],
)
def test_broken_deployment(index: int, replacement: tuple[bytes, str]) -> None:
    responses = RESPONSES.copy()
    responses[index] = replacement
    with patch.object(monitor, "fetch", side_effect=responses), pytest.raises(ValueError):
        monitor.check("https://api.example.test", "https://web.example.test")


@pytest.mark.parametrize(
    "url", ["", "http://example.test", "https://u:p@example.test", "https://x/y"]
)
def test_invalid_monitor_origin(url: str) -> None:
    with pytest.raises(ValueError):
        monitor.origin(url)


def test_retries_fail_closed_without_logging_remote_details(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch("sys.argv", ["check", "--api-url", "https://a.test", "--web-url", "https://w.test"]),
        patch.object(monitor, "check", side_effect=OSError("private remote details")) as check,
        patch.object(monitor.time, "sleep"),
    ):
        assert monitor.main() == 1
    assert check.call_count == 3
    assert "private remote details" not in capsys.readouterr().out

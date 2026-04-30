from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.routes.spa import _inject_bootstrap
from app.settings import Settings


def test_inline_bootstrap_escapes_script_terminators() -> None:
    html = "<html><body><main id=\"root\"></main></body></html>"

    rendered = _inject_bootstrap(
        html,
        {
            "dashboard": {
                "query": "all",
                "data": {"unsafe": "</script><img src=x onerror=alert(1)>"},
            }
        },
    )

    assert "window.__MILEMARK_BOOTSTRAP__" in rendered
    assert "\\u003c/script\\u003e" in rendered
    assert "</script><img" not in rendered


def test_app_shell_bootstraps_canonical_dashboard_query(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html><body><div id=\"root\"></div></body></html>", encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path / "data",
        config_dir=tmp_path / "config",
        frontend_dist_dir=dist_dir,
    )
    client = TestClient(create_app(settings))

    response = client.get("/?trip_group_id=ignored&include_booked=false")

    assert response.status_code == 200
    assert '"query":"all"' in response.text
    assert '"includeBooked":true' in response.text
    assert '"includeSkipped":true' in response.text

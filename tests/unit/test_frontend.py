from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_gateway import main as main_module
from ai_gateway.frontend import mount_console


def _write_dist(dist: Path) -> None:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>console</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("export {}", encoding="utf-8")


def test_console_serves_index_history_and_assets(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_dist(dist)
    app = FastAPI()
    mount_console(app, dist)

    with TestClient(app) as client:
        for path in ("/console", "/console/", "/console/providers"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.text == "<html>console</html>"
            assert response.headers["cache-control"] == "no-cache"

        asset_response = client.get("/console/assets/app.js")
        assert asset_response.status_code == 200
        assert asset_response.text == "export {}"


def test_console_redirects_root_requests_to_console(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_dist(dist)
    app = FastAPI()
    mount_console(app, dist)

    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/console/"


def test_console_is_not_registered_when_dist_is_missing(tmp_path: Path) -> None:
    app = FastAPI()
    original_route_count = len(app.routes)

    mount_console(app, tmp_path / "missing")

    assert len(app.routes) == original_route_count
    with TestClient(app) as client:
        assert client.get("/console").status_code == 404
        assert client.get("/console/").status_code == 404


def test_console_is_not_registered_without_index(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("export {}", encoding="utf-8")
    app = FastAPI()

    mount_console(app, dist)

    with TestClient(app) as client:
        assert client.get("/console/assets/app.js").status_code == 404


def test_console_is_not_registered_without_assets_directory(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>console</html>", encoding="utf-8")
    app = FastAPI()

    mount_console(app, dist)

    with TestClient(app) as client:
        assert client.get("/console/").status_code == 404
        response = client.get("/console/assets/missing.js")

    assert response.status_code == 404
    assert response.text != "<html>console</html>"


def test_missing_asset_does_not_fall_back_to_index(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_dist(dist)
    app = FastAPI()
    mount_console(app, dist)

    with TestClient(app) as client:
        response = client.get("/console/assets/missing.js")

    assert response.status_code == 404
    assert response.text != "<html>console</html>"


def test_asset_mount_rejects_path_traversal(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_dist(dist)
    app = FastAPI()
    mount_console(app, dist)

    with TestClient(app) as client:
        response = client.get("/console/assets/%2e%2e/index.html")

    assert response.status_code == 404
    assert response.text != "<html>console</html>"


def test_console_routes_do_not_intercept_backend_paths(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _write_dist(dist)
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    async def openai_models() -> dict[str, str]:
        return {"protocol": "openai"}

    @app.get("/v1beta/models")
    async def gemini_models() -> dict[str, str]:
        return {"protocol": "gemini"}

    mount_console(app, dist)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/v1/models").json() == {"protocol": "openai"}
        assert client.get("/v1beta/models").json() == {"protocol": "gemini"}
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/consoleish").status_code == 404


def test_create_app_mounts_default_console_after_backend_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mounted: list[tuple[FastAPI, Path]] = []

    def record_mount(app: FastAPI, dist_dir: Path) -> None:
        mounted.append((app, dist_dir))
        assert getattr(app.routes[-1], "path", None) == "/health"

    monkeypatch.setattr(main_module, "mount_console", record_mount)

    app = main_module.create_app()

    assert mounted == [
        (
            app,
            Path(main_module.__file__).resolve().parents[2] / "frontend" / "dist",
        )
    ]

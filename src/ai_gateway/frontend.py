from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles


def mount_console(app: FastAPI, dist_dir: Path) -> None:
    index = dist_dir / "index.html"
    assets = dist_dir / "assets"
    if not index.is_file():
        return

    if assets.is_dir():
        app.mount(
            "/console/assets",
            StaticFiles(directory=assets),
            name="console-assets",
        )

    async def console_index() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    app.add_api_route("/console", console_index, include_in_schema=False)
    app.add_api_route("/console/", console_index, include_in_schema=False)
    app.add_api_route("/console/{path:path}", console_index, include_in_schema=False)

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.account import router as account_router
from app.api.audit import router as audit_router
from app.api.bets import router as bet_router
from app.api.catalog import router as catalog_router
from app.api.disclosures import router as disclosure_router
from app.api.inventory import router as inventory_router
from app.api.routes import router
from app.config import get_settings
from app.db import engine
from app.telemetry import instrument_application

settings = get_settings()
app = FastAPI(
    title="GwenGift Demo API",
    version="0.1.0",
    debug=settings.environment == "development",
)
app.include_router(router)
app.include_router(account_router)
app.include_router(catalog_router)
app.include_router(audit_router)
app.include_router(disclosure_router)
app.include_router(inventory_router)
app.include_router(bet_router)

frontend_dist = settings.frontend_dist_path.resolve()
frontend_index = frontend_dist / "index.html"
if frontend_index.is_file():
    assets = frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/{_path:path}", include_in_schema=False)
    def frontend(_path: str) -> FileResponse:
        if _path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        return FileResponse(frontend_index)


instrument_application(app, engine=engine, settings=settings)

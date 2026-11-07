from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.api.dependencies import DbSession
from app.models import Disclosure
from app.services.disclosures import DisclosurePackage

router = APIRouter(prefix="/api/rounds", tags=["disclosures"])


@router.get(
    "/{round_id}/disclosure",
    response_model=DisclosurePackage,
    summary="Download a disclosed round package",
    description=(
        "Returns the immutable canonical JSON package after sell-out or deadline disclosure."
    ),
)
def download_disclosure(round_id: str, db: DbSession) -> Response:
    disclosure = db.scalar(select(Disclosure).where(Disclosure.round_id == round_id))
    if disclosure is None:
        raise HTTPException(status_code=404, detail="Round disclosure is not available")
    return Response(
        content=disclosure.package_json,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="gwengift-{round_id}-disclosure.json"',
            "X-Disclosure-SHA256": disclosure.package_hash,
        },
    )

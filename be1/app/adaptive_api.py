"""FastAPI routes for the Adaptive Decision Ontology Engine."""
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, status

from .adaptive_ontology import (
    AdaptCategoryRequest,
    AdaptedOntologyResponse,
    AdaptiveOntologyEngine,
    NextQuestionRequest,
    NextQuestionResponse,
)
from .config import ONTOLOGY_REVIEWER_TOKEN


router = APIRouter(prefix="/api/v1/ontology", tags=["adaptive-ontology"])
_root = Path(__file__).resolve().parents[2]
engine = AdaptiveOntologyEngine(_root / "data" / "ontology_data.json", _root / "be1" / "data" / "adaptive_profiles.json")


def require_reviewer(authorization: str | None = Header(default=None)) -> None:
    if not ONTOLOGY_REVIEWER_TOKEN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Reviewer authentication is not configured.")
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reviewer authentication is required.")
    if authorization != f"Bearer {ONTOLOGY_REVIEWER_TOKEN}":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer permission is required.")


@router.post("/adapt", response_model=AdaptedOntologyResponse)
def adapt(request: AdaptCategoryRequest) -> AdaptedOntologyResponse:
    return engine.adapt(request)


@router.post("/questions/next", response_model=NextQuestionResponse | None)
def next_question(request: NextQuestionRequest) -> NextQuestionResponse | None:
    if not engine.get_profile(request.category_profile_id):
        raise HTTPException(status_code=404, detail="KhÃ´ng tÃ¬m tháº¥y ontology profile.")
    return engine.next_question(request)


@router.get("/profiles/{category_name}", response_model=AdaptedOntologyResponse)
def profile(category_name: str) -> AdaptedOntologyResponse:
    found = engine.get_profile(category_name)
    if not found:
        raise HTTPException(status_code=404, detail="Không tìm thấy ontology profile.")
    return found


@router.post("/review/{profile_id}/approve", response_model=AdaptedOntologyResponse)
def approve(profile_id: str, _: None = Depends(require_reviewer)) -> AdaptedOntologyResponse:
    try:
        return engine.review(profile_id, approved=True)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Không tìm thấy profile.") from error


@router.post("/review/{profile_id}/reject", response_model=AdaptedOntologyResponse)
def reject(profile_id: str, _: None = Depends(require_reviewer)) -> AdaptedOntologyResponse:
    try:
        return engine.review(profile_id, approved=False)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Không tìm thấy profile.") from error


@router.get("/seeds")
def seeds() -> list[dict]:
    return engine.seeds()


@router.get("/modules")
def modules() -> list[dict]:
    return engine.modules()

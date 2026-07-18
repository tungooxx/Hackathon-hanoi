"""FastAPI routes for the Adaptive Decision Ontology Engine."""
from pathlib import Path

from fastapi import APIRouter, HTTPException

from .adaptive_ontology import (
    AdaptCategoryRequest,
    AdaptedOntologyResponse,
    AdaptiveOntologyEngine,
    NextQuestionRequest,
    NextQuestionResponse,
)


router = APIRouter(prefix="/api/v1/ontology", tags=["adaptive-ontology"])
_root = Path(__file__).resolve().parents[2]
engine = AdaptiveOntologyEngine(_root / "data" / "ontology_data.json", _root / "be1" / "data" / "generated_categories.json")


@router.post("/adapt", response_model=AdaptedOntologyResponse)
def adapt(request: AdaptCategoryRequest) -> AdaptedOntologyResponse:
    return engine.adapt(request)


@router.post("/questions/next", response_model=NextQuestionResponse | None)
def next_question(request: NextQuestionRequest) -> NextQuestionResponse | None:
    return engine.next_question(request)


@router.get("/profiles/{category_name}", response_model=AdaptedOntologyResponse)
def profile(category_name: str) -> AdaptedOntologyResponse:
    found = engine.get_profile(category_name)
    if not found:
        raise HTTPException(status_code=404, detail="Không tìm thấy ontology profile.")
    return found


@router.post("/review/{profile_id}/approve", response_model=AdaptedOntologyResponse)
def approve(profile_id: str) -> AdaptedOntologyResponse:
    try:
        return engine.review(profile_id, approved=True)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Không tìm thấy profile.") from error


@router.post("/review/{profile_id}/reject", response_model=AdaptedOntologyResponse)
def reject(profile_id: str) -> AdaptedOntologyResponse:
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

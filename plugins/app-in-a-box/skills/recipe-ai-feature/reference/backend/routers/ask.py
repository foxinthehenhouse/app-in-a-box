"""Ask questions about your own notes, answered from them with citations.

PUT    /api/v1/ask/sources/{source_id}  {"title": "...", "text": "..."}  -> 200 AskSourceIndexed
DELETE /api/v1/ask/sources/{source_id}                                  -> 204
POST   /api/v1/ask                      {"question": "..."}              -> 200 AskAnswer

All model work lives in backend/services/ai_ask.py (the AI fence). This file wires the
dependencies and turns its errors into honest status codes:
  503 "<feature> not configured"  a key is missing (named, never a fake answer)
  429 ai_daily_limit              today's token budget is spent
  502 ai_unavailable              the provider failed, or its answer wasn't grounded

Retrieval runs as the CALLER: `caller_db` hands the service the user's own JWT, so RLS
and the auth.uid() filter in the SQL decide what comes back. Never pass `get_db()` (the
service key) to the retrieval calls.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field

from backend.auth import CurrentUser, get_current_user
from backend.config import feature_missing
from backend.db import get_db
from backend.idempotency import idempotent
from backend.ratelimit import rate_limit
from backend.routers.me import Wire, WireIn
from backend.services import ai_ask

router = APIRouter(prefix="/api/v1/ask", tags=["ask"])
_bearer = HTTPBearer(auto_error=False)

SourceId = Annotated[str, Path(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")]


class AskQuestion(WireIn):
    """POST body. Mirrored by `AskQuestionWire` in mobile/lib/api.ts."""

    question: str = Field(min_length=1, max_length=1000)


class AskSource(WireIn):
    """PUT body: the full text of one of the caller's sources (a note, an entry).
    Mirrored by `AskSourceWire` in mobile/lib/api.ts."""

    title: str = Field(default="", max_length=200)
    text: str = Field(min_length=1, max_length=100_000)


class AskCitation(Wire):
    index: int
    source_id: str
    title: str
    snippet: str


class AskAnswer(Wire):
    """`found: false` is a real answer ("not in your notes"), with no text and no citations."""

    found: bool
    answer: str | None
    citations: list[AskCitation]


class AskSourceIndexed(Wire):
    source_id: str
    chunks: int


def _require(feature: str) -> None:
    if feature_missing(feature):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{feature} not configured")


def require_ai() -> None:
    _require(ai_ask.FEATURE)


def require_retrieval() -> None:
    _require(ai_ask.RETRIEVAL_FEATURE)


def caller_db(
    _user: CurrentUser = Depends(get_current_user),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> ai_ask.UserDB:
    """The caller's own PostgREST session (their verified JWT, so RLS applies)."""
    if creds is None:  # unreachable once get_current_user passed; never fall back
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return ai_ask.UserDB(creds.credentials)


def get_embedder() -> ai_ask.Embedder:
    return ai_ask.default_embedder()


def get_generator() -> ai_ask.Generator:
    return ai_ask.default_generator()


def _to_wire(answer: ai_ask.Answer) -> AskAnswer:
    return AskAnswer(
        found=answer.found,
        answer=answer.text,
        citations=[
            AskCitation(index=c.index, source_id=c.source_id, title=c.title, snippet=c.snippet)
            for c in answer.citations
        ],
    )


def _honest(exc: Exception) -> HTTPException:
    if isinstance(exc, ai_ask.DailyLimit):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "ai_daily_limit")
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "ai_unavailable")


@router.post(
    "",
    response_model=AskAnswer,
    response_model_by_alias=True,
    dependencies=[
        Depends(require_ai),
        Depends(require_retrieval),
        Depends(rate_limit("ai.ask", 10)),
        # A retried question (same Idempotency-Key) gets the stored answer back instead of
        # paying for a second model call.
        Depends(idempotent()),
    ],
)
def ask(
    body: AskQuestion,
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
    user_db: ai_ask.UserDB = Depends(caller_db),
    embedder: ai_ask.Embedder = Depends(get_embedder),
    generator: ai_ask.Generator = Depends(get_generator),
) -> AskAnswer:
    try:
        answer = ai_ask.ask(db, user_db, user.id, body.question, embedder, generator)
    except (ai_ask.DailyLimit, ai_ask.AIUnavailable) as exc:
        raise _honest(exc) from exc
    return _to_wire(answer)


@router.put(
    "/sources/{source_id}",
    response_model=AskSourceIndexed,
    response_model_by_alias=True,
    dependencies=[Depends(require_retrieval), Depends(rate_limit("ai.index", 30))],
)
def index_source(
    source_id: SourceId,
    body: AskSource,
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
    user_db: ai_ask.UserDB = Depends(caller_db),
    embedder: ai_ask.Embedder = Depends(get_embedder),
) -> AskSourceIndexed:
    try:
        n = ai_ask.index_source(db, user_db, user.id, source_id, body.title, body.text, embedder)
    except (ai_ask.DailyLimit, ai_ask.AIUnavailable) as exc:
        raise _honest(exc) from exc
    return AskSourceIndexed(source_id=source_id, chunks=n)


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_retrieval), Depends(rate_limit("ai.index", 30))],
)
def delete_source(source_id: SourceId, user_db: ai_ask.UserDB = Depends(caller_db)) -> Response:
    try:
        ai_ask.remove_source(user_db, source_id)
    except ai_ask.AIUnavailable as exc:
        raise _honest(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)

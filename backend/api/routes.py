from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.orchestrator.runner import Runner

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


runner = Runner()


class QueryRequest(BaseModel):
    query: str


@router.post("/run")
@limiter.limit("20/minute")
def run_pipeline(request: Request, body: QueryRequest):
    try:
        result = runner.run(body.query)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
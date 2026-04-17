import logging

from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.api.routes import router
from backend.api.websocket import stream_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="GTM Intelligence API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root():
    return {"status": "running"}


@app.websocket("/ws/run")
async def websocket_run(websocket: WebSocket):
    await stream_run(websocket)
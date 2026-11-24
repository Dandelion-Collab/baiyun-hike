"""FastAPI 入口：接口只做转发，编排在 app/orchestrator.py。"""

from __future__ import annotations

from fastapi import FastAPI

from app.models import CheckRequest, Issue, RouteRequest, RouteResult
from app.orchestrator import run_check, run_route

app = FastAPI(title="广州旅行助手", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/check", response_model=list[Issue])
def check_endpoint(payload: CheckRequest) -> list[Issue]:
    return run_check(payload.text).issues


@app.post("/route", response_model=RouteResult)
def route_endpoint(payload: RouteRequest) -> RouteResult:
    return run_route("", payload.from_node, payload.to_node, payload.depart_at).route
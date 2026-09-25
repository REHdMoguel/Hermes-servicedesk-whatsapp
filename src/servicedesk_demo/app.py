"""Minimal FastAPI surface around the approval workflow."""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .core import Action, Actor, DemoAdapter, JsonlAudit, Workflow

app = FastAPI(title="Conversational Service Desk Automation Demo", version="1.0.0")
workflow = Workflow(DemoAdapter(), JsonlAudit(Path(os.getenv("AUDIT_PATH", "./data/audit.jsonl"))))


class DraftRequest(BaseModel):
    action: Action
    payload: dict
    actor_id: str


class ActorRequest(BaseModel):
    actor_id: str
    display_name: str = "Demo Operator"
    roles: list[str] = []


@app.get("/health")
def health():
    return {"ok": True, "adapter": "demo"}


@app.post("/work-items")
def draft(request: DraftRequest):
    actor = Actor(request.actor_id, request.actor_id, ("requester",))
    return workflow.draft(request.action, request.payload, actor)


@app.post("/work-items/{item_id}/request-approval")
def request_approval(item_id: str, request: ActorRequest):
    try:
        return workflow.request_approval(item_id, Actor(request.actor_id, request.display_name, tuple(request.roles)))
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/work-items/{item_id}/approve")
def approve(item_id: str, request: ActorRequest):
    try:
        return workflow.approve(item_id, Actor(request.actor_id, request.display_name, tuple(request.roles)))
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/work-items/{item_id}/execute")
def execute(item_id: str, request: ActorRequest):
    try:
        return workflow.execute(item_id, Actor(request.actor_id, request.display_name, tuple(request.roles)))
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc

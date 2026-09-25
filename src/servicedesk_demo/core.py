"""Domain core for a human-approved conversational Service Desk workflow."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Protocol
import uuid


class State(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTED = "executed"
    REJECTED = "rejected"


class Action(str, Enum):
    CREATE_TICKET = "create_ticket"
    ADD_REPLY = "add_reply"
    RESOLVE_TICKET = "resolve_ticket"


@dataclass(frozen=True)
class Actor:
    actor_id: str
    display_name: str
    roles: tuple[str, ...]


@dataclass
class WorkItem:
    action: Action
    payload: dict
    requested_by: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: State = State.DRAFT
    approved_by: str | None = None
    result: dict | None = None


class ServiceDeskAdapter(Protocol):
    def execute(self, action: Action, payload: dict, idempotency_key: str) -> dict: ...


class JsonlAudit:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, event: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


class Workflow:
    """State machine that requires explicit approval before external writes."""

    REQUIRED_ROLES = {
        Action.CREATE_TICKET: {"it_support", "admin"},
        Action.ADD_REPLY: {"it_support", "admin"},
        Action.RESOLVE_TICKET: {"it_support", "admin"},
    }

    def __init__(self, adapter: ServiceDeskAdapter, audit: JsonlAudit):
        self.adapter = adapter
        self.audit = audit
        self.items: dict[str, WorkItem] = {}

    def draft(self, action: Action, payload: dict, actor: Actor) -> WorkItem:
        if not payload:
            raise ValueError("payload cannot be empty")
        item = WorkItem(action=action, payload=payload, requested_by=actor.actor_id)
        self.items[item.id] = item
        self.audit.append({"event": "work_item.drafted", "item_id": item.id, "action": action.value, "actor_id": actor.actor_id})
        return item

    def request_approval(self, item_id: str, actor: Actor) -> WorkItem:
        item = self._require(item_id, State.DRAFT)
        item.state = State.PENDING_APPROVAL
        self.audit.append({"event": "work_item.pending_approval", "item_id": item.id, "actor_id": actor.actor_id})
        return item

    def approve(self, item_id: str, actor: Actor) -> WorkItem:
        item = self._require(item_id, State.PENDING_APPROVAL)
        if not set(actor.roles) & self.REQUIRED_ROLES[item.action]:
            self.audit.append({"event": "work_item.approval_denied", "item_id": item.id, "actor_id": actor.actor_id})
            raise PermissionError("actor is not authorized for this action")
        item.approved_by = actor.actor_id
        item.state = State.APPROVED
        self.audit.append({"event": "work_item.approved", "item_id": item.id, "actor_id": actor.actor_id})
        return item

    def reject(self, item_id: str, actor: Actor, reason: str) -> WorkItem:
        item = self._require(item_id, State.PENDING_APPROVAL)
        item.state = State.REJECTED
        self.audit.append({"event": "work_item.rejected", "item_id": item.id, "actor_id": actor.actor_id, "reason": reason})
        return item

    def execute(self, item_id: str, actor: Actor) -> WorkItem:
        item = self._require(item_id, State.APPROVED)
        key = hashlib.sha256(f"{item.id}:{item.action.value}".encode()).hexdigest()
        item.result = self.adapter.execute(item.action, item.payload, key)
        item.state = State.EXECUTED
        self.audit.append({"event": "work_item.executed", "item_id": item.id, "actor_id": actor.actor_id, "result_ref": item.result.get("id")})
        return item

    def _require(self, item_id: str, expected: State) -> WorkItem:
        item = self.items[item_id]
        if item.state is not expected:
            raise ValueError(f"expected {expected.value}, found {item.state.value}")
        return item


class DemoAdapter:
    """Deterministic adapter for local demos; performs no network calls."""

    def __init__(self):
        self.calls: dict[str, dict] = {}

    def execute(self, action: Action, payload: dict, idempotency_key: str) -> dict:
        if idempotency_key not in self.calls:
            self.calls[idempotency_key] = {"id": f"DEMO-{len(self.calls)+1:04d}", "action": action.value, "status": "simulated"}
        return self.calls[idempotency_key]

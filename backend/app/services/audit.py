"""Audit trail: every insert, update and delete of an `Audited` model is written to audit_log
in the same transaction, with the acting user, request id and a before/after diff.

The acting user comes from `Session.info["actor_id"]`, set by the auth dependency.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, insert, inspect
from sqlalchemy.orm import Session, UOWTransaction

from app.core.context import client_ip_var, request_id_var
from app.models.audit import AuditLog
from app.models.base import ActorMixin, Audited
from app.models.enums import AuditAction

ACTOR_KEY = "actor_id"
_ALWAYS_SKIP = frozenset({"created_at", "updated_at", "created_by", "updated_by", "tenant_id"})
REDACTED = "***"


def set_actor(db: Session, user_id: int | None) -> None:
    db.info[ACTOR_KEY] = user_id


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _entity_id(obj: Any) -> str | None:
    # In after_flush the identity key of a new row is not set yet; read the primary key values.
    state = inspect(obj)
    values = [state.dict.get(col.key) for col in state.mapper.primary_key]
    if any(v is None for v in values):
        return None
    return ",".join(str(v) for v in values)


def _diff(obj: Any, action: AuditAction) -> dict[str, Any]:
    state = inspect(obj)
    skip = _ALWAYS_SKIP | getattr(obj, "__audit_exclude__", frozenset())
    redact: frozenset[str] = getattr(obj, "__audit_redact__", frozenset())
    out: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in skip:
            continue
        if action is AuditAction.UPDATE:
            history = state.attrs[key].history
            if not history.has_changes():
                continue
            before = history.deleted[0] if history.deleted else None
            after = history.added[0] if history.added else None
            if key in redact:
                out[key] = {"from": REDACTED, "to": REDACTED}
            else:
                out[key] = {"from": _jsonable(before), "to": _jsonable(after)}
        elif key in state.dict:  # only values already loaded; never trigger SQL mid-flush
            out[key] = REDACTED if key in redact else _jsonable(state.dict[key])
    return out


def _row(
    session: Session, obj: Any, action: AuditAction, changes: dict[str, Any]
) -> dict[str, Any]:
    return {
        "tenant_id": getattr(obj, "tenant_id", None) or 1,
        "user_id": session.info.get(ACTOR_KEY),
        "action": action,
        "entity": obj.__tablename__,
        "entity_id": _entity_id(obj),
        "changes": changes,
        "request_id": request_id_var.get(),
        "ip": client_ip_var.get(),
    }


@event.listens_for(Session, "before_flush")
def _stamp_actor(session: Session, _ctx: UOWTransaction, _instances: object) -> None:
    actor = session.info.get(ACTOR_KEY)
    if actor is None:
        return
    for obj in session.new:
        if isinstance(obj, ActorMixin):
            obj.created_by = obj.created_by or actor
            obj.updated_by = actor
    for obj in session.dirty:
        if isinstance(obj, ActorMixin) and session.is_modified(obj):
            obj.updated_by = actor


@event.listens_for(Session, "after_flush")
def _write_audit(session: Session, _ctx: UOWTransaction) -> None:
    rows: list[dict[str, Any]] = []
    for obj in session.new:
        if isinstance(obj, Audited):
            rows.append(_row(session, obj, AuditAction.INSERT, _diff(obj, AuditAction.INSERT)))
    for obj in session.dirty:
        if isinstance(obj, Audited) and session.is_modified(obj, include_collections=False):
            changes = _diff(obj, AuditAction.UPDATE)
            if changes:
                rows.append(_row(session, obj, AuditAction.UPDATE, changes))
    for obj in session.deleted:
        if isinstance(obj, Audited):
            rows.append(_row(session, obj, AuditAction.DELETE, _diff(obj, AuditAction.DELETE)))
    if rows:
        session.connection().execute(insert(AuditLog), rows)


def record_event(
    db: Session,
    action: AuditAction,
    entity: str,
    entity_id: str | int | None = None,
    changes: dict[str, Any] | None = None,
    user_id: int | None = None,
    tenant_id: int = 1,
) -> None:
    """Log something that is not a row change: a login, a failed login, an owner override."""
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id if user_id is not None else db.info.get(ACTOR_KEY),
            action=action,
            entity=entity,
            entity_id=None if entity_id is None else str(entity_id),
            changes={k: _jsonable(v) for k, v in (changes or {}).items()},
            request_id=request_id_var.get(),
            ip=client_ip_var.get(),
        )
    )

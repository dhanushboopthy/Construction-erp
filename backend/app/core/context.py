"""Per-request context shared with logging and auditing.

These are set by middleware in the event loop, so they are copied into the worker threads
that run sync dependencies and endpoints. The acting user is NOT kept here: a value set
inside a sync dependency would not flow back out of its thread. The auth dependency
stores the user on `request.state` (for the access log) and on `Session.info` (for audit).
"""

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)

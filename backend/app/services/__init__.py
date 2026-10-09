"""Application services: load data, apply app.domain rules, persist, commit.

Importing this package registers the audit listeners on every SQLAlchemy Session.
"""

from app.services import audit as _audit  # noqa: F401 - registers session event listeners

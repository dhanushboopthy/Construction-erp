"""The one place that starts `pg_dump`, `pg_restore` and `tar` (Milestone 25).

Command lines are lists (`shell=False`), the executable is an absolute path found in an
allow-listed folder (`PG_BIN_DIR`, then the system folders), the password reaches the tool only
through the `PGPASSWORD` environment variable, and a timeout kills the process.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.domain import backups as rules


class ToolMissingError(Exception):
    pass


class ToolFailedError(Exception):
    pass


@dataclass(frozen=True)
class ToolStatus:
    name: str
    path: str | None


def find_tool(name: str) -> Path:
    """Absolute path of an allow-listed tool, or ToolMissingError."""
    if name not in rules.TOOLS:
        raise ToolMissingError(f"{name} is not an allowed tool")
    for folder in rules.tool_dirs(get_settings().pg_bin_dir):
        candidate = Path(folder) / name
        if candidate.is_absolute() and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise ToolMissingError(f"{name} was not found")


def tool_status() -> list[ToolStatus]:
    found: list[ToolStatus] = []
    for name in sorted(rules.TOOLS):
        try:
            found.append(ToolStatus(name, str(find_tool(name))))
        except ToolMissingError:
            found.append(ToolStatus(name, None))
    return found


def run(
    argv: list[str],
    *,
    password: str = "",
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one allow-listed command. Raises ToolFailedError with the tool's own message on a
    non-zero exit, a timeout (the process is killed) or a missing program."""
    if not argv or Path(argv[0]).name not in rules.TOOLS or not Path(argv[0]).is_absolute():
        raise ToolFailedError("The command is not allowed")
    try:
        rules.assert_no_secret(argv, password)
    except ValueError as exc:
        raise ToolFailedError("The command carries a password and was not run") from exc
    seconds = timeout or get_settings().backup_tool_timeout_seconds
    child_env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TMPDIR"}}
    child_env.update(env or {})
    try:
        done = subprocess.run(  # noqa: S603 - argv list, absolute allow-listed path, no shell
            argv,
            capture_output=True,
            text=True,
            timeout=seconds,
            check=False,
            shell=False,
            env=child_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolFailedError(f"{Path(argv[0]).name} took longer than {seconds} seconds") from exc
    except OSError as exc:
        raise ToolFailedError(f"{Path(argv[0]).name} could not be started") from exc
    if done.returncode != 0:
        message = (done.stderr or "").strip().splitlines()[-1:] or ["failed"]
        raise ToolFailedError(f"{Path(argv[0]).name}: {message[0][:300]}")
    return done

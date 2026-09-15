"""Whitelisted command execution.

There is deliberately **no** ``run_any_command``. This module exposes exactly one
command-running tool, ``run_safe_command``, and it will only run a command whose
program name appears in the allow-list AND whose arguments contain no shell
metacharacters. The command is executed as an argument vector with
``shell=False``, so even a clever argument cannot start a second process.

Two layers must agree before anything runs:
  1. this module's own allow-list check (program + argument scan), and
  2. the permission manager (which treats it as MODERATE by default).

Neither layer trusts the model.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from typing import Any

from tools.registry import Level, Tool, ToolError

log = logging.getLogger(__name__)

# Programs that are always refused, even if someone adds them to config.
_ALWAYS_BLOCKED = {
    "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    "bash", "sh", "wsl", "cscript", "wscript", "mshta", "rundll32",
    "regsvr32", "bitsadmin", "wmic", "schtasks", "reg", "regedit", "net",
    "netsh", "takeown", "icacls", "cacls", "attrib", "diskpart", "format",
    "del", "erase", "rmdir", "rd", "rm", "mv", "move", "copy", "xcopy",
    "robocopy", "curl", "wget", "certutil", "forfiles", "start", "runas",
    "python", "pythonw", "python3", "pip", "node", "npm", "npx",
}

# Characters that would let one argument turn into several commands.
_SHELL_METACHARS = re.compile(r"[&|;<>`$%\r\n\x00]|\$\(|\./")

# Extra arguments that are dangerous even for an allow-listed program.
_DENY_ARG_PATTERNS = (
    re.compile(r"^-e$", re.I),          # powershell-style eval
    re.compile(r"^-c$", re.I),
    re.compile(r"^/c$", re.I),          # cmd-style command
    re.compile(r"--exec", re.I),
    re.compile(r"^-EncodedCommand", re.I),
)


class CommandNotAllowed(ToolError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "command_not_allowed")


def _normalise(program: str) -> str:
    return program.strip().lower().removesuffix(".exe")


def check_command(command: str, allowed: list[str]) -> tuple[str, list[str]]:
    """Validate a command string. Returns ``(executable_path, args)``.

    Raises :class:`CommandNotAllowed` with a specific reason otherwise.
    """
    text = (command or "").strip()
    if not text:
        raise CommandNotAllowed("No command given.")
    if len(text) > 500:
        raise CommandNotAllowed("Command is too long to be reviewed safely.")

    if _SHELL_METACHARS.search(text):
        raise CommandNotAllowed(
            "Command contains shell control characters (& | ; < > ` $ % or line "
            "breaks). Only a single, plain command is allowed."
        )

    parts = text.split()
    program = parts[0]
    args = parts[1:]
    base = _normalise(program)

    if base in _ALWAYS_BLOCKED:
        raise CommandNotAllowed(
            f"{program!r} is permanently blocked because it is a shell, script "
            "host, or can modify the system."
        )

    allow = {_normalise(a) for a in (allowed or [])}
    if base not in allow:
        listing = ", ".join(sorted(allow)) or "(the allow-list is empty)"
        raise CommandNotAllowed(
            f"{program!r} is not in the allowed command list. Allowed: {listing}. "
            "The list lives in config/config.json -> permissions.allowed_commands."
        )

    for arg in args:
        for pattern in _DENY_ARG_PATTERNS:
            if pattern.match(arg):
                raise CommandNotAllowed(
                    f"Argument {arg!r} would let the command execute arbitrary "
                    "input and is not allowed."
                )

    resolved = shutil.which(program)
    if resolved is None:
        raise CommandNotAllowed(f"{program!r} was not found on this system.")

    return resolved, args


def run_safe_command(command: str, timeout: int = 20) -> dict[str, Any]:
    """Run one allow-listed command and return its output.

    Requires confirmation (MODERATE level). Never uses a shell.
    """
    from agent.config import Config

    try:
        allowed = Config.load().permissions.allowed_commands
    except Exception:  # noqa: BLE001 - config problems must not bypass the list
        log.exception("could not load allowed commands; denying")
        raise CommandNotAllowed(
            "Could not load the allowed-command list from configuration."
        )

    resolved, args = check_command(command, allowed)
    limit = max(1, min(int(timeout), 60))

    log.info("running allowed command: %s %s", resolved, args)
    try:
        completed = subprocess.run(
            [resolved, *args],
            capture_output=True,
            text=True,
            timeout=limit,
            shell=False,
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            f"Command timed out after {limit}s: {' '.join([resolved, *args])}",
            "timeout",
        ) from exc
    except OSError as exc:
        raise ToolError(f"Could not run the command: {exc}", "exec_failed") from exc

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    parts = [f"$ {command}", f"exit code: {completed.returncode}"]
    if stdout:
        parts.append(stdout[:4000])
    if stderr:
        parts.append(f"stderr: {stderr[:1000]}")
    if not stdout and not stderr:
        parts.append("(no output)")

    return {
        "result": "\n".join(parts),
        "exit_code": completed.returncode,
        "stdout": stdout[:4000],
        "stderr": stderr[:1000],
    }


def list_allowed_commands() -> dict[str, Any]:
    """Show which commands the agent is permitted to run."""
    from agent.config import Config

    try:
        allowed = Config.load().permissions.allowed_commands
    except Exception as exc:  # noqa: BLE001
        return {"result": f"Could not load the allow-list: {exc}", "allowed": []}
    text = "\n".join(f"  - {c}" for c in sorted(allowed)) or "  (none)"
    return {
        "result": f"Allowed commands:\n{text}",
        "allowed": sorted(allowed),
        "always_blocked_count": len(_ALWAYS_BLOCKED),
    }


TOOLS = [
    Tool(
        name="run_safe_command",
        description=(
            "Run a single read-only command that is on the allow-list "
            "(for example 'ipconfig', 'tasklist', 'systeminfo'). Shells and "
            "system-modifying tools are always blocked. Ask the user first."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The full command line, e.g. 'ipconfig /all'",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Seconds to wait (1-60)",
                    "default": 20,
                },
            },
            "required": ["command"],
        },
        handler=run_safe_command,
        level=Level.MODERATE,
        timeout=70.0,
        confirm_template="run the command '{command}' and show its output",
        category="system",
    ),
    Tool(
        name="list_allowed_commands",
        description="List the commands this agent is allowed to run.",
        parameters={"type": "object", "properties": {}},
        handler=list_allowed_commands,
        level=Level.SAFE,
        timeout=10.0,
        category="system",
    ),
]
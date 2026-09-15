"""Tool registry: schemas, dispatch, structured results.

Every tool is declared once with the metadata the rest of the system needs:

    name, description, parameters (JSON Schema), permission level, timeout,
    handler, and whether it needs a confirmation prompt.

The registry produces the ``tools=[...]`` array for Ollama and is the ONLY entry
point for executing anything. The model never touches the OS directly -- a
requested tool name must exist in the registry or it is rejected before any code
runs.
"""

from __future__ import annotations

import inspect
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Permission levels
# --------------------------------------------------------------------------


class Level:
    """Permission levels, ordered by severity."""

    SAFE = 1
    MODERATE = 2
    DANGEROUS = 3

    NAMES = {1: "SAFE", 2: "MODERATE", 3: "DANGEROUS"}

    @classmethod
    def name(cls, level: int) -> str:
        return cls.NAMES.get(level, f"UNKNOWN({level})")


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass
class ToolResult:
    """Structured outcome of a tool call."""

    success: bool
    tool: str
    result: str = ""
    error: str = ""
    error_kind: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"success": self.success, "tool": self.tool}
        if self.success:
            out["result"] = self.result
        else:
            out["error"] = self.error
            if self.error_kind:
                out["error_kind"] = self.error_kind
        if self.data:
            out["data"] = self.data
        if self.truncated:
            out["truncated"] = True
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def ok(cls, tool: str, result: str = "", **data: Any) -> "ToolResult":
        return cls(success=True, tool=tool, result=result, data=data)

    @classmethod
    def fail(
        cls, tool: str, error: str, kind: str = "error", **data: Any
    ) -> "ToolResult":
        return cls(success=False, tool=tool, error=error, error_kind=kind, data=data)


class ToolError(Exception):
    """Raised inside a tool handler to signal a clean, expected failure."""

    def __init__(self, message: str, kind: str = "error") -> None:
        self.kind = kind
        super().__init__(message)


class ToolNotFound(ToolError):
    def __init__(self, name: str, known: Iterable[str]) -> None:
        listing = ", ".join(sorted(known)) or "(none)"
        super().__init__(f"Unknown tool {name!r}. Available tools: {listing}", "unknown_tool")


class ToolPermissionDenied(ToolError):
    """Raised when the user declines, or policy forbids, an action."""

    def __init__(self, message: str) -> None:
        super().__init__(message, "permission_denied")


# --------------------------------------------------------------------------
# Tool definition
# --------------------------------------------------------------------------


@dataclass
class Tool:
    """A single callable capability."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    level: int = Level.SAFE
    timeout: float = 30.0
    # Extra human-readable context shown at a confirmation prompt.
    confirm_template: str = ""
    # Category used for grouping in help output and diagnostics.
    category: str = "general"

    # -- schema ------------------------------------------------------------

    def to_ollama_schema(self) -> dict[str, Any]:
        """JSON-Schema description handed to Ollama."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    # -- validation --------------------------------------------------------

    def validate(self, args: dict[str, Any]) -> dict[str, Any]:
        """Coerce and validate arguments against ``self.parameters``.

        Deliberately small: checks the object shape, required keys, and performs
        light type coercion (models frequently send numbers or booleans as
        strings). Unknown keys are dropped rather than rejected, because small
        models occasionally invent extra fields and failing the whole call is
        worse than ignoring them.
        """
        if not isinstance(args, dict):
            raise ToolError(f"{self.name}: arguments must be an object", "bad_arguments")

        schema = self.parameters or {}
        props: dict[str, Any] = schema.get("properties", {}) or {}
        required: list[str] = schema.get("required", []) or []

        missing = [k for k in required if k not in args or args.get(k) in (None, "")]
        if missing:
            raise ToolError(
                f"{self.name}: missing required argument(s): {', '.join(missing)}",
                "bad_arguments",
            )

        clean: dict[str, Any] = {}
        for key, value in args.items():
            if key.startswith("_"):
                continue
            spec = props.get(key)
            if spec is None:
                continue  # ignore invented keys
            clean[key] = _coerce(value, spec.get("type", "string"), key, self.name)

        # Apply declared defaults for absent optional arguments.
        for key, spec in props.items():
            if key not in clean and "default" in spec:
                clean[key] = spec["default"]
        return clean

    def describe_call(self, args: dict[str, Any]) -> str:
        """Plain-language description of what this call will do.

        Used by the confirmation prompt so the user is told WHAT, WHERE and WHY.
        """
        if self.confirm_template:
            try:
                return self.confirm_template.format(**args)
            except (KeyError, IndexError):
                pass
        rendered = ", ".join(f"{k}={v!r}" for k, v in args.items())
        return f"{self.name}({rendered})" if rendered else f"{self.name}()"


def _coerce(value: Any, type_name: str, key: str, tool: str) -> Any:
    """Best-effort coercion of a model-supplied value to the declared type."""
    if value is None:
        return value
    try:
        if type_name == "string":
            return value if isinstance(value, str) else str(value)
        if type_name == "integer":
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, str):
                return int(float(value.strip()))
            return int(value)
        if type_name == "number":
            if isinstance(value, str):
                return float(value.strip())
            return float(value)
        if type_name == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes", "y", "on"}
            return bool(value)
        if type_name == "array":
            if isinstance(value, str):
                return [v.strip() for v in value.split(",") if v.strip()]
            if isinstance(value, (list, tuple)):
                return list(value)
            return [value]
    except (TypeError, ValueError) as exc:
        raise ToolError(
            f"{tool}: argument {key!r} must be {type_name} (got {value!r})",
            "bad_arguments",
        ) from exc
    return value


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


class ToolRegistry:
    """Holds tools and executes them safely."""

    def __init__(self, tool_result_max_chars: int = 4000) -> None:
        self._tools: dict[str, Tool] = {}
        self.tool_result_max_chars = tool_result_max_chars

    # -- registration ------------------------------------------------------

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered")
        if not tool.name.isidentifier():
            raise ValueError(
                f"Tool name {tool.name!r} must be a valid identifier "
                "(some models require this)"
            )
        self._tools[tool.name] = tool
        return tool

    def tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        level: int = Level.SAFE,
        timeout: float = 30.0,
        confirm_template: str = "",
        category: str = "general",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator form of :meth:`register`."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                Tool(
                    name=name,
                    description=description,
                    parameters=parameters or {"type": "object", "properties": {}},
                    handler=fn,
                    level=level,
                    timeout=timeout,
                    confirm_template=confirm_template,
                    category=category,
                )
            )
            return fn

        return decorator

    def register_module(self, module: Any) -> int:
        """Register every :class:`Tool` found in a module's ``TOOLS`` list."""
        count = 0
        for item in getattr(module, "TOOLS", []) or []:
            if isinstance(item, Tool):
                self.register(item)
                count += 1
        return count

    # -- lookup ------------------------------------------------------------

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFound(name, self._tools.keys())
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[Tool]:
        return [self._tools[n] for n in self.names()]

    def by_level(self, level: int) -> list[Tool]:
        return [t for t in self.all() if t.level == level]

    def schemas(self) -> list[dict[str, Any]]:
        """The full ``tools`` array for Ollama."""
        return [t.to_ollama_schema() for t in self.all()]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    # -- execution ---------------------------------------------------------

    def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Validate and run a tool, returning a structured result.

        Never raises for anticipated failures -- the model needs a result it can
        read and react to. Only truly unexpected bugs propagate.
        """
        started = time.perf_counter()

        try:
            tool = self.get(name)
        except ToolNotFound as exc:
            return ToolResult.fail(name, str(exc), exc.kind)

        try:
            clean_args = tool.validate(args)
        except ToolError as exc:
            log.warning("tool %s: bad arguments %r (%s)", name, args, exc)
            return ToolResult.fail(name, str(exc), exc.kind)

        log.info("tool call: %s %s", name, json.dumps(clean_args, ensure_ascii=False))
        try:
            raw = _call_with_timeout(tool, clean_args)
        except ToolError as exc:
            log.info("tool %s failed: %s", name, exc)
            return ToolResult.fail(name, str(exc), exc.kind)
        except TimeoutError:
            msg = f"{name} timed out after {tool.timeout:g}s"
            log.warning(msg)
            return ToolResult.fail(name, msg, "timeout")
        except Exception as exc:  # noqa: BLE001 - report, never crash the loop
            log.exception("tool %s raised", name)
            return ToolResult.fail(name, f"{type(exc).__name__}: {exc}", "exception")

        result = _normalise_result(name, raw)
        result.duration_ms = int((time.perf_counter() - started) * 1000)

        # Truncate so a single verbose tool cannot blow the context budget.
        text = result.result
        limit = self.tool_result_max_chars
        if limit and len(text) > limit:
            result.result = (
                text[:limit]
                + f"\n... [truncated: {len(text) - limit} more characters omitted]"
            )
            result.truncated = True

        return result


def _call_with_timeout(tool: Tool, args: dict[str, Any]) -> Any:
    """Invoke ``tool.handler`` with a wall-clock timeout where possible.

    Windows cannot interrupt a running thread, so the timeout is enforced by
    running the handler in a daemon thread and abandoning it. Tools that block
    forever are avoided by design (every subprocess has its own timeout).
    """
    import threading

    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = tool.handler(**args)
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller
            box["error"] = exc

    thread = threading.Thread(target=runner, name=f"tool-{tool.name}", daemon=True)
    thread.start()
    thread.join(timeout=tool.timeout)

    if thread.is_alive():
        raise TimeoutError(tool.timeout)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _normalise_result(name: str, raw: Any) -> ToolResult:
    """Turn whatever a handler returned into a :class:`ToolResult`."""
    if isinstance(raw, ToolResult):
        return raw
    if raw is None:
        return ToolResult.ok(name, "done")
    if isinstance(raw, str):
        return ToolResult.ok(name, raw)
    if isinstance(raw, dict):
        # A handler may return {"result": ..., "data": {...}} or plain data.
        if "success" in raw:
            return ToolResult(
                success=bool(raw["success"]),
                tool=name,
                result=str(raw.get("result") or ""),
                error=str(raw.get("error") or ""),
                error_kind=str(raw.get("error_kind") or ""),
                data=raw.get("data") or {},
            )
        text = raw.pop("result", None)
        if text is not None:
            return ToolResult.ok(name, str(text), **raw)
        return ToolResult.ok(name, json.dumps(raw, ensure_ascii=False), **raw)
    if isinstance(raw, (list, tuple)):
        return ToolResult.ok(
            name, "\n".join(str(x) for x in raw), count=len(raw)
        )
    return ToolResult.ok(name, str(raw))


def build_registry(tool_result_max_chars: int = 4000) -> ToolRegistry:
    """Create a registry populated with every built-in tool.

    Import failures are tolerated per-module so that, for example, a missing
    ``pyautogui`` disables the input tools without taking down file and memory
    tools.
    """
    from tools import apps, browser, filesystem, keyboard, memory_tools, mouse, powershell, system

    registry = ToolRegistry(tool_result_max_chars=tool_result_max_chars)
    for module in (apps, browser, keyboard, mouse, filesystem, system,
                   powershell, memory_tools):
        try:
            count = registry.register_module(module)
            log.debug("registered %d tools from %s", count, module.__name__)
        except Exception:  # noqa: BLE001
            log.exception("failed to register tools from %s", module.__name__)
    return registry

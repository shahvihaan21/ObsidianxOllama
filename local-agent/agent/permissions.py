"""Permission enforcement.

This module is the security boundary. It is deliberately independent of the
language model: the model only *proposes* tool calls, and every proposal passes
through :meth:`PermissionManager.check` before any handler runs.

Rules that are enforced here and nowhere else:

  * LEVEL 1 (SAFE)      auto-executes when ``auto_approve_safe`` is true
  * LEVEL 2 (MODERATE)  requires confirmation unless ``auto_approve_moderate``
  * LEVEL 3 (DANGEROUS) ALWAYS requires confirmation; this cannot be disabled
                        for destructive operations
  * A deny-list of paths (credential stores, keys, SSH, browser profiles)
    overrides everything, including an auto-approval setting.
  * Only an explicit affirmative ("yes", "y", "ok"...) approves a dangerous
    action. Hedged answers such as "maybe" or "if you think so" are DENIED.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from tools.registry import Level, Tool

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------


class Decision:
    ALLOW = "allow"          # proceed silently
    CONFIRM = "confirm"      # ask the user first
    DENY = "deny"            # refuse outright


@dataclass
class PermissionVerdict:
    """Outcome of a policy check for one proposed tool call."""

    decision: str
    reason: str = ""
    level: int = Level.SAFE
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision == Decision.ALLOW

    @property
    def needs_confirmation(self) -> bool:
        return self.decision == Decision.CONFIRM

    def prompt_text(self, tool: Tool | None = None) -> str:
        """The human-readable confirmation question (WHAT / WHERE / WHY)."""
        what = tool.describe_call(self.args) if tool else f"{self.tool}({self.args})"
        level = Level.name(self.level)
        lines = [
            f"I want to run: {what}",
            f"Risk level:     {level}",
        ]
        where = _describe_target(tool, self.args)
        if where:
            lines.append(f"Where:          {where}")
        if self.reason:
            lines.append(f"Why:            {self.reason}")
        if self.level >= Level.DANGEROUS:
            lines.append("This may be irreversible.")
        lines.append("Proceed? (yes / no)")
        return "\n".join(lines)


def _describe_target(tool: Tool | None, args: dict[str, Any]) -> str:
    """Best-effort plain-language location for a confirmation prompt."""
    if not tool:
        return ""
    for key in ("path", "target", "destination", "dest", "source", "url", "command"):
        value = args.get(key)
        if value:
            return str(value)
    if tool.category == "obsidian":
        return "your Obsidian vault"
    return ""


# --------------------------------------------------------------------------
# Explicit-confirmation parser
# --------------------------------------------------------------------------

_AFFIRMATIVE = {
    "yes", "y", "yeah", "yep", "yup", "ok", "okay", "sure", "go", "go ahead",
    "proceed", "do it", "confirm", "confirmed", "approved", "approve", "affirmative",
}

# Anything in here is treated as a refusal even if it contains "yes"-ish words.
_HEDGE_PATTERNS = (
    r"\bmaybe\b", r"\bprobably\b", r"\bperhaps\b", r"\bpossibly\b",
    r"\bi guess\b", r"\bnot sure\b", r"\bif you (think|want|feel)\b",
    r"\bwhatever you\b", r"\byour call\b", r"\bup to you\b", r"\bsure,? but\b",
)


def parse_confirmation(answer: str) -> bool:
    """Return True only for an unambiguous, explicit approval.

    "yes" approves. "maybe", "probably", "go ahead if you think it's okay" do NOT.
    An empty answer (timeout) does NOT.
    """
    if not answer:
        return False
    text = answer.strip().lower()
    if not text:
        return False

    for pattern in _HEDGE_PATTERNS:
        if re.search(pattern, text):
            return False

    # Strip politeness so "yes please" and "yes, go ahead" both work.
    core = re.sub(r"[^a-z ]", " ", text)
    words = [w for w in core.split() if w not in {"please", "thanks", "thank", "you", "the"}]
    if not words:
        return False

    joined = " ".join(words)
    if joined in _AFFIRMATIVE:
        return True
    # A leading explicit affirmative with a short tail, e.g. "yes do it".
    if words[0] in _AFFIRMATIVE and len(words) <= 4:
        return True
    return False


# --------------------------------------------------------------------------
# Protected paths
# --------------------------------------------------------------------------

# Paths that must never be read or written by a tool, regardless of approval.
# Overridable only by editing this file, not by configuration or the model.
_CREDENTIAL_MARKERS = (
    ".ssh", ".aws", ".azure", ".gnupg", ".kube",
    ".git-credentials", ".netrc", ".npmrc", ".pypirc",
    "id_rsa", "id_ed25519", "id_ecdsa",
    "credentials", "credential", "secrets", "secret",
    "passwords", "password", "passwd", ".env",
    "login data", "cookies", "keychain", "keystore", "private key",
    "ntuser.dat", "sam", "security", "system32", "syswow64",
)

# Filesystem roots that a tool may not touch at all.
_FORBIDDEN_ROOTS = (
    "c:\\windows",
    "c:\\program files",
    "c:\\program files (x86)",
)


class PathGuard:
    """Rejects access to credential stores and OS directories."""

    def __init__(self, extra_denied: list[str] | None = None) -> None:
        self.extra_denied = [Path(p).resolve() for p in (extra_denied or [])]

    def check(self, raw_path: str) -> str | None:
        """Return a refusal reason, or None when the path is acceptable."""
        if not raw_path:
            return None
        try:
            path = Path(raw_path).expanduser()
            resolved = path.resolve()
        except (OSError, ValueError) as exc:
            return f"unusable path ({exc})"

        lowered = str(resolved).lower()

        for root in _FORBIDDEN_ROOTS:
            if lowered == root or lowered.startswith(root + "\\"):
                return f"'{resolved}' is inside a protected system directory"

        for marker in _CREDENTIAL_MARKERS:
            # Match as a whole path segment, so "security_notes.md" is fine.
            if re.search(rf"(^|[\\/]){re.escape(marker)}([\\/]|$)", lowered):
                return (
                    f"'{resolved}' looks like a credential or OS store and is "
                    "never accessible to the agent"
                )

        for denied in self.extra_denied:
            try:
                if resolved == denied or denied in resolved.parents:
                    return f"'{resolved}' is in a user-configured denied path"
            except (OSError, ValueError):
                continue

        # Also scan the file name itself for obvious secrets.
        name = resolved.name.lower()
        if re.match(r"^\.?env(\.|$)", name) or name.endswith((".pem", ".key", ".pfx", ".p12")):
            return f"'{resolved}' looks like a secret file and is not accessible"

        return None


# --------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------


class PermissionManager:
    """Decides whether a proposed tool call may run, and asks when unsure.

    ``asker`` is injected so the CLI, the voice loop, and the tests can each
    supply their own confirmation channel.
    """

    def __init__(
        self,
        config: Any,
        registry: Any,
        asker: Callable[[str], str] | None = None,
        auto_approve_moderate: bool | None = None,
    ) -> None:
        perms = getattr(config, "permissions", config)
        self.auto_approve_safe = bool(getattr(perms, "auto_approve_safe", True))
        self.auto_approve_moderate = (
            bool(getattr(perms, "auto_approve_moderate", False))
            if auto_approve_moderate is None
            else bool(auto_approve_moderate)
        )
        # Dangerous is intentionally NOT configurable to true.
        self.auto_approve_dangerous = False
        self.guard = PathGuard(list(getattr(perms, "denied_paths", []) or []))
        self.registry = registry
        self.asker = asker
        self.pending: PermissionVerdict | None = None

    # -- policy ------------------------------------------------------------

    def check(self, tool: Tool, args: dict[str, Any]) -> PermissionVerdict:
        """Classify a proposed call without asking the user yet."""
        # 1. Hard deny: protected paths win over every other rule.
        for key in ("path", "target", "source", "destination", "dest", "folder"):
            raw = args.get(key)
            if isinstance(raw, str) and raw:
                reason = self.guard.check(raw)
                if reason:
                    return PermissionVerdict(
                        decision=Decision.DENY,
                        reason=reason,
                        level=Level.DANGEROUS,
                        tool=tool.name,
                        args=args,
                    )

        # 2. Tool-declared hard-deny (a tool may veto itself for some inputs).
        veto = getattr(tool.handler, "deny_reason", None)
        if callable(veto):
            reason = veto(**args)
            if reason:
                return PermissionVerdict(
                    decision=Decision.DENY,
                    reason=reason,
                    level=Level.DANGEROUS,
                    tool=tool.name,
                    args=args,
                )

        # 3. Level-based policy.
        if tool.level >= Level.DANGEROUS:
            return PermissionVerdict(
                decision=Decision.CONFIRM,
                reason="this action is irreversible or affects the system",
                level=tool.level,
                tool=tool.name,
                args=args,
            )
        if tool.level == Level.MODERATE:
            if self.auto_approve_moderate:
                return PermissionVerdict(Decision.ALLOW, "auto-approved (moderate)", tool.level, tool.name, args)
            return PermissionVerdict(
                Decision.CONFIRM,
                "this modifies files or memory",
                tool.level,
                tool.name,
                args,
            )
        if self.auto_approve_safe:
            return PermissionVerdict(Decision.ALLOW, "safe", tool.level, tool.name, args)
        return PermissionVerdict(Decision.CONFIRM, "confirmation enabled for safe tools", tool.level, tool.name, args)

    def request(self, tool: Tool, args: dict[str, Any]) -> PermissionVerdict:
        """Check policy and, when required, ask the user for a decision.

        Returns a verdict whose ``decision`` is ALLOW or DENY -- CONFIRM is
        always resolved before returning.
        """
        verdict = self.check(tool, args)

        if verdict.decision != Decision.CONFIRM:
            log.info(
                "permission %s for %s (%s)",
                verdict.decision, tool.name, verdict.reason or "-",
            )
            return verdict

        if self.asker is None:
            verdict.decision = Decision.DENY
            verdict.reason = "no confirmation channel available; refused by default"
            log.warning("permission denied (no asker) for %s", tool.name)
            return verdict

        question = verdict.prompt_text(tool)
        self.pending = verdict
        log.info("permission requested for %s (level %s)", tool.name, Level.name(verdict.level))
        try:
            answer = self.asker(question)
        except Exception:  # noqa: BLE001 - a broken asker must not crash a run
            log.exception("confirmation channel raised")
            answer = ""

        if parse_confirmation(answer or ""):
            verdict.decision = Decision.ALLOW
            verdict.reason = "confirmed by user"
            log.info("permission granted by user for %s", tool.name)
        else:
            verdict.decision = Decision.DENY
            verdict.reason = "not confirmed by user"
            log.info("permission denied by user for %s (answer=%r)", tool.name, answer)
        self.pending = None
        return verdict

    # -- reporting ---------------------------------------------------------

    def summary(self) -> str:
        return (
            "permissions: "
            f"safe={'auto' if self.auto_approve_safe else 'ask'} "
            f"moderate={'auto' if self.auto_approve_moderate else 'ask'} "
            "dangerous=always-ask"
        )

"""Guardrails for AI agents that call tools.

The model suggests, deterministic code decides what is allowed.

Every tool call goes through GuardedToolbox.call(), which:
  1. validates argument names and types against a schema,
  2. runs custom validators (hard limits that the prompt cannot override),
  3. keeps writes in dry-run mode on request (returns a proposal, runs nothing),
  4. requires explicit approval for writes that a policy marks as risky,
  5. records every attempt in an audit log, including rejected ones.

Standard library only.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class Rejected(Exception):
    """Raised by a validator to block a call with a human-readable reason."""


@dataclass
class Tool:
    name: str
    func: Callable[..., Any]
    schema: Dict[str, type]
    write: bool = False
    validators: List[Callable[[Dict[str, Any]], None]] = field(default_factory=list)
    needs_approval: Optional[Callable[[Dict[str, Any]], bool]] = None


@dataclass
class Result:
    status: str  # executed | rejected | proposed | pending_approval
    value: Any = None
    reason: str = ""


class GuardedToolbox:
    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self.audit: List[Dict[str, Any]] = []

    def register(self, name: str, func: Callable[..., Any], schema: Dict[str, type], *,
                 write: bool = False,
                 validators: Optional[List[Callable[[Dict[str, Any]], None]]] = None,
                 needs_approval: Optional[Callable[[Dict[str, Any]], bool]] = None) -> None:
        self._tools[name] = Tool(name, func, schema, write, validators or [], needs_approval)

    def call(self, name: str, args: Dict[str, Any], *, dry_run: bool = False,
             approved: bool = False) -> Result:
        tool = self._tools.get(name)
        if tool is None:
            return self._log(name, args, Result("rejected", reason="unknown tool"))

        problem = self._check_schema(tool, args)
        if problem:
            return self._log(name, args, Result("rejected", reason=problem))

        try:
            for validate in tool.validators:
                validate(args)
        except Rejected as exc:
            return self._log(name, args, Result("rejected", reason=str(exc)))

        if tool.write and dry_run:
            return self._log(name, args, Result("proposed", value=dict(args)))

        if tool.write and tool.needs_approval and tool.needs_approval(args) and not approved:
            return self._log(name, args, Result("pending_approval", value=dict(args),
                                                reason="needs human approval"))

        value = tool.func(**args)
        return self._log(name, args, Result("executed", value=value))

    @staticmethod
    def _check_schema(tool: Tool, args: Dict[str, Any]) -> str:
        missing = [k for k in tool.schema if k not in args]
        if missing:
            return "missing arguments: " + ", ".join(sorted(missing))
        extra = [k for k in args if k not in tool.schema]
        if extra:
            return "unexpected arguments: " + ", ".join(sorted(extra))
        for key, expected in tool.schema.items():
            value = args[key]
            if isinstance(value, bool) and expected is not bool:
                return f"argument '{key}' must be {expected.__name__}"
            if not isinstance(value, expected):
                return f"argument '{key}' must be {expected.__name__}"
        return ""

    def _log(self, name: str, args: Dict[str, Any], result: Result) -> Result:
        self.audit.append({
            "ts": round(time.time(), 3),
            "tool": name,
            "args": args,
            "status": result.status,
            "reason": result.reason,
        })
        return result

    def audit_jsonl(self) -> str:
        return "\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in self.audit)


def max_change_pct(field_name: str, current: float, limit_pct: float) -> Callable[[Dict[str, Any]], None]:
    """Validator: reject if a numeric value moves more than limit_pct from current."""
    def _validate(args: Dict[str, Any]) -> None:
        new = float(args[field_name])
        if current == 0:
            return
        change = abs(new - current) / abs(current) * 100
        if change > limit_pct:
            raise Rejected(f"{field_name} change of {change:.0f}% exceeds the {limit_pct:.0f}% limit")
    return _validate


def between(field_name: str, low: float, high: float) -> Callable[[Dict[str, Any]], None]:
    """Validator: reject values outside [low, high]."""
    def _validate(args: Dict[str, Any]) -> None:
        value = args[field_name]
        if not (low <= value <= high):
            raise Rejected(f"{field_name}={value} is outside the allowed range {low}..{high}")
    return _validate

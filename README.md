# agent-guardrails

Guardrails for AI agents that call tools. The model suggests, deterministic code decides what is allowed.

A better prompt lowers the odds of a bad action. It does not remove the risk. If an agent can change a budget, message a customer or write to a CRM, the limits belong in code that the model cannot talk its way around.

## What it does

Every tool call goes through `GuardedToolbox.call()`:

1. **Schema check.** Missing, extra or wrongly typed arguments are rejected before anything runs.
2. **Hard limits.** Validators raise `Rejected` with a readable reason (value out of range, change above a percentage).
3. **Dry run.** With `dry_run=True` a write returns a proposal and executes nothing.
4. **Approval gate.** Writes that a policy marks as risky return `pending_approval` until a human re-submits with `approved=True`.
5. **Audit log.** Every attempt is recorded, including rejected ones, so you can answer "why did it do that?" a week later.

Standard library only, Python 3.9+.

## Example

```python
from agent_guardrails import GuardedToolbox, between, max_change_pct

toolbox = GuardedToolbox()
toolbox.register(
    "set_daily_budget",
    set_daily_budget,
    schema={"campaign_id": str, "daily_budget": float},
    write=True,
    validators=[between("daily_budget", 10.0, 500.0),
                max_change_pct("daily_budget", current=100.0, limit_pct=50)],
    needs_approval=lambda a: abs(a["daily_budget"] - 100.0) > 20.0,
)

result = toolbox.call("set_daily_budget", {"campaign_id": "c-1", "daily_budget": 135.0})
print(result.status)  # pending_approval
```

Run the full example and the tests:

```
python example.py
python -m unittest -v
```

## Design notes

- Validators are plain functions, so they are easy to test and review.
- A rejected call returns a reason the agent can read and retry with, instead of throwing a stack trace into the loop.
- Reads need no approval; only tools registered with `write=True` are gated.
- For irreversible actions, keep a human in the loop. This library makes that gate explicit rather than implicit.

## License

MIT

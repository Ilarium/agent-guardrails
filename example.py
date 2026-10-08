"""Example: an ad-budget agent whose proposals are checked by code, not by the prompt."""
from agent_guardrails import GuardedToolbox, between, max_change_pct

CAMPAIGN = {"id": "c-1", "daily_budget": 100.0}


def set_daily_budget(campaign_id: str, daily_budget: float) -> str:
    CAMPAIGN["daily_budget"] = daily_budget
    return f"{campaign_id} budget set to {daily_budget}"


toolbox = GuardedToolbox()
toolbox.register(
    "set_daily_budget",
    set_daily_budget,
    schema={"campaign_id": str, "daily_budget": float},
    write=True,
    validators=[
        between("daily_budget", 10.0, 500.0),
        max_change_pct("daily_budget", current=CAMPAIGN["daily_budget"], limit_pct=50),
    ],
    # changes above 20% need a human to confirm
    needs_approval=lambda a: abs(a["daily_budget"] - CAMPAIGN["daily_budget"]) / CAMPAIGN["daily_budget"] > 0.2,
)

# These calls stand in for what a model might decide.
proposals = [
    {"campaign_id": "c-1", "daily_budget": 110.0},   # small change: runs
    {"campaign_id": "c-1", "daily_budget": 135.0},   # risky change: waits for approval
    {"campaign_id": "c-1", "daily_budget": 190.0},   # above the 50% limit: rejected
    {"campaign_id": "c-1", "daily_budget": 5000.0},  # outside the allowed range: rejected
]

for proposal in proposals:
    result = toolbox.call("set_daily_budget", proposal)
    print(proposal["daily_budget"], "->", result.status, result.reason)

print("\nAudit log:")
print(toolbox.audit_jsonl())

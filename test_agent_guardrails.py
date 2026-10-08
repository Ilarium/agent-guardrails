import unittest

from agent_guardrails import GuardedToolbox, between, max_change_pct


def make_toolbox(state):
    def set_budget(value: float) -> float:
        state["budget"] = value
        return value

    toolbox = GuardedToolbox()
    toolbox.register(
        "set_budget",
        set_budget,
        schema={"value": float},
        write=True,
        validators=[between("value", 10, 500), max_change_pct("value", current=100, limit_pct=50)],
        needs_approval=lambda a: abs(a["value"] - 100) > 20,
    )
    return toolbox


class GuardrailTests(unittest.TestCase):
    def setUp(self):
        self.state = {"budget": 100.0}
        self.toolbox = make_toolbox(self.state)

    def test_small_change_executes(self):
        result = self.toolbox.call("set_budget", {"value": 110.0})
        self.assertEqual(result.status, "executed")
        self.assertEqual(self.state["budget"], 110.0)

    def test_out_of_range_is_rejected_and_not_run(self):
        result = self.toolbox.call("set_budget", {"value": 5000.0})
        self.assertEqual(result.status, "rejected")
        self.assertEqual(self.state["budget"], 100.0)

    def test_large_change_is_rejected_by_percentage_limit(self):
        result = self.toolbox.call("set_budget", {"value": 400.0})
        self.assertEqual(result.status, "rejected")
        self.assertIn("limit", result.reason)

    def test_risky_change_waits_for_approval(self):
        result = self.toolbox.call("set_budget", {"value": 140.0})
        self.assertEqual(result.status, "pending_approval")
        self.assertEqual(self.state["budget"], 100.0)
        approved = self.toolbox.call("set_budget", {"value": 140.0}, approved=True)
        self.assertEqual(approved.status, "executed")
        self.assertEqual(self.state["budget"], 140.0)

    def test_dry_run_returns_proposal_without_running(self):
        result = self.toolbox.call("set_budget", {"value": 110.0}, dry_run=True)
        self.assertEqual(result.status, "proposed")
        self.assertEqual(self.state["budget"], 100.0)

    def test_schema_errors_are_rejected(self):
        self.assertEqual(self.toolbox.call("set_budget", {}).status, "rejected")
        self.assertEqual(self.toolbox.call("set_budget", {"value": "110"}).status, "rejected")
        self.assertEqual(self.toolbox.call("set_budget", {"value": 110.0, "x": 1}).status, "rejected")
        self.assertEqual(self.toolbox.call("set_budget", {"value": True}).status, "rejected")
        self.assertEqual(self.toolbox.call("nope", {}).status, "rejected")

    def test_every_attempt_is_audited(self):
        self.toolbox.call("set_budget", {"value": 110.0})
        self.toolbox.call("set_budget", {"value": 5000.0})
        statuses = [entry["status"] for entry in self.toolbox.audit]
        self.assertEqual(statuses, ["executed", "rejected"])


if __name__ == "__main__":
    unittest.main()

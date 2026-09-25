import tempfile
import unittest
from pathlib import Path

from servicedesk_demo import Action, Actor, DemoAdapter, JsonlAudit, State, Workflow


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.adapter = DemoAdapter()
        self.workflow = Workflow(self.adapter, JsonlAudit(Path(self.temp.name) / "audit.jsonl"))
        self.requester = Actor("user-1", "Demo User", ("requester",))
        self.tech = Actor("tech-1", "Demo Technician", ("it_support",))

    def tearDown(self):
        self.temp.cleanup()

    def test_side_effect_requires_approval(self):
        item = self.workflow.draft(Action.CREATE_TICKET, {"subject": "Demo"}, self.requester)
        with self.assertRaises(ValueError):
            self.workflow.execute(item.id, self.tech)
        self.workflow.request_approval(item.id, self.requester)
        self.workflow.approve(item.id, self.tech)
        executed = self.workflow.execute(item.id, self.tech)
        self.assertEqual(executed.state, State.EXECUTED)
        self.assertEqual(executed.result["status"], "simulated")

    def test_requester_cannot_approve_write(self):
        item = self.workflow.draft(Action.ADD_REPLY, {"ticket": "DEMO-1", "text": "Example"}, self.requester)
        self.workflow.request_approval(item.id, self.requester)
        with self.assertRaises(PermissionError):
            self.workflow.approve(item.id, self.requester)

    def test_adapter_is_idempotent(self):
        first = self.adapter.execute(Action.CREATE_TICKET, {}, "same-key")
        second = self.adapter.execute(Action.CREATE_TICKET, {}, "same-key")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

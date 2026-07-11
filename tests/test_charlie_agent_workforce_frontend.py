import unittest
from pathlib import Path


class CharlieAgentWorkforceFrontendTests(unittest.TestCase):
    def test_full_page_workforce_contract(self):
        template = Path("templates/charlie-agents.html").read_text(encoding="utf-8")
        script = Path("static/js/charlieAgentWorkforce.js").read_text(encoding="utf-8")
        app = Path("app.py").read_text(encoding="utf-8")

        self.assertIn('@app.route("/charlie-agents")', app)
        self.assertIn('id="agentList"', template)
        self.assertIn('id="systemMap"', template)
        self.assertIn('id="detailBody"', template)
        self.assertIn("/api/charlie/agent-workforce", script)
        self.assertIn("Not measured", script)
        self.assertNotIn("setInterval(() => { state.packet = null", script)


if __name__ == "__main__":
    unittest.main()

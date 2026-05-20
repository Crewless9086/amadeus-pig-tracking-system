import unittest

from app import app


class PrintSheetsRouteTests(unittest.TestCase):
    def test_print_sheets_route_loads(self):
        app.testing = True
        client = app.test_client()

        response = client.get("/print-sheets")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Weekly Weight Capture Sheet", response.data)
        self.assertIn(b"printSheets.js", response.data)


if __name__ == "__main__":
    unittest.main()

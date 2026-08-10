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

    def test_mating_litter_record_route_loads_in_afrikaans(self):
        app.testing = True
        client = app.test_client()

        response = client.get("/paring-werpselrekord")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Parings- en Werpselrekord".encode("utf-8"), response.data)
        self.assertIn("Eerste behandeling".encode("utf-8"), response.data)
        self.assertIn("Vrektes en notas".encode("utf-8"), response.data)
        self.assertIn(b"paringWerpselrekord.js", response.data)

    def test_expected_farrowing_dates_print_route_loads_in_afrikaans(self):
        app.testing = True
        client = app.test_client()

        response = client.get("/verwagte-jongdatums")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Verwagte Jong Datums".encode("utf-8"), response.data)
        self.assertIn("Sog".encode("utf-8"), response.data)
        self.assertIn("Beer".encode("utf-8"), response.data)
        self.assertIn(b"verwagteJongdatums.js", response.data)


if __name__ == "__main__":
    unittest.main()

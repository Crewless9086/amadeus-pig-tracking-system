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
        self.assertIn(b"KLAAR", response.data)
        self.assertIn("Paringshok".encode("utf-8"), response.data)
        self.assertIn("Jonghok / Kraamhok".encode("utf-8"), response.data)
        self.assertNotIn(b"Huidige hok", response.data)
        self.assertIn("Verwagte speendatum".encode("utf-8"), response.data)
        self.assertIn("Soggies".encode("utf-8"), response.data)
        self.assertIn("Kommentaar".encode("utf-8"), response.data)
        self.assertIn(b'pwr_header_sow', response.data)
        self.assertIn(b'pwr_weaned_male_total', response.data)
        self.assertIn("Terug na Litters".encode("utf-8"), response.data)
        self.assertIn(b'pwr_back_link', response.data)
        self.assertIn(b'pwr_mating_id', response.data)
        self.assertIn(b'pwr_mating_from', response.data)
        self.assertIn(b'pwr_mating_to', response.data)
        self.assertNotIn(b'pwr_mating_method', response.data)
        self.assertIn(b'pwr_expected_from', response.data)
        self.assertIn(b'pwr_expected_to', response.data)
        self.assertIn(b"paringWerpselrekord.js", response.data)
        self.assertNotIn(b"MAT-2026-8EFC7F", response.data)
        self.assertNotIn(b"Bonnie", response.data)

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

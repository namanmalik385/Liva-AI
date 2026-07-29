import unittest

from services.biomarker_service import metric_status, report_to_dict


class BiomarkerServiceTests(unittest.TestCase):
    def test_report_mapping_includes_ggt_without_shifting_other_fields(self):
        report = report_to_dict((
            30,
            35,
            25,
            0.8,
            4.2,
            220,
            1.0,
            12,
            4,
            0,
            0,
            0.3,
            1.1,
            "Normal",
            "2026-07-28 09:00:00",
        ))

        self.assertEqual(report["ast"], 30)
        self.assertEqual(report["alt"], 35)
        self.assertEqual(report["ggt"], 25)
        self.assertEqual(report["bilirubin"], 0.8)
        self.assertEqual(report["date_added"], "2026-07-28 09:00:00")

    def test_ggt_status_is_available(self):
        self.assertEqual(metric_status("ggt", 25), "normal")
        self.assertEqual(metric_status("ggt", 60), "elevated")


if __name__ == "__main__":
    unittest.main()

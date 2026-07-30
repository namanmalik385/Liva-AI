import unittest

from services.biomarker_service import (
    build_current_report_metrics,
    build_dashboard_metrics,
    metric_response_value,
    metric_status,
    report_to_dict,
)


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

    def test_hepatitis_values_and_statuses_use_clinical_labels(self):
        self.assertEqual(metric_response_value("hbsag", 0), "-ve")
        self.assertEqual(metric_status("hbsag", 0), "non-reactive")
        self.assertEqual(metric_response_value("anti_hcv", 1), "+ve")
        self.assertEqual(metric_status("anti_hcv", 1), "reactive")
        self.assertIsNone(metric_response_value("hbsag", None))
        self.assertIsNone(metric_status("hbsag", None))

    def test_dashboard_formats_hepatitis_without_changing_trends(self):
        result = build_dashboard_metrics([
            {"hbsag": 1, "anti_hcv": 0},
            {"hbsag": 0, "anti_hcv": 1},
        ])

        self.assertEqual(result["hbsag"], {
            "score": "-ve",
            "status": "non-reactive",
            "trend": "changed",
        })
        self.assertEqual(result["anti_hcv"], {
            "score": "+ve",
            "status": "reactive",
            "trend": "changed",
        })

    def test_report_analysis_formats_hepatitis_values_and_statuses(self):
        result = build_current_report_metrics(
            {"hbsag": 0, "anti_hcv": 1},
            {"hbsag": 1, "anti_hcv": 1},
        )

        self.assertEqual(result["hbsag"]["value"], "-ve")
        self.assertEqual(result["hbsag"]["status"], "non-reactive")
        self.assertEqual(result["hbsag"]["trend"], "changed")
        self.assertEqual(result["anti_hcv"]["value"], "+ve")
        self.assertEqual(result["anti_hcv"]["status"], "reactive")
        self.assertEqual(result["anti_hcv"]["trend"], "stable")


if __name__ == "__main__":
    unittest.main()

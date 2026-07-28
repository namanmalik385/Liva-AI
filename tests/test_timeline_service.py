from datetime import datetime
import importlib
import sys
import types
import unittest


USER_ROW = (
    "Test User",
    35,
    "other",
    70,
    170,
    24.2,
    0,
    0,
    0,
    0,
    "moderately active",
    "2-4 times per week",
    "none",
    "never",
)


def _report(report_id, date_added, alt, ast=30, ggt=25):
    return {
        "id": report_id,
        "ast": ast,
        "alt": alt,
        "ggt": ggt,
        "bilirubin": 0.8,
        "albumin": 4.2,
        "platelets": 220,
        "inr": 1.0,
        "pt": 12,
        "afp": 4,
        "hbsag": 0,
        "anti_hcv": 0,
        "apri": None,
        "fib4": None,
        "ultrasound_prediction": None,
        "date_added": date_added,
    }


class TimelineServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_module = sys.modules.get("db")
        if db_module is None:
            db_module = types.ModuleType("db")
            sys.modules["db"] = db_module
        if not hasattr(db_module, "get_connection"):
            db_module.get_connection = lambda: None
        if not hasattr(db_module, "get_timeline_records"):
            db_module.get_timeline_records = lambda _user_id: None

        sys.modules.pop("services.timeline_service", None)
        cls.timeline = importlib.import_module(
            "services.timeline_service"
        )

    def setUp(self):
        self.reports = [
            _report(1, "2025-06-10 09:00:00", 110),
            _report(2, "2026-06-20 09:00:00", 80),
            _report(3, "2026-07-15 09:00:00", 100),
            _report(4, "2026-07-23 09:00:00", 100),
            _report(5, "2026-07-28 09:00:00", 30),
        ]
        self.timeline.get_timeline_records = lambda _user_id: {
            "user": USER_ROW,
            "reports": self.reports,
        }
        self.now = datetime(2026, 7, 28, 12, 0, 0)

    def test_weekly_returns_only_four_ordered_weeks(self):
        result = self.timeline.build_timeline(7, "weekly", self.now)

        self.assertEqual(result["selected_period"], "weekly")
        self.assertEqual(len(result["health_history"]), 4)
        self.assertEqual(
            [item["period"] for item in result["health_history"]],
            ["Week 1", "Week 2", "Week 3", "Week 4"],
        )
        self.assertEqual(result["biomarkers"]["alt"]["value"], 30)
        self.assertEqual(result["biomarkers"]["alt"]["trend"], "-70%")
        self.assertTrue(result["health_trend"].startswith("+"))

    def test_monthly_returns_all_months_of_current_year(self):
        result = self.timeline.build_timeline(7, "monthly", self.now)

        self.assertEqual(len(result["health_history"]), 12)
        self.assertEqual(result["health_history"][0]["period"], "January")
        self.assertEqual(result["health_history"][-1]["period"], "December")
        july = result["health_history"][6]
        self.assertEqual(july["biomarkers"]["alt"]["value"], 30)
        self.assertEqual(july["biomarkers"]["alt"]["trend"], "-62.5%")

    def test_yearly_returns_every_year_with_available_data(self):
        result = self.timeline.build_timeline(7, "yearly", self.now)

        self.assertEqual(
            [item["period"] for item in result["health_history"]],
            ["2025", "2026"],
        )
        self.assertEqual(result["biomarkers"]["alt"]["value"], 30)
        self.assertEqual(result["biomarkers"]["alt"]["trend"], "-72.7%")


if __name__ == "__main__":
    unittest.main()

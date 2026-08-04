from datetime import datetime, timezone
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


def _report(fib4, date_added):
    return (
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
        fib4,
        "Normal",
        date_added,
    )


class AchievementServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_module = sys.modules.get("db")
        if db_module is None:
            db_module = types.ModuleType("db")
            sys.modules["db"] = db_module

        required_stubs = {
            "get_connection": lambda: None,
            "get_dashboard_records": lambda _user_id: None,
            "get_user_achievement_unlocks": lambda _user_id: {},
            "unlock_user_achievements": lambda *_args: None,
        }
        for name, stub in required_stubs.items():
            if not hasattr(db_module, name):
                setattr(db_module, name, stub)

        sys.modules.pop("services.achievement_service", None)
        cls.achievements = importlib.import_module(
            "services.achievement_service"
        )

    def setUp(self):
        self.unlocks = {}
        self.reports = []
        unlocked_at = datetime(
            2026,
            7,
            30,
            12,
            0,
            tzinfo=timezone.utc,
        )

        self.achievements.get_dashboard_records = lambda _user_id: {
            "user": USER_ROW,
            "reports": self.reports,
        }
        self.achievements.get_user_achievement_unlocks = (
            lambda _user_id: dict(self.unlocks)
        )

        def unlock(_user_id, keys):
            for key in keys:
                self.unlocks.setdefault(key, unlocked_at)

        self.achievements.unlock_user_achievements = unlock

    def _by_title(self, result):
        return {
            item["title"]: item
            for item in result["achievements"]
        }

    def test_new_user_has_four_locked_achievements(self):
        result = self.achievements.build_achievements(7)

        self.assertEqual(len(result["achievements"]), 4)
        self.assertTrue(
            all(
                item["is_unlocked"] is False
                and item["date"] is None
                and set(item) == {"title", "date", "is_unlocked"}
                for item in result["achievements"]
            )
        )

    def test_first_report_unlocks_first_report_achievement(self):
        self.reports = [
            _report(1.1, "2026-07-30 09:00:00"),
        ]

        result = self.achievements.build_achievements(7)
        by_title = self._by_title(result)

        self.assertTrue(by_title["First Report Uploaded"]["is_unlocked"])
        self.assertEqual(
            by_title["First Report Uploaded"]["date"],
            "July 2026",
        )
        self.assertFalse(by_title["Trend Tracker"]["is_unlocked"])
        self.assertFalse(by_title["Score Improved"]["is_unlocked"])

    def test_follow_up_and_historical_improvement_unlock_achievements(self):
        self.reports = [
            _report(3.0, "2026-06-30 09:00:00"),
            _report(1.1, "2026-07-30 09:00:00"),
        ]

        result = self.achievements.build_achievements(7)
        by_title = self._by_title(result)

        self.assertTrue(by_title["First Report Uploaded"]["is_unlocked"])
        self.assertTrue(by_title["Trend Tracker"]["is_unlocked"])
        self.assertTrue(by_title["Score Improved"]["is_unlocked"])

    def test_successful_insights_view_unlocks_insights_explorer(self):
        self.achievements.record_insights_explorer(7)

        result = self.achievements.build_achievements(7)
        insight = self._by_title(result)["Insights Explorer"]

        self.assertTrue(insight["is_unlocked"])
        self.assertEqual(insight["date"], "July 2026")


if __name__ == "__main__":
    unittest.main()

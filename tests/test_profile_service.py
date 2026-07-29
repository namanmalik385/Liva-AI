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


def _report(**overrides):
    values = {
        "ast": 30,
        "alt": 35,
        "ggt": 25,
        "bilirubin": 0.8,
        "albumin": 4.2,
        "platelets": 220,
        "inr": 1.0,
        "pt": 12,
        "afp": 4,
        "hbsag": 0,
        "anti_hcv": 0,
        "apri": 0.3,
        "fib4": 1.1,
        "ultrasound_prediction": "Normal",
        "date_added": "2026-07-15 09:00:00",
    }
    values.update(overrides)
    return (
        values["ast"],
        values["alt"],
        values["ggt"],
        values["bilirubin"],
        values["albumin"],
        values["platelets"],
        values["inr"],
        values["pt"],
        values["afp"],
        values["hbsag"],
        values["anti_hcv"],
        values["apri"],
        values["fib4"],
        values["ultrasound_prediction"],
        values["date_added"],
    )


class ProfileServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_module = sys.modules.get("db")
        if db_module is None:
            db_module = types.ModuleType("db")
            sys.modules["db"] = db_module
        if not hasattr(db_module, "get_connection"):
            db_module.get_connection = lambda: None
        if not hasattr(db_module, "get_profile_summary_records"):
            db_module.get_profile_summary_records = lambda _user_id: None
        if not hasattr(db_module, "update_user_personal_info"):
            db_module.update_user_personal_info = (
                lambda _user_id, _updates: None
            )

        sys.modules.pop("services.profile_service", None)
        cls.profile = importlib.import_module(
            "services.profile_service"
        )

    def test_profile_uses_latest_report_and_upload_count(self):
        self.profile.get_profile_summary_records = lambda _user_id: {
            "user": USER_ROW,
            "latest_report": _report(),
            "total_uploaded_reports": 7,
            "latest_upload_date": "2026-07-15 09:00:00",
        }

        result = self.profile.build_profile(7)

        self.assertEqual(result["full_name"], "Test User")
        self.assertEqual(result["age"], 35)
        self.assertEqual(result["gender"], "other")
        self.assertEqual(result["health_score"], 100)
        self.assertEqual(result["total_uploaded_reports"], 7)
        self.assertEqual(result["liver_health_status"], "Healthy")
        self.assertEqual(result["biomarkers_status"], "Stable")
        self.assertEqual(result["month_year"], "July 2026")

    def test_critical_biomarker_is_reported(self):
        self.profile.get_profile_summary_records = lambda _user_id: {
            "user": USER_ROW,
            "latest_report": _report(bilirubin=4.2),
            "total_uploaded_reports": 2,
            "latest_upload_date": "2026-07-15 09:00:00",
        }

        result = self.profile.build_profile(7)

        self.assertEqual(result["biomarkers_status"], "Critical")

    def test_missing_report_uses_profile_baseline_and_current_month(self):
        self.profile.get_profile_summary_records = lambda _user_id: {
            "user": USER_ROW,
            "latest_report": None,
            "total_uploaded_reports": 0,
            "latest_upload_date": None,
        }

        result = self.profile.build_profile(
            7,
            now=datetime(2026, 8, 1, 12, 0, 0),
        )

        self.assertEqual(result["health_score"], 100)
        self.assertEqual(result["biomarkers_status"], "Monitor")
        self.assertEqual(result["month_year"], "August 2026")

    def test_incomplete_core_biomarkers_need_monitoring(self):
        self.profile.get_profile_summary_records = lambda _user_id: {
            "user": USER_ROW,
            "latest_report": _report(platelets=None),
            "total_uploaded_reports": 1,
            "latest_upload_date": "2026-07-15 09:00:00",
        }

        result = self.profile.build_profile(7)

        self.assertEqual(result["biomarkers_status"], "Monitor")

    def test_liver_health_status_bands(self):
        self.assertEqual(
            self.profile._liver_health_status(80),
            "Healthy",
        )
        self.assertEqual(
            self.profile._liver_health_status(60),
            "Needs Improvement",
        )
        self.assertEqual(
            self.profile._liver_health_status(40),
            "At Risk",
        )
        self.assertEqual(
            self.profile._liver_health_status(39),
            "Critical",
        )

    def test_personal_info_update_is_partial_and_normalized(self):
        updates = self.profile.validate_personal_info_update({
            "full_name": "  Updated   User  ",
            "gender": " FEMALE ",
        })

        self.assertEqual(updates, {
            "full_name": "Updated User",
            "gender": "female",
        })
        self.assertNotIn("age", updates)

    def test_personal_info_update_validates_age(self):
        self.assertEqual(
            self.profile.validate_personal_info_update({"age": "42"}),
            {"age": 42},
        )

        with self.assertRaises(self.profile.ProfileValidationError):
            self.profile.validate_personal_info_update({"age": 12})
        with self.assertRaises(self.profile.ProfileValidationError):
            self.profile.validate_personal_info_update({"age": 25.5})

    def test_personal_info_update_rejects_unknown_fields(self):
        with self.assertRaises(self.profile.ProfileValidationError):
            self.profile.validate_personal_info_update({
                "email": "new@example.com",
            })

    def test_update_returns_refreshed_full_profile(self):
        captured = {}

        def update_user(user_id, updates):
            captured["user_id"] = user_id
            captured["updates"] = updates
            return {
                "full_name": "Updated User",
                "age": 36,
                "gender": "other",
            }

        updated_user = (
            "Updated User",
            36,
            "other",
            *USER_ROW[3:],
        )
        self.profile.update_user_personal_info = update_user
        self.profile.get_profile_summary_records = lambda _user_id: {
            "user": updated_user,
            "latest_report": _report(),
            "total_uploaded_reports": 7,
            "latest_upload_date": "2026-07-15 09:00:00",
        }

        result = self.profile.update_personal_info(
            7,
            {"full_name": "Updated User", "age": 36},
        )

        self.assertEqual(captured["user_id"], 7)
        self.assertEqual(captured["updates"], {
            "full_name": "Updated User",
            "age": 36,
        })
        self.assertEqual(result["full_name"], "Updated User")
        self.assertEqual(result["age"], 36)


if __name__ == "__main__":
    unittest.main()

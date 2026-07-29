from datetime import datetime, timezone
import importlib
import sys
import types
import unittest


class SupportServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_module = sys.modules.get("db")
        if db_module is None:
            db_module = types.ModuleType("db")
            sys.modules["db"] = db_module
        if not hasattr(db_module, "create_support_ticket"):
            db_module.create_support_ticket = (
                lambda _user_id, _subject, _description: None
            )

        sys.modules.pop("services.support_service", None)
        cls.support = importlib.import_module(
            "services.support_service"
        )

    def test_valid_request_is_normalized(self):
        result = self.support.validate_support_request({
            "subject": "  application ISSUE ",
            "description": "  The upload screen freezes.  ",
        })

        self.assertEqual(result, {
            "subject": "Application Issue",
            "description": "The upload screen freezes.",
        })

    def test_plural_other_subject_from_frontend_is_supported(self):
        result = self.support.validate_support_request({
            "subject": "Other Support Queries",
            "description": "I need help understanding the application.",
        })

        self.assertEqual(result["subject"], "Other Support Query")

    def test_message_is_accepted_as_description_alias(self):
        result = self.support.validate_support_request({
            "subject": "Report Upload Query",
            "message": "Can I upload two reports together?",
        })

        self.assertEqual(
            result["description"],
            "Can I upload two reports together?",
        )

    def test_description_and_message_cannot_both_be_sent(self):
        with self.assertRaises(self.support.SupportValidationError):
            self.support.validate_support_request({
                "subject": "Application Issue",
                "description": "The application closes.",
                "message": "The application closes.",
            })

    def test_invalid_subject_is_rejected(self):
        with self.assertRaises(self.support.SupportValidationError):
            self.support.validate_support_request({
                "subject": "Billing",
                "description": "I have a billing question.",
            })

    def test_empty_and_oversized_descriptions_are_rejected(self):
        with self.assertRaises(self.support.SupportValidationError):
            self.support.validate_support_request({
                "subject": "Application Issue",
                "description": "   ",
            })

        with self.assertRaises(self.support.SupportValidationError):
            self.support.validate_support_request({
                "subject": "Application Issue",
                "description": "x" * 4001,
            })

    def test_submit_persists_authenticated_user_ticket(self):
        captured = {}
        created_at = datetime(2026, 7, 29, 9, 30, tzinfo=timezone.utc)

        def create_ticket(user_id, subject, description):
            captured.update({
                "user_id": user_id,
                "subject": subject,
                "description": description,
            })
            return {
                "ticket_id": 17,
                "subject": subject,
                "status": "open",
                "created_at": created_at,
            }

        self.support.create_support_ticket = create_ticket

        ticket = self.support.submit_support_request(7, {
            "subject": "AI Health Assessment Explanation",
            "description": "Please explain the health assessment.",
        })

        self.assertEqual(captured["user_id"], 7)
        self.assertEqual(ticket["ticket_id"], 17)
        self.assertEqual(ticket["status"], "open")
        self.assertEqual(
            ticket["created_at"],
            "2026-07-29T09:30:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()

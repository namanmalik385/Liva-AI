from io import BytesIO
import importlib
import sys
import tempfile
import types
import unittest


class FakeFile:
    def __init__(self, filename, content=b"%PDF-test"):
        self.filename = filename
        self.stream = BytesIO(content)
        self.content = content

    def save(self, filepath):
        with open(filepath, "wb") as output:
            output.write(self.content)


class ReportBatchServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_module = sys.modules.get("db")
        if db_module is None:
            db_module = types.ModuleType("db")
            sys.modules["db"] = db_module

        required_stubs = {
            "complete_report_batch": lambda *_args, **_kwargs: None,
            "create_or_get_report_batch": lambda *_args, **_kwargs: None,
            "get_user_profile_record": lambda _user_id: None,
            "mark_report_batch_failed": lambda *_args, **_kwargs: None,
        }
        for name, stub in required_stubs.items():
            if not hasattr(db_module, name):
                setattr(db_module, name, stub)

        sys.modules.pop("services.report_batch_service", None)
        cls.batch = importlib.import_module(
            "services.report_batch_service"
        )

    def test_manifest_rejects_duplicate_report_types(self):
        with self.assertRaises(self.batch.ReportBatchError):
            self.batch.validate_batch_manifest(
                [FakeFile("one.pdf"), FakeFile("two.pdf")],
                ["lft", "lft"],
            )

    def test_apri_is_calculated_when_alt_is_missing(self):
        result = self.batch.calculate_batch_metrics(35, {
            "ast": 40,
            "alt": None,
            "platelets": 200,
            "ast_uln": 40,
        })

        self.assertIsNone(result["fib4"]["value"])
        self.assertEqual(result["fib4"]["missing_inputs"], ["alt"])
        self.assertEqual(result["apri"]["value"], 0.5)
        self.assertEqual(result["apri"]["missing_inputs"], [])

    def test_fib4_is_calculated_when_ast_uln_is_missing(self):
        result = self.batch.calculate_batch_metrics(35, {
            "ast": 40,
            "alt": 25,
            "platelets": 200,
            "ast_uln": None,
        })

        self.assertIsNotNone(result["fib4"]["value"])
        self.assertIsNone(result["apri"]["value"])
        self.assertEqual(
            result["apri"]["missing_inputs"],
            ["ast_uln"],
        )

    def test_completed_idempotency_key_replays_saved_response(self):
        saved_response = {
            "success": True,
            "batch": {"batch_id": "saved", "status": "completed"},
            "report": {"report_id": 42},
        }
        self.batch.create_or_get_report_batch = (
            lambda *_args, **_kwargs: {
                "created": False,
                "batch_id": "saved",
                "status": "completed",
                "report_id": 42,
                "response": saved_response,
                "error_message": None,
                "file_count": 1,
            }
        )

        result, status = self.batch.process_report_batch(
            7,
            [FakeFile("lft.pdf")],
            ["lft"],
            "a98d50c8-cbd7-4931-a468-34f421b5b31f",
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["idempotent_replay"])
        self.assertEqual(result["report"]["report_id"], 42)

    def test_two_files_create_one_completed_report(self):
        self.batch.create_or_get_report_batch = (
            lambda batch_id, *_args, **_kwargs: {
                "created": True,
                "batch_id": batch_id,
                "status": "processing",
                "report_id": None,
                "response": None,
                "error_message": None,
                "file_count": 2,
            }
        )
        self.batch.get_user_profile_record = lambda _user_id: (
            "Test User",
            35,
        )
        self.batch.mark_report_batch_failed = (
            lambda *_args, **_kwargs: None
        )

        def extract(_filepath, report_type):
            if report_type == "lft":
                return {
                    "ast": 40,
                    "alt": 25,
                    "ggt": 30,
                    "total_bilirubin": 0.8,
                    "albumin": 4.2,
                    "ast_uln": 40,
                }
            return {"platelets": 200}

        self.batch._extract_file = extract

        def complete(
            _batch_id,
            _user_id,
            _age,
            _report_data,
            _file_results,
            response,
        ):
            response["report"]["report_id"] = 51
            return response

        self.batch.complete_report_batch = complete

        with tempfile.TemporaryDirectory() as directory:
            original_folder = self.batch.UPLOAD_FOLDER
            self.batch.UPLOAD_FOLDER = directory
            try:
                result, status = self.batch.process_report_batch(
                    7,
                    [FakeFile("lft.pdf"), FakeFile("cbc.pdf")],
                    ["lft", "cbc"],
                    "62536fe1-1cff-440c-bf42-5c90ed6420d2",
                )
            finally:
                self.batch.UPLOAD_FOLDER = original_folder

        self.assertEqual(status, 201)
        self.assertEqual(result["batch"]["file_count"], 2)
        self.assertEqual(result["report"]["report_id"], 51)
        self.assertEqual(
            result["report"]["biomarkers"]["platelets"],
            200,
        )
        self.assertIsNotNone(
            result["report"]["calculated_metrics"]["fib4"]["value"]
        )
        self.assertIsNotNone(
            result["report"]["calculated_metrics"]["apri"]["value"]
        )


if __name__ == "__main__":
    unittest.main()

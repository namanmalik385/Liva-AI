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

    def test_ultrasound_content_must_match_its_extension(self):
        with self.assertRaises(self.batch.ReportBatchError):
            self.batch._validated_extension(
                FakeFile(
                    "ultrasound.png",
                    content=b"\xff\xd8\xfftest",
                ),
                "ultrasound",
            )

    def test_batch_response_formats_hepatitis_values(self):
        response = self.batch._build_response(
            "batch-id",
            [],
            {
                "hbsag": 0,
                "anti_hcv": 1,
            },
            {
                "fib4": {
                    "value": None,
                    "status": None,
                    "missing_inputs": [],
                },
                "apri": {
                    "value": None,
                    "status": None,
                    "missing_inputs": [],
                },
            },
        )

        self.assertEqual(
            response["report"]["biomarkers"]["hbsag"],
            "-ve",
        )
        self.assertEqual(
            response["report"]["biomarkers"]["anti_hcv"],
            "+ve",
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
            "report": {
                "report_id": 42,
                "biomarkers": {
                    "hbsag": 0,
                    "anti_hcv": 1,
                },
            },
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
        self.assertEqual(
            result["report"]["biomarkers"]["hbsag"],
            "-ve",
        )
        self.assertEqual(
            result["report"]["biomarkers"]["anti_hcv"],
            "+ve",
        )
        self.assertEqual(
            saved_response["report"]["biomarkers"]["hbsag"],
            0,
        )

    def test_database_failure_cleans_up_uploaded_object(self):
        original_functions = {
            name: getattr(self.batch, name)
            for name in (
                "create_or_get_report_batch",
                "get_user_profile_record",
                "mark_report_batch_failed",
                "_extract_file",
                "upload_report_document",
                "delete_report_documents",
                "complete_report_batch",
            )
        }
        deleted_keys = []
        self.batch.create_or_get_report_batch = (
            lambda batch_id, *_args, **_kwargs: {
                "created": True,
                "batch_id": batch_id,
                "status": "processing",
                "report_id": None,
                "response": None,
                "error_message": None,
                "file_count": 1,
            }
        )
        self.batch.get_user_profile_record = lambda _user_id: (
            "Test User",
            35,
        )
        self.batch.mark_report_batch_failed = (
            lambda *_args, **_kwargs: None
        )
        self.batch._extract_file = lambda *_args, **_kwargs: {
            "ast": 40,
            "alt": 25,
            "ast_uln": 40,
        }
        self.batch.upload_report_document = (
            lambda *_args, **_kwargs: None
        )
        self.batch.delete_report_documents = (
            lambda keys: deleted_keys.extend(keys)
        )
        self.batch.complete_report_batch = (
            lambda *_args, **_kwargs: (
                _ for _ in ()
            ).throw(RuntimeError("database unavailable"))
        )

        try:
            with tempfile.TemporaryDirectory() as directory:
                original_folder = self.batch.UPLOAD_FOLDER
                self.batch.UPLOAD_FOLDER = directory
                try:
                    with self.assertRaises(
                        self.batch.ReportBatchError
                    ) as raised:
                        self.batch.process_report_batch(
                            7,
                            [FakeFile("lft.pdf")],
                            ["lft"],
                            "071d7cbe-3554-4d20-8af8-e44ba2f5a3d0",
                        )
                finally:
                    self.batch.UPLOAD_FOLDER = original_folder
        finally:
            for name, function in original_functions.items():
                setattr(self.batch, name, function)

        self.assertEqual(raised.exception.status_code, 500)
        self.assertEqual(len(deleted_keys), 1)
        self.assertTrue(deleted_keys[0].endswith(".pdf"))

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
        self.batch.upload_report_document = (
            lambda *_args, **_kwargs: None
        )
        self.batch.delete_report_documents = (
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
            document_results,
        ):
            response["report"]["report_id"] = 51
            self.assertEqual(len(document_results), 2)
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
        self.assertTrue(
            result["batch"]["files"][0]["file_available"]
        )
        self.assertEqual(
            result["batch"]["files"][0]["mime_type"],
            "application/pdf",
        )
        self.assertEqual(
            result["batch"]["files"][0]["viewer_type"],
            "pdf",
        )
        self.assertIsNotNone(
            result["batch"]["files"][0]["document_id"]
        )
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

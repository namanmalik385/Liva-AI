import os
from unittest.mock import patch
import unittest

from services import report_document_storage as storage


STORAGE_ENV = {
    "R2_BUCKET": "private-reports",
    "R2_ACCESS_KEY_ID": "test-access-key",
    "R2_SECRET_ACCESS_KEY": "test-secret-key",
    "R2_ENDPOINT": "https://example.r2.cloudflarestorage.com",
    "R2_REGION": "auto",
    "REPORT_VIEW_URL_TTL_SECONDS": "300",
}


class FakeStorageClient:
    def __init__(self):
        self.uploads = []
        self.deletions = []
        self.presigns = []

    def upload_file(self, filepath, bucket, key, ExtraArgs):
        self.uploads.append((filepath, bucket, key, ExtraArgs))

    def delete_object(self, **kwargs):
        self.deletions.append(kwargs)

    def generate_presigned_url(self, operation, **kwargs):
        self.presigns.append((operation, kwargs))
        return "https://signed.example/report"


class ReportDocumentStorageTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeStorageClient()
        self.environment = patch.dict(
            os.environ,
            STORAGE_ENV,
            clear=False,
        )
        self.environment.start()
        configuration = storage._storage_configuration()
        storage._client = self.client
        storage._client_signature = tuple(configuration.values())

    def tearDown(self):
        storage._client = None
        storage._client_signature = None
        self.environment.stop()

    def test_view_url_is_short_lived_and_uses_private_object_key(self):
        url, ttl_seconds = storage.create_report_view_url(
            "reports/7/batch/document.pdf"
        )

        self.assertEqual(url, "https://signed.example/report")
        self.assertEqual(ttl_seconds, 300)
        operation, arguments = self.client.presigns[0]
        self.assertEqual(operation, "get_object")
        self.assertEqual(
            arguments["Params"],
            {
                "Bucket": "private-reports",
                "Key": "reports/7/batch/document.pdf",
            },
        )
        self.assertEqual(arguments["ExpiresIn"], 300)

    def test_invalid_endpoint_is_rejected(self):
        with patch.dict(
            os.environ,
            {"R2_ENDPOINT": "http://insecure.example"},
        ):
            with self.assertRaises(
                storage.ReportDocumentStorageConfigurationError
            ):
                storage._storage_configuration()

    def test_upload_uses_private_no_store_response_headers(self):
        storage.upload_report_document(
            filepath="report.pdf",
            storage_key="reports/7/batch/document.pdf",
            mime_type="application/pdf",
            original_filename='Patient "Report".pdf',
            metadata={"document-id": "document"},
        )

        _path, bucket, key, extra_args = self.client.uploads[0]
        self.assertEqual(bucket, "private-reports")
        self.assertEqual(key, "reports/7/batch/document.pdf")
        self.assertEqual(
            extra_args["CacheControl"],
            "private, no-store, max-age=0",
        )
        self.assertEqual(extra_args["ContentType"], "application/pdf")
        self.assertNotIn('"Report"', extra_args["ContentDisposition"])

    def test_cleanup_deletes_each_uploaded_object(self):
        storage.delete_report_documents(["one", "two", "one"])

        self.assertEqual(
            self.client.deletions,
            [
                {"Bucket": "private-reports", "Key": "one"},
                {"Bucket": "private-reports", "Key": "two"},
            ],
        )


if __name__ == "__main__":
    unittest.main()

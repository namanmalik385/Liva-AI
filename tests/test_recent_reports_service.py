from datetime import date, datetime, timezone
import unittest

from services.recent_reports_service import (
    format_date_uploaded,
    format_recent_reports,
)


class RecentReportsServiceTests(unittest.TestCase):
    def test_formats_legacy_day_first_date(self):
        self.assertEqual(
            format_date_uploaded("30-07-2026"),
            "July 30, 2026",
        )

    def test_formats_current_database_timestamp(self):
        self.assertEqual(
            format_date_uploaded("2026-07-30 18:05:12"),
            "July 30, 2026",
        )

    def test_formats_date_and_timezone_aware_datetime(self):
        self.assertEqual(
            format_date_uploaded(date(2026, 7, 30)),
            "July 30, 2026",
        )
        self.assertEqual(
            format_date_uploaded(
                datetime(
                    2026,
                    7,
                    30,
                    18,
                    5,
                    tzinfo=timezone.utc,
                )
            ),
            "July 30, 2026",
        )

    def test_recent_report_formatting_does_not_mutate_database_result(self):
        source = [{
            "report_type": "lft",
            "date_uploaded": "30-07-2026",
            "mime_type": "application/pdf",
        }]

        result = format_recent_reports(source)

        self.assertEqual(source[0]["date_uploaded"], "30-07-2026")
        self.assertEqual(result[0]["date_uploaded"], "July 30, 2026")
        self.assertEqual(result[0]["title"], "Liver Function Test")
        self.assertEqual(result[0]["viewer_type"], "pdf")


if __name__ == "__main__":
    unittest.main()

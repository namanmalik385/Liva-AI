import ast
from pathlib import Path
import unittest


PROTECTED_ROUTE_FUNCTIONS = {
    "routes/auth.py": {"logout_route", "current_user_route", "onboarding"},
    "routes/upload.py": {"upload_file", "recent_reports"},
    "routes/calculate.py": {"calculate"},
    "routes/insights.py": {"insights"},
    "routes/dashboard.py": {"dashboard"},
    "routes/report_analysis.py": {"report_analysis"},
    "routes/health_insights.py": {"health_insights"},
    "routes/chatbot.py": {"assistant_chat"},
    "routes/timeline.py": {"timeline"},
    "routes/profile.py": {"profile", "update_profile"},
    "routes/report_batches.py": {"create_report_batch"},
    "routes/support.py": {"submit_help_support"},
    "routes/report_documents.py": {"report_document_view_url"},
    "routes/achievements.py": {"achievements"},
}


class RouteProtectionTests(unittest.TestCase):
    def test_user_data_routes_require_authentication(self):
        project_root = Path(__file__).resolve().parents[1]

        for relative_path, function_names in (
            PROTECTED_ROUTE_FUNCTIONS.items()
        ):
            tree = ast.parse(
                (project_root / relative_path).read_text(
                    encoding="utf-8"
                )
            )
            functions = {
                node.name: node
                for node in tree.body
                if isinstance(node, ast.FunctionDef)
            }

            for function_name in function_names:
                with self.subTest(
                    file=relative_path,
                    function=function_name,
                ):
                    function = functions[function_name]
                    decorators = {
                        decorator.id
                        for decorator in function.decorator_list
                        if isinstance(decorator, ast.Name)
                    }
                    self.assertIn("auth_required", decorators)


if __name__ == "__main__":
    unittest.main()

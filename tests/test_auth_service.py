import importlib
import os
import sys
import types
import unittest

from flask import Flask, g


class AuthServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["JWT_SECRET"] = "x" * 48
        cls.state = {
            "created_sessions": {},
            "password_hash": None,
        }

        db_stub = types.ModuleType("db")
        db_stub.clear_auth_rate_limit = lambda _key: None
        db_stub.consume_auth_rate_limit = (
            lambda *_args, **_kwargs: (True, 0)
        )

        def create_session(session_id, user_id, token_hash, expires_at):
            cls.state["created_sessions"][session_id] = {
                "user_id": user_id,
                "token_hash": token_hash,
                "expires_at": expires_at,
                "revoked": False,
            }

        db_stub.create_auth_session = create_session
        db_stub.get_auth_user_by_email = lambda _email: None
        db_stub.get_auth_user_by_id = lambda user_id: {
            "user_id": user_id,
            "full_name": "Test User",
            "email": "test@example.com",
            "age": None,
            "gender": None,
        }
        db_stub.is_auth_session_active = (
            lambda session_id, user_id: (
                session_id in cls.state["created_sessions"]
                and cls.state["created_sessions"][session_id]["user_id"]
                == user_id
                and not cls.state["created_sessions"][session_id]["revoked"]
            )
        )
        db_stub.revoke_auth_session = (
            lambda session_id, _user_id: cls.state[
                "created_sessions"
            ][session_id].update({"revoked": True})
        )
        def rotate_session(
            session_id,
            presented_hash,
            new_session_id,
            new_token_hash,
            new_expires_at,
        ):
            session = cls.state["created_sessions"].get(session_id)
            if session is None or session["token_hash"] != presented_hash:
                return {"status": "invalid", "user_id": None}
            if session["revoked"]:
                for active_session in cls.state["created_sessions"].values():
                    active_session["revoked"] = True
                return {
                    "status": "reused",
                    "user_id": session["user_id"],
                }

            session["revoked"] = True
            cls.state["created_sessions"][new_session_id] = {
                "user_id": session["user_id"],
                "token_hash": new_token_hash,
                "expires_at": new_expires_at,
                "revoked": False,
            }
            return {
                "status": "rotated",
                "user_id": session["user_id"],
            }

        db_stub.rotate_auth_session = rotate_session

        def signup(_email, password_hash, _name, _terms_accepted_at):
            cls.state["password_hash"] = password_hash
            return 7

        db_stub.signup = signup
        db_stub.update_password_hash = lambda *_args, **_kwargs: None
        sys.modules["db"] = db_stub
        sys.modules.pop("services.auth_service", None)
        cls.auth = importlib.import_module("services.auth_service")

    def setUp(self):
        self.state["created_sessions"].clear()
        self.state["password_hash"] = None

    def test_registration_hashes_password_and_issues_tokens(self):
        password = "correct horse battery staple"
        result = self.auth.register_user(
            {
                "full_name": "Test User",
                "email": "TEST@EXAMPLE.COM",
                "password": password,
                "confirm_password": password,
                "terms_accepted": True,
            },
            "127.0.0.1",
        )

        self.assertEqual(result["user"]["user_id"], 7)
        self.assertNotEqual(self.state["password_hash"], password)
        self.assertTrue(
            result["auth"]["access_token"]
        )
        self.assertTrue(
            result["auth"]["refresh_token"]
        )

    def test_protected_route_rejects_missing_token(self):
        app = Flask(__name__)

        @app.get("/protected")
        @self.auth.auth_required
        def protected():
            return {"user_id": g.current_user_id}

        client = app.test_client()
        response = client.get("/protected")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.headers["WWW-Authenticate"],
            "Bearer",
        )

    def test_access_token_uses_server_identity(self):
        app = Flask(__name__)
        auth_data = self.auth._new_auth_session(7)

        @app.get("/protected")
        @self.auth.auth_required
        def protected():
            return {"user_id": g.current_user_id}

        client = app.test_client()
        response = client.get(
            "/protected",
            headers={
                "Authorization": (
                    f"Bearer {auth_data['access_token']}"
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user_id"], 7)

    def test_refresh_rotates_session_and_invalidates_old_access(self):
        app = Flask(__name__)
        original_auth = self.auth._new_auth_session(7)
        replacement_auth = self.auth.rotate_refresh_token(
            original_auth["refresh_token"],
            "127.0.0.1",
        )

        @app.get("/protected")
        @self.auth.auth_required
        def protected():
            return {"user_id": g.current_user_id}

        client = app.test_client()
        old_response = client.get(
            "/protected",
            headers={
                "Authorization": (
                    f"Bearer {original_auth['access_token']}"
                )
            },
        )
        new_response = client.get(
            "/protected",
            headers={
                "Authorization": (
                    f"Bearer {replacement_auth['access_token']}"
                )
            },
        )

        self.assertEqual(old_response.status_code, 401)
        self.assertEqual(new_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()

from flask import Blueprint, jsonify, request

from db import update_user_profile
from services.auth_service import (
    AuthConfigurationError,
    AuthRateLimitError,
    AuthTokenError,
    AuthValidationError,
    InvalidCredentialsError,
    RegistrationRejectedError,
    auth_required,
    authenticate_user,
    current_user,
    current_user_id,
    logout_current_session,
    register_user,
    rotate_refresh_token,
    validate_onboarding_payload,
)


auth_bp = Blueprint("auth", __name__)


def _rate_limit_response(error):
    response = jsonify({
        "success": False,
        "error": "Too many attempts. Please try again later.",
        "retry_after": error.retry_after,
    })
    response.status_code = 429
    response.headers["Retry-After"] = str(error.retry_after)
    return response


@auth_bp.route("/auth/signup", methods=["POST"])
@auth_bp.route("/signup", methods=["POST"])
def signup_route():
    data = request.get_json(silent=True)

    try:
        result = register_user(data, request.remote_addr)
    except AuthValidationError as error:
        return jsonify({
            "success": False,
            "error": str(error),
        }), 400
    except AuthRateLimitError as error:
        return _rate_limit_response(error)
    except RegistrationRejectedError:
        return jsonify({
            "success": False,
            "error": "Unable to create account with the provided details",
        }), 409
    except AuthConfigurationError:
        return jsonify({
            "success": False,
            "error": "Authentication service is not configured",
        }), 503
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not create account",
        }), 500

    return jsonify({
        "success": True,
        **result,
    }), 201


@auth_bp.route("/auth/login", methods=["POST"])
@auth_bp.route("/login", methods=["POST"])
def login_route():
    data = request.get_json(silent=True)

    try:
        result = authenticate_user(data, request.remote_addr)
    except AuthValidationError as error:
        return jsonify({
            "success": False,
            "error": str(error),
        }), 400
    except InvalidCredentialsError:
        return jsonify({
            "success": False,
            "error": "Invalid email or password",
        }), 401
    except AuthRateLimitError as error:
        return _rate_limit_response(error)
    except AuthConfigurationError:
        return jsonify({
            "success": False,
            "error": "Authentication service is not configured",
        }), 503
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not sign in",
        }), 500

    return jsonify({
        "success": True,
        **result,
    }), 200


@auth_bp.route("/auth/refresh", methods=["POST"])
def refresh_route():
    data = request.get_json(silent=True) or {}

    try:
        auth = rotate_refresh_token(
            data.get("refresh_token"),
            request.remote_addr,
        )
    except AuthRateLimitError as error:
        return _rate_limit_response(error)
    except AuthTokenError:
        return jsonify({
            "success": False,
            "error": "Invalid or expired refresh token",
        }), 401
    except AuthConfigurationError:
        return jsonify({
            "success": False,
            "error": "Authentication service is not configured",
        }), 503
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not refresh authentication",
        }), 500

    return jsonify({
        "success": True,
        "auth": auth,
    }), 200


@auth_bp.route("/auth/logout", methods=["POST"])
@auth_required
def logout_route():
    logout_current_session()
    return jsonify({
        "success": True,
        "message": "Signed out",
    }), 200


@auth_bp.route("/auth/me", methods=["GET"])
@auth_required
def current_user_route():
    user = current_user()
    if user is None:
        return jsonify({
            "success": False,
            "error": "User not found",
        }), 404
    return jsonify({
        "success": True,
        "user": user,
    }), 200


@auth_bp.route("/onboarding", methods=["POST"])
@auth_required
def onboarding():
    data = request.get_json(silent=True) or {}

    try:
        profile = validate_onboarding_payload(data)
    except AuthValidationError as error:
        return jsonify({
            "success": False,
            "error": str(error),
        }), 400

    updated = update_user_profile(
        current_user_id(),
        profile["age"],
        profile["gender"],
        profile["weight"],
        profile["height"],
        profile["diabetes_status"],
        profile["hypertension"],
        profile["previous_liver_disease"],
        profile["family_history"],
        profile["activity_level"],
        profile["exercise_frequency"],
        profile["alcohol_consumption"],
        profile["smoking_status"],
    )

    if not updated:
        return jsonify({
            "success": False,
            "error": "Could not update profile",
        }), 404

    return jsonify({
        "success": True,
        "message": "Onboarding completed",
    }), 200

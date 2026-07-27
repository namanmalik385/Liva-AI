from datetime import datetime, timedelta, timezone
from functools import wraps
import hashlib
import os
import re
import secrets
import uuid

import jwt
from flask import g, jsonify, request

from db import (
    clear_auth_rate_limit,
    consume_auth_rate_limit,
    create_auth_session,
    get_auth_user_by_email,
    get_auth_user_by_id,
    is_auth_session_active,
    revoke_auth_session,
    rotate_auth_session,
    signup,
    update_password_hash,
)
from services.password_service import (
    PasswordValidationError,
    hash_password,
    password_needs_rehash,
    validate_password,
    verify_password,
)


JWT_ALGORITHM = "HS256"
JWT_ISSUER = os.getenv("JWT_ISSUER", "livora-api")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "livora-mobile")
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 30

LOGIN_ACCOUNT_LIMIT = 5
LOGIN_IP_LIMIT = 20
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_BLOCK_SECONDS = 15 * 60
SIGNUP_IP_LIMIT = 5
SIGNUP_WINDOW_SECONDS = 60 * 60
SIGNUP_BLOCK_SECONDS = 60 * 60
REFRESH_IP_LIMIT = 30
REFRESH_WINDOW_SECONDS = 15 * 60
REFRESH_BLOCK_SECONDS = 15 * 60

_EMAIL_PATTERN = re.compile(
    r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$"
)
_GENDERS = {"male", "female", "other"}
_ACTIVITY_LEVELS = {
    "sedentary",
    "lightly active",
    "moderately active",
    "very active",
}
_EXERCISE_FREQUENCIES = {
    "never",
    "1-2 times per week",
    "2-4 times per week",
    "5+ times every week",
    "every day",
}
_ALCOHOL_LEVELS = {"none", "occasional", "moderate", "heavy"}
_SMOKING_STATUSES = {"never", "former", "current"}
_DUMMY_PASSWORD_HASH = hash_password(
    "invalid-account-password-placeholder"
)


class AuthValidationError(ValueError):
    pass


class InvalidCredentialsError(Exception):
    pass


class RegistrationRejectedError(Exception):
    pass


class AuthTokenError(Exception):
    pass


class AuthConfigurationError(Exception):
    pass


class AuthRateLimitError(Exception):
    def __init__(self, retry_after):
        super().__init__("Too many authentication attempts")
        self.retry_after = retry_after


def _jwt_secret():
    secret = os.getenv("JWT_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise AuthConfigurationError(
            "JWT_SECRET must contain at least 32 bytes"
        )
    return secret


def validate_auth_configuration():
    _jwt_secret()


def _normalize_email(value):
    if not isinstance(value, str):
        raise AuthValidationError("email must be a string")
    email = value.strip().casefold()
    if len(email) > 254 or _EMAIL_PATTERN.fullmatch(email) is None:
        raise AuthValidationError("enter a valid email address")
    return email


def _validate_name(value):
    if not isinstance(value, str):
        raise AuthValidationError("full_name must be a string")
    name = " ".join(value.strip().split())
    if len(name) < 2 or len(name) > 100:
        raise AuthValidationError(
            "full_name must be between 2 and 100 characters"
        )
    return name


def _number_field(data, field, minimum, maximum):
    value = data.get(field)
    if isinstance(value, bool):
        raise AuthValidationError(f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise AuthValidationError(
            f"{field} must be a number"
        ) from error
    if number < minimum or number > maximum:
        raise AuthValidationError(
            f"{field} must be between {minimum:g} and {maximum:g}"
        )
    return number


def _choice_field(data, field, allowed, required=True):
    value = data.get(field)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise AuthValidationError(f"{field} must be a string")
    normalized = " ".join(value.strip().casefold().split())
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise AuthValidationError(
            f"{field} must be one of: {choices}"
        )
    return normalized


def _boolean_field(data, field):
    value = data.get(field, False)
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise AuthValidationError(f"{field} must be a boolean")


def validate_onboarding_payload(data):
    if not isinstance(data, dict):
        raise AuthValidationError("JSON body is required")

    age = _number_field(data, "age", 13, 120)
    if not age.is_integer():
        raise AuthValidationError("age must be a whole number")
    height = _number_field(data, "height", 80, 250)
    weight = _number_field(data, "weight", 20, 500)
    gender = _choice_field(data, "gender", _GENDERS)

    return {
        "age": int(age),
        "gender": gender,
        "weight": weight,
        "height": height,
        "diabetes_status": _boolean_field(
            data,
            "diabetes_status",
        ),
        "hypertension": _boolean_field(data, "hypertension"),
        "previous_liver_disease": _boolean_field(
            data,
            "previous_liver_disease",
        ),
        "family_history": _boolean_field(data, "family_history"),
        "activity_level": _choice_field(
            data,
            "activity_level",
            _ACTIVITY_LEVELS,
        ),
        "exercise_frequency": _choice_field(
            data,
            "exercise_frequency",
            _EXERCISE_FREQUENCIES,
        ),
        "alcohol_consumption": _choice_field(
            data,
            "alcohol_consumption",
            _ALCOHOL_LEVELS,
            required=False,
        ),
        "smoking_status": _choice_field(
            data,
            "smoking_status",
            _SMOKING_STATUSES,
            required=False,
        ),
    }


def _rate_key(kind, value):
    material = f"{kind}:{value}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _consume_rate_limit(
    kind,
    value,
    limit,
    window_seconds,
    block_seconds,
):
    allowed, retry_after = consume_auth_rate_limit(
        _rate_key(kind, value),
        limit,
        window_seconds,
        block_seconds,
    )
    if not allowed:
        raise AuthRateLimitError(retry_after)


def _client_identifier(client_ip):
    return client_ip or "unknown-client"


def _user_from_login_row(row):
    return {
        "user_id": row[0],
        "full_name": row[2],
        "email": row[3],
        "age": row[4],
        "gender": row[5],
    }


def _refresh_token(session_id):
    return f"{session_id}.{secrets.token_urlsafe(48)}"


def _token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _access_token(user_id, session_id):
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    payload = {
        "sub": str(user_id),
        "sid": session_id,
        "jti": str(uuid.uuid4()),
        "typ": "access",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
    }
    return (
        jwt.encode(
            payload,
            _jwt_secret(),
            algorithm=JWT_ALGORITHM,
        ),
        expires_at,
    )


def _new_auth_session(user_id):
    session_id = str(uuid.uuid4())
    refresh_token = _refresh_token(session_id)
    refresh_expires_at = (
        datetime.now(timezone.utc)
        + timedelta(days=REFRESH_TOKEN_DAYS)
    )
    create_auth_session(
        session_id,
        user_id,
        _token_hash(refresh_token),
        refresh_expires_at,
    )
    access_token, access_expires_at = _access_token(
        user_id,
        session_id,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
        "access_expires_at": access_expires_at.isoformat(),
        "refresh_expires_at": refresh_expires_at.isoformat(),
    }


def register_user(data, client_ip):
    _jwt_secret()
    _consume_rate_limit(
        "signup-ip",
        _client_identifier(client_ip),
        SIGNUP_IP_LIMIT,
        SIGNUP_WINDOW_SECONDS,
        SIGNUP_BLOCK_SECONDS,
    )

    if not isinstance(data, dict):
        raise AuthValidationError("JSON body is required")

    name = _validate_name(data.get("full_name"))
    email = _normalize_email(data.get("email"))
    password = data.get("password")
    confirm_password = data.get("confirm_password")

    if password != confirm_password:
        raise AuthValidationError("passwords do not match")
    if data.get("terms_accepted") is not True:
        raise AuthValidationError(
            "terms_accepted must be true to create an account"
        )

    try:
        validate_password(password)
    except PasswordValidationError as error:
        raise AuthValidationError(str(error)) from error

    password_hash = hash_password(password)
    user_id = signup(
        email,
        password_hash,
        name,
        datetime.now(timezone.utc),
    )
    if user_id is None:
        raise RegistrationRejectedError

    user = get_auth_user_by_id(user_id)
    return {
        "user": user,
        "auth": _new_auth_session(user_id),
    }


def authenticate_user(data, client_ip):
    _jwt_secret()
    if not isinstance(data, dict):
        raise AuthValidationError("JSON body is required")

    email = _normalize_email(data.get("email"))
    password = data.get("password")
    if not isinstance(password, str) or not password:
        raise AuthValidationError("password is required")

    client_identifier = _client_identifier(client_ip)
    account_rate_key = _rate_key("login-account", email)
    _consume_rate_limit(
        "login-ip",
        client_identifier,
        LOGIN_IP_LIMIT,
        LOGIN_WINDOW_SECONDS,
        LOGIN_BLOCK_SECONDS,
    )
    _consume_rate_limit(
        "login-account",
        email,
        LOGIN_ACCOUNT_LIMIT,
        LOGIN_WINDOW_SECONDS,
        LOGIN_BLOCK_SECONDS,
    )

    row = get_auth_user_by_email(email)
    password_hash = row[1] if row else _DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password_hash, password)

    if row is None or not password_is_valid:
        raise InvalidCredentialsError

    clear_auth_rate_limit(account_rate_key)

    if password_needs_rehash(password_hash):
        update_password_hash(row[0], hash_password(password))

    return {
        "user": _user_from_login_row(row),
        "auth": _new_auth_session(row[0]),
    }


def rotate_refresh_token(refresh_token, client_ip):
    _jwt_secret()
    _consume_rate_limit(
        "refresh-ip",
        _client_identifier(client_ip),
        REFRESH_IP_LIMIT,
        REFRESH_WINDOW_SECONDS,
        REFRESH_BLOCK_SECONDS,
    )

    if not isinstance(refresh_token, str) or "." not in refresh_token:
        raise AuthTokenError

    session_id = refresh_token.split(".", 1)[0]
    try:
        uuid.UUID(session_id)
    except (ValueError, TypeError):
        raise AuthTokenError

    new_session_id = str(uuid.uuid4())
    new_refresh_token = _refresh_token(new_session_id)
    refresh_expires_at = (
        datetime.now(timezone.utc)
        + timedelta(days=REFRESH_TOKEN_DAYS)
    )
    rotation = rotate_auth_session(
        session_id,
        _token_hash(refresh_token),
        new_session_id,
        _token_hash(new_refresh_token),
        refresh_expires_at,
    )
    if rotation["status"] != "rotated":
        raise AuthTokenError

    access_token, access_expires_at = _access_token(
        rotation["user_id"],
        new_session_id,
    )
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
        "access_expires_at": access_expires_at.isoformat(),
        "refresh_expires_at": refresh_expires_at.isoformat(),
    }


def decode_access_token(token):
    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            leeway=5,
            options={
                "require": [
                    "sub",
                    "sid",
                    "jti",
                    "typ",
                    "iss",
                    "aud",
                    "iat",
                    "nbf",
                    "exp",
                ]
            },
        )
        user_id = int(payload["sub"])
        session_id = str(payload["sid"])
        if payload["typ"] != "access" or user_id <= 0:
            raise AuthTokenError
        uuid.UUID(session_id)
    except (
        jwt.PyJWTError,
        AuthConfigurationError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise AuthTokenError from error

    if not is_auth_session_active(session_id, user_id):
        raise AuthTokenError

    return {
        "user_id": user_id,
        "session_id": session_id,
        "jti": payload["jti"],
    }


def _unauthorized_response():
    response = jsonify({
        "success": False,
        "error": "Authentication required",
    })
    response.status_code = 401
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


def auth_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if (
            separator != " "
            or scheme.casefold() != "bearer"
            or not token.strip()
        ):
            return _unauthorized_response()

        try:
            identity = decode_access_token(token.strip())
        except AuthTokenError:
            return _unauthorized_response()

        g.current_user_id = identity["user_id"]
        g.auth_session_id = identity["session_id"]
        g.access_token_jti = identity["jti"]
        return view(*args, **kwargs)

    return wrapped


def current_user_id():
    return g.current_user_id


def logout_current_session():
    revoke_auth_session(
        g.auth_session_id,
        g.current_user_id,
    )


def current_user():
    return get_auth_user_by_id(g.current_user_id)

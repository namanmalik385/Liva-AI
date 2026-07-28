import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

from routes.auth import auth_bp
from routes.upload import upload_bp
from routes.calculate import calculate_bp
from routes.insights import insights_bp
from routes.report_analysis import report_analysis_bp
from routes.dashboard import dashboard_bp
from routes.health_insights import health_insights_bp
from routes.chatbot import chatbot_bp
from routes.timeline import timeline_bp
from services.auth_service import validate_auth_configuration

app = Flask(__name__)

app_env = os.getenv("APP_ENV", "development").strip().lower()
if app_env not in {"development", "testing", "production"}:
    raise RuntimeError(
        "APP_ENV must be development, testing, or production"
    )
if os.getenv("TRUST_PROXY", "0") == "1":
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,
        x_proto=1,
        x_host=1,
    )

app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))
)

configured_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if app_env == "production" and not configured_origins:
    raise RuntimeError("CORS_ORIGINS is required in production")
if not configured_origins:
    configured_origins = [
        "http://localhost:3000",
        "http://localhost:8081",
        "http://localhost:19006",
    ]

CORS(
    app,
    origins=configured_origins,
    methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    supports_credentials=False,
)

if app_env == "production":
    validate_auth_configuration()


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return jsonify({
        "success": False,
        "error": "Uploaded file is too large",
    }), 413


@app.before_request
def require_https():
    if (
        app_env == "production"
        and os.getenv("ENFORCE_HTTPS", "1") == "1"
        and not request.is_secure
    ):
        return jsonify({
            "success": False,
            "error": "HTTPS is required",
        }), 400


@app.after_request
def add_security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()"
    )
    if app_env == "production" and request.is_secure:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response

app.register_blueprint(auth_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(calculate_bp)
app.register_blueprint(insights_bp)
app.register_blueprint(report_analysis_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(health_insights_bp)
app.register_blueprint(chatbot_bp)
app.register_blueprint(timeline_bp)

@app.route("/", methods=["GET"])
def home():
    return {
        "success": True,
        "message": "Livora Backend is running"
    }, 200

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )

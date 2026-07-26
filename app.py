from flask import Flask
from flask_cors import CORS

from routes.auth import auth_bp
from routes.upload import upload_bp
from routes.calculate import calculate_bp
from routes.insights import insights_bp
from routes.report_analysis import report_analysis_bp
from routes.dashboard import dashboard_bp
from routes.health_insights import health_insights_bp
from routes.chatbot import chatbot_bp

app = Flask(__name__)

CORS(app)

app.register_blueprint(auth_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(calculate_bp)
app.register_blueprint(insights_bp)
app.register_blueprint(report_analysis_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(health_insights_bp)
app.register_blueprint(chatbot_bp)

@app.route("/", methods=["GET"])
def home():
    return {
        "success": True,
        "message": "Livora Backend is running"
    }, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

from flask import Blueprint, jsonify, request

from services.chatbot_service import (
    ChatbotContextMismatchError,
    ChatbotConversationNotFoundError,
    ChatbotReportNotFoundError,
    ChatbotUnavailableError,
    ChatbotUserNotFoundError,
    ChatbotValidationError,
    chat,
)


chatbot_bp = Blueprint("chatbot", __name__)


@chatbot_bp.route("/assistant/chat", methods=["POST"])
def assistant_chat():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    report_id = data.get("report_id")

    if user_id is None:
        return jsonify({
            "success": False,
            "error": "user_id is required",
        }), 400

    try:
        user_id = int(user_id)
        report_id = int(report_id) if report_id is not None else None
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "user_id and report_id must be integers",
        }), 400

    if user_id <= 0 or (report_id is not None and report_id <= 0):
        return jsonify({
            "success": False,
            "error": "user_id and report_id must be positive integers",
        }), 400

    try:
        result = chat(
            user_id=user_id,
            message=data.get("message"),
            conversation_id=data.get("conversation_id"),
            report_id=report_id,
        )
    except ChatbotValidationError as error:
        return jsonify({
            "success": False,
            "error": str(error),
        }), 400
    except ChatbotUserNotFoundError:
        return jsonify({
            "success": False,
            "error": "User not found",
        }), 404
    except ChatbotReportNotFoundError:
        return jsonify({
            "success": False,
            "error": "Report not found for this user",
        }), 404
    except ChatbotConversationNotFoundError:
        return jsonify({
            "success": False,
            "error": "Conversation not found for this user",
        }), 404
    except ChatbotContextMismatchError:
        return jsonify({
            "success": False,
            "error": (
                "report_id cannot be changed within a conversation; "
                "start a new conversation instead"
            ),
        }), 409
    except ChatbotUnavailableError:
        return jsonify({
            "success": False,
            "error": "The health assistant is temporarily unavailable",
        }), 503
    except Exception:
        return jsonify({
            "success": False,
            "error": "Could not process assistant message",
        }), 500

    return jsonify({
        "success": True,
        "assistant": result,
    }), 200

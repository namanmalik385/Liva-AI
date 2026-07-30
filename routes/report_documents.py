from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify

from db import get_report_document_for_user
from services.auth_service import auth_required, current_user_id
from services.report_document_storage import (
    ReportDocumentStorageConfigurationError,
    ReportDocumentStorageOperationError,
    create_report_view_url,
)


report_documents_bp = Blueprint("report_documents", __name__)


def _viewer_type(mime_type):
    if mime_type == "application/pdf":
        return "pdf"
    if isinstance(mime_type, str) and mime_type.startswith("image/"):
        return "image"
    return None


@report_documents_bp.route(
    "/report-documents/<string:document_id>/view-url",
    methods=["GET"],
)
@auth_required
def report_document_view_url(document_id):
    document = get_report_document_for_user(
        document_id,
        current_user_id(),
    )
    if document is None:
        return jsonify({
            "success": False,
            "error": "Report document not found",
        }), 404

    try:
        url, ttl_seconds = create_report_view_url(
            document["storage_key"]
        )
    except ReportDocumentStorageConfigurationError:
        current_app.logger.error(
            "Private report storage is not configured"
        )
        return jsonify({
            "success": False,
            "error": "Report document storage is unavailable",
        }), 503
    except ReportDocumentStorageOperationError:
        current_app.logger.exception(
            "Could not create report document viewing link"
        )
        return jsonify({
            "success": False,
            "error": "Could not open report document",
        }), 503

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=ttl_seconds
    )
    return jsonify({
        "success": True,
        "document": {
            "document_id": document["document_id"],
            "report_id": document["report_id"],
            "report_type": document["report_type"],
            "filename": document["filename"],
            "mime_type": document["mime_type"],
            "size_bytes": document["size_bytes"],
            "viewer_type": _viewer_type(document["mime_type"]),
            "url": url,
            "expires_in": ttl_seconds,
            "expires_at": expires_at.isoformat(),
        },
    })

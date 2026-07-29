from flask import Blueprint, current_app, jsonify, request

from services.auth_service import auth_required, current_user_id
from services.report_batch_service import (
    ReportBatchError,
    process_report_batch,
)


report_batches_bp = Blueprint("report_batches", __name__)


@report_batches_bp.route("/report-batches", methods=["POST"])
@auth_required
def create_report_batch():
    files = request.files.getlist("files")
    report_types = request.form.getlist("report_types")
    idempotency_key = request.headers.get("Idempotency-Key")

    try:
        response, status_code = process_report_batch(
            current_user_id(),
            files,
            report_types,
            idempotency_key,
        )
    except ReportBatchError as error:
        if error.status_code >= 500:
            current_app.logger.exception(
                "Report batch processing failed"
            )
        body = {
            "success": False,
            "error": str(error),
        }
        if error.batch_id is not None:
            body["batch_id"] = error.batch_id
        return jsonify(body), error.status_code
    except Exception:
        current_app.logger.exception(
            "Could not create report batch"
        )
        return jsonify({
            "success": False,
            "error": "Could not create report batch",
        }), 500

    return jsonify(response), status_code

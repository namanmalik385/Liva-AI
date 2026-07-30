import os
import re
import unicodedata
from urllib.parse import urlparse


class ReportDocumentStorageError(Exception):
    pass


class ReportDocumentStorageConfigurationError(
    ReportDocumentStorageError
):
    pass


class ReportDocumentStorageOperationError(ReportDocumentStorageError):
    pass


_client = None
_client_signature = None


def _storage_configuration():
    configuration = {
        "bucket": os.getenv("R2_BUCKET", "").strip(),
        "access_key_id": os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        "secret_access_key": os.getenv(
            "R2_SECRET_ACCESS_KEY",
            "",
        ).strip(),
        "endpoint": os.getenv("R2_ENDPOINT", "").strip().rstrip("/"),
        "region": os.getenv("R2_REGION", "auto").strip() or "auto",
    }
    missing = [
        key
        for key in (
            "bucket",
            "access_key_id",
            "secret_access_key",
            "endpoint",
        )
        if not configuration[key]
    ]
    if missing:
        raise ReportDocumentStorageConfigurationError(
            "Private report storage is not configured"
        )

    endpoint = urlparse(configuration["endpoint"])
    if endpoint.scheme != "https" or not endpoint.netloc:
        raise ReportDocumentStorageConfigurationError(
            "R2_ENDPOINT must be a valid HTTPS URL"
        )
    return configuration


def _view_url_ttl_seconds():
    raw_value = os.getenv("REPORT_VIEW_URL_TTL_SECONDS", "300").strip()
    try:
        ttl_seconds = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ReportDocumentStorageConfigurationError(
            "REPORT_VIEW_URL_TTL_SECONDS must be a whole number"
        ) from error

    if ttl_seconds < 60 or ttl_seconds > 900:
        raise ReportDocumentStorageConfigurationError(
            "REPORT_VIEW_URL_TTL_SECONDS must be between 60 and 900"
        )
    return ttl_seconds


def _get_client():
    global _client, _client_signature

    configuration = _storage_configuration()
    signature = tuple(configuration.values())
    if _client is not None and _client_signature == signature:
        return _client, configuration

    try:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=configuration["endpoint"],
            aws_access_key_id=configuration["access_key_id"],
            aws_secret_access_key=configuration["secret_access_key"],
            region_name=configuration["region"],
            config=Config(signature_version="s3v4"),
        )
    except ImportError as error:
        raise ReportDocumentStorageConfigurationError(
            "Private report storage dependency is unavailable"
        ) from error
    except Exception as error:
        raise ReportDocumentStorageOperationError(
            "Could not initialize private report storage"
        ) from error

    _client_signature = signature
    return _client, configuration


def _content_disposition(original_filename):
    normalized = unicodedata.normalize(
        "NFKD",
        original_filename or "",
    ).encode("ascii", "ignore").decode("ascii")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", normalized)
    safe_name = safe_name.strip("._")[:180] or "report"
    return f'inline; filename="{safe_name}"'


def upload_report_document(
    filepath,
    storage_key,
    mime_type,
    original_filename,
    metadata,
):
    client, configuration = _get_client()
    try:
        client.upload_file(
            filepath,
            configuration["bucket"],
            storage_key,
            ExtraArgs={
                "ContentType": mime_type,
                "ContentDisposition": _content_disposition(
                    original_filename
                ),
                "CacheControl": "private, no-store, max-age=0",
                "Metadata": {
                    str(key): str(value)
                    for key, value in metadata.items()
                },
            },
        )
    except Exception as error:
        raise ReportDocumentStorageOperationError(
            "Could not store uploaded report"
        ) from error


def delete_report_documents(storage_keys):
    keys = list(dict.fromkeys(
        key for key in storage_keys if isinstance(key, str) and key
    ))
    if not keys:
        return

    client, configuration = _get_client()
    errors = []
    for storage_key in keys:
        try:
            client.delete_object(
                Bucket=configuration["bucket"],
                Key=storage_key,
            )
        except Exception as error:
            errors.append(error)
    if errors:
        raise ReportDocumentStorageOperationError(
            "Could not clean up uploaded report"
        ) from errors[0]


def create_report_view_url(storage_key):
    client, configuration = _get_client()
    ttl_seconds = _view_url_ttl_seconds()
    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": configuration["bucket"],
                "Key": storage_key,
            },
            ExpiresIn=ttl_seconds,
            HttpMethod="GET",
        )
    except Exception as error:
        raise ReportDocumentStorageOperationError(
            "Could not create report viewing link"
        ) from error
    return url, ttl_seconds

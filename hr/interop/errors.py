"""Standardized HTTP error envelope for the interop API.

Errors follow a JSON:API-like ``errors`` array (status/code/title/detail),
which is the shape HR Open's REST profile aligns with. Small helpers keep the
views clean and the error contract consistent across every endpoint.
"""

from __future__ import annotations

from rest_framework.response import Response


def error_response(status_code: int, code: str, title: str, detail: str = "") -> Response:
    return Response(
        {
            "errors": [
                {
                    "status": str(status_code),
                    "code": code,
                    "title": title,
                    "detail": detail or title,
                }
            ]
        },
        status=status_code,
    )


def bad_request(code: str, detail: str) -> Response:
    return error_response(400, code, "Bad Request", detail)


def forbidden(detail: str) -> Response:
    return error_response(403, "forbidden", "Forbidden", detail)


def not_found(code: str, detail: str) -> Response:
    return error_response(404, code, "Not Found", detail)

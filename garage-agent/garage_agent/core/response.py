"""Standardized API response helpers for JSON routes."""


def success_response(data=None, message=None):
    """Wrap a successful result in the standard envelope."""
    return {
        "success": True,
        "data": data,
        "message": message,
    }


def error_response(code: str, message: str):
    """Wrap an error result in the standard envelope."""
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }

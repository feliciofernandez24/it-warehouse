"""Public errors never contain actor details, raw payloads, SQL or evidence."""
CODES = frozenset({
    "AUTHENTICATION_REQUIRED", "INVALID_ACTOR_CONTEXT", "ACTOR_DATABASE_MISMATCH",
    "ACTOR_UNAVAILABLE", "ACTOR_INACTIVE", "PERMISSION_DENIED", "UNKNOWN_CAPABILITY",
    "REVISION_NOT_FOUND", "SELF_REVIEW_UPLOADER", "SELF_REVIEW_CREATOR",
    "SELF_REVIEW_CONTRIBUTOR", "INVALID_REQUEST", "ACTION_DISABLED",
    "GATEWAY_UNAVAILABLE", "VERSION_CONFLICT", "REQUEST_CONFLICT",
    "DATABASE_OPERATION_FAILED", "RETRYABLE_TRANSACTION", "LOCK_TIMEOUT",
    "REQUEST_TOO_LARGE", "REVISION_STATE_INVALID", "INTERNAL_ERROR",
})


class ReviewServiceError(Exception):
    def __init__(self, code):
        self.code = code if code in CODES else "INTERNAL_ERROR"
        self.retryable = self.code in ("RETRYABLE_TRANSACTION", "LOCK_TIMEOUT")
        super().__init__(self.code)

    def as_dict(self):
        return {"code": self.code, "retryable": self.retryable}


def database_error(error):
    """Call outside the failed atomic block; never copy the driver message."""
    cause = getattr(error, "__cause__", None)
    state = getattr(cause, "sqlstate", None) or getattr(error, "sqlstate", None)
    if state in ("40P01", "40001"):
        return ReviewServiceError("RETRYABLE_TRANSACTION")
    if state in ("55P03", "57014"):
        return ReviewServiceError("LOCK_TIMEOUT")
    return ReviewServiceError("DATABASE_OPERATION_FAILED")

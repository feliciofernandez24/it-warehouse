class StockError(ValueError):
    """Rejected request; no portion of the posting commits."""


class AuthorizationError(StockError):
    pass


class IdempotencyConflict(StockError):
    pass

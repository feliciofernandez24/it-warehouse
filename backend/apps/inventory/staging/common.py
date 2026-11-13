"""Canonical serialization and sanitized failures shared by staging."""
import hashlib
import json


class StagingError(ValueError):
    """The message is always a code, never input content or a filesystem path."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(value):
    def validate(v):
        if isinstance(v, float):
            raise StagingError("NONCANONICAL_NUMBER")
        if v is None or type(v) in (str, bool, int):
            return
        if isinstance(v, list):
            for x in v:
                validate(x)
            return
        if isinstance(v, dict) and all(type(k) is str for k in v):
            for x in v.values():
                validate(x)
            return
        raise StagingError("NONCANONICAL_TYPE")
    validate(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

"""Isolated adapter contract only. Shared Django identity has no trusted verifier."""
import hashlib
import os
import uuid
from apps.inventory.review.services import _payload

CODES=frozenset({"IDENTITY_VERIFICATION_UNAVAILABLE","ACTION_DISABLED","INVALID_REQUEST",
    "UNSUPPORTED_TRANSACTION","ACCESS_DENIED","REQUEST_CONFLICT","VERSION_CONFLICT",
    "REVISION_STATE_INVALID","DATABASE_OPERATION_FAILED","LOCK_TIMEOUT","GATEWAY_UNAVAILABLE"})

class GatewayError(Exception):
    def __init__(self,code):
        self.code=code if code in CODES else "DATABASE_OPERATION_FAILED"
        super().__init__(self.code)

def inspect_metadata(connection,*,action,request_id,revision_id,expected_version,payload=None,
                     isolated_db_principal=False):
    # No request.user/actor_id/GUC is promoted into an independently authenticated identity.
    if not isolated_db_principal or os.environ.get("ITW_REVIEW_READ_PROOF")!="1":
        raise GatewayError("IDENTITY_VERIFICATION_UNAVAILABLE")
    try:
        request_id=uuid.UUID(str(request_id)); revision_id=uuid.UUID(str(revision_id))
        if type(expected_version) is not int or not 1<=expected_version<2**63:
            raise ValueError
        data=_payload({} if payload is None else payload)
    except Exception:
        raise GatewayError("INVALID_REQUEST") from None
    try:
        with connection.transaction():
            connection.execute("SET LOCAL lock_timeout='2s'")
            connection.execute("SET LOCAL statement_timeout='5s'")
            result=connection.execute("SELECT itw_read_poc.inspect_v1(%s,%s,%s,%s,%s)",
                (action,request_id,revision_id,expected_version,hashlib.sha256(data).hexdigest())).fetchone()[0]
    except Exception as error:
        code="LOCK_TIMEOUT" if getattr(error,"sqlstate",None) in ("55P03","57014") else "DATABASE_OPERATION_FAILED"
        raise GatewayError(code) from None
    if "code" in result:
        raise GatewayError(result["code"])
    return result
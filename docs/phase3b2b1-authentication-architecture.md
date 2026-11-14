# Phase 3B.2B.1 authentication architecture

Status: internal authorization foundation implemented; all registration and review writes unavailable.
No endpoint, permission provisioning, deployment setting, or administrator grant was added.

## Authenticated actor boundary

Trusted application code passes its authenticated Django request/session User as the keyword
`actor`. Never construct this object from a request body, actor ID, custom GUC, uploaded evidence,
or a staging row. The helper rejects anonymous users, non-User objects, unsaved objects and
database-alias mismatches. It reloads active status and explicit permission grants for each call.
Django staff/superuser flags confer no authority here; neither has_perm nor cached permission
sets are consulted. Direct and group grants are joined to the inventory ImportBatch content type.

A saved ORM User is not cryptographic evidence of a human login. A compromised application can
construct such an object, alter its state or supply another database identity. Correct session
authentication, CSRF enforcement for future session endpoints, trusted caller isolation, and
credential protection remain deployment requirements. No HTTP endpoints are introduced here.
The default Django session/DRF configuration is preserved, not newly security-certified.

## Permission matrix

| Interface | Required explicit permission | Evidence permission |
| --- | --- | --- |
| register_verified_capture | inventory.capture_import | Not read by this reserved interface |
| start_preparation | inventory.prepare_import | inventory.view_import_evidence |
| edit_preparation | inventory.prepare_import | inventory.view_import_evidence |
| submit_for_review | inventory.prepare_import | inventory.view_import_evidence |
| record_review | inventory.review_import | inventory.view_import_evidence |
| return_for_correction | inventory.review_import | inventory.view_import_evidence |
| reject_revision | inventory.review_import | inventory.view_import_evidence |
| approve_revision | Hard-disabled | No permission enables issuance |
| revoke_approval | Hard-disabled | No permission enables issuance |
| promote_import | Hard-disabled | No permission enables posting |

The authorization helper recognizes capture, prepare, review, approve, revoke and view-evidence
capabilities. Recognition of an approve/revoke permission is not permission to issue events.
promote_import is not a supported authorization capability in this foundation.

## Independent review

require_independent_reviewer requires review and evidence permissions, checks the current active
user, then rejects the batch uploader, revision creator and any current/inherited participant.
It returns only revision/batch identifiers, state and version. Participant history is read,
never edited; the existing database immutability/inheritance guards remain authoritative.
No confidential evidence-fetching service is introduced. Future evidence reads require their own
explicit access check and sanitized output policy.

## Interface contract

All seven reserved write functions accept keyword arguments: actor, request_id, payload,
optional revision_id and expected_version, and a server-selected database alias.
Capture has no revision/version; other actions require a UUID revision and positive integer version.
Payloads are bounded canonical JSON objects, reject reserved actor/identity keys and unsupported
types, and are never included in errors. These interfaces validate a read-only preflight then
raise GATEWAY_UNAVAILABLE. They do not register captures, prepare rows, submit snapshots or review
inventory. APPROVE/REVOKE/promotion fail immediately with ACTION_DISABLED.

inspect_request is a read-only diagnostic, not an authorization token. Its metadata can become
stale as soon as its transaction ends. Callers must never use it to authorize subsequent direct
ORM/SQL writes. It can report an exact historical event identifier after current authorization
and independence checks. The write interfaces still fail closed, including for historical retries.

Errors expose a fixed code and retryable boolean. Driver SQL, raw payloads, user names and
evidence paths are excluded. Deadlock/serialization failures map to RETRYABLE_TRANSACTION;
lock/statement cancellation maps to LOCK_TIMEOUT. No automatic retry is performed.

## Limits

Fresh reads avoid stale Django caches; they do not provide race-safe authorization against
concurrent permission, group, user-active, or master-data changes. No shared coordination protocol
for those writers has been implemented. Request user provenance is a trusted application boundary.
No real candidate has been evaluated or advanced by this code.

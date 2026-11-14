# Phase 3B.2D.2 readiness decision

Date: 2026-11-14; develop at 922e84c.

**NO-GO for executing development deployment now. NO-GO for operational review reads or capture. GO for the isolated metadata-read architecture as a basis for independent review.**

## Established

- A function-owning NOLOGIN role can read only required metadata columns without owning review tables or obtaining DML/UPDATE-for-lock privileges.
- Actual nonowner LOGIN roles cannot read confidential evidence directly, alter/truncate protected objects, assume owner identities or call private authorization helpers.
- Scope, independence, fresh permission checks and request history can be inspected without returning workbook cells, drafts, snapshots, storage keys, event reasons/details/signatures or participant identities.
- The gateway cannot register a source, issue a review event or promote stock. It returns diagnostic metadata only.
- A real shared Django runtime with EXECUTE remains denied because no trusted human identity binding exists.
- Existing stock/session/audit behavior and integrity guards remain compatible with the read grant envelope.

## Blocking decisions and prerequisites

| Dependency | State / required resolution |
| --- | --- |
| Independent human authentication | BLOCKED: per-login synthetic mappings are not a broker for shared Django credentials. Select and independently review an actual verifier/session binding; keep shared runtime unmapped |
| Application integration | NOT IMPLEMENTED: B.1 still performs direct ORM review reads. The isolated adapter fails closed by default. Replace those reads only after identity/scoping is proven; never fall back to broad SELECT |
| Batch entitlement policy | PROPOSED: administrator-owned explicit scopes work in the proof. Production ownership, revocation, administration and audit policy require approval |
| Authority concurrency | PARTIALLY VERIFIED: one cooperating direct-permission revocation race passes. All auth, group, active-user, scope and key writers require the shared lock protocol |
| Gateway deployment packaging | NOT IMPLEMENTED: no migration, startup installer or production provisioning script. The proof SQL must not be installed in development |
| Runtime/migration configuration split | PROPOSED only: Compose currently shares .env and settings read POSTGRES_USER/PASSWORD. Separate service/job secrets and restricted admin routes must be prepared/reviewed |
| Existing schema migration rollout | Rehearsed previously on a verified restore; current synthetic fresh migration also passes. A CURRENT backup/restore and maintenance-window authorization are still required |
| Capture write architecture | Still blocked by identity, cryptographic/serialization/storage prerequisites and the earlier write-owner policy decision; this read design grants no write authority |

Read-only ownership itself introduces no new review-table ownership conflict: its definer does not own application tables. The separate writable capture-owner proposal remains unresolved.

## Deployment decision boundaries

A later, separately authorized maintenance change could apply only inventory.0002/.0003 and transition stock/session/audit traffic to a reviewed restricted runtime while all review/capture paths remain explicitly disabled. That narrower rollout still requires the configuration, administrative-route, backup/recovery and operational checks in the [deployment plan](phase3b2d2-role-and-migration-deployment-plan.md).

Enabling review metadata access is a separate gate. It requires trusted identity and scoped authorization before B.1 integration, plus independent security review. Installing the synthetic per-user login registry or making isolated_db_principal a production request flag is not an acceptable shortcut.

The current authorization is preparation and disposable testing only. No persistent migration, credential/ACL/owner change, inventory.0004, operational endpoint, production deployment, commit or push was performed. Prior uncommitted runtime-role work remains intact. Test and command details are in [security validation](phase3b2d2-security-validation.md).
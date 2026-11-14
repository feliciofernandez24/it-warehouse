# Runtime database role separation: tested grant matrix

Date: 2026-11-14. Scope: actual Django authentication/session, Phase 2C stock and audit foundation services, and an isolated synthetic review-owner proof over the verified restored backup. This is a documented deployment candidate, not a production provisioning script.

## Role and database boundary

| Principal | Rehearsal authority |
| --- | --- |
| itw_django_rehearsal | LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOINHERIT, NOBYPASSRLS; no role memberships, table/schema ownership or grant option |
| it_warehouse | NOLOGIN object/database owner reconstructed in the disposable cluster; owns original tables and review migrations in the ordinary migrated restore |
| itw_rehearsal_migrator | Separate restricted LOGIN, allowed to SET ROLE it_warehouse for migrations and synthetic fixture setup; never available to Django runtime |
| itw_review_rehearsal_owner | NOLOGIN, no superuser/role administration/bypass authority; owns exactly the seven review/import tables and synthetic definer function in the gateway comparison clone |
| postgres | Disposable-cluster administrator only; restores backup and installs rehearsal ACLs/ownership changes |

Runtime receives database CONNECT and public schema USAGE only. PUBLIC CONNECT/TEMP and public schema CREATE are removed in each disposable comparison database. Runtime cannot CREATE TEMP objects, create schemas/tables, ALTER tables, disable triggers, TRUNCATE protected data, change replication role or SET ROLE to any owner/migrator. NOINHERIT alone is insufficient: membership must also be absent, as verified here. [PostgreSQL role membership](https://www.postgresql.org/docs/17/role-membership.html).

## Exact table privileges exercised

S = SELECT; I = INSERT; U = UPDATE as specified; D = DELETE. A dash means no grant. All listed grants target explicit objects. No ALL TABLES, ALL SEQUENCES, broad default privileges or owner-role membership is used.

| Table(s) | S | I | U | D | Purpose |
| --- | --- | --- | --- | --- | --- |
| auth_user | yes | — | last_login, password only | — | Django authentication, automatic password-hash upgrade and login timestamp |
| auth_group, auth_permission, auth_user_groups, auth_user_user_permissions, auth_group_permissions, django_content_type | yes | — | — | — | Fresh application permission joins and Django auth/admin reads |
| django_admin_log | yes | — | — | — | Existing admin index recent-action rendering |
| django_session | yes | yes | session_data, expire_date | yes | Login/session save/logout |
| accounts_assetrecipient, warehouse_warehouse, warehouse_storagelocation | yes | — | — | — | Active recipient/location checks, custody, hierarchy/audit reads |
| inventory_productmodel | yes | — | version only | — | Product read and SELECT FOR UPDATE |
| inventory_asset | yes | yes | condition, lifecycle_status, current_location_id, version, updated_at | — | Serialized receipt/issue/return/transfer |
| inventory_stockbalance | yes | yes | quantity, version, updated_at | — | Bucket creation and guarded debits/credits |
| transactions_stockoperation | yes | yes | posted_at, approved_by_id, approved_at, approval_reason | — | Existing operation completion and existing stock approval service compatibility |
| transactions_stockmovement | yes | yes | id only, for row locks; actual UPDATE rejected by guard | — | Append-only ledger and return/reversal locking |
| transactions_assetassignment | yes | yes | returned_at, returned_by_id, return_movement_id, updated_at | — | Custody creation/return |
| audits_physicalinventoryaudit | yes | yes | status, started_at, updated_at | — | Draft/start/counting foundation |
| audits_auditline | yes | yes | table UPDATE, required by current save() | — | Snapshot creation and observed count recording |
| inventory_importbatch, inventory_importstagingrecord and five new review tables | — | — | — | — | Confidential evidence isolated; future gateway access only |
| django_migrations | — | — | — | — | Migration administration excluded |
| Other catalog tables, audits_assetchangelog and unlisted tables | — | — | — | — | No implemented-path requirement demonstrated in this rehearsal |

Django's AuditLine.save() currently sends all model columns. The table UPDATE grant is therefore necessary for that unmodified service, but immutable snapshot/count guards still apply; a changed expected_quantity after counting is rejected. A future service change using update_fields could reduce this grant further; no stock/audit service was changed here.

The existing stock approval columns are included because approve_operation writes them. This stage did not issue stock adjustments/disposals or exercise positive approval issuance. It tested ordinary posting and rejection/immutability safeguards. No import APPROVE, REVOKE or PROMOTED functionality was introduced or enabled.

## Row locks are not writes

The first candidate omitted movement UPDATE rights and failed both bulk and serialized return paths at StockMovement.select_for_update(). UPDATE(id) permits that lock without permitting a ledger rewrite: the existing history trigger rejects even SET id=id with SQLSTATE 23514. ProductModel similarly needs UPDATE(version) for its row lock, not a grant to change product names/tracking mode. PostgreSQL requires UPDATE on at least one column for these locking SELECTs. [PostgreSQL 17 SELECT](https://www.postgresql.org/docs/17/sql-select.html).

Column privileges are separate from full-table privileges; do not infer a required full-table UPDATE grant from has_table_privilege alone. Actual role_column_grants are recorded in the evidence JSON. [PostgreSQL 17 GRANT](https://www.postgresql.org/docs/17/sql-grant.html).

Adversarial tests temporarily add ledger UPDATE/DELETE to prove the guard layer remains effective, then revoke them and restore the original narrow column grant. No extra privileges remain afterward. The required UPDATE(id) grant is present in final evidence for all three stages.

## Sequences and SQL helpers

Runtime receives USAGE only on these identity sequences:

- inventory_asset_id_seq
- inventory_stockbalance_id_seq
- transactions_stockmovement_id_seq
- transactions_assetassignment_id_seq
- audits_physicalinventoryaudit_id_seq
- audits_auditline_id_seq

StockOperation uses a UUID; django_session uses its string key. Auth/catalog/import/review sequence access is denied. No sequence UPDATE/setval grant is given.

Only public.itw_can(bigint,text), public.itw_scope(bigint,boolean) and public.itw_frozen(bigint) receive direct runtime EXECUTE among the existing Phase 2C helpers. The rehearsal revokes PUBLIC and runtime EXECUTE on the explicit 19-function stock-helper list, then grants those three nested helpers. Unchanged triggers still execute; a direct runtime itw_engine_lock() call is denied. No trigger definition, guard body or stock lock ordering changed.

Review helper EXECUTE remains denied to runtime after inventory.0003. In the gateway clone only, runtime receives USAGE on fa_owner and EXECUTE on fa_owner.enroll(bigint,uuid). That function creates only synthetic revision/event evidence over preseeded dummy rows. It is not an authenticated capture API and must not be deployed.

## Limits and deployment decision

This matrix covers the tested current paths, not arbitrary future CRUD. Django auth user/group administration, untested password-reset routes, master-data editing, review preflight/evidence reads and operational capture need separately designed access paths. Do not add owner/migrator membership or broad table grants to make those routes work.

**GO for the tested role-separation mechanism; NO-GO for an unqualified application-wide rollout.** See [rehearsal results and required configuration changes](runtime-role-separation-rehearsal.md).
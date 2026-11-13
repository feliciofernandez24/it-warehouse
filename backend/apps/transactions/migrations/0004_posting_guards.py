"""Posting guards; final-state constraints defer intermediate coherence."""
from django.db import migrations

FORWARD_SQL = r"""
-- Fail closed rather than adopt unposted legacy positions/history without a reviewed cutover.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM inventory_asset) OR EXISTS(SELECT 1 FROM transactions_stockmovement)
 OR EXISTS(SELECT 1 FROM inventory_stockbalance WHERE quantity<>0)
 OR EXISTS(SELECT 1 FROM audits_physicalinventoryaudit WHERE status IN ('COUNTING','SUBMITTED')) THEN
  RAISE EXCEPTION 'Phase 2C requires a reviewed cutover for existing stock/history or active audits';
 END IF;
END $$;
ALTER FUNCTION itw_assignment_identity_guard() SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION itw_reject_history_change() SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION itw_asset_identity_guard() SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION itw_bucket_identity_guard() SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION itw_tracking_guard() SET search_path=pg_catalog,public,pg_temp;
ALTER FUNCTION itw_product_mode_guard() SET search_path=pg_catalog,public,pg_temp;

-- No SECURITY DEFINER functions and no privilege changes. All functions use invoker rights.
CREATE FUNCTION itw_engine_lock() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 PERFORM pg_advisory_xact_lock(73921,2);
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER engine_lock BEFORE INSERT OR UPDATE OR DELETE ON inventory_stockbalance FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();
CREATE TRIGGER engine_lock BEFORE INSERT OR UPDATE OR DELETE ON inventory_asset FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();
CREATE TRIGGER engine_lock BEFORE INSERT OR UPDATE OR DELETE ON transactions_stockmovement FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();
CREATE TRIGGER engine_lock BEFORE INSERT OR UPDATE OR DELETE ON transactions_stockoperation FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();
CREATE TRIGGER engine_lock BEFORE INSERT OR UPDATE OR DELETE ON transactions_assetassignment FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();
CREATE TRIGGER engine_lock BEFORE INSERT OR UPDATE OR DELETE ON audits_physicalinventoryaudit FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();
CREATE TRIGGER engine_lock BEFORE INSERT OR UPDATE OR DELETE ON audits_auditline FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();
CREATE TRIGGER engine_lock BEFORE INSERT OR UPDATE OR DELETE ON warehouse_storagelocation FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();

CREATE TRIGGER engine_lock BEFORE UPDATE ON inventory_productmodel FOR EACH STATEMENT EXECUTE FUNCTION itw_engine_lock();

CREATE FUNCTION itw_scope(root_id bigint, descendants boolean) RETURNS TABLE(id bigint)
LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 WITH RECURSIVE scope(id) AS (
 SELECT root_id UNION ALL
 SELECT l.id FROM public.warehouse_storagelocation l JOIN scope s ON l.parent_id=s.id WHERE descendants
 ) SELECT id FROM scope
$$;
CREATE FUNCTION itw_frozen(location_id bigint) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM public.audits_physicalinventoryaudit a
 CROSS JOIN LATERAL public.itw_scope(a.scope_location_id,a.include_descendants) s
 WHERE a.status IN ('COUNTING','SUBMITTED') AND s.id=location_id)
$$;
CREATE FUNCTION itw_freeze_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE source_id bigint; target_id bigint;
BEGIN
 IF TG_TABLE_NAME='inventory_stockbalance' THEN
  IF TG_OP='UPDATE' AND NEW.quantity=OLD.quantity THEN RETURN NEW; END IF;
  source_id:=CASE WHEN TG_OP='INSERT' THEN NEW.location_id ELSE OLD.location_id END;
  IF TG_OP<>'DELETE' THEN target_id:=NEW.location_id; END IF;
 ELSIF TG_TABLE_NAME='inventory_asset' THEN
  IF TG_OP='UPDATE' AND (NEW.current_location_id,NEW.condition,NEW.lifecycle_status) IS NOT DISTINCT FROM (OLD.current_location_id,OLD.condition,OLD.lifecycle_status) THEN RETURN NEW; END IF;
  IF TG_OP<>'INSERT' THEN source_id:=OLD.current_location_id; END IF;
  IF TG_OP<>'DELETE' THEN target_id:=NEW.current_location_id; END IF;
 ELSE
  source_id:=NEW.source_location_id; target_id:=NEW.destination_location_id;
 END IF;
 IF public.itw_frozen(source_id) OR public.itw_frozen(target_id) THEN
  RAISE EXCEPTION 'Stock scope is frozen by an active audit' USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER freeze_guard BEFORE INSERT OR UPDATE OR DELETE ON inventory_stockbalance FOR EACH ROW EXECUTE FUNCTION itw_freeze_guard();
CREATE TRIGGER freeze_guard BEFORE INSERT OR UPDATE OR DELETE ON inventory_asset FOR EACH ROW EXECUTE FUNCTION itw_freeze_guard();
CREATE TRIGGER freeze_guard BEFORE INSERT ON transactions_stockmovement FOR EACH ROW EXECUTE FUNCTION itw_freeze_guard();

CREATE FUNCTION itw_audit_scope_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP='INSERT' AND NEW.status<>'DRAFT' THEN RAISE EXCEPTION 'Audits must start as drafts' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' THEN
  IF OLD.status='DRAFT' AND NEW.status NOT IN ('DRAFT','COUNTING','CANCELLED')
   OR OLD.status='COUNTING' AND NEW.status NOT IN ('COUNTING','SUBMITTED','CANCELLED') THEN
   RAISE EXCEPTION 'Invalid audit transition; reconciliation closing is not enabled' USING ERRCODE='23514'; END IF;
  IF OLD.status IN ('SUBMITTED','APPROVED','REJECTED','CANCELLED') AND NEW IS DISTINCT FROM OLD THEN
   RAISE EXCEPTION 'Submitted and closed audit evidence requires a future controlled closing workflow' USING ERRCODE='23514';
  END IF;
  IF OLD.status='COUNTING' AND (NEW.scope_location_id,NEW.include_descendants,NEW.performed_by_id,NEW.started_at) IS DISTINCT FROM (OLD.scope_location_id,OLD.include_descendants,OLD.performed_by_id,OLD.started_at) THEN
   RAISE EXCEPTION 'Active scope identity is immutable' USING ERRCODE='23514';
  END IF;
 END IF;
 IF NEW.status IN ('COUNTING','SUBMITTED') AND EXISTS(
  SELECT 1 FROM public.audits_physicalinventoryaudit a
  CROSS JOIN LATERAL public.itw_scope(a.scope_location_id,a.include_descendants) x
  JOIN public.itw_scope(NEW.scope_location_id,NEW.include_descendants) y ON y.id=x.id
  WHERE a.id<>NEW.id AND a.status IN ('COUNTING','SUBMITTED')
 ) THEN RAISE EXCEPTION 'Overlapping active audit scopes' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER scope_guard BEFORE INSERT OR UPDATE ON audits_physicalinventoryaudit FOR EACH ROW EXECUTE FUNCTION itw_audit_scope_guard();
CREATE FUNCTION itw_audit_line_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE status text;
BEGIN
 SELECT a.status INTO status FROM public.audits_physicalinventoryaudit a WHERE a.id=NEW.audit_id;
 IF status<>'COUNTING' THEN RAISE EXCEPTION 'Counts may only be recorded while counting' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND (
  (NEW.audit_id,NEW.asset_id,NEW.product_model_id,NEW.stock_balance_id,NEW.expected_location_id,NEW.location_id,NEW.expected_quantity,NEW.expected_condition,NEW.expected_stock_state)
  IS DISTINCT FROM (OLD.audit_id,OLD.asset_id,OLD.product_model_id,OLD.stock_balance_id,OLD.expected_location_id,OLD.location_id,OLD.expected_quantity,OLD.expected_condition,OLD.expected_stock_state)
  OR OLD.counted_at IS NOT NULL
 ) THEN RAISE EXCEPTION 'Expected snapshots and recorded observations are immutable' USING ERRCODE='23514'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.audits_physicalinventoryaudit a CROSS JOIN LATERAL public.itw_scope(a.scope_location_id,a.include_descendants) s WHERE a.id=NEW.audit_id AND s.id=NEW.location_id) THEN
  RAISE EXCEPTION 'Audit line outside scope' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER evidence_guard BEFORE INSERT OR UPDATE ON audits_auditline FOR EACH ROW EXECUTE FUNCTION itw_audit_line_guard();
CREATE FUNCTION itw_hierarchy_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE parent_row public.warehouse_storagelocation%ROWTYPE;
BEGIN
 IF TG_OP='UPDATE' AND (NEW.parent_id,NEW.warehouse_id,NEW.kind,NEW.is_active) IS NOT DISTINCT FROM (OLD.parent_id,OLD.warehouse_id,OLD.kind,OLD.is_active) THEN RETURN NEW; END IF;
 IF EXISTS(SELECT 1 FROM public.audits_physicalinventoryaudit WHERE status IN ('COUNTING','SUBMITTED')) THEN
  RAISE EXCEPTION 'Hierarchy changes are blocked during active audits' USING ERRCODE='23514';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 IF TG_OP='UPDATE' AND (NEW.warehouse_id<>OLD.warehouse_id OR NOT NEW.is_active) AND (
  EXISTS(SELECT 1 FROM public.inventory_asset WHERE current_location_id=OLD.id)
  OR EXISTS(SELECT 1 FROM public.inventory_stockbalance WHERE location_id=OLD.id AND quantity>0)
  OR EXISTS(SELECT 1 FROM public.warehouse_storagelocation WHERE parent_id=OLD.id)
 ) THEN RAISE EXCEPTION 'Occupied locations cannot be moved between warehouses or deactivated' USING ERRCODE='23514'; END IF;
 IF NEW.parent_id IS NOT NULL THEN
  SELECT * INTO parent_row FROM public.warehouse_storagelocation WHERE id=NEW.parent_id;
  IF parent_row.warehouse_id<>NEW.warehouse_id OR NOT parent_row.is_active
   OR NOT (parent_row.kind='AREA' OR parent_row.kind='RACK' AND NEW.kind IN ('SHELF','BIN') OR parent_row.kind='SHELF' AND NEW.kind='BIN')
   OR EXISTS(SELECT 1 FROM public.itw_scope(NEW.id,true) WHERE id=NEW.parent_id)
  THEN RAISE EXCEPTION 'Invalid parent warehouse, kind, active state or cycle' USING ERRCODE='23514'; END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM public.warehouse_storagelocation c WHERE c.parent_id=NEW.id AND NOT (NEW.kind='AREA' OR NEW.kind='RACK' AND c.kind IN ('SHELF','BIN') OR NEW.kind='SHELF' AND c.kind='BIN')) THEN
  RAISE EXCEPTION 'Location kind invalidates children' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER hierarchy_guard BEFORE INSERT OR UPDATE OR DELETE ON warehouse_storagelocation FOR EACH ROW EXECUTE FUNCTION itw_hierarchy_guard();

CREATE FUNCTION itw_operation_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF (NEW.operation_key,NEW.request,NEW.fingerprint,NEW.requested_by_id,NEW.requested_at)
 IS DISTINCT FROM (OLD.operation_key,OLD.request,OLD.fingerprint,OLD.requested_by_id,OLD.requested_at)
 OR OLD.posted_at IS NOT NULL
 OR OLD.approved_at IS NOT NULL AND (NEW.approved_by_id,NEW.approved_at,NEW.approval_reason) IS DISTINCT FROM (OLD.approved_by_id,OLD.approved_at,OLD.approval_reason)
 THEN RAISE EXCEPTION 'Operation identity, approval and committed results are immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER operation_guard BEFORE UPDATE ON transactions_stockoperation FOR EACH ROW EXECUTE FUNCTION itw_operation_guard();
CREATE TRIGGER history_no_delete BEFORE DELETE ON transactions_stockoperation FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();

CREATE FUNCTION itw_can(user_id bigint, capability text) RETURNS boolean LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM public.auth_user u WHERE u.id=user_id AND u.is_active AND EXISTS(
 SELECT 1 FROM public.auth_permission p JOIN public.django_content_type c ON c.id=p.content_type_id
 WHERE c.app_label='transactions' AND p.codename=capability AND (
 EXISTS(SELECT 1 FROM public.auth_user_user_permissions up WHERE up.user_id=u.id AND up.permission_id=p.id)
 OR EXISTS(SELECT 1 FROM public.auth_user_groups ug JOIN public.auth_group_permissions gp ON gp.group_id=ug.group_id WHERE ug.user_id=u.id AND gp.permission_id=p.id))))
$$;
CREATE FUNCTION itw_movement_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE operation public.transactions_stockoperation%ROWTYPE; original public.transactions_stockmovement%ROWTYPE; b public.inventory_stockbalance%ROWTYPE; a public.inventory_asset%ROWTYPE; used bigint; payload jsonb; capability text;
BEGIN
 SELECT * INTO operation FROM public.transactions_stockoperation WHERE operation_key=NEW.operation_key FOR UPDATE;
 IF NOT FOUND OR operation.posted_at IS NOT NULL OR operation.requested_by_id<>NEW.actor_id THEN
  RAISE EXCEPTION 'Movement requires an open operation owned by its actor' USING ERRCODE='23514'; END IF;
 IF NEW.line_number>jsonb_array_length(operation.request->'lines') OR operation.request->'lines'->(NEW.line_number-1)->>'operation_type' IS DISTINCT FROM NEW.operation_type
 OR (operation.request->'lines'->(NEW.line_number-1)->>'quantity')::bigint IS DISTINCT FROM NEW.quantity
 OR NEW.reason IS DISTINCT FROM operation.request->>'reason' OR NEW.external_reference IS DISTINCT FROM operation.request->>'external_reference'
 THEN RAISE EXCEPTION 'Movement does not match complete request' USING ERRCODE='23514'; END IF;
 payload:=operation.request->'lines'->(NEW.line_number-1);
 capability:=CASE NEW.operation_type WHEN 'STOCK_IN' THEN 'receive_stock' WHEN 'STOCK_OUT' THEN 'issue_stock' WHEN 'TRANSFER' THEN 'transfer_stock' WHEN 'RETURN' THEN 'return_stock' WHEN 'DISPOSAL' THEN 'request_disposal' ELSE 'request_adjustment' END;
 IF NOT public.itw_can(NEW.actor_id,capability) THEN RAISE EXCEPTION 'Explicit movement permission required' USING ERRCODE='23514'; END IF;
 IF (NEW.source_location_id,NEW.destination_location_id) IS DISTINCT FROM ((payload->>'source_location_id')::bigint,(payload->>'destination_location_id')::bigint)
 OR payload->>'asset_id' IS NOT NULL AND NEW.asset_id IS DISTINCT FROM (payload->>'asset_id')::bigint
 OR payload->>'asset_id' IS NULL AND NEW.asset_id IS NULL AND NEW.product_model_id IS DISTINCT FROM (payload->>'product_model_id')::bigint
 OR NEW.reverses_id IS DISTINCT FROM (payload->>'reverses_id')::bigint
 THEN RAISE EXCEPTION 'Movement target differs from approved request' USING ERRCODE='23514'; END IF;
 IF NEW.operation_type IN ('ADJUSTMENT_IN','ADJUSTMENT_OUT','DISPOSAL') AND NOT public.itw_can(operation.approved_by_id,CASE WHEN NEW.operation_type='DISPOSAL' THEN 'approve_disposal' ELSE 'approve_adjustment' END) THEN
  RAISE EXCEPTION 'Approver requires current explicit permission' USING ERRCODE='23514'; END IF;
 IF NEW.operation_type IN ('ADJUSTMENT_IN','ADJUSTMENT_OUT','DISPOSAL') AND (operation.approved_at IS NULL OR operation.approved_by_id=NEW.actor_id) THEN
  RAISE EXCEPTION 'Separate durable approval required' USING ERRCODE='23514'; END IF;
 IF NEW.audit_line_id IS NOT NULL OR NEW.import_row_id IS NOT NULL THEN
  RAISE EXCEPTION 'Audit correction and import posting are not enabled' USING ERRCODE='23514'; END IF;
 IF NEW.source_balance_id IS NOT NULL THEN
  SELECT * INTO b FROM public.inventory_stockbalance WHERE id=NEW.source_balance_id;
  IF (b.product_model_id,b.location_id) IS DISTINCT FROM (NEW.product_model_id,NEW.source_location_id) THEN RAISE EXCEPTION 'Source bucket mismatch' USING ERRCODE='23514'; END IF;
  IF (b.condition,b.stock_state) IS DISTINCT FROM (payload->>'source_condition',payload->>'source_state') THEN RAISE EXCEPTION 'Source bucket differs from request' USING ERRCODE='23514'; END IF;
  IF NEW.operation_type='STOCK_OUT' AND b.stock_state<>'AVAILABLE' THEN RAISE EXCEPTION 'Quarantined stock cannot be issued' USING ERRCODE='23514'; END IF;
 END IF;
 IF NEW.destination_balance_id IS NOT NULL THEN
  SELECT * INTO b FROM public.inventory_stockbalance WHERE id=NEW.destination_balance_id;
  IF (b.condition,b.stock_state) IS DISTINCT FROM (payload->>'condition',payload->>'state') THEN RAISE EXCEPTION 'Destination bucket differs from request' USING ERRCODE='23514'; END IF;
  IF (b.product_model_id,b.location_id) IS DISTINCT FROM (NEW.product_model_id,NEW.destination_location_id) THEN RAISE EXCEPTION 'Destination bucket mismatch' USING ERRCODE='23514'; END IF;
 END IF;
 IF NEW.asset_id IS NOT NULL THEN
  SELECT * INTO a FROM public.inventory_asset WHERE id=NEW.asset_id FOR UPDATE;
  IF NEW.condition_after IS DISTINCT FROM (CASE WHEN NEW.destination_location_id IS NOT NULL THEN payload->>'condition' ELSE a.condition END)
   OR NEW.destination_location_id IS NOT NULL AND NEW.lifecycle_after IS DISTINCT FROM payload->>'state'
   OR payload->>'asset_id' IS NULL AND (a.product_model_id,a.device_name,a.serial_raw) IS DISTINCT FROM ((payload->>'product_model_id')::bigint,payload->>'device_name',payload->>'serial_raw')
  THEN RAISE EXCEPTION 'Asset result differs from request' USING ERRCODE='23514'; END IF;
  IF NEW.operation_type='STOCK_IN' THEN
   IF EXISTS(SELECT 1 FROM public.transactions_stockmovement WHERE asset_id=NEW.asset_id) OR NEW.condition_before IS NOT NULL OR NEW.lifecycle_before IS NOT NULL THEN RAISE EXCEPTION 'Asset receipt must be its first movement' USING ERRCODE='23514'; END IF;
  ELSE
   IF (a.current_location_id,a.condition,a.lifecycle_status) IS DISTINCT FROM (NEW.source_location_id,NEW.condition_before,NEW.lifecycle_before)
    OR a.lifecycle_status IN ('LOST','DISPOSED') THEN RAISE EXCEPTION 'Asset source snapshot mismatch or terminal state' USING ERRCODE='23514'; END IF;
  END IF;
  IF NEW.operation_type='STOCK_OUT' AND NOT EXISTS(SELECT 1 FROM public.inventory_productmodel WHERE id=a.product_model_id AND is_active) THEN RAISE EXCEPTION 'Inactive product cannot be issued' USING ERRCODE='23514'; END IF;
  IF NEW.operation_type='STOCK_OUT' AND (a.lifecycle_status<>'AVAILABLE' OR NEW.lifecycle_after<>'ASSIGNED')
   OR NEW.operation_type='RETURN' AND (a.lifecycle_status<>'ASSIGNED' OR NEW.lifecycle_after NOT IN ('AVAILABLE','QUARANTINED'))
   OR NEW.operation_type='DISPOSAL' AND NEW.lifecycle_after<>'DISPOSED'
   OR NEW.operation_type='ADJUSTMENT_OUT' AND NEW.lifecycle_after<>'LOST'
   OR NEW.operation_type IN ('STOCK_IN','TRANSFER') AND NEW.lifecycle_after NOT IN ('AVAILABLE','QUARANTINED')
  THEN RAISE EXCEPTION 'Invalid asset lifecycle transition' USING ERRCODE='23514'; END IF;
 END IF;
 IF NEW.operation_type='RETURN' AND NEW.reverses_id IS NULL THEN RAISE EXCEPTION 'Return requires original issue' USING ERRCODE='23514'; END IF;
 IF NEW.reverses_id IS NOT NULL THEN
  SELECT * INTO original FROM public.transactions_stockmovement WHERE id=NEW.reverses_id FOR UPDATE;
  SELECT coalesce(sum(quantity),0) INTO used FROM public.transactions_stockmovement WHERE reverses_id=NEW.reverses_id;
  IF original.reverses_id IS NOT NULL OR used+NEW.quantity>original.quantity
   OR (original.asset_id,original.product_model_id) IS DISTINCT FROM (NEW.asset_id,NEW.product_model_id)
   OR NEW.operation_type='RETURN' AND original.operation_type<>'STOCK_OUT'
   OR NEW.operation_type<>'RETURN' AND (NEW.source_location_id,NEW.destination_location_id) IS DISTINCT FROM (original.destination_location_id,original.source_location_id)
  THEN RAISE EXCEPTION 'Invalid or excessive reversal' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER movement_posting_guard BEFORE INSERT ON transactions_stockmovement FOR EACH ROW EXECUTE FUNCTION itw_movement_guard();

CREATE FUNCTION itw_balance_conservation() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE bucket_id bigint; expected numeric; actual bigint;
BEGIN
 bucket_id:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
 SELECT coalesce(sum(CASE WHEN destination_balance_id=bucket_id THEN quantity ELSE 0 END - CASE WHEN source_balance_id=bucket_id THEN quantity ELSE 0 END),0)
 INTO expected FROM public.transactions_stockmovement WHERE source_balance_id=bucket_id OR destination_balance_id=bucket_id;
 SELECT quantity INTO actual FROM public.inventory_stockbalance WHERE id=bucket_id;
 IF actual IS NULL OR actual<>expected THEN RAISE EXCEPTION 'Stock balance must equal immutable ledger' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER balance_conservation AFTER INSERT OR UPDATE OR DELETE ON inventory_stockbalance DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION itw_balance_conservation();
CREATE FUNCTION itw_final_state_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
#variable_conflict use_variable
DECLARE a public.inventory_asset%ROWTYPE; m public.transactions_stockmovement%ROWTYPE; episode public.transactions_assetassignment%ROWTYPE; asset_id bigint; balance_id bigint; expected numeric; actual bigint; op public.transactions_stockoperation%ROWTYPE;
BEGIN
 IF TG_TABLE_NAME='transactions_stockoperation' THEN
  SELECT * INTO op FROM public.transactions_stockoperation WHERE operation_key=NEW.operation_key;
  IF op.posted_at IS NOT NULL AND (SELECT count(*) FROM public.transactions_stockmovement WHERE operation_key=op.operation_key)<>jsonb_array_length(op.request->'lines')
   OR op.posted_at IS NULL AND EXISTS(SELECT 1 FROM public.transactions_stockmovement WHERE operation_key=op.operation_key)
  THEN RAISE EXCEPTION 'Partial operation cannot commit' USING ERRCODE='23514'; END IF;
  RETURN NULL;
 END IF;
 IF TG_TABLE_NAME='inventory_asset' THEN asset_id:=CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END;
 ELSE asset_id:=NEW.asset_id; END IF;
 IF TG_TABLE_NAME='transactions_stockmovement' THEN
  SELECT * INTO op FROM public.transactions_stockoperation WHERE operation_key=NEW.operation_key;
  IF op.posted_at IS NULL THEN RAISE EXCEPTION 'Uncommitted operation movement' USING ERRCODE='23514'; END IF;
  FOREACH balance_id IN ARRAY ARRAY[NEW.source_balance_id,NEW.destination_balance_id] LOOP
   IF balance_id IS NOT NULL THEN
    SELECT coalesce(sum(CASE WHEN destination_balance_id=balance_id THEN quantity ELSE 0 END - CASE WHEN source_balance_id=balance_id THEN quantity ELSE 0 END),0)
    INTO expected FROM public.transactions_stockmovement WHERE source_balance_id=balance_id OR destination_balance_id=balance_id;
    SELECT quantity INTO actual FROM public.inventory_stockbalance WHERE id=balance_id;
    IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'Movement must update its stock buckets' USING ERRCODE='23514'; END IF;
   END IF;
  END LOOP;
 END IF;
 IF asset_id IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO a FROM public.inventory_asset WHERE id=asset_id;
 SELECT * INTO m FROM public.transactions_stockmovement WHERE transactions_stockmovement.asset_id=asset_id ORDER BY id DESC LIMIT 1;
 IF a.id IS NULL OR m.id IS NULL OR (a.current_location_id,a.condition,a.lifecycle_status) IS DISTINCT FROM (m.destination_location_id,m.condition_after,m.lifecycle_after) THEN
  RAISE EXCEPTION 'Asset position must match its latest ledger entry' USING ERRCODE='23514'; END IF;
 SELECT * INTO episode FROM public.transactions_assetassignment WHERE transactions_assetassignment.asset_id=asset_id AND returned_at IS NULL;
 IF (a.lifecycle_status='ASSIGNED') IS DISTINCT FROM (episode.id IS NOT NULL) OR episode.id IS NOT NULL AND episode.issue_movement_id<>m.id THEN
  RAISE EXCEPTION 'Asset lifecycle and active custody disagree' USING ERRCODE='23514'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER asset_final_state AFTER INSERT OR UPDATE OR DELETE ON inventory_asset DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION itw_final_state_guard();
CREATE CONSTRAINT TRIGGER movement_final_state AFTER INSERT ON transactions_stockmovement DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION itw_final_state_guard();
CREATE CONSTRAINT TRIGGER assignment_final_state AFTER INSERT OR UPDATE ON transactions_assetassignment DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION itw_final_state_guard();
CREATE CONSTRAINT TRIGGER operation_complete AFTER INSERT OR UPDATE ON transactions_stockoperation DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION itw_final_state_guard();
CREATE FUNCTION itw_custody_guard() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE issue public.transactions_stockmovement%ROWTYPE; returned public.transactions_stockmovement%ROWTYPE; payload jsonb;
BEGIN
 SELECT * INTO issue FROM public.transactions_stockmovement WHERE id=NEW.issue_movement_id;
 IF (issue.asset_id,issue.operation_type,issue.actor_id,issue.occurred_at) IS DISTINCT FROM (NEW.asset_id,'STOCK_OUT'::varchar,NEW.issued_by_id,NEW.assigned_at) THEN
  RAISE EXCEPTION 'Custody issue evidence mismatch' USING ERRCODE='23514'; END IF;
 SELECT request->'lines'->(issue.line_number-1) INTO payload FROM public.transactions_stockoperation WHERE operation_key=issue.operation_key;
 IF (NEW.recipient_id,NEW.destination_description,NEW.destination_reference,NEW.purpose,NEW.due_at) IS DISTINCT FROM ((payload->>'recipient_id')::bigint,payload->>'destination_description',payload->>'destination_reference',payload->>'purpose',(payload->>'due_at')::timestamptz) THEN
  RAISE EXCEPTION 'Custody differs from approved request' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' AND NOT EXISTS(SELECT 1 FROM public.accounts_assetrecipient WHERE id=NEW.recipient_id AND is_active) THEN
  RAISE EXCEPTION 'Recipient is inactive' USING ERRCODE='23514'; END IF;
 IF NEW.return_movement_id IS NOT NULL THEN
  SELECT * INTO returned FROM public.transactions_stockmovement WHERE id=NEW.return_movement_id;
  IF (returned.asset_id,returned.operation_type,returned.actor_id,returned.occurred_at,returned.reverses_id) IS DISTINCT FROM (NEW.asset_id,'RETURN'::varchar,NEW.returned_by_id,NEW.returned_at,NEW.issue_movement_id) THEN
   RAISE EXCEPTION 'Custody return evidence mismatch' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER custody_evidence BEFORE INSERT OR UPDATE ON transactions_assetassignment FOR EACH ROW EXECUTE FUNCTION itw_custody_guard();
"""

REVERSE_SQL = r"""
ALTER FUNCTION itw_assignment_identity_guard() RESET search_path;
ALTER FUNCTION itw_reject_history_change() RESET search_path;
ALTER FUNCTION itw_asset_identity_guard() RESET search_path;
ALTER FUNCTION itw_bucket_identity_guard() RESET search_path;
ALTER FUNCTION itw_tracking_guard() RESET search_path;
ALTER FUNCTION itw_product_mode_guard() RESET search_path;
DROP TRIGGER custody_evidence ON transactions_assetassignment;
DROP TRIGGER operation_complete ON transactions_stockoperation;
DROP TRIGGER assignment_final_state ON transactions_assetassignment;
DROP TRIGGER movement_final_state ON transactions_stockmovement;
DROP TRIGGER asset_final_state ON inventory_asset;
DROP TRIGGER balance_conservation ON inventory_stockbalance;
DROP TRIGGER movement_posting_guard ON transactions_stockmovement;
DROP TRIGGER history_no_delete ON transactions_stockoperation;
DROP TRIGGER operation_guard ON transactions_stockoperation;
DROP TRIGGER hierarchy_guard ON warehouse_storagelocation;
DROP TRIGGER evidence_guard ON audits_auditline;
DROP TRIGGER scope_guard ON audits_physicalinventoryaudit;
DROP TRIGGER freeze_guard ON transactions_stockmovement;
DROP TRIGGER freeze_guard ON inventory_asset;
DROP TRIGGER freeze_guard ON inventory_stockbalance;
DROP TRIGGER engine_lock ON inventory_productmodel;
DROP TRIGGER engine_lock ON warehouse_storagelocation;
DROP TRIGGER engine_lock ON audits_auditline;
DROP TRIGGER engine_lock ON audits_physicalinventoryaudit;
DROP TRIGGER engine_lock ON transactions_assetassignment;
DROP TRIGGER engine_lock ON transactions_stockoperation;
DROP TRIGGER engine_lock ON transactions_stockmovement;
DROP TRIGGER engine_lock ON inventory_asset;
DROP TRIGGER engine_lock ON inventory_stockbalance;
DROP FUNCTION itw_custody_guard();
DROP FUNCTION itw_final_state_guard();
DROP FUNCTION itw_balance_conservation();
DROP FUNCTION itw_movement_guard();
DROP FUNCTION itw_can(user_id bigint, capability text);
DROP FUNCTION itw_operation_guard();
DROP FUNCTION itw_hierarchy_guard();
DROP FUNCTION itw_audit_line_guard();
DROP FUNCTION itw_audit_scope_guard();
DROP FUNCTION itw_freeze_guard();
DROP FUNCTION itw_frozen(location_id bigint);
DROP FUNCTION itw_scope(root_id bigint, descendants boolean);
DROP FUNCTION itw_engine_lock();
"""

class Migration(migrations.Migration):
    dependencies = [("transactions", "0003_stockoperation")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]

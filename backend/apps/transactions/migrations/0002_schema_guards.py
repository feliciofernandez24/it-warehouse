"""Schema guards only; no posting routines or data changes."""
from django.db import migrations

FORWARD_SQL = """
CREATE FUNCTION itw_assignment_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.asset_id,NEW.recipient_id,NEW.issued_by_id,NEW.assigned_at,NEW.issue_movement_id,
     NEW.destination_description,NEW.destination_reference,NEW.purpose,NEW.due_at)
 IS DISTINCT FROM
    (OLD.asset_id,OLD.recipient_id,OLD.issued_by_id,OLD.assigned_at,OLD.issue_movement_id,
     OLD.destination_description,OLD.destination_reference,OLD.purpose,OLD.due_at)
 OR OLD.returned_at IS NOT NULL THEN
  RAISE EXCEPTION 'Custody identity and closed assignments are immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER assignment_identity_guard BEFORE UPDATE ON transactions_assetassignment
FOR EACH ROW EXECUTE FUNCTION itw_assignment_identity_guard();

CREATE FUNCTION itw_reject_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Historical record in % cannot be %', TG_TABLE_NAME, TG_OP USING ERRCODE='23514';
END;
$$;
CREATE FUNCTION itw_asset_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.asset_tag,NEW.product_model_id) IS DISTINCT FROM (OLD.asset_tag,OLD.product_model_id) THEN
  RAISE EXCEPTION 'Asset tag and catalog identity are immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER asset_identity_guard BEFORE UPDATE ON inventory_asset FOR EACH ROW EXECUTE FUNCTION itw_asset_identity_guard();
CREATE FUNCTION itw_bucket_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.product_model_id,NEW.location_id,NEW.condition,NEW.stock_state)
 IS DISTINCT FROM (OLD.product_model_id,OLD.location_id,OLD.condition,OLD.stock_state) THEN
  RAISE EXCEPTION 'Stock bucket identity is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER bucket_identity_guard BEFORE UPDATE ON inventory_stockbalance FOR EACH ROW EXECUTE FUNCTION itw_bucket_identity_guard();
CREATE FUNCTION itw_tracking_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actual_mode text; expected_mode text;
BEGIN
 IF NEW.product_model_id IS NULL THEN RETURN NEW; END IF;
 expected_mode := CASE WHEN TG_TABLE_NAME='inventory_asset' THEN 'SERIALIZED' ELSE 'BULK' END;
 SELECT tracking_mode INTO actual_mode FROM inventory_productmodel WHERE id=NEW.product_model_id FOR SHARE;
 IF actual_mode IS DISTINCT FROM expected_mode THEN
  RAISE EXCEPTION '% requires % tracking',TG_TABLE_NAME,expected_mode USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE FUNCTION itw_product_mode_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.tracking_mode IS DISTINCT FROM OLD.tracking_mode AND (
 EXISTS(SELECT 1 FROM inventory_asset WHERE product_model_id=OLD.id)
 OR EXISTS(SELECT 1 FROM inventory_stockbalance WHERE product_model_id=OLD.id)
 OR EXISTS(SELECT 1 FROM inventory_stockthreshold WHERE product_model_id=OLD.id)
 OR EXISTS(SELECT 1 FROM transactions_stockmovement WHERE product_model_id=OLD.id)
 OR EXISTS(SELECT 1 FROM audits_auditline WHERE product_model_id=OLD.id)) THEN
  RAISE EXCEPTION 'Referenced product tracking mode is immutable' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END;
$$;
CREATE TRIGGER product_mode_guard BEFORE UPDATE ON inventory_productmodel FOR EACH ROW EXECUTE FUNCTION itw_product_mode_guard();
CREATE TRIGGER history_no_delete BEFORE DELETE ON transactions_stockmovement FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER history_no_delete BEFORE DELETE ON transactions_assetassignment FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER history_no_delete BEFORE DELETE ON audits_physicalinventoryaudit FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER history_no_delete BEFORE DELETE ON audits_auditline FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER history_no_delete BEFORE DELETE ON audits_assetchangelog FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER history_no_delete BEFORE DELETE ON inventory_importbatch FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER history_no_delete BEFORE DELETE ON inventory_importstagingrecord FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER history_no_update BEFORE UPDATE ON transactions_stockmovement FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER history_no_update BEFORE UPDATE ON audits_assetchangelog FOR EACH ROW EXECUTE FUNCTION itw_reject_history_change();
CREATE TRIGGER tracking_guard BEFORE INSERT OR UPDATE ON inventory_asset FOR EACH ROW EXECUTE FUNCTION itw_tracking_guard();
CREATE TRIGGER tracking_guard BEFORE INSERT OR UPDATE ON inventory_stockbalance FOR EACH ROW EXECUTE FUNCTION itw_tracking_guard();
CREATE TRIGGER tracking_guard BEFORE INSERT OR UPDATE ON inventory_stockthreshold FOR EACH ROW EXECUTE FUNCTION itw_tracking_guard();
CREATE TRIGGER tracking_guard BEFORE INSERT OR UPDATE ON transactions_stockmovement FOR EACH ROW EXECUTE FUNCTION itw_tracking_guard();
CREATE TRIGGER tracking_guard BEFORE INSERT OR UPDATE ON audits_auditline FOR EACH ROW EXECUTE FUNCTION itw_tracking_guard();
"""
REVERSE_SQL = """
DROP TRIGGER assignment_identity_guard ON transactions_assetassignment;
DROP FUNCTION itw_assignment_identity_guard();
DROP TRIGGER tracking_guard ON inventory_asset;
DROP TRIGGER tracking_guard ON inventory_stockbalance;
DROP TRIGGER tracking_guard ON inventory_stockthreshold;
DROP TRIGGER tracking_guard ON transactions_stockmovement;
DROP TRIGGER tracking_guard ON audits_auditline;
DROP TRIGGER history_no_update ON transactions_stockmovement;
DROP TRIGGER history_no_update ON audits_assetchangelog;
DROP TRIGGER history_no_delete ON transactions_stockmovement;
DROP TRIGGER history_no_delete ON transactions_assetassignment;
DROP TRIGGER history_no_delete ON audits_physicalinventoryaudit;
DROP TRIGGER history_no_delete ON audits_auditline;
DROP TRIGGER history_no_delete ON audits_assetchangelog;
DROP TRIGGER history_no_delete ON inventory_importbatch;
DROP TRIGGER history_no_delete ON inventory_importstagingrecord;
DROP TRIGGER product_mode_guard ON inventory_productmodel;
DROP TRIGGER asset_identity_guard ON inventory_asset;
DROP TRIGGER bucket_identity_guard ON inventory_stockbalance;
DROP FUNCTION itw_product_mode_guard();
DROP FUNCTION itw_tracking_guard();
DROP FUNCTION itw_bucket_identity_guard();
DROP FUNCTION itw_asset_identity_guard();
DROP FUNCTION itw_reject_history_change();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("transactions", "0001_initial"),
        ("inventory", "0001_initial"),
        ("audits", "0001_initial"),
    ]
    operations = [migrations.RunSQL(FORWARD_SQL, reverse_sql=REVERSE_SQL)]

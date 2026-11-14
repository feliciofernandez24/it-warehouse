"""Forward-only review integrity guards. Approval and promotion remain disabled."""
from django.db import migrations

FORWARD_SQL = r"""
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';

-- Stage A integrity only: invoker functions, no authentication gateway or approval.
CREATE FUNCTION public.itw_review_lock() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN PERFORM pg_advisory_xact_lock(73921,2); RETURN NULL; END $$;

CREATE FUNCTION public.itw_review_can(actor bigint, capability text) RETURNS boolean
LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
 SELECT EXISTS (
 SELECT 1 FROM public.auth_user u WHERE u.id=actor AND u.is_active AND EXISTS (
 SELECT 1 FROM public.auth_permission p JOIN public.django_content_type c ON c.id=p.content_type_id
 WHERE c.app_label='inventory' AND p.codename=capability AND (
 EXISTS(SELECT 1 FROM public.auth_user_user_permissions x WHERE x.user_id=u.id AND x.permission_id=p.id)
 OR EXISTS(SELECT 1 FROM public.auth_user_groups g JOIN public.auth_group_permissions gp ON gp.group_id=g.group_id
 WHERE g.user_id=u.id AND gp.permission_id=p.id))));
$$;


-- Definitions may be bootstrapped only by their migration owner. No runtime registry gateway.
CREATE FUNCTION public.itw_review_profile_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE doc jsonb; item record;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'REVIEW_PROFILE_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF current_user<>pg_get_userbyid((SELECT relowner FROM pg_class
    WHERE oid='public.inventory_importsourceprofile'::regclass)) THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_REGISTRATION_DISABLED' USING ERRCODE='23514'; END IF;
 NEW.registered_by:=current_user; NEW.created_at:=statement_timestamp();
 IF octet_length(NEW.canonical_bytes)=0 OR octet_length(NEW.canonical_bytes)>65536 OR
    encode(sha256(NEW.canonical_bytes),'hex') IS DISTINCT FROM NEW.digest THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_DIGEST_INVALID' USING ERRCODE='23514'; END IF;
 BEGIN doc:=convert_from(NEW.canonical_bytes,'UTF8')::jsonb;
 EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'REVIEW_PROFILE_JSON_INVALID' USING ERRCODE='23514'; END;
 IF doc IS DISTINCT FROM jsonb_build_object(
    'domain','itw.source-profile.v1','code',NEW.code,'version',NEW.version,
    'workbook_sha256',NEW.workbook_sha256,'layout_digest',NEW.layout_digest,
    'expected_counts',NEW.expected_counts) THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_UNSUPPORTED' USING ERRCODE='23514'; END IF;
 IF jsonb_typeof(NEW.expected_counts) IS DISTINCT FROM 'object' THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_COUNTS_INVALID' USING ERRCODE='23514'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(NEW.expected_counts))<>5 OR
   EXISTS(SELECT 1 FROM jsonb_object_keys(NEW.expected_counts) k WHERE
          k NOT IN ('worksheets','populated','CANDIDATE','HEADER','SEQUENCE_ONLY')) THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_COUNTS_INVALID' USING ERRCODE='23514'; END IF;
 FOR item IN SELECT key,value FROM jsonb_each(NEW.expected_counts) LOOP
  IF jsonb_typeof(item.value)<>'number' OR item.value::text !~ '^[0-9]{1,7}$' THEN
   RAISE EXCEPTION 'REVIEW_PROFILE_COUNTS_INVALID' USING ERRCODE='23514'; END IF;
 END LOOP;
 IF (NEW.expected_counts->>'worksheets')::bigint<1 OR
    (NEW.expected_counts->>'CANDIDATE')::bigint<1 OR
    (NEW.expected_counts->>'populated')::bigint <>
     (NEW.expected_counts->>'CANDIDATE')::bigint+(NEW.expected_counts->>'HEADER')::bigint+
     (NEW.expected_counts->>'SEQUENCE_ONLY')::bigint OR
    (NEW.expected_counts->>'worksheets')::bigint>(NEW.expected_counts->>'populated')::bigint THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_COUNTS_INVALID' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION public.itw_review_check_profile(owner_batch bigint, profile_id uuid, expected_layout text)
RETURNS void LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE p public.inventory_importsourceprofile%ROWTYPE; counts jsonb;
BEGIN
 IF profile_id IS NULL THEN RAISE EXCEPTION 'REVIEW_PROFILE_REQUIRED' USING ERRCODE='23514'; END IF;
 SELECT * INTO p FROM public.inventory_importsourceprofile WHERE id=profile_id;
 IF NOT FOUND OR NOT p.definition_verified OR p.verification_evidence_digest IS NULL THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_UNVERIFIED' USING ERRCODE='23514'; END IF;
 IF p.workbook_sha256 IS DISTINCT FROM
     (SELECT file_sha256 FROM public.inventory_importbatch WHERE id=owner_batch)
    OR p.layout_digest IS DISTINCT FROM expected_layout THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_BINDING_INVALID' USING ERRCODE='23514'; END IF;
 SELECT jsonb_build_object('worksheets',count(DISTINCT worksheet_name),'populated',count(*),
   'CANDIDATE',count(*) FILTER(WHERE normalized_values#>>'{capture,classification}'='CANDIDATE'),
   'HEADER',count(*) FILTER(WHERE normalized_values#>>'{capture,classification}'='HEADER'),
   'SEQUENCE_ONLY',count(*) FILTER(WHERE normalized_values#>>'{capture,classification}'='SEQUENCE_ONLY'))
 INTO counts FROM public.inventory_importstagingrecord WHERE batch_id=owner_batch;
 IF counts IS DISTINCT FROM p.expected_counts THEN
  RAISE EXCEPTION 'REVIEW_PROFILE_COUNTS_INVALID' USING ERRCODE='23514'; END IF;
END $$;

CREATE FUNCTION public.itw_review_revision_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE b public.inventory_importbatch%ROWTYPE; p public.inventory_importpreparationrevision%ROWTYPE;
 last_number bigint;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'REVIEW_HISTORY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF TG_OP='UPDATE' AND current_user<>pg_get_userbyid((SELECT relowner FROM pg_class
    WHERE oid='public.inventory_importpreparationrevision'::regclass)) THEN
  RAISE EXCEPTION 'REVIEW_SERVICE_DISABLED' USING ERRCODE='23514'; END IF;
 IF octet_length(NEW.draft_payload::text)>33554432 THEN
  RAISE EXCEPTION 'REVIEW_PAYLOAD_LIMIT' USING ERRCODE='23514'; END IF;
 SELECT * INTO b FROM public.inventory_importbatch WHERE id=NEW.batch_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_BATCH_INVALID' USING ERRCODE='23514'; END IF;
 IF NEW.state IN ('APPROVED','REVOKED','PROMOTED') THEN
  RAISE EXCEPTION 'REVIEW_APPROVAL_DISABLED' USING ERRCODE='23514'; END IF;
 IF TG_OP='INSERT' THEN
  IF current_user<>pg_get_userbyid((SELECT relowner FROM pg_class
      WHERE oid='public.inventory_importpreparationrevision'::regclass)) THEN
   RAISE EXCEPTION 'REVIEW_CAPTURE_SERVICE_DISABLED' USING ERRCODE='23514'; END IF;
  NEW.created_at:=statement_timestamp();
  IF NEW.revision_number=1 AND NEW.created_by_id<>b.uploaded_by_id THEN
   RAISE EXCEPTION 'REVIEW_CAPTURE_UPLOADER_INVALID' USING ERRCODE='23514'; END IF;
  IF b.status IN ('APPROVED','PROMOTED') OR b.reviewed_by_id IS NOT NULL OR b.reviewed_at IS NOT NULL
     OR b.approved_preview_digest<>'' THEN
   RAISE EXCEPTION 'REVIEW_ADOPTION_DISABLED' USING ERRCODE='23514'; END IF;
  PERFORM public.itw_review_check_profile(NEW.batch_id,NEW.source_profile_id,NEW.layout_digest);
  IF NEW.state<>'CAPTURED' OR NEW.version<>1 OR NEW.draft_payload<>'{}'::jsonb THEN
   RAISE EXCEPTION 'REVIEW_INITIAL_STATE_INVALID' USING ERRCODE='23514'; END IF;
  SELECT coalesce(max(revision_number),0) INTO last_number
   FROM public.inventory_importpreparationrevision WHERE batch_id=NEW.batch_id;
  IF NEW.revision_number<>last_number+1 THEN
   RAISE EXCEPTION 'REVIEW_REVISION_NUMBER_INVALID' USING ERRCODE='23514'; END IF;
  IF NEW.revision_number>1 THEN
   SELECT * INTO p FROM public.inventory_importpreparationrevision WHERE id=NEW.parent_id;
   IF NOT FOUND OR p.batch_id<>NEW.batch_id OR p.revision_number<>last_number
      OR p.state NOT IN ('SUPERSEDED','RETURNED_FOR_CORRECTION','REJECTED','REVOKED')
      OR (NEW.source_profile_id,NEW.layout_digest,NEW.manifest_digest,NEW.capture_storage_key,NEW.capture_artifact_digest)
      IS DISTINCT FROM (p.source_profile_id,p.layout_digest,p.manifest_digest,p.capture_storage_key,p.capture_artifact_digest) THEN
    RAISE EXCEPTION 'REVIEW_PARENT_INVALID' USING ERRCODE='23514'; END IF;
  END IF;
 ELSE
  IF (NEW.id,NEW.batch_id,NEW.source_profile_id,NEW.revision_number,NEW.parent_id,NEW.created_by_id,NEW.created_at,
      NEW.layout_digest,NEW.manifest_digest,NEW.capture_storage_key,NEW.capture_artifact_digest)
    IS DISTINCT FROM
     (OLD.id,OLD.batch_id,OLD.source_profile_id,OLD.revision_number,OLD.parent_id,OLD.created_by_id,OLD.created_at,
      OLD.layout_digest,OLD.manifest_digest,OLD.capture_storage_key,OLD.capture_artifact_digest) THEN
   RAISE EXCEPTION 'REVIEW_IDENTITY_IMMUTABLE' USING ERRCODE='23514'; END IF;
  IF NEW.version<>OLD.version+1 THEN
   RAISE EXCEPTION 'REVIEW_VERSION_INVALID' USING ERRCODE='23514'; END IF;
  IF EXISTS(SELECT 1 FROM public.inventory_importpreparationrevision
    WHERE batch_id=OLD.batch_id AND revision_number>OLD.revision_number) THEN
   RAISE EXCEPTION 'REVIEW_NOT_CURRENT_REVISION' USING ERRCODE='23514'; END IF;
  IF NOT (
   OLD.state='CAPTURED' AND NEW.state IN ('PREPARING','SUPERSEDED') OR
   OLD.state='PREPARING' AND NEW.state IN ('PREPARING','READY_FOR_REVIEW','SUPERSEDED') OR
   OLD.state='READY_FOR_REVIEW' AND NEW.state IN ('READY_FOR_REVIEW','RETURNED_FOR_CORRECTION','REJECTED','SUPERSEDED')
  ) THEN RAISE EXCEPTION 'REVIEW_TRANSITION_INVALID' USING ERRCODE='23514'; END IF;
  IF NEW.draft_payload IS DISTINCT FROM OLD.draft_payload
   AND NOT (OLD.state='PREPARING' AND NEW.state='PREPARING') THEN
   RAISE EXCEPTION 'REVIEW_PAYLOAD_FROZEN' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION public.itw_review_source_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE owner_id bigint;
BEGIN
 IF TG_TABLE_NAME='inventory_importbatch' THEN
  IF EXISTS(SELECT 1 FROM public.inventory_importpreparationrevision WHERE batch_id=OLD.id) THEN
   IF TG_OP='DELETE' THEN RAISE EXCEPTION 'REVIEW_SOURCE_IMMUTABLE' USING ERRCODE='23514'; END IF;
   IF (NEW.id,NEW.public_id,NEW.original_filename,NEW.file_sha256,NEW.source_storage_key,
       NEW.uploaded_by_id,NEW.uploaded_at,NEW.mapping_version,NEW.source_timezone,NEW.status,
       NEW.reviewed_by_id,NEW.reviewed_at,NEW.approved_preview_digest,NEW.created_at)
    IS DISTINCT FROM
      (OLD.id,OLD.public_id,OLD.original_filename,OLD.file_sha256,OLD.source_storage_key,
       OLD.uploaded_by_id,OLD.uploaded_at,OLD.mapping_version,OLD.source_timezone,OLD.status,
       OLD.reviewed_by_id,OLD.reviewed_at,OLD.approved_preview_digest,OLD.created_at) THEN
    RAISE EXCEPTION 'REVIEW_SOURCE_IMMUTABLE' USING ERRCODE='23514'; END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
 ELSE
  IF TG_OP='INSERT' THEN owner_id:=NEW.batch_id; ELSE owner_id:=OLD.batch_id; END IF;
 END IF;
 IF EXISTS(SELECT 1 FROM public.inventory_importpreparationrevision WHERE batch_id=owner_id)
 THEN
  RAISE EXCEPTION 'REVIEW_SOURCE_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF TG_TABLE_NAME='inventory_importstagingrecord' AND TG_OP='UPDATE' THEN
  IF EXISTS(SELECT 1 FROM public.inventory_importpreparationrevision WHERE batch_id=NEW.batch_id) THEN
   RAISE EXCEPTION 'REVIEW_SOURCE_IMMUTABLE' USING ERRCODE='23514'; END IF;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END $$;

CREATE FUNCTION public.itw_review_participant_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'REVIEW_HISTORY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF current_user<>pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid='public.inventory_importrevisionparticipant'::regclass)) THEN
  RAISE EXCEPTION 'REVIEW_SERVICE_DISABLED' USING ERRCODE='23514'; END IF;
 NEW.first_seen_at:=statement_timestamp();
 IF NOT EXISTS(SELECT 1 FROM public.inventory_importpreparationrevision
  WHERE id=NEW.revision_id AND state IN ('CAPTURED','PREPARING')) THEN
  RAISE EXCEPTION 'REVIEW_PARTICIPANTS_FROZEN' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION public.itw_review_snapshot_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE r public.inventory_importpreparationrevision%ROWTYPE; doc jsonb; source_total bigint;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'REVIEW_SNAPSHOT_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF current_user<>pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid='public.inventory_importpreviewsnapshot'::regclass)) THEN
  RAISE EXCEPTION 'REVIEW_SERVICE_DISABLED' USING ERRCODE='23514'; END IF;
 NEW.created_at:=statement_timestamp();
 SELECT * INTO r FROM public.inventory_importpreparationrevision WHERE id=NEW.revision_id;
 IF NOT FOUND OR r.state<>'READY_FOR_REVIEW' THEN
  RAISE EXCEPTION 'REVIEW_SNAPSHOT_STATE_INVALID' USING ERRCODE='23514'; END IF;
 IF octet_length(NEW.canonical_bytes)=0 OR octet_length(NEW.canonical_bytes)>33554432
  OR encode(sha256(NEW.canonical_bytes),'hex') IS DISTINCT FROM NEW.digest THEN
  RAISE EXCEPTION 'REVIEW_SNAPSHOT_DIGEST_INVALID' USING ERRCODE='23514'; END IF;
 BEGIN doc:=convert_from(NEW.canonical_bytes,'UTF8')::jsonb;
 EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION 'REVIEW_SNAPSHOT_JSON_INVALID' USING ERRCODE='23514'; END;
 IF doc IS DISTINCT FROM r.draft_payload OR doc->>'domain' IS DISTINCT FROM 'itw.import-preview.v1'
  OR doc->>'verification_status' IS DISTINCT FROM 'STRUCTURAL_ONLY'
  OR doc->>'source_profile_digest' IS DISTINCT FROM
    (SELECT digest FROM public.inventory_importsourceprofile WHERE id=r.source_profile_id)
  OR doc->>'layout_digest' IS DISTINCT FROM r.layout_digest
  OR doc->>'manifest_digest' IS DISTINCT FROM r.manifest_digest
  OR doc->>'workbook_sha256' IS DISTINCT FROM
   (SELECT file_sha256 FROM public.inventory_importbatch WHERE id=r.batch_id)
  OR jsonb_typeof(doc->'source_rows') IS DISTINCT FROM 'array'
  OR jsonb_typeof(doc->'candidate_decisions') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'REVIEW_SNAPSHOT_CONTENT_INVALID' USING ERRCODE='23514'; END IF;

 IF EXISTS(SELECT 1 FROM jsonb_array_elements(doc->'source_rows') x WHERE
    jsonb_typeof(x) IS DISTINCT FROM 'object' OR
    jsonb_typeof(x->'worksheet_name') IS DISTINCT FROM 'string' OR
    jsonb_typeof(x->'excel_row_number') IS DISTINCT FROM 'number' OR
    coalesce(x->>'excel_row_number','') !~ '^[1-9][0-9]*$' OR
    jsonb_typeof(x->'source_row_digest') IS DISTINCT FROM 'string' OR
    coalesce(x->>'source_row_digest','') !~ '^[0-9a-f]{64}$' OR
    jsonb_typeof(x->'classification') IS DISTINCT FROM 'string') OR
 EXISTS(SELECT 1 FROM jsonb_array_elements(doc->'candidate_decisions') x WHERE
    jsonb_typeof(x) IS DISTINCT FROM 'object' OR
    jsonb_typeof(x->'worksheet_name') IS DISTINCT FROM 'string' OR
    jsonb_typeof(x->'excel_row_number') IS DISTINCT FROM 'number' OR
    coalesce(x->>'excel_row_number','') !~ '^[1-9][0-9]*$' OR
    jsonb_typeof(x->'source_row_digest') IS DISTINCT FROM 'string' OR
    coalesce(x->>'source_row_digest','') !~ '^[0-9a-f]{64}$' OR
    jsonb_typeof(x->'label') IS DISTINCT FROM 'string' OR
    jsonb_typeof(x->'scope') IS DISTINCT FROM 'string') THEN
  RAISE EXCEPTION 'REVIEW_SNAPSHOT_ENTRY_INVALID' USING ERRCODE='23514'; END IF;
 SELECT count(*) INTO source_total FROM public.inventory_importstagingrecord WHERE batch_id=r.batch_id;
 IF jsonb_array_length(doc->'source_rows')<>source_total OR EXISTS (
  SELECT 1 FROM public.inventory_importstagingrecord s WHERE s.batch_id=r.batch_id AND
   (SELECT count(*) FROM jsonb_array_elements(doc->'source_rows') x WHERE
    x->>'worksheet_name'=s.worksheet_name AND x->>'excel_row_number'=s.excel_row_number::text
    AND x->>'source_row_digest'=s.source_row_digest
    AND x->>'classification'=s.normalized_values#>>'{capture,classification}')<>1) THEN
  RAISE EXCEPTION 'REVIEW_SOURCE_RECONCILIATION_INVALID' USING ERRCODE='23514'; END IF;
 IF jsonb_array_length(doc->'candidate_decisions')<>
   (SELECT count(*) FROM public.inventory_importstagingrecord WHERE batch_id=r.batch_id
    AND normalized_values#>>'{capture,classification}'='CANDIDATE')
 OR EXISTS (SELECT 1 FROM public.inventory_importstagingrecord s WHERE s.batch_id=r.batch_id
   AND s.normalized_values#>>'{capture,classification}'='CANDIDATE' AND
    (SELECT count(*) FROM jsonb_array_elements(doc->'candidate_decisions') x
     WHERE x->>'worksheet_name'=s.worksheet_name AND x->>'excel_row_number'=s.excel_row_number::text
      AND x->>'source_row_digest'=s.source_row_digest)<>1)
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(doc->'candidate_decisions') x WHERE
   coalesce(x->>'label','') NOT IN ('BLOCKED','NEEDS_CLARIFICATION','READY_FOR_REVIEW','EXCLUDED_WITH_REASON')
   OR coalesce(x->>'scope','') NOT IN ('ACCEPTED','DEFERRED','EXCLUDED')
   OR (x->>'scope'='ACCEPTED' AND x->>'label'<>'READY_FOR_REVIEW')
   OR (x->>'scope'='EXCLUDED' AND (
       x->>'label'<>'EXCLUDED_WITH_REASON' OR
       jsonb_typeof(x->'reason_code') IS DISTINCT FROM 'string' OR
       coalesce(x->>'reason_code','')!~'\S'))
   OR (x->>'label'='EXCLUDED_WITH_REASON' AND x->>'scope'<>'EXCLUDED')) THEN
  RAISE EXCEPTION 'REVIEW_DECISIONS_INVALID' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION public.itw_review_event_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE r public.inventory_importpreparationrevision%ROWTYPE;
 p public.inventory_importreviewevent%ROWTYPE; capability text;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'REVIEW_HISTORY_IMMUTABLE' USING ERRCODE='23514'; END IF;
 IF current_user<>pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid='public.inventory_importreviewevent'::regclass)) THEN
  RAISE EXCEPTION 'REVIEW_SERVICE_DISABLED' USING ERRCODE='23514'; END IF;
 NEW.recorded_at:=statement_timestamp();
 IF octet_length(NEW.details::text)>1048576 OR length(NEW.reason)>32767 THEN
  RAISE EXCEPTION 'REVIEW_EVENT_LIMIT' USING ERRCODE='23514'; END IF;
 IF NEW.kind IN ('APPROVE','REVOKE') OR NEW.to_state IN ('APPROVED','REVOKED','PROMOTED') THEN
  RAISE EXCEPTION 'REVIEW_APPROVAL_DISABLED' USING ERRCODE='23514'; END IF;
 SELECT * INTO r FROM public.inventory_importpreparationrevision WHERE id=NEW.revision_id;
 IF NOT FOUND OR NEW.sequence<>r.version OR NEW.to_state<>r.state THEN
  RAISE EXCEPTION 'REVIEW_EVENT_VERSION_INVALID' USING ERRCODE='23514'; END IF;
 IF NEW.details->>'after_payload_digest' IS DISTINCT FROM
     encode(sha256(convert_to(r.draft_payload::text,'UTF8')),'hex') THEN
  RAISE EXCEPTION 'REVIEW_EVENT_PAYLOAD_INVALID' USING ERRCODE='23514'; END IF;
 IF NEW.source_row_id IS NOT NULL AND NOT EXISTS(
  SELECT 1 FROM public.inventory_importstagingrecord WHERE id=NEW.source_row_id AND batch_id=r.batch_id) THEN
  RAISE EXCEPTION 'REVIEW_SOURCE_OWNER_INVALID' USING ERRCODE='23514'; END IF;
 IF NEW.snapshot_id IS NOT NULL AND NOT EXISTS(
  SELECT 1 FROM public.inventory_importpreviewsnapshot WHERE id=NEW.snapshot_id AND revision_id=r.id) THEN
  RAISE EXCEPTION 'REVIEW_SNAPSHOT_OWNER_INVALID' USING ERRCODE='23514'; END IF;
 IF NEW.sequence=1 THEN
  IF NEW.kind<>'CAPTURE' OR NEW.from_state<>'CAPTURED' OR NEW.to_state<>'CAPTURED'
   OR NEW.actor_id<>r.created_by_id OR NEW.snapshot_id IS NOT NULL THEN
   RAISE EXCEPTION 'REVIEW_CAPTURE_EVENT_INVALID' USING ERRCODE='23514'; END IF;
 ELSE
  SELECT * INTO p FROM public.inventory_importreviewevent WHERE revision_id=r.id AND sequence=NEW.sequence-1;
  IF NOT FOUND OR p.to_state<>NEW.from_state THEN
   RAISE EXCEPTION 'REVIEW_EVENT_CHAIN_INVALID' USING ERRCODE='23514'; END IF;
  IF NOT (
   NEW.kind='START' AND NEW.from_state='CAPTURED' AND NEW.to_state='PREPARING' OR
   NEW.kind IN ('EDIT','EVIDENCE') AND NEW.from_state='PREPARING' AND NEW.to_state='PREPARING' OR
   NEW.kind='SUBMIT' AND NEW.from_state='PREPARING' AND NEW.to_state='READY_FOR_REVIEW' OR
   NEW.kind='REVIEW_ACCEPT' AND NEW.from_state='READY_FOR_REVIEW' AND NEW.to_state='READY_FOR_REVIEW' OR
   NEW.kind IN ('RETURN','REJECT') AND NEW.from_state='READY_FOR_REVIEW' AND
     NEW.to_state=CASE NEW.kind WHEN 'RETURN' THEN 'RETURNED_FOR_CORRECTION' ELSE 'REJECTED' END OR
   NEW.kind='SUPERSEDE' AND NEW.from_state IN ('CAPTURED','PREPARING','READY_FOR_REVIEW')
     AND NEW.to_state='SUPERSEDED'
  ) THEN RAISE EXCEPTION 'REVIEW_EVENT_TRANSITION_INVALID' USING ERRCODE='23514'; END IF;
 END IF;
 capability:=CASE WHEN NEW.kind='CAPTURE' AND r.revision_number=1 THEN 'capture_import'
  WHEN NEW.kind IN ('REVIEW_ACCEPT','RETURN','REJECT') THEN 'review_import' ELSE 'prepare_import' END;
 IF NOT public.itw_review_can(NEW.actor_id,capability) THEN
  RAISE EXCEPTION 'REVIEW_ACTOR_UNAUTHORIZED' USING ERRCODE='23514'; END IF;
 IF NEW.kind IN ('REVIEW_ACCEPT','RETURN','REJECT') THEN
  IF NOT public.itw_review_can(NEW.actor_id,'view_import_evidence')
   OR NEW.actor_id=(SELECT uploaded_by_id FROM public.inventory_importbatch WHERE id=r.batch_id)
   OR EXISTS(SELECT 1 FROM public.inventory_importrevisionparticipant
      WHERE revision_id=r.id AND user_id=NEW.actor_id) THEN
   RAISE EXCEPTION 'REVIEW_ACTOR_NOT_INDEPENDENT' USING ERRCODE='23514'; END IF;
 ELSE
  IF r.state IN ('CAPTURED','PREPARING') THEN
   INSERT INTO public.inventory_importrevisionparticipant(revision_id,user_id,first_seen_at)
    VALUES(r.id,NEW.actor_id,statement_timestamp()) ON CONFLICT(revision_id,user_id) DO NOTHING;
  ELSIF NOT EXISTS(SELECT 1 FROM public.inventory_importrevisionparticipant
     WHERE revision_id=r.id AND user_id=NEW.actor_id) THEN
   RAISE EXCEPTION 'REVIEW_PREPARER_NOT_REGISTERED' USING ERRCODE='23514'; END IF;
 END IF;
 IF NEW.kind='SUBMIT' OR NEW.from_state='READY_FOR_REVIEW' THEN
  IF NEW.snapshot_id IS NULL THEN RAISE EXCEPTION 'REVIEW_SNAPSHOT_REQUIRED' USING ERRCODE='23514'; END IF;
 ELSIF NEW.snapshot_id IS NOT NULL THEN
  RAISE EXCEPTION 'REVIEW_UNEXPECTED_SNAPSHOT' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;

CREATE FUNCTION public.itw_review_assert(target_revision uuid) RETURNS void LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE r public.inventory_importpreparationrevision%ROWTYPE; event_count bigint;
 last_event public.inventory_importreviewevent%ROWTYPE; source_count bigint;
BEGIN
 SELECT * INTO r FROM public.inventory_importpreparationrevision WHERE id=target_revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'REVIEW_REVISION_MISSING' USING ERRCODE='23514'; END IF;
 SELECT count(*) INTO event_count FROM public.inventory_importreviewevent e WHERE e.revision_id=r.id;
 SELECT * INTO last_event FROM public.inventory_importreviewevent e
  WHERE e.revision_id=r.id ORDER BY sequence DESC LIMIT 1;
 IF event_count<>r.version OR last_event.sequence IS DISTINCT FROM r.version
   OR last_event.to_state IS DISTINCT FROM r.state OR last_event.details->>'after_payload_digest'
    IS DISTINCT FROM encode(sha256(convert_to(r.draft_payload::text,'UTF8')),'hex') THEN
  RAISE EXCEPTION 'REVIEW_EVENT_EVIDENCE_REQUIRED' USING ERRCODE='23514'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.inventory_importrevisionparticipant WHERE revision_id=r.id AND user_id=r.created_by_id)
 OR EXISTS(SELECT 1 FROM public.inventory_importrevisionparticipant oldp WHERE oldp.revision_id=r.parent_id
   AND NOT EXISTS(SELECT 1 FROM public.inventory_importrevisionparticipant newp
      WHERE newp.revision_id=r.id AND newp.user_id=oldp.user_id)) THEN
  RAISE EXCEPTION 'REVIEW_PARTICIPANT_EVIDENCE_REQUIRED' USING ERRCODE='23514'; END IF;
 IF r.state='SUPERSEDED' AND NOT EXISTS(SELECT 1 FROM public.inventory_importpreparationrevision WHERE parent_id=r.id) THEN
  RAISE EXCEPTION 'REVIEW_SUCCESSOR_REQUIRED' USING ERRCODE='23514'; END IF;
 IF r.state IN ('READY_FOR_REVIEW','RETURNED_FOR_CORRECTION','REJECTED')
 OR EXISTS(SELECT 1 FROM public.inventory_importpreviewsnapshot WHERE revision_id=r.id) THEN
  IF NOT EXISTS(SELECT 1 FROM public.inventory_importpreviewsnapshot s
    JOIN public.inventory_importreviewevent e ON e.snapshot_id=s.id
    WHERE s.revision_id=r.id AND e.revision_id=r.id AND e.kind='SUBMIT') THEN
   RAISE EXCEPTION 'REVIEW_SUBMISSION_EVIDENCE_REQUIRED' USING ERRCODE='23514'; END IF;
 END IF;
 SELECT count(*) INTO source_count FROM public.inventory_importstagingrecord WHERE batch_id=r.batch_id;
 IF source_count=0 OR EXISTS(SELECT 1 FROM public.inventory_importstagingrecord WHERE batch_id=r.batch_id AND
   (status<>'CAPTURED' OR asset_id IS NOT NULL OR stock_balance_id IS NOT NULL OR promoted_at IS NOT NULL
    OR coalesce(normalized_values#>>'{capture,classification}','')
       NOT IN ('CANDIDATE','HEADER','SEQUENCE_ONLY'))) THEN
  RAISE EXCEPTION 'REVIEW_CAPTURE_SOURCE_INVALID' USING ERRCODE='23514'; END IF;
 PERFORM public.itw_review_check_profile(r.batch_id,r.source_profile_id,r.layout_digest);
END $$;

CREATE FUNCTION public.itw_review_final_guard() RETURNS trigger LANGUAGE plpgsql
SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_TABLE_NAME='inventory_importpreparationrevision' THEN PERFORM public.itw_review_assert(NEW.id);
 ELSE PERFORM public.itw_review_assert(NEW.revision_id); END IF;
 RETURN NULL;
END $$;

CREATE TRIGGER review_lock BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importpreparationrevision FOR EACH STATEMENT EXECUTE FUNCTION public.itw_review_lock();
CREATE TRIGGER review_integrity BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importpreparationrevision FOR EACH ROW EXECUTE FUNCTION public.itw_review_revision_guard();
CREATE CONSTRAINT TRIGGER review_final AFTER INSERT OR UPDATE ON public.inventory_importpreparationrevision DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.itw_review_final_guard();

CREATE TRIGGER review_lock BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importrevisionparticipant FOR EACH STATEMENT EXECUTE FUNCTION public.itw_review_lock();
CREATE TRIGGER review_integrity BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importrevisionparticipant FOR EACH ROW EXECUTE FUNCTION public.itw_review_participant_guard();
CREATE CONSTRAINT TRIGGER review_final AFTER INSERT OR UPDATE ON public.inventory_importrevisionparticipant DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.itw_review_final_guard();

CREATE TRIGGER review_lock BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importpreviewsnapshot FOR EACH STATEMENT EXECUTE FUNCTION public.itw_review_lock();
CREATE TRIGGER review_integrity BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importpreviewsnapshot FOR EACH ROW EXECUTE FUNCTION public.itw_review_snapshot_guard();
CREATE CONSTRAINT TRIGGER review_final AFTER INSERT OR UPDATE ON public.inventory_importpreviewsnapshot DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.itw_review_final_guard();

CREATE TRIGGER review_lock BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importreviewevent FOR EACH STATEMENT EXECUTE FUNCTION public.itw_review_lock();
CREATE TRIGGER review_integrity BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importreviewevent FOR EACH ROW EXECUTE FUNCTION public.itw_review_event_guard();
CREATE CONSTRAINT TRIGGER review_final AFTER INSERT OR UPDATE ON public.inventory_importreviewevent DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.itw_review_final_guard();

CREATE TRIGGER review_lock BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importbatch FOR EACH STATEMENT EXECUTE FUNCTION public.itw_review_lock();
CREATE TRIGGER review_source BEFORE UPDATE OR DELETE ON public.inventory_importbatch FOR EACH ROW EXECUTE FUNCTION public.itw_review_source_guard();

CREATE TRIGGER review_lock BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importstagingrecord FOR EACH STATEMENT EXECUTE FUNCTION public.itw_review_lock();
CREATE TRIGGER review_source BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importstagingrecord FOR EACH ROW EXECUTE FUNCTION public.itw_review_source_guard();

REVOKE EXECUTE ON FUNCTION public.itw_review_lock() FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.itw_review_can(bigint,text) FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.itw_review_revision_guard() FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.itw_review_source_guard() FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.itw_review_participant_guard() FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.itw_review_snapshot_guard() FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.itw_review_event_guard() FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.itw_review_assert(uuid) FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION public.itw_review_final_guard() FROM PUBLIC;

CREATE TRIGGER review_lock BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importsourceprofile
 FOR EACH STATEMENT EXECUTE FUNCTION public.itw_review_lock();
CREATE TRIGGER review_profile_integrity BEFORE INSERT OR UPDATE OR DELETE ON public.inventory_importsourceprofile
 FOR EACH ROW EXECUTE FUNCTION public.itw_review_profile_guard();
REVOKE EXECUTE ON FUNCTION public.itw_review_profile_guard() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.itw_review_check_profile(bigint,uuid,text) FROM PUBLIC;

"""


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_import_review_schema")]
    operations = [migrations.RunSQL(FORWARD_SQL)]

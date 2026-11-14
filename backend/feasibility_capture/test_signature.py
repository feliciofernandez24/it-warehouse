"""Real PostgreSQL Ed25519 verification. Synthetic signing keys stay in this client."""
import hashlib
import json
import time
import unittest
import uuid
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from common import connect, clone, canonical, strict_load, EVIDENCE

SQL = """
CREATE SCHEMA fa_crypto;
CREATE TABLE fa_crypto.keys(id text PRIMARY KEY, purpose text NOT NULL, public bytea NOT NULL, revoked boolean NOT NULL);
CREATE TABLE fa_crypto.used(nonce uuid PRIMARY KEY, request uuid UNIQUE NOT NULL);
CREATE FUNCTION fa_crypto.check_assertion(data bytea, sig bytea, actor bigint, request uuid, fp text, purpose text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $$
DECLARE d jsonb; pk bytea; now_epoch bigint; txt text;
BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(73921,2);
 IF data IS NULL OR sig IS NULL OR octet_length(data)>16384 OR octet_length(sig)<>64
 THEN RAISE EXCEPTION 'ASSERTION_INVALID'; END IF;
 txt:=convert_from(data,'UTF8');
 IF NOT (txt IS JSON OBJECT WITH UNIQUE KEYS) THEN RAISE EXCEPTION 'ASSERTION_INVALID'; END IF;
 d:=txt::jsonb;
 SELECT k.public INTO pk FROM fa_crypto.keys k
 WHERE k.id=d->>'key_id' AND k.purpose=check_assertion.purpose AND NOT k.revoked;
 IF pk IS NULL OR NOT pgsodium.crypto_sign_verify_detached(sig,data,pk)
 THEN RAISE EXCEPTION 'ASSERTION_INVALID'; END IF;
 now_epoch:=extract(epoch FROM clock_timestamp())::bigint;
 IF d->>'domain' IS DISTINCT FROM 'itw.synthetic-assertion.v1' OR d->>'algorithm' IS DISTINCT FROM 'Ed25519'
 OR d->>'audience' IS DISTINCT FROM 'isolated-pg17/phase3b2b2a' OR d->>'action' IS DISTINCT FROM 'register_verified_capture'
 OR d->>'purpose' IS DISTINCT FROM purpose OR d->>'actor_id' IS DISTINCT FROM actor::text
 OR d->>'request_id' IS DISTINCT FROM request::text OR d->>'fingerprint' IS DISTINCT FROM fp
 OR (SELECT count(*) FROM jsonb_object_keys(d))<>13
 OR NOT (d ?& ARRAY['domain','algorithm','audience','action','purpose','actor_id','request_id',
                   'fingerprint','key_id','nonce','issued_at','expires_at','envelope_digest'])
 OR jsonb_typeof(d->'actor_id')<>'number'
 OR coalesce(d->>'issued_at','') !~ '^[0-9]+$'
 OR coalesce(d->>'expires_at','') !~ '^[0-9]+$'
 OR (d->>'issued_at')::bigint>now_epoch
 OR (d->>'expires_at')::bigint<=now_epoch
 OR (d->>'expires_at')::bigint-(d->>'issued_at')::bigint NOT BETWEEN 1 AND 300
 OR d->>'envelope_digest' IS DISTINCT FROM fp
 THEN RAISE EXCEPTION 'ASSERTION_INVALID'; END IF;
 INSERT INTO fa_crypto.used(nonce,request) VALUES((d->>'nonce')::uuid,request);
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION fa_crypto.check_assertion(bytea,bytea,bigint,uuid,text,text) FROM PUBLIC;
"""


class SignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=clone("crypto")
        cls.keys={p:Ed25519PrivateKey.generate() for p in ("identity","verifier")}
        with connect(cls.db) as c:
            c.execute(SQL)
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='itw_fa_crypto_owner'").fetchone():
                c.execute("CREATE ROLE itw_fa_crypto_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
            if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='itw_fa_crypto_runtime'").fetchone():
                c.execute("CREATE ROLE itw_fa_crypto_runtime LOGIN PASSWORD 'feasibility-synthetic-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS")
            c.execute("ALTER SCHEMA fa_crypto OWNER TO itw_fa_crypto_owner")
            c.execute("ALTER TABLE fa_crypto.keys OWNER TO itw_fa_crypto_owner")
            c.execute("ALTER TABLE fa_crypto.used OWNER TO itw_fa_crypto_owner")
            c.execute("ALTER FUNCTION fa_crypto.check_assertion(bytea,bytea,bigint,uuid,text,text) OWNER TO itw_fa_crypto_owner")
            c.execute("REVOKE ALL ON SCHEMA fa_crypto,pgsodium FROM PUBLIC")
            c.execute("GRANT USAGE ON SCHEMA pgsodium TO itw_fa_crypto_owner")
            c.execute("GRANT EXECUTE ON FUNCTION pgsodium.crypto_sign_verify_detached(bytea,bytea,bytea) TO itw_fa_crypto_owner")
            c.execute("GRANT USAGE ON SCHEMA fa_crypto TO itw_fa_crypto_runtime")
            c.execute("GRANT EXECUTE ON FUNCTION fa_crypto.check_assertion(bytea,bytea,bigint,uuid,text,text) TO itw_fa_crypto_runtime")
            for p,k in cls.keys.items():
                c.execute("INSERT INTO fa_crypto.keys VALUES(%s,%s,%s,false)",
                    (p,p,k.public_key().public_bytes_raw()))
            EVIDENCE["crypto"] = c.execute("SELECT extversion,pg_get_userbyid(extowner) "
                "FROM pg_extension WHERE extname='pgsodium'").fetchone()

    def runtime(self):
        import psycopg
        # Validate safety through the shared connection guard before connecting real LOGIN.
        with connect(self.db):
            pass
        return psycopg.connect(host="127.0.0.1",dbname=self.db,user="itw_fa_crypto_runtime",
            password="feasibility-synthetic-only",autocommit=True)

    def claims(self, purpose="identity", **changes):
        now=int(time.time())
        doc={"domain":"itw.synthetic-assertion.v1","algorithm":"Ed25519",
            "audience":"isolated-pg17/phase3b2b2a","action":"register_verified_capture",
            "purpose":purpose,"actor_id":101,"request_id":str(uuid.uuid4()),
            "fingerprint":"a"*64,"key_id":purpose,"nonce":str(uuid.uuid4()),
            "issued_at":now,"expires_at":now+180,"envelope_digest":"a"*64}
        doc.update(changes)
        return doc

    def check(self, doc, data=None, sig=None, **expected):
        data=canonical(doc) if data is None else data
        sig=self.keys[doc["key_id"]].sign(data) if sig is None else sig
        args=(data,sig,expected.get("actor",101),expected.get("request",uuid.UUID(doc["request_id"])),
              expected.get("fp","a"*64),expected.get("purpose",doc["purpose"]))
        with self.runtime() as c:
            return c.execute("SELECT fa_crypto.check_assertion(%s,%s,%s,%s,%s,%s)",args).fetchone()[0]

    def test_both_independent_signature_purposes(self):
        for purpose in self.keys:
            self.assertTrue(self.check(self.claims(purpose)))

    def test_rfc8032_known_answer_and_changed_message(self):
        pk=bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig=bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555f"
                          "b8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        with connect(self.db) as c:
            self.assertTrue(c.execute("SELECT pgsodium.crypto_sign_verify_detached(%s,%s,%s)",(sig,b"",pk)).fetchone()[0])
            self.assertFalse(c.execute("SELECT pgsodium.crypto_sign_verify_detached(%s,%s,%s)",(sig,b"x",pk)).fetchone()[0])

    def test_invalid_signature_and_lengths(self):
        import psycopg
        for signature in (b"x"*64,b"x"*63,b"",None):
            with self.subTest(length=None if signature is None else len(signature)),self.assertRaises(psycopg.Error):
                if signature is None:
                    d=self.claims()
                    with self.runtime() as c:
                        c.execute("SELECT fa_crypto.check_assertion(%s,NULL,101,%s,%s,'identity')",
                            (canonical(d),uuid.UUID(d["request_id"]),"a"*64))
                else:
                    self.check(self.claims(),sig=signature)

    def test_wrong_claim_bindings(self):
        import psycopg
        for change in ({"audience":"other"},{"action":"approve"},{"actor_id":102},
                       {"fingerprint":"b"*64},{"algorithm":"none"},{"purpose":"verifier"},
                       {"domain":"other"},{"issued_at":int(time.time())+600},
                       {"expires_at":int(time.time())-1}):
            with self.subTest(change=change),self.assertRaises(psycopg.Error):
                self.check(self.claims(**change),purpose="identity")

    def test_wrong_request_and_key(self):
        import psycopg
        with self.assertRaises(psycopg.Error):
            self.check(self.claims(),request=uuid.uuid4())
        d=self.claims()
        with self.assertRaises(psycopg.Error):
            self.check(d,sig=self.keys["verifier"].sign(canonical(d)))

    def test_replay_and_revoked_key(self):
        import psycopg
        d=self.claims()
        self.assertTrue(self.check(d))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.check(d)
        with connect(self.db) as c:
            c.execute("UPDATE fa_crypto.keys SET revoked=true WHERE id='identity'")
            try:
                with self.assertRaises(psycopg.Error):
                    self.check(self.claims())
            finally:
                c.execute("UPDATE fa_crypto.keys SET revoked=false WHERE id='identity'")

    def test_private_helpers_and_key_reads_denied(self):
        import psycopg
        with self.runtime() as c:
            for query in ("SELECT * FROM fa_crypto.keys","SELECT * FROM fa_crypto.used",
                "SELECT pgsodium.crypto_sign_verify_detached('x','x','x')",
                "SET ROLE itw_fa_crypto_owner"):
                with self.subTest(query=query), self.assertRaises(psycopg.Error):
                    c.execute(query)

    def test_duplicate_keys_rejected_even_with_valid_signature(self):
        import psycopg
        d=self.claims()
        data=canonical(d)
        duplicate=b'{"actor_id":101,'+data[1:]
        with self.assertRaises(psycopg.Error):
            self.check(d,data=duplicate)

    def test_noncanonical_sql_gap_is_explicit(self):
        d=self.claims()
        data=json.dumps(d,ensure_ascii=False,indent=1).encode()
        with self.assertRaises(ValueError):
            strict_load(data)
        # Signature integrity is proven, but full SQL canonical-byte enforcement is NOT.
        self.assertTrue(self.check(d,data=data))
        EVIDENCE["sql_canonical_gap"]="Valid signed noncanonical whitespace accepted; production remains blocked"

    def test_assertion_rollback_does_not_consume_nonce(self):
        d=self.claims()
        data=canonical(d); sig=self.keys["identity"].sign(data)
        with self.runtime() as c:
            with self.assertRaisesRegex(RuntimeError,"ROLLBACK"):
                with c.transaction():
                    c.execute("SELECT fa_crypto.check_assertion(%s,%s,101,%s,%s,'identity')",
                        (data,sig,uuid.UUID(d["request_id"]),"a"*64))
                    raise RuntimeError("ROLLBACK")
        self.assertTrue(self.check(d))
    def test_canonical_vector_signatures_cover_exact_bytes(self):
        from pathlib import Path
        vectors=json.loads(Path(__file__).with_name("canonical-vectors.json").read_text())
        key=self.keys["verifier"]
        with connect(self.db) as c:
            for vector in vectors:
                data=bytes.fromhex(vector["canonical_utf8_hex"])
                sig=key.sign(data)
                with self.subTest(name=vector["name"]):
                    self.assertTrue(c.execute("SELECT pgsodium.crypto_sign_verify_detached(%s,%s,%s)",
                        (sig,data,key.public_key().public_bytes_raw())).fetchone()[0])
                    self.assertFalse(c.execute("SELECT pgsodium.crypto_sign_verify_detached(%s,%s,%s)",
                        (sig,data+b" ",key.public_key().public_bytes_raw())).fetchone()[0])

    def test_null_or_extra_protocol_fields_rejected(self):
        import psycopg
        for changes in ({"algorithm":None},{"audience":None},{"action":None},{"domain":None},{"extra":True}):
            with self.subTest(changes=changes),self.assertRaises(psycopg.Error):
                self.check(self.claims(**changes))
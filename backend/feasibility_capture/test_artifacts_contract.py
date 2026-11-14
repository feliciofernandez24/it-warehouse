"""Synthetic retention state machine and canonical byte vectors; no inventory capture."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from common import connect, clone, canonical, strict_load, lock, wait_for_lock, EVIDENCE


class ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db=clone("storage")
        with connect(cls.db) as c:
            c.execute("CREATE SCHEMA fa_storage")
            c.execute("CREATE TABLE fa_storage.reservations(version uuid PRIMARY KEY,digest text NOT NULL,"
                "expires bigint NOT NULL,state text NOT NULL CHECK(state IN ('READY','RETIRED')))")
            c.execute("CREATE TABLE fa_storage.refs(request uuid PRIMARY KEY,version uuid NOT NULL "
                "REFERENCES fa_storage.reservations,result bytea NOT NULL)")

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="itw-fake-artifacts-")
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        os.chmod(self.root,0o700)
        self.payload=b"synthetic confidential evidence only"
        self.digest=hashlib.sha256(self.payload).hexdigest()
        self.version=uuid.uuid4()
        self.path=self.root/(self.digest+"."+str(self.version))
        fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as f:
            f.write(self.payload); f.flush(); os.fchmod(f.fileno(),0o400); os.fsync(f.fileno())
        fd=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        with connect(self.db) as c:
            c.execute("INSERT INTO fa_storage.reservations VALUES(%s,%s,100,'READY')",(self.version,self.digest))
        self.request=uuid.uuid4()

    def verify(self):
        fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,"rb") as f:
            if hashlib.sha256(f.read()).hexdigest()!=self.digest:
                raise ValueError("EVIDENCE_INTEGRITY")

    def register(self,c,fail=False):
        lock(c)
        existing=c.execute("SELECT version,result FROM fa_storage.refs WHERE request=%s",(self.request,)).fetchone()
        if existing:
            if existing[0]!=self.version:
                raise ValueError("REQUEST_CONFLICT")
            return bytes(existing[1])
        row=c.execute("SELECT state,expires,digest FROM fa_storage.reservations WHERE version=%s",(self.version,)).fetchone()
        if row!=("READY",100,self.digest):
            raise ValueError("RESERVATION_INVALID")
        result=canonical({"domain":"itw.synthetic-retention-result.v1","request_id":str(self.request),"version":str(self.version)})
        c.execute("INSERT INTO fa_storage.refs VALUES(%s,%s,%s)",(self.request,self.version,result))
        if fail:
            raise RuntimeError("SQL_ROLLBACK")
        return result

    def retire(self,c,now):
        lock(c)
        return c.execute("UPDATE fa_storage.reservations r SET state='RETIRED' "
            "WHERE r.version=%s AND r.state='READY' AND r.expires<%s "
            "AND NOT EXISTS(SELECT 1 FROM fa_storage.refs f WHERE f.version=r.version) RETURNING version",
            (self.version,now)).fetchone() is not None

    def collect(self,now=101):
        with connect(self.db) as c, c.transaction():
            retired=self.retire(c,now)
        if retired:  # Outside transaction; tombstone prevents subsequent adoption of this version.
            self.path.unlink()
        return retired

    def test_durable_publication_exact_version(self):
        self.verify()
        self.assertEqual(self.path.stat().st_mode & 0o777,0o400)
        self.assertEqual(self.root.stat().st_mode & 0o777,0o700)
        self.assertIn(str(self.version),self.path.name)
        with self.assertRaises(FileExistsError):
            os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o400)

    def test_publication_sql_rollback_orphan_recovery(self):
        self.verify()
        with connect(self.db) as c, self.assertRaisesRegex(RuntimeError,"SQL_ROLLBACK"),c.transaction():
            self.register(c,fail=True)
        self.assertTrue(self.path.exists())
        self.assertFalse(self.collect(now=99))
        self.assertTrue(self.collect())
        self.assertFalse(self.path.exists())
        with connect(self.db) as c,c.transaction(),self.assertRaisesRegex(ValueError,"RESERVATION_INVALID"):
            self.register(c)

    def test_committed_lost_ack_exact_replay_and_no_collection(self):
        self.verify()
        with connect(self.db) as c,c.transaction():
            original=self.register(c)
        # Deliberately discard the transport response; a new connection resolves unknown outcome.
        with connect(self.db) as c,c.transaction():
            replay=self.register(c)
        self.assertEqual(original,replay)
        self.assertFalse(self.collect(now=1000000))
        self.verify()

    def test_changed_and_missing_evidence_rejected(self):
        self.verify()
        os.chmod(self.path,0o600)
        self.path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"EVIDENCE_INTEGRITY"):
            self.verify()
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.verify()

    def test_capture_commit_wins_collector_race(self):
        self.verify()
        with connect(self.db) as h,connect(self.db) as w:
            with h.transaction():
                self.register(h)
                def run():
                    with w.transaction():
                        return self.retire(w,101)
                pool=ThreadPoolExecutor(max_workers=1)
                f=pool.submit(run)
                wait_for_lock(h,w.info.backend_pid)
            try:
                self.assertFalse(f.result(5))
            finally:
                pool.shutdown()
        self.verify()

    def test_collector_tombstone_wins_registration_race(self):
        self.verify()
        with connect(self.db) as h,connect(self.db) as w:
            with h.transaction():
                self.assertTrue(self.retire(h,101))
                def run():
                    with w.transaction():
                        return self.register(w)
                pool=ThreadPoolExecutor(max_workers=1)
                f=pool.submit(run)
                wait_for_lock(h,w.info.backend_pid)
            try:
                with self.assertRaisesRegex(ValueError,"RESERVATION_INVALID"):
                    f.result(5)
            finally:
                pool.shutdown()
        # Deletion may be retried after collector crash; tombstone still refuses registration.
        self.path.unlink()


class CanonicalTests(unittest.TestCase):
    def test_frozen_contract_vectors_python_and_postgresql(self):
        vectors=json.loads(Path(__file__).with_name("canonical-vectors.json").read_text())
        with connect() as c:
            for vector in vectors:
                with self.subTest(name=vector["name"]):
                    data=bytes.fromhex(vector["canonical_utf8_hex"])
                    self.assertEqual(canonical(vector["value"]),data)
                    self.assertEqual(strict_load(data),vector["value"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(),vector["sha256"])
                    self.assertEqual(c.execute("SELECT encode(sha256(%s),'hex')",(data,)).fetchone()[0],vector["sha256"])
        by_name={v["name"]:v for v in vectors}
        request=by_name["capture-request"]["value"]
        envelope=by_name["verified-capture"]["value"]
        self.assertEqual(request["envelope_digest"],by_name["verified-capture"]["sha256"])
        self.assertEqual(set(request),{"domain","actor_id","action","request_id","revision_id",
            "expected_version","envelope_digest"})
        self.assertEqual(set(envelope),{"domain","profile","workbook","layout_digest","manifest",
            "capture","parser","normalization","source_timezone","date_system","counts",
            "source_row_set_digest","storage_receipt_id","retention_policy_version"})
        self.assertEqual(request["domain"],"itw.capture-request.v1")
        self.assertEqual(envelope["domain"],"itw.verified-capture.v1")
        self.assertIs(type(by_name["source-row"]["value"]["excel_row_number"]),int)
        EVIDENCE["canonical_vectors"]=len(vectors)

    def test_ambiguous_and_invalid_encodings(self):
        for data in (b'{"a":1,"a":2}',b'{"a":1.0}',b'{"a":NaN}',b'{"a":1e0}',
                     b'{"a":"\xff"}',b'\xef\xbb\xbf{}',b' {"a":1}',b'{"a":"\\ud800"}'):
            with self.subTest(data=data),self.assertRaises((ValueError,UnicodeError)):
                strict_load(data)

    def test_unicode_and_array_order_are_identity_sensitive(self):
        self.assertNotEqual(canonical({"x":"é"}),canonical({"x":"e\u0301"}))
        self.assertNotEqual(canonical([1,2]),canonical([2,1]))
        self.assertNotEqual(canonical({"row":2}),canonical({"row":"2"}))

    def test_deployment_and_source_timezones_are_separate(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        instant=datetime(2026,11,14,tzinfo=ZoneInfo("UTC"))
        self.assertEqual(instant.astimezone(ZoneInfo("Asia/Dili")).utcoffset().total_seconds(),32400)
        source={"source_timezone":"Asia/Tokyo"}
        self.assertEqual(strict_load(canonical(source)),source)
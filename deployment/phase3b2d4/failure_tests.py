"""Failure-path integration checks; all DDL targets an explicitly new tmpfs container."""
import copy,json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
import runbook as r
BASE=Path.home()/".local/share/it-warehouse-d4/rehearsal"
cfg=json.load(open(BASE/"rehearsal.json"))
before=json.load(open(BASE/"ordered/before.json"))
DB="itw-d4-failure-db"
def sql(q):
    return r.output(["docker","exec",DB,"psql","-X","-At","-v","ON_ERROR_STOP=1","-U","it_warehouse","-d","it_warehouse","-c",q])
def manage(migration,timeout=False):
    c=dict(cfg,db_container=DB)
    args=["docker","run","--rm","--network","container:"+DB,"--mount",f"type=bind,source={r.ROOT/'backend'},target=/app,readonly",
        "-e","PYTHONDONTWRITEBYTECODE=1","-e","DJANGO_SECRET_KEY=d4-failure-only","-e","POSTGRES_HOST=127.0.0.1","-e","POSTGRES_DB=it_warehouse",
        "-e","POSTGRES_USER=it_warehouse","-e","POSTGRES_PASSWORD=d4-disposable-only"]
    if timeout:args+=["-e","PGOPTIONS=-clock_timeout=1s -cstatement_timeout=10s"]
    return subprocess.run(args+[cfg["backend_image"],"python","manage.py","migrate","inventory",migration,"--noinput"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
class FailureTests(unittest.TestCase):
    def test_01_persistent_mutations_default_deny(self):
        for action in ["isolate","backup","restore-check","apply","verify","resume"]:
            with self.subTest(action=action):
                result=subprocess.run(["python3",str(r.HERE/"runbook.py"),action,"--config",str(r.HERE/"development.json"),
                    "--state",str(BASE/"denial")],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                self.assertEqual(result.returncode,1)
                self.assertIn(b"LATER_DEVELOPMENT_AUTHORIZATION_REQUIRED",result.stderr)
    def test_02_empty_and_failed_dump_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):r.file_output(["true"],Path(d)/"empty")
            with self.assertRaises(subprocess.CalledProcessError):r.file_output(["false"],Path(d)/"failed")
    def test_03_original_row_tampering_rejected(self):
        altered=copy.deepcopy(before);row=next(iter(altered["tables"]["auth_permission"]["rows"]))
        altered["tables"]["auth_permission"]["rows"][row]="tampered"
        with self.assertRaisesRegex(RuntimeError,"ORIGINAL_ROW_CHANGED"):r.comparison(before,altered)
    def test_04_role_acl_owner_drift_rejected(self):
        altered=copy.deepcopy(before);altered["tables"]["auth_permission"]["acl"]="unexpected"
        with self.assertRaisesRegex(RuntimeError,"SOURCE_ACL_CHANGED"):r.comparison(before,altered)
        altered=copy.deepcopy(before);altered["roles"]=[]
        with self.assertRaisesRegex(RuntimeError,"ROLE_METADATA_CHANGED"):r.comparison(before,altered)
    def test_05_unknown_committed_outcome_readonly_verification(self):
        current=r.job(cfg,"verify",before=BASE/"ordered/before.json")
        self.assertEqual(len(current["history"]),29)
        self.assertEqual(sum(v["count"] for k,v in current["tables"].items()),177)
    def test_06_corrupted_archive_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/"truncated.dump";archive.write_bytes((BASE/"ordered/backup.dump").read_bytes()[:20])
            result=subprocess.run(["docker","run","--rm","--network","none","--mount",f"type=bind,source={archive},target=/bad.dump,readonly",
                "--entrypoint","pg_restore",cfg["postgres_image"],"--list","/bad.dump"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode,0)
    def test_07_uncommitted_0003_rolls_back_but_0002_remains(self):
        r.restore(cfg,BASE/"ordered",BASE/"ordered/backup.dump",BASE/"ordered/roles-no-passwords.sql",DB)
        self.assertEqual(manage("0002").returncode,0)
        locker=subprocess.Popen(["docker","exec",DB,"psql","-X","-U","it_warehouse","-d","it_warehouse","-c",
            "BEGIN; LOCK TABLE inventory_importbatch IN ACCESS EXCLUSIVE MODE; SELECT pg_sleep(30); ROLLBACK;"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for n in range(50):
            if sql("SELECT count(*) FROM pg_locks WHERE relation='inventory_importbatch'::regclass AND mode='AccessExclusiveLock' AND granted")=="1":break
            time.sleep(.1)
        else:self.fail("lock not acquired")
        try:
            result=manage("0003",timeout=True)
            self.assertNotEqual(result.returncode,0);self.assertIn(b"lock timeout",result.stderr)
        finally:
            sql("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid<>pg_backend_pid() AND query LIKE 'BEGIN; LOCK TABLE inventory_importbatch%'")
            locker.wait(timeout=10)
        self.assertEqual(sql("SELECT count(*) FROM django_migrations WHERE app='inventory' AND name LIKE '0002%'"),"1")
        self.assertEqual(sql("SELECT count(*) FROM django_migrations WHERE app='inventory' AND name LIKE '0003%'"),"0")
        self.assertEqual(sql("SELECT count(*) FROM pg_proc WHERE proname LIKE 'itw_review_%'"),"0")
        partial=r.job(dict(cfg,db_container=DB),"snapshot")
        self.assertEqual(len(partial["tables"]),34)
        with self.assertRaises(subprocess.CalledProcessError):
            r.job(dict(cfg,db_container=DB,cluster=partial["identity"][4]),"apply",before=BASE/"ordered/before.json",write=True)
        with self.assertRaises(subprocess.CalledProcessError):
            r.job(dict(cfg,db_container=DB),"verify",before=BASE/"ordered/before.json")
    def test_08_partial_target_not_overwritten_restore_to_new_target(self):
        snap=r.restore(cfg,BASE/"ordered",BASE/"ordered/backup.dump",BASE/"ordered/roles-no-passwords.sql","itw-d4-recovery-check")
        self.assertEqual(len(snap["history"]),27)
        self.assertEqual(sql("SELECT count(*) FROM django_migrations WHERE app='inventory' AND name LIKE '0002%'"),"1")
if __name__=="__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FailureTests))
    r.save(BASE/"failure-results.json",dict(ran=result.testsRun,failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)))
    sys.exit(not result.wasSuccessful())

"""Disposable-only end-to-end rehearsal. Creates no named data volumes."""
import argparse,json,os,re,subprocess,time
from pathlib import Path
import runbook as r
parser=argparse.ArgumentParser();parser.add_argument("--tag",default="rehearsal");a=parser.parse_args()
if not re.fullmatch("[a-z0-9]{3,20}",a.tag):raise RuntimeError("INVALID_DISPOSABLE_TAG")
OUT=Path.home()/".local/share/it-warehouse-d4"/a.tag
OUT.mkdir(mode=0o700,parents=True,exist_ok=True)
cfg=json.load(open(r.HERE/"development.json"));cfg.update(mode="rehearsal",db_container="itw-d4-"+a.tag+"-db",apps=["itw-d4-"+a.tag+"-running","itw-d4-"+a.tag+"-stopped"])
def cmd(*args,**kw):return r.run(list(args),**kw)
cmd("docker","network","create","--label","itw.d4.created=true","itw-d4-"+a.tag+"-net")
cmd("docker","run","-d","--name",cfg["db_container"],"--label","itw.d4.created=true","--network","itw-d4-"+a.tag+"-net",
    "--tmpfs","/var/lib/postgresql/data:rw,noexec,nosuid,size=1g","-e","POSTGRES_USER=it_warehouse","-e","POSTGRES_PASSWORD=d4-disposable-only",cfg["postgres_image"])
for n in range(60):
    if subprocess.run(["docker","exec",cfg["db_container"],"pg_isready","-U","it_warehouse"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
    time.sleep(1)
else:raise RuntimeError("START_TIMEOUT")
archive=Path.home()/"it-warehouse-db-backups/it_warehouse_pre_review_migration_20261114_111141.dump"
assert r.digest(archive)=="2dfe16325d081973a41d246a065c631dc54560d459419d411fd820f057f97697"
with archive.open("rb") as f:cmd("docker","exec","-i",cfg["db_container"],"pg_restore","--single-transaction","--exit-on-error","-U","it_warehouse","-d","it_warehouse",stdin=f)
for app in cfg["apps"]:
    cmd("docker","run","-d","--name",app,"--label","itw.d4.created=true","--network","itw-d4-"+a.tag+"-net","--entrypoint","sleep",cfg["postgres_image"],"infinity")
cmd("docker","stop",cfg["apps"][1])
r.save(OUT/"rehearsal.json",cfg)
for action in ["audit","isolate","backup","restore-check","apply","verify","resume"]:
    result=cmd("python3",r.HERE/"runbook.py",action,"--config",OUT/"rehearsal.json","--state",OUT/"ordered","--execute-rehearsal",
        "--restore-name","itw-d4-"+a.tag+"-restored")
    (OUT/(action+".log")).write_bytes(result.stdout)
    print(action+": "+(result.stdout.decode() if action!="audit" else "READ_ONLY_INVENTORY_PASS"),flush=True)
assert r.inspect(cfg["apps"][0],".State.Status")=="running"
assert r.inspect(cfg["apps"][1],".State.Status")=="exited"
print("ORIGINAL_RUNNING_AND_STOPPED_APPLICATION_STATES_PRESERVED",flush=True)

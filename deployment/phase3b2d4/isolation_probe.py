"""Prove network isolation and pre-migration abort recovery on the disposable final twin."""
import json,subprocess
from pathlib import Path
import runbook as r
base=Path.home()/".local/share/it-warehouse-d4/final";cfg=json.load(open(base/"rehearsal.json"));state=base/"abort-probe"
def action(name,*extra):
    print(r.output(["python3",r.HERE/"runbook.py",name,"--config",base/"rehearsal.json","--state",state,"--execute-rehearsal",*extra]),flush=True)
ip=next(iter(r.inspect(cfg["db_container"],".NetworkSettings.Networks").values()))["IPAddress"]
action("isolate")
probe=subprocess.run(["docker","run","--rm","--network","bridge",cfg["postgres_image"],"pg_isready","-h",ip,"-p","5432","-U","it_warehouse","-t","2"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
assert probe.returncode==2
assert r.job(cfg,"snapshot")["sessions"]==[]
print("EXTERNAL_CONNECTION_DENIED_LOCAL_ADMIN_RETAINED",flush=True)
action("resume","--allow-pre-migration-abort")
assert r.inspect(cfg["apps"][0],".State.Status")=="running"
assert r.inspect(cfg["apps"][1],".State.Status")=="exited"
print("PRE_MIGRATION_ABORT_RECOVERY_PASS",flush=True)

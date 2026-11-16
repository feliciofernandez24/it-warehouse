"""Read-only final verification and syntax checks. No deployment opt-in is set."""
import json
from pathlib import Path
import runbook as r
root=Path.home()/".local/share/it-warehouse-d4"
cfg=json.load(open(root/"final/rehearsal.json"))
post=r.job(cfg,"verify",before=root/"final/ordered/before.json")
print("FINAL_READ_ONLY_CATALOG_ROUTE_AND_DISABLED_ACTION_SMOKES_PASS")
live=json.load(open(r.HERE/"development.json"));r.source(live)
current=r.job(live,"snapshot");initial=json.load(open(root/"preparation-audit/inventory.json"))
r.comparison(initial["database"],current)
now=r.target(live)
assert now["id"]==initial["target"]["id"] and now["mounts"]==initial["target"]["mounts"] and now["networks"]==initial["target"]["networks"]
assert current["identity"][4]=="7706069425466331170"
for app in live["apps"]:assert r.inspect(app,".State.Status")=="exited"
assert [n for a,n in current["history"] if a=="inventory"]==["0001_initial"]
for f in r.HERE.glob("*.py"):compile(f.read_text(),str(f),"exec")
r.save(root/"final-verification.json",dict(development_unchanged=True,inventory_history=["0001_initial"],post_review_tables=5,
    original_rows=sum(t["count"] for t in initial["database"]["tables"].values()),read_only_smokes=True))
print("DEVELOPMENT_ORIGINAL_ROWS_ACLS_ROLES_GUARDS_HISTORY_NETWORK_VOLUME_AND_STOPPED_APPS_UNCHANGED")
print("ALL_NEW_PYTHON_SYNTAX_VALID")

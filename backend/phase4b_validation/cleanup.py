"""Remove only this Phase 4B run's labeled disposable containers, never volumes."""
import json,os,subprocess
from pathlib import Path
OUT=Path.home()/".local/share/it-warehouse-phase4b"
def run(*args):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
names=["itw-phase4b-http-frontend","itw-phase4b-http-backend","itw-phase4b-test-client","itw-phase4b-test-db"]
objects=[]
for name in names:
    item=json.loads(run("docker","inspect",name).stdout)[0]
    if item["Name"]!="/"+name or item["Config"]["Labels"].get("itw.phase4b")!="true":
        raise RuntimeError("NOT_A_CREATED_PHASE4B_TEST_TARGET")
    if any(m["Type"]=="volume" for m in item["Mounts"]):
        raise RuntimeError("VOLUME_TARGET_REJECTED")
    if name.endswith("test-db") and "/var/lib/postgresql/data" not in item["HostConfig"]["Tmpfs"]:
        raise RuntimeError("DISPOSABLE_TMPFS_REQUIRED")
    objects.append(item["Id"])
for source,dest in [("/tmp/phase3b2d2-evidence.json","review-read-evidence.json"),("/tmp/phase3b2d2-runtime-evidence.json","runtime-evidence.json")]:
    data=run("docker","exec","itw-phase4b-test-client","cat",source).stdout
    with os.fdopen(os.open(OUT/dest,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600),"wb") as f:f.write(data)
for ident in objects:
    run("docker","stop",ident)
    run("docker","rm",ident)
print("ONLY_FOUR_VERIFIED_DISPOSABLE_PHASE4B_CONTAINERS_REMOVED; NO_VOLUME_DELETION")

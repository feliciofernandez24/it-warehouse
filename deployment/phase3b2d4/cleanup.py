"""Remove only resources created by the recorded D.4 rehearsals; never any development volume."""
import json,re
import runbook as r
NAMES=["itw-d4-rehearsal-db","itw-d4-app-running","itw-d4-app-stopped","itw-d4-restored-check",
    "itw-d4-regression-client","itw-d4-regression-db","itw-d4-failure-db","itw-d4-recovery-check",
    "itw-d4-final-running","itw-d4-final-stopped","itw-d4-final-db","itw-d4-final-restored"]
targets=[]
for name in NAMES:
    ident=r.inspect(name,".Id");labels=r.inspect(name,".Config.Labels") or {}
    if labels.get("itw.d4.created")!="true":raise RuntimeError("NOT_REHEARSAL_CREATED")
    for m in r.inspect(name,".Mounts"):
        if m["Type"]=="volume":
            if name not in ["itw-d4-app-running","itw-d4-app-stopped","itw-d4-final-running","itw-d4-final-stopped"]:
                raise RuntimeError("UNEXPECTED_VOLUME")
            if not re.fullmatch("[0-9a-f]{64}",m["Name"]):raise RuntimeError("NAMED_VOLUME_REJECTED")
            attached=r.output(["docker","ps","-aq","--no-trunc","--filter","volume="+m["Name"]]).splitlines()
            if attached!=[ident]:raise RuntimeError("SHARED_ANONYMOUS_VOLUME")
    targets.append(ident)
for ident in targets:
    r.run(["docker","stop",ident]);r.run(["docker","rm","-v",ident])
for name in ["itw-d4-rehearsal-net","itw-d4-final-net"]:
    labels=json.loads(r.output(["docker","network","inspect","--format","{{json .Labels}}",name]))
    if labels.get("itw.d4.created")!="true":raise RuntimeError("NOT_REHEARSAL_NETWORK")
    r.run(["docker","network","rm",name])
print("ONLY_TWELVE_REHEARSAL_CONTAINERS_THEIR_EXCLUSIVE_ANONYMOUS_VOLUMES_AND_TWO_NETWORKS_REMOVED")

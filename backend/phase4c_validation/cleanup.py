"""Remove only this run's explicitly named, labeled tmpfs test containers."""
import json,subprocess
names=["itw-phase4c-test-client","itw-phase4c-test-db"]
objects=[]
for name in names:
 item=json.loads(subprocess.check_output(["docker","inspect",name]))[0]
 assert item["Name"]=="/"+name
 assert item["Config"]["Labels"].get("itw.phase4c")=="true"
 assert not any(m["Type"]=="volume" for m in item["Mounts"])
 if name.endswith("test-db"):assert "/var/lib/postgresql/data" in item["HostConfig"]["Tmpfs"]
 objects.append(item["Id"])
for ident in objects:
 subprocess.run(["docker","stop",ident],check=True,stdout=subprocess.DEVNULL)
 subprocess.run(["docker","rm",ident],check=True,stdout=subprocess.DEVNULL)
print("Only verified disposable Phase 4C containers removed; no volumes deleted.")

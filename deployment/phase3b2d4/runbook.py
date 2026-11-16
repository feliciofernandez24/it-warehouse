"""Host-side reviewed runbook. audit is read-only; all other actions require explicit authorization."""
import argparse,hashlib,json,os,shutil,stat,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
HASHES={"0002_import_review_schema.py":"0a9028ef00485e0048cbb21b9e8011a707cbd2380a404a6ca7974f141a06133c",
        "0003_import_review_guards.py":"58fff9f1844291019ef8f55497b547d7d19968b440dcd273c414b96f4fa5e879"}
def run(args,**kwargs):
    return subprocess.run(list(map(str,args)),check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
def output(args): return run(args).stdout.decode().strip()
def digest(path):
    d=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):d.update(block)
    return d.hexdigest()
def save(path,data):
    path=Path(path);temp=path.with_suffix(path.suffix+".tmp")
    with open(os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),"w") as f:
        json.dump(data,f,indent=2,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
def inspect(name,field): return json.loads(output(["docker","inspect","--format","{{json "+field+"}}",name]))
def target(cfg):
    db=cfg["db_container"]
    ident={"id":inspect(db,".Id"),"mounts":inspect(db,".Mounts"),"networks":inspect(db,".NetworkSettings.Networks"),
        "ports":inspect(db,".HostConfig.PortBindings"),"image":inspect(db,".Image"),"state":inspect(db,".State.Status")}
    if ident["state"]!="running" or ident["ports"]:raise RuntimeError("DATABASE_NOT_RUNNING_OR_PUBLISHED")
    if cfg["mode"]=="development":
        if db!="it-warehouse-db-1" or cfg["database"]!="it_warehouse":raise RuntimeError("DEVELOPMENT_TARGET_MISMATCH")
        expected=[m for m in ident["mounts"] if m.get("Name")=="it-warehouse_postgres_data"
                  and m["Destination"]=="/var/lib/postgresql/data" and m["Type"]=="volume"]
        if len(expected)!=1 or ident["id"]!=cfg["container_id"]:raise RuntimeError("VOLUME_OR_CONTAINER_MISMATCH")
    elif cfg["mode"]=="rehearsal":
        if not db.startswith("itw-d4-") or any(m["Type"]=="volume" for m in ident["mounts"]):
            raise RuntimeError("REHEARSAL_TARGET_REJECTED")
        if "/var/lib/postgresql/data" not in inspect(db,".HostConfig.Tmpfs"):raise RuntimeError("TMPFS_REQUIRED")
    else:raise RuntimeError("UNKNOWN_MODE")
    if ident["image"]!=cfg["postgres_image"]:raise RuntimeError("IMAGE_MISMATCH")
    return ident
def source(cfg):
    if output(["git","-C",ROOT,"rev-parse","HEAD"])!=cfg["head"]:raise RuntimeError("HEAD_MISMATCH")
    run(["git","-C",ROOT,"diff","--exit-code"]);run(["git","-C",ROOT,"diff","--cached","--exit-code"])
    for name,expected in HASHES.items():
        if digest(ROOT/"backend/apps/inventory/migrations"/name)!=expected:raise RuntimeError("MIGRATION_HASH_MISMATCH")
def authorize(cfg,args):
    source(cfg);target(cfg)
    if cfg["mode"]=="development":
        approval=json.load(open(args.approval)) if args.approval else {}
        expected=cfg["head"]+":"+cfg["container_id"]
        if (not args.execute_development or os.environ.get("ITW_D4_AUTHORIZE_PERSISTENT")!=expected
            or not approval.get("approver") or approval.get("head")!=cfg["head"]
            or approval.get("container_id")!=cfg["container_id"]
            or not all(approval.get(k) is True for k in ["accept_superuser_owner_risk","exclusive_docker_host_control",
                "background_jobs_reviewed","unrelated_dependents_reviewed"])):
            raise RuntimeError("LATER_DEVELOPMENT_AUTHORIZATION_REQUIRED")
        for f in ("runbook.py","dbcheck.py"):
            if approval.get("script_hashes",{}).get(f)!=digest(HERE/f):raise RuntimeError("SCRIPT_APPROVAL_REQUIRED")
    elif not args.execute_rehearsal:raise RuntimeError("REHEARSAL_OPT_IN_REQUIRED")
def job(cfg,action,before=None,write=False,db=None):
    db=db or cfg["db_container"]
    args=["docker","run","--rm","--network","container:"+db,
        "--mount",f"type=bind,source={ROOT/'backend'},target=/app,readonly",
        "--mount",f"type=bind,source={HERE},target=/runbook,readonly",
        "-e","PYTHONDONTWRITEBYTECODE=1","-e","DJANGO_SECRET_KEY=d4-maintenance-process-only",
        "-e","POSTGRES_HOST=127.0.0.1","-e","POSTGRES_DB="+cfg["database"],
        "-e","POSTGRES_USER=it_warehouse","-e","POSTGRES_PASSWORD=local-maintenance-not-a-production-secret"]
    if before:
        args+=["--mount",f"type=bind,source={Path(before).resolve()},target=/before.json,readonly"]
    if write:
        args+=["-e","PGOPTIONS=-clock_timeout=5s -cstatement_timeout=60s"]
        args+=["-e","ITW_D4_EXECUTE=AUTHORIZE_INVENTORY_0002_0003","-e","ITW_D4_CLUSTER="+cfg["cluster"]]
    else:args+=["-e","PGOPTIONS=-cdefault_transaction_read_only=on"]
    args+=[cfg["backend_image"],"python","/runbook/dbcheck.py",action]
    if before:args+=["--before","/before.json"]
    return json.loads(run(args).stdout)
def isolated(cfg,state):
    ident=target(cfg)
    if ident["id"]!=state["target"]["id"] or ident["mounts"]!=state["target"]["mounts"] or ident["networks"]:
        raise RuntimeError("ISOLATION_OR_IDENTITY_LOST")
    snap=job(cfg,"snapshot")
    if snap["identity"][4]!=state["cluster"] or snap["sessions"]:raise RuntimeError("OTHER_SESSIONS_OR_CLUSTER_CHANGED")
    return snap
def file_output(cmd,path):
    # No shell or pipeline; subprocess errors cannot be masked by redirection.
    with open(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),"wb") as f:
        subprocess.run(cmd,stdout=f,stderr=subprocess.PIPE,check=True)
        f.flush();os.fsync(f.fileno())
    if Path(path).stat().st_size==0:raise RuntimeError("EMPTY_BACKUP")
def restore(cfg,out,archive,globals_file,name):
    if not name.startswith("itw-d4-"):raise RuntimeError("DISPOSABLE_NAME_REQUIRED")
    run(["docker","run","-d","--name",name,"--label","itw.d4.created=true","--network","none",
         "--tmpfs","/var/lib/postgresql/data:rw,noexec,nosuid,size=1g","-e","POSTGRES_USER=restore_admin",
         "-e","POSTGRES_PASSWORD=d4-disposable-only",cfg["postgres_image"]])
    for attempt in range(60):
        if subprocess.run(["docker","exec",name,"pg_isready","-U","restore_admin"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
        time.sleep(1)
    else:raise RuntimeError("RESTORE_SERVER_TIMEOUT")
    with open(globals_file,"rb") as f:
        run(["docker","exec","-i",name,"psql","-X","-q","-v","ON_ERROR_STOP=1","-U","restore_admin","-d","postgres"],stdin=f)
    run(["docker","exec",name,"createdb","-U","restore_admin","-O","it_warehouse",cfg["database"]])
    # Empty disposable database only: recreate built-in PL/pgSQL under the recorded source owner.
    run(["docker","exec",name,"psql","-X","-v","ON_ERROR_STOP=1","-U","it_warehouse","-d",cfg["database"],
        "-c","DROP EXTENSION plpgsql; CREATE EXTENSION plpgsql;"])
    with open(archive,"rb") as f:
        run(["docker","exec","-i",name,"pg_restore","--single-transaction","--exit-on-error","-U","restore_admin","-d",cfg["database"]],stdin=f)
    snap=job(cfg,"snapshot",db=name)
    before=json.load(open(out/"before.json"))
    comparison(before,snap)
    return snap

def comparison(before,after):
    # Import only the pure comparator; importing dbcheck itself would initialize Django.
    import ast
    tree=ast.parse((HERE/"dbcheck.py").read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="compare")
    ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),"<manifest-compare>","exec"),ns)
    ns["compare"](before,after)

def verified_backup(out):
    backup=json.load(open(out/"backup.json"));proof=json.load(open(out/"restore.json"))
    if (not proof["passed"] or proof["backup_sha256"]!=digest(out/"backup.dump")
        or backup["sha256"]!=digest(out/"backup.dump")
        or backup["roles_sha256"]!=digest(out/"roles-no-passwords.sql")
        or backup["before_sha256"]!=digest(out/"before.json")
        or proof["before_sha256"]!=digest(out/"before.json") or time.time()-backup["created"]>7200):
        raise RuntimeError("FRESH_VERIFIED_BACKUP_REQUIRED")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["audit","isolate","backup","restore-check","apply","verify","resume"])
    p.add_argument("--config",required=True);p.add_argument("--state",required=True)
    p.add_argument("--execute-development",action="store_true");p.add_argument("--execute-rehearsal",action="store_true")
    p.add_argument("--approval");p.add_argument("--restore-name",default="itw-d4-restore-check")
    p.add_argument("--allow-pre-migration-abort",action="store_true");a=p.parse_args()
    cfg=json.load(open(a.config));out=Path(a.state).resolve()
    if out.exists() and (out.is_symlink() or stat.S_IMODE(out.stat().st_mode)!=0o700):raise RuntimeError("PRIVATE_STATE_DIRECTORY_REQUIRED")
    out.mkdir(mode=0o700,parents=True,exist_ok=True)
    if a.action=="audit":
        source(cfg);ident=target(cfg);snap=job(cfg,"snapshot");save(out/"inventory.json",{"target":ident,"database":snap})
        print(json.dumps({"read_only":True,"container_id":ident["id"],"history":snap["history"],
            "table_counts":{k:v["count"] for k,v in snap["tables"].items()},"roles":snap["roles"],"sessions":snap["sessions"]}))
        return
    authorize(cfg,a)
    if a.action=="isolate":
        if (out/"state.json").exists():raise RuntimeError("NEW_STATE_DIRECTORY_REQUIRED")
        ident=target(cfg);snap=job(cfg,"snapshot")
        if snap["sessions"]:raise RuntimeError("UNREVIEWED_SESSIONS")
        state={"target":ident,"cluster":snap["identity"][4],"apps":[],"disconnected":[],"verified":False}
        save(out/"before.json",snap)
        cfg["cluster"]=state["cluster"]
        save(out/"config-used.json",cfg);save(out/"state.json",state)
        for app in cfg["apps"]:
            if inspect(app,".Id")==ident["id"]:raise RuntimeError("DATABASE_CANNOT_BE_STOPPED")
            item={"name":app,"id":inspect(app,".Id"),"status":inspect(app,".State.Status")}
            state["apps"].append(item);save(out/"state.json",state)
            if item["status"]=="running":run(["docker","stop",item["id"]])
        for network,data in ident["networks"].items():
            run(["docker","network","disconnect",network,ident["id"]])
            state["disconnected"].append(network);save(out/"state.json",state)
        isolated(cfg,state);print("ISOLATED_DATABASE_ID_AND_VOLUME_UNCHANGED");return
    state=json.load(open(out/"state.json"));cfg["cluster"]=state["cluster"]
    if a.action=="backup":
        snap=isolated(cfg,state);job(cfg,"plan")
        required=max(1024**3,snap["identity"][5]*8)
        if shutil.disk_usage(out).free<required or snap["identity"][5]*8>1024**3:raise RuntimeError("BACKUP_OR_RESTORE_CAPACITY_INSUFFICIENT")
        save(out/"before.json",snap)
        archive=out/"backup.dump";globals_file=out/"roles-no-passwords.sql"
        file_output(["docker","exec",cfg["db_container"],"pg_dump","-U","it_warehouse","-d",cfg["database"],"-Fc"],archive)
        file_output(["docker","exec",cfg["db_container"],"pg_dumpall","-U","it_warehouse","--roles-only","--no-role-passwords"],globals_file)
        listing=out/"archive.list"
        file_output(["docker","run","--rm","--network","none","--mount",f"type=bind,source={archive},target=/backup.dump,readonly",
            "--entrypoint","pg_restore",cfg["postgres_image"],"--list","/backup.dump"],listing)
        save(out/"backup.json",{"sha256":digest(archive),"bytes":archive.stat().st_size,
            "roles_sha256":digest(globals_file),"created":time.time(),"before_sha256":digest(out/"before.json")})
        print("PRIVATE_BACKUP_COMPLETE_AND_ARCHIVE_READABLE");return
    if a.action=="restore-check":
        isolated(cfg,state);backup=json.load(open(out/"backup.json"))
        if digest(out/"backup.dump")!=backup["sha256"] or digest(out/"roles-no-passwords.sql")!=backup["roles_sha256"]:raise RuntimeError("BACKUP_HASH_MISMATCH")
        snap=restore(cfg,out,out/"backup.dump",out/"roles-no-passwords.sql",a.restore_name)
        save(out/"restore.json",{"passed":True,"backup_sha256":backup["sha256"],"before_sha256":digest(out/"before.json"),
            "container":a.restore_name,"tables":len(snap["tables"])})
        print("DISPOSABLE_RESTORE_DATA_ROLE_ACL_OWNER_HISTORY_MATCH");return
    if a.action in ("apply","verify"):
        isolated(cfg,state)
        verified_backup(out)
        after=job(cfg,a.action,before=out/"before.json",write=a.action=="apply")
        save(out/"after.json",after);state["verified"]=True;save(out/"state.json",state)
        print("MIGRATION_AND_PRESERVATION_VERIFIED");return
    if not state["verified"]:
        if not a.allow_pre_migration_abort:raise RuntimeError("VERIFIED_OUTCOME_REQUIRED_BEFORE_RESUME")
        current=isolated(cfg,state)
        before=json.load(open(out/"before.json"))
        if current["history"]!=before["history"]:raise RuntimeError("NO_BLIND_RESUME_AFTER_DDL")
        comparison(before,current)
    if state["verified"]:job(cfg,"verify",before=out/"before.json")
    ident=target(cfg)
    if ident["id"]!=state["target"]["id"] or ident["mounts"]!=state["target"]["mounts"]:raise RuntimeError("DATABASE_CHANGED")
    for network in state["disconnected"]:
        data=state["target"]["networks"][network];cmd=["docker","network","connect"]
        if data.get("IPAddress"):cmd+=["--ip",data["IPAddress"]]
        for alias in data.get("Aliases") or []:cmd+=["--alias",alias]
        cmd += [network,ident["id"]];run(cmd)
    for app in state["apps"]:
        if inspect(app["name"],".Id")!=app["id"]:raise RuntimeError("APPLICATION_RECREATED")
        if app["status"]=="running":run(["docker","start",app["id"]])
    print("ORIGINAL_NETWORK_AND_PREVIOUSLY_RUNNING_APPS_ONLY_RESTORED")

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("STOP: "+(str(e) if isinstance(e,RuntimeError) else type(e).__name__),file=sys.stderr)
        sys.exit(1)

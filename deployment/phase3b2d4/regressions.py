"""Existing suites on an additional synthetic tmpfs cluster, with no persistent connection."""
import json,subprocess,time
from pathlib import Path
import runbook as r
cfg=json.load(open(r.HERE/"development.json"))
out=Path.home()/".local/share/it-warehouse-d4/regressions";out.mkdir(mode=0o700,parents=True,exist_ok=True)
db="itw-d4-regression-db";client="itw-d4-regression-client"
r.run(["docker","run","-d","--name",db,"--label","itw.d4.created=true","--network","none","--tmpfs","/var/lib/postgresql/data:rw,noexec,nosuid,size=1g",
    "-e","POSTGRES_USER=postgres","-e","POSTGRES_PASSWORD=phase3b2d2-synthetic-only","-e","POSTGRES_DB=phase3b2b1_test",cfg["postgres_image"]])
for n in range(60):
    if subprocess.run(["docker","exec",db,"pg_isready","-U","postgres"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
    time.sleep(1)
else:raise RuntimeError("TIMEOUT")
r.run(["docker","run","-d","--name",client,"--label","itw.d4.created=true","--network","container:"+db,
    "--mount",f"type=bind,source={r.ROOT/'backend'},target=/app,readonly","-e","PYTHONDONTWRITEBYTECODE=1","-e","DJANGO_SECRET_KEY=d4-regression-only",
    "-e","POSTGRES_USER=postgres","-e","POSTGRES_PASSWORD=phase3b2d2-synthetic-only","-e","POSTGRES_DB=phase3b2b1_test","-e","POSTGRES_HOST=127.0.0.1",
    cfg["backend_image"],"sleep","infinity"])
commands=[
("current",["python","manage.py","test","config.tests","apps.inventory.test_staging","apps.transactions.test_engine","apps.inventory.test_review_schema",
    "apps.inventory.test_review_hardening","apps.inventory.test_review_services","apps.inventory.test_review_gateway","--noinput"],[]),
("historical",["python","manage.py","test","apps.inventory.tests","apps.transactions.tests","--settings=config.settings.historical_tests","--noinput"],
    ["-e","POSTGRES_DB=phase3b2a_history","-e","ITW_ISOLATED_TESTS=1"]),
("migrate-synthetic",["python","manage.py","migrate","--noinput"],[]),
("read-proof",["python","feasibility_review_read/run.py"],["-e","ITW_REVIEW_READ_PROOF=1"]),
("runtime",["python","feasibility_review_read/runtime_regression.py"],["-e","ITW_REVIEW_READ_PROOF=1"]),
("model-drift",["python","manage.py","makemigrations","--check","--dry-run"],["-e","POSTGRES_PASSWORD=runtime-rehearsal-admin-only"])]
for name,args,env in commands:
    result=subprocess.run(["docker","exec",*env,client,*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (out/(name+".log")).write_bytes(result.stdout)
    print(name+" exit="+str(result.returncode)+"\n"+result.stdout.decode()[-1300:],flush=True)
    if result.returncode:raise RuntimeError(name+" failed; inspect private log")

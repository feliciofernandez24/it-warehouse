"""Phase 4C tests on a new private PostgreSQL 17 cluster; never loads .env."""
import json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path.home()/".local/share/it-warehouse-phase4c";OUT.mkdir(mode=0o700,parents=True,exist_ok=True)
DB="itw-phase4c-test-db";CLIENT="itw-phase4c-test-client"
def run(args):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
run(["docker","run","-d","--name",DB,"--label","itw.phase4c=true","--network","none",
     "--tmpfs","/var/lib/postgresql/data:rw,noexec,nosuid,size=1g",
     "-e","POSTGRES_PASSWORD=phase3b2d2-synthetic-only","-e","POSTGRES_DB=phase3b2b1_test","postgres:17-alpine"])
for n in range(60):
    if subprocess.run(["docker","exec",DB,"pg_isready","-U","postgres"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
    time.sleep(1)
else:raise RuntimeError("DISPOSABLE_DB_TIMEOUT")
run(["docker","run","-d","--name",CLIENT,"--label","itw.phase4c=true","--network","container:"+DB,
     "--mount","type=bind,source="+str(ROOT/"backend")+",target=/app,readonly",
     "-e","ITW_PHASE4A_TEST=1","-e","ITW_PHASE4B_TEST=1","-e","PYTHONDONTWRITEBYTECODE=1",
     "-e","DJANGO_SECRET_KEY=phase4b-test-only","-e","POSTGRES_HOST=127.0.0.1",
     "-e","POSTGRES_DB=phase3b2b1_test","-e","POSTGRES_USER=postgres","-e","POSTGRES_PASSWORD=phase3b2d2-synthetic-only",
     "itw-phase4c-backend-validation","sleep","infinity"])
stages=[
("phase4c",[],["python","manage.py","test","config.test_phase4c","--noinput"]),
("master-delete",[],["python","manage.py","test","config.test_master_delete","--noinput"]),
("phase4b",[],["python","manage.py","test","config.test_phase4b","--noinput"]),
("phase4a",[],["python","manage.py","test","config.test_phase4a","--noinput"]),
("current",[],["python","manage.py","test","config.tests","apps.inventory.test_staging","apps.transactions.test_engine",
 "apps.inventory.test_review_schema","apps.inventory.test_review_hardening","apps.inventory.test_review_services","apps.inventory.test_review_gateway","--noinput"]),
("historical",["-e","POSTGRES_DB=phase3b2a_history","-e","ITW_ISOLATED_TESTS=1"],
 ["python","manage.py","test","apps.inventory.tests","apps.transactions.tests","--settings=config.settings.historical_tests","--noinput"]),
("migrate-synthetic",[],["python","manage.py","migrate","--noinput"]),
("phase4b-runtime",[],["python","phase4b_validation/runtime_probe.py"]),
("phase4a-runtime",[],["python","phase4a_validation/runtime_probe.py"]),
("read-proof",["-e","ITW_REVIEW_READ_PROOF=1"],["python","feasibility_review_read/run.py"]),
("runtime-regression",["-e","ITW_REVIEW_READ_PROOF=1"],["python","feasibility_review_read/runtime_regression.py"]),
("model-drift",["-e","POSTGRES_PASSWORD=runtime-rehearsal-admin-only"],["python","manage.py","makemigrations","--check","--dry-run"]),
("system-check",["-e","POSTGRES_PASSWORD=runtime-rehearsal-admin-only"],["python","manage.py","check"]),
]
stages.append(("phase4c-runtime",["-e","POSTGRES_PASSWORD=runtime-rehearsal-admin-only"],["python","phase4c_validation/runtime_probe.py"]))
stages.append(("master-delete-runtime",["-e","POSTGRES_PASSWORD=runtime-rehearsal-admin-only"],["python","phase4c_validation/master_delete_runtime.py"]))
for name,env,args in stages:
    result=subprocess.run(["docker","exec",*env,CLIENT,*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    with os.fdopen(os.open(OUT/(name+".log"),os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600),"wb") as f:f.write(result.stdout)
    print(name+" exit="+str(result.returncode)+"\n"+result.stdout.decode()[-3500:],flush=True)
    if result.returncode:raise RuntimeError(name+" failed; inspect private log")

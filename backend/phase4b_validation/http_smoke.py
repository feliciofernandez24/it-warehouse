"""Real HTTP/Vite master writes on the disposable Phase 4B clone only."""
import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path.home()/".local/share/it-warehouse-phase4b"
def run(*args,**kw):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
setup=b'''import os,json
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django;django.setup()
from django.contrib.auth import get_user_model
from django.db import connection
u=get_user_model().objects.get(username="phase4b-editor")
u.set_password("phase4b-http-only");u.save(update_fields=["password"])
tables=["inventory_assetcategory","inventory_manufacturer","inventory_productmodel","warehouse_warehouse","warehouse_storagelocation","inventory_asset","transactions_stockmovement","transactions_stockoperation","inventory_stockbalance","audits_assetchangelog"]
with connection.cursor() as c:
    result={}
    for table in tables:
        c.execute("SELECT count(*) FROM "+table);result[table]=c.fetchone()[0]
print(json.dumps(result))
'''
before=json.loads(run("docker","exec","-i","-e","POSTGRES_DB=phase4b_runtime_test","-e","POSTGRES_PASSWORD=runtime-rehearsal-admin-only",
    "itw-phase4b-test-client","python","-",input=setup).stdout)
run("docker","run","-d","--name","itw-phase4b-http-backend","--label","itw.phase4b=true","--network","container:itw-phase4b-test-db",
    "-e","DJANGO_SECRET_KEY=phase4b-private-http-only","-e","DJANGO_DEBUG=true","-e","DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost",
    "-e","DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173","-e","POSTGRES_HOST=127.0.0.1","-e","POSTGRES_DB=phase4b_runtime_test",
    "-e","POSTGRES_USER=itw_phase4b_runtime","-e","POSTGRES_PASSWORD=phase4b-runtime-only",
    "itw-phase4b-backend-validation","python","-c",
    "from wsgiref.simple_server import make_server; from config.wsgi import application; make_server('0.0.0.0',8000,application).serve_forever()")
run("docker","run","-d","--name","itw-phase4b-http-frontend","--label","itw.phase4b=true","--network","container:itw-phase4b-test-db",
    "-e","VITE_PROXY_TARGET=http://127.0.0.1:8000","itw-phase4b-frontend-validation")
client=b'''import http.cookiejar,json,time,urllib.error,urllib.request
origin="http://127.0.0.1:5173"
for n in range(30):
    try:
        with urllib.request.urlopen(origin+"/api/health/",timeout=2) as r:
            if r.status==200:break
    except Exception:time.sleep(.5)
else:raise RuntimeError("PRIVATE_HTTP_READINESS_FAILED")
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def req(path,method="GET",data=None,token=None):
    headers={"Origin":origin}
    if token:headers["X-CSRFToken"]=token
    if data is not None:headers["Content-Type"]="application/json"
    q=urllib.request.Request(origin+path,data=None if data is None else json.dumps(data).encode(),headers=headers,method=method)
    try:
        with opener.open(q,timeout=5) as r:return r.status,r.read()
    except urllib.error.HTTPError as r:return r.code,r.read()
assert req("/")[0]==200
assert req("/api/management/categories/")[0]==401
token=json.loads(req("/api/auth/csrf/")[1])["csrfToken"]
status,body=req("/api/auth/login/","POST",{"username":"phase4b-editor","password":"phase4b-http-only"},token)
assert status==200,body
token=json.loads(body)["csrfToken"]
assert req("/api/management/categories/","POST",{"code":"BAD","name":"No token","change_reason":"test"})[0]==403
ids={}
for resource in ["categories","manufacturers","product-models","warehouses","locations"]:
    payload={"code":"HTTPTEST","name":"HTTP created","change_reason":"Synthetic HTTP proof"}
    if resource=="product-models":payload={"sku_code":"HTTPTEST","name":"HTTP created","category":ids["categories"],"manufacturer":ids["manufacturers"],"tracking_mode":"BULK","change_reason":"Synthetic product"}
    if resource=="locations":payload.update(warehouse=ids["warehouses"],kind="AREA")
    status,body=req("/api/management/"+resource+"/","POST",payload,token)
    assert status==201,(resource,status,body)
    ids[resource]=json.loads(body)["id"]
status,body=req("/api/management/categories/"+str(ids["categories"])+"/","PATCH",{"name":"HTTP corrected","expected_version":0,"change_reason":"HTTP correction"},token)
assert status==200,body
assert req("/api/management/categories/"+str(ids["categories"])+"/","PATCH",{"name":"Stale","expected_version":0,"change_reason":"Stale"},token)[0]==409
row=json.loads(req("/api/inventory/assets/")[1])["results"][0]
asset=json.loads(req("/api/management/assets/"+str(row["id"])+"/")[1])
status,body=req("/api/management/assets/"+str(row["id"])+"/","PATCH",{"device_name":"HTTP metadata corrected","expected_version":asset["version"],"change_reason":"Metadata only"},token)
assert status==200,body
status,body=req("/api/management/assets/","POST",{"product_model":asset["product_model_id"],"current_location":asset["current_location_id"],"device_name":"Blocked","change_reason":"No receipt"},token)
assert status==409 and json.loads(body)["code"]=="ASSET_REGISTRATION_REQUIRES_RECEIPT"
assert req("/api/management/categories/"+str(ids["categories"])+"/","DELETE",{},token)[0]==405
assert req("/api/inventory/categories/","POST",{},token)[0]==405
assert req("/api/auth/logout/","POST",{},token)[0]==200
assert req("/api/auth/me/")[0]==401
print(json.dumps({"http":"PASS","frontend":200,"login":200,"five_master_creates":201,"metadata_updates":200,
"missing_csrf":403,"stale_edit":409,"asset_registration":409,"deletion":405,"legacy_write":405,"logout":200,
"runtime":"itw_phase4b_runtime","published_ports":False}))
'''
result=run("docker","exec","-i","itw-phase4b-test-client","python","-",input=client)
after=json.loads(run("docker","exec","-i","-e","POSTGRES_DB=phase4b_runtime_test","-e","POSTGRES_PASSWORD=runtime-rehearsal-admin-only",
    "itw-phase4b-test-client","python","-",input=setup).stdout)
for table in ["inventory_assetcategory","inventory_manufacturer","inventory_productmodel","warehouse_warehouse","warehouse_storagelocation"]:
    assert after[table]==before[table]+1
for table in ["inventory_asset","transactions_stockmovement","transactions_stockoperation","inventory_stockbalance"]:
    assert after[table]==before[table]
assert after["audits_assetchangelog"]==before["audits_assetchangelog"]+7
record=json.loads(result.stdout);record.update(audit_events_added=7,stock_history_unchanged=True,scope="Disposable fixtures only")
with os.fdopen(os.open(OUT/"http-smoke.json",os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600),"w") as f:json.dump(record,f,indent=2)
print(json.dumps(record,indent=2))

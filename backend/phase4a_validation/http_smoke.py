"""HTTP session + Vite smoke inside the disposable DB's private network namespace."""
import json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path.home()/".local/share/it-warehouse-phase4a"
def run(*args,**kw):return subprocess.run(list(args),check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
seed=b'''import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django;django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
u=get_user_model().objects.get(username="phase4-reader")
u.user_permissions.add(Permission.objects.get(content_type__app_label="inventory",codename="view_asset"))
'''
run("docker","exec","-i","-e","POSTGRES_DB=phase4a_runtime_test","-e","POSTGRES_PASSWORD=runtime-rehearsal-admin-only",
    "itw-phase4a-test-client","python","-",input=seed)
run("docker","run","-d","--name","itw-phase4a-http-backend","--label","itw.phase4a=true","--network","container:itw-phase4a-test-db",
    "-e","DJANGO_SECRET_KEY=phase4a-isolated-http-only","-e","DJANGO_DEBUG=true",
    "-e","DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost","-e","DJANGO_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173",
    "-e","POSTGRES_HOST=127.0.0.1","-e","POSTGRES_DB=phase4a_runtime_test","-e","POSTGRES_USER=itw_phase4a_runtime",
    "-e","POSTGRES_PASSWORD=phase4-runtime-only","itw-phase4a-backend-validation","python","-c",
    "from wsgiref.simple_server import make_server; from config.wsgi import application; make_server('0.0.0.0',8000,application).serve_forever()")
run("docker","run","-d","--name","itw-phase4a-http-frontend","--label","itw.phase4a=true","--network","container:itw-phase4a-test-db",
    "-e","VITE_PROXY_TARGET=http://127.0.0.1:8000",
    "--mount","type=bind,source="+str(ROOT/"frontend/vite.config.js")+",target=/app/vite.config.js,readonly",
    "--mount","type=bind,source="+str(ROOT/"frontend/proxy-target.js")+",target=/app/proxy-target.js,readonly",
    "itw-phase4a-frontend-validation")
client=b'''import http.cookiejar,json,time,urllib.error,urllib.request
origin="http://127.0.0.1:5173"
for n in range(30):
    try:
        with urllib.request.urlopen(origin+"/api/health/",timeout=2) as response:
            if response.status==200:break
    except Exception:time.sleep(.5)
else:raise RuntimeError("HTTP_SMOKE_READINESS_FAILED")
jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def req(path,method="GET",data=None,token=None):
    headers={"Origin":origin}
    if token:headers["X-CSRFToken"]=token
    if data is not None:headers["Content-Type"]="application/json"
    request=urllib.request.Request(origin+path,data=None if data is None else json.dumps(data).encode(),headers=headers,method=method)
    try:
        with opener.open(request,timeout=5) as response:return response.status,response.read()
    except urllib.error.HTTPError as response:return response.code,response.read()
assert req("/")[0]==200
assert req("/api/inventory/assets/")[0]==401
csrf=json.loads(req("/api/auth/csrf/")[1])["csrfToken"]
status,body=req("/api/auth/login/","POST",{"username":"phase4-reader","password":"synthetic-phase4-password"},csrf)
assert status==200,body
new_token=json.loads(body)["csrfToken"]
assert req("/api/auth/me/")[0]==200
status,body=req("/api/dashboard/summary/");assert status==200 and json.loads(body)["total_assets"]==1
status,body=req("/api/inventory/assets/");assert status==200 and json.loads(body)["count"]==1
assert req("/api/auth/logout/","POST",{})[0]==403
assert req("/api/auth/logout/","POST",{},new_token)[0]==200
assert req("/api/auth/me/")[0]==401
print(json.dumps({"http_smoke":"PASS","frontend_html":200,"proxy_health":200,"anonymous_asset_read":401,"login":200,
"dashboard":200,"assets":200,"logout_without_csrf":403,"logout":200,"session_after_logout":401,
"runtime_user":"itw_phase4a_runtime","scope":"Synthetic fixtures; private shared namespace, no published ports."}))
'''
result=run("docker","exec","-i","itw-phase4a-test-client","python","-",input=client)
with os.fdopen(os.open(OUT/"http-smoke.json",os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600),"wb") as f:f.write(result.stdout)
print(result.stdout.decode())

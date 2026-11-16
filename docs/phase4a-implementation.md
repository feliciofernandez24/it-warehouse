# Phase 4A implementation

Date: 2026-11-16. Starting develop HEAD: f059d114ccbd6e94d053b3236e9c69342e67668f. Implementation and isolated validation are complete; this is **not a successful persistent deployment claim**.

## Environment actually observed

A read-only PostgreSQL query confirmed inventory.0001, .0002 and .0003 are applied in it_warehouse. This differs from the historical stopped D.5 report; that preexisting untracked report was preserved, not rewritten. Phase 4A did not run a persistent migration or alter any historical migration.

At initial inspection itw_app_runtime was absent. During work, application containers were externally started/configured. A read-only query executed through the actual Django container returned session_user=current_user=itwarehouse_backend. That role has no superuser, CREATEDB, CREATEROLE, REPLICATION or BYPASSRLS flags, no memberships and no public-schema CREATE privilege. However, it currently has direct SELECT privilege on inventory_importreviewevent and UPDATE privilege on transactions_stockmovement. The former conflicts with the reviewed evidence-isolation policy; UPDATE privilege alone does not demonstrate that immutable-ledger guards can be bypassed.

No persistent credentials, owners, roles or ACLs were changed. No persistent fixtures, stock service calls, login/logout tests or destructive probes were executed. The existing backend was not restarted. Its new routes were available through the existing source bind/reloader. Read-only HTTP checks returned health 200, CSRF 200, anonymous me 401 and anonymous assets 401.

The externally running frontend subsequently exited. Its logs identify an invalid VITE_PROXY_TARGET value, http://backend:8000git. The active .env was not read wholesale or edited. Correct the nonsecret proxy setting to http://backend:8000 through the authorized configuration workflow. Persistent application activation remains blocked on runtime-ACL review and configuration readiness. No persistent service was started or recreated by this phase.

## Architecture

Existing Django User, AssetCategory, Manufacturer, ProductModel, Asset, StockBalance, StockThreshold, Warehouse, StorageLocation and StockMovement models are reused. No model, schema, trigger, stock service or protected review code changed.

- apps/accounts/session_api.py: ordinary Django JSON views for CSRF bootstrap, login, logout and current user.
- apps/inventory/read_api.py: explicit DRF serializers, model-view permissions, bounded pagination/filtering and read-only viewsets; dashboard ORM aggregates.
- config/api_urls.py: namespaced-by-path API routing; existing admin and public health stay available.
- frontend/src/App.jsx: reusable Login, State, Dashboard and Catalog components, session-aware protected hash routes, navigation, responsive layout, search/filter/pagination and asset detail.
- frontend/src/api.js: relative same-origin fetch client with in-memory CSRF token and session-expiry handling.
- frontend/proxy-target.js: safe startup validation of the existing Vite backend proxy target.
- frontend/src/styles.css: responsive sidebar/header, login, summary cards, tables, loading/error/empty states.
- backend/phase4a_validation/: disposable-only regression runner, real restricted-LOGIN integration probe and HTTP/Vite smoke.

No import/review serializer, writable viewset, account-management endpoint or stock posting API is registered.

## Session authentication

1. GET /api/auth/csrf/ sets an HttpOnly CSRF cookie and returns a masked csrfToken in JSON.
2. The client POSTs JSON credentials to /api/auth/login/ with X-CSRFToken and same-origin cookies.
3. Django's authenticate/login validates active users, cycles the session key and rotates the CSRF secret. The response returns only current-user identity/limited read permissions plus the new masked CSRF token.
4. GET /api/auth/me/ restores UI state on reload; anonymous requests get 401.
5. POST /api/auth/logout/ requires CSRF, flushes the server-side session and rotates CSRF again.

Login/logout are normal Django views with csrf_protect, not DRF anonymous-auth exceptions or csrf_exempt views. Middleware remains enabled. Origin rejection, session fixation prevention and stale-CSRF rejection are tested. Session/CSRF cookies use HttpOnly and SameSite=Lax. Credentials and session tokens are not stored in localStorage or logged.

Invalid and inactive credentials have the same 401 message. Malformed JSON/fields return 400; non-JSON login returns 415. Throttled attempts return 429 plus Retry-After; unavailable throttle storage returns 503 and does not authenticate. Auth responses and business APIs are no-store.

Login has fixed-window limits of 5 attempts/account and 30 attempts/peer per 60 seconds. Peer IP is REMOTE_ADDR; untrusted X-Forwarded-For is ignored. Cache keys use HMAC rather than raw usernames/addresses. Peer budget is checked first to bound account-key creation after a peer is blocked.

The default LocMemCache is process-local and suitable only for the single-process development server. Multiworker/production deployment requires a shared cache backend with atomic add/incr, its necessary client dependency, correct trusted proxy/IP handling and infrastructure abuse controls. Do not claim distributed brute-force protection from LocMemCache. This phase tested fail-closed cache errors and cross-peer account throttling.

Relevant framework references: [Django session authentication](https://docs.djangoproject.com/en/5.2/topics/auth/default/), [DRF session/CSRF behavior](https://www.django-rest-framework.org/api-guide/authentication/), [Django cache configuration](https://docs.djangoproject.com/en/5.2/topics/cache/).

## API reference and authorization

All business endpoints require an active authenticated session and the corresponding Django model view permission. Anonymous reads return 401; authenticated users without the required permission receive 403. Permissions are checked on the current request, including revocation. Django superuser semantics are retained for these ordinary business reads; confidential review capability rules are unchanged.

| Endpoint | Methods | Required permission / response |
| --- | --- | --- |
| /api/auth/csrf/ | GET | Public masked token, no business data |
| /api/auth/login/ | POST | Public but CSRF protected and throttled |
| /api/auth/logout/ | POST | Authenticated + CSRF |
| /api/auth/me/ | GET | Authenticated; id, username, limited read permission names |
| /api/dashboard/summary/ | GET | view_asset, view_warehouse, view_assetcategory, view_stockbalance, view_stockthreshold |
| /api/inventory/assets/ and {id}/ | GET | inventory.view_asset |
| /api/inventory/categories/ and {id}/ | GET | inventory.view_assetcategory |
| /api/inventory/manufacturers/ and {id}/ | GET | inventory.view_manufacturer |
| /api/inventory/product-models/ and {id}/ | GET | inventory.view_productmodel |
| /api/warehouses/ and {id}/ | GET | warehouse.view_warehouse |
| /api/warehouses/{id}/locations/ | GET | Both view_warehouse and view_storagelocation |
| /api/locations/ and {id}/ | GET | warehouse.view_storagelocation |
| /api/health/ | GET | Existing public liveness response |

Business POST/PUT/PATCH/DELETE have no handlers and cannot mutate data. OPTIONS/HEAD retain normal DRF behavior. No protected evidence or operation endpoints exist.

Lists return count, next, previous and results; page starts at 1. API_PAGE_SIZE defaults to 25; page_size is capped at 100. Stable id ordering is the default. Search uses DRF's ORM-backed search; ordering fields are allowlisted.

| Resource | Search | Exact filters |
| --- | --- | --- |
| Assets | tag, device name, product SKU/name | category, product_model, warehouse, lifecycle_status |
| Categories/manufacturers | code/name | is_active=true/false |
| Product models | name/SKU/model number | category, manufacturer, tracking_mode, is_active |
| Warehouses | code/name | is_active |
| Locations | code/name/warehouse name | warehouse, is_active |

IDs must be bounded positive integers; malformed/oversized values and unsupported choices return 400. Unknown details return 404. Related objects use select_related; a 22-asset list is tested to stay within nine database queries, including authentication/pagination.

Asset JSON omits raw serials, remarks, source rows and import/audit links. Related labels are part of authorized business records. Recent activity requires transactions.view_stockmovement and exposes only id, operation_type, quantity and recorded_at, at most ten entries. Reasons, actors, recipient details, audit/import evidence and external references are excluded.

Dashboard totals are ORM counts/aggregations over actual data. Stock totals are bulk StockBalance units; serialized assets are counted separately, not added to bulk units. Low stock uses existing thresholds and summed AVAILABLE bulk stock per product/warehouse, including a zero-stock site. It returns a total alert count and at most twenty indicators. Zero tables yield zero totals and empty arrays. No fabricated metrics or production seed data were added.

## Frontend behavior and limitations

Eight pages: login, overview/dashboard, assets, categories, manufacturers, product models, warehouses and storage locations. The session check guards rendering; server authorization remains authoritative. Navigation follows read permissions. Asset detail excludes sensitive fields. Warehouse rows link to a location-filtered route.

Hash routing works with the existing Vite/static deployment without a server route-rewrite dependency. Search is debounced; requests are cancelled when views change. The location picker shows up to the first 100 permitted warehouses; the paginated warehouse list links to any site's locations. Location/catalog tables themselves remain paginated. No writable controls are presented.

Component tests cover login failure/success, logout, protected routes, session expiry, dashboard/empty states, retry errors, search/filter/pagination and CSRF-aware requests. Actual HTTP proxy/login/logout was separately verified; no full browser-engine visual automation was run.

The existing Vite development proxy is retained. A malformed URL now fails with a clear startup error instead of crashing on the first proxied request; credentials/query/fragment and non-HTTP targets are rejected. No fallback silently ignores an invalid configured target.

## Configuration

No actual .env credentials were read or changed. Existing Compose database/bootstrap variables are not repurposed.

- DJANGO_DEBUG=true: explicit local HTTP development; Secure cookie defaults become false.
- Otherwise, Secure session/CSRF cookies default true.
- DJANGO_SESSION_COOKIE_SECURE and DJANGO_CSRF_COOKIE_SECURE explicitly override those defaults; use true behind production HTTPS.
- DJANGO_ALLOWED_HOSTS and DJANGO_CSRF_TRUSTED_ORIGINS must name the actual frontend/backend origins, with no wildcard trust.
- VITE_PROXY_TARGET=http://backend:8000 inside Compose, or http://localhost:8000 for a host-run frontend.
- API_PAGE_SIZE sets default list size, bounded to 1–100.
- LOGIN_CACHE_BACKEND / LOGIN_CACHE_LOCATION configure the login cache. Shared-backend deployment must supply/test its client dependency.
- Runtime DB credentials must be service-specific, nonowner and separately approved. Do not globally replace database bootstrap credentials or run migrations using runtime credentials.

The new synthetic runtime proof supplements the older Phase 2C grant matrix: it requires SELECT on category/manufacturer/threshold/catalog/location/balance tables plus existing auth permission joins, auth_user password/last_login UPDATE and session SELECT/INSERT/UPDATE/DELETE. Stock activity needs only SELECT of four movement columns. No business DML, review table SELECT/DML, owner membership, table ownership or schema CREATE was needed for Phase 4A HTTP APIs.

That test-only provisioning is not deployment SQL. The old stock-service matrix permits additional carefully guarded service writes; Phase 4A registers none of those endpoints. Persistent runtime grants require separate review, especially the observed direct review SELECT privilege. The live role name is itwarehouse_backend, not the requested itw_app_runtime.

A standard runserver startup may additionally inspect migration-history metadata; choose an approved server/startup policy and exact grants rather than broadening evidence permissions. The isolated HTTP smoke used Python's wsgiref server only for test transport, never as a production server recommendation.

## Executed tests and builds

Each final suite is reported separately, without summing earlier runs or manual assertions.

| Suite | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: |
| New Phase 4A HTTP/security/query tests | 29 | 0 | 0 | 0 |
| New real restricted-LOGIN API proof | 6 | 0 | 0 | 0 |
| Existing current regression | 205 | 0 | 0 | 0 |
| Existing historical registry | 45 | 0 | 0 | 0 |
| Existing review read-gateway proof | 20 | 0 | 0 | 0 |
| Existing runtime/stock/review regression | 16 | 0 | 0 | 0 |
| Frontend components/API client/proxy configuration | 21 | 0 | 0 | 0 |

The original 205+45 baseline remains passing. No previous test was weakened or modified. Initial new fixtures violated the ledger's final-state guard; they were corrected to use the existing posting service. Initial combined security validation found stock-fixture contamination in the base proof database; the new runtime probe now creates a separate disposable clone. A clean combined rerun then passed the unchanged 20-method security proof.

Django check: no issues. makemigrations --check --dry-run: no changes detected. No model migration generated.

npm production build: PASS, including a clean npm ci image build. Backend and frontend validation Docker images built successfully under distinct tags; development images/services were not replaced. New test dependencies are locked. An initial old Vitest version reported advisories and was upgraded to 5.1.0; final npm audit reports zero vulnerabilities. npm notes an esbuild install-script policy notice; actual builds succeeded without weakening that policy.

Real HTTP smoke inside the disposable private namespace passed: frontend HTML 200; proxied health 200; anonymous assets 401; CSRF bootstrap/login 200; authenticated dashboard/assets 200 with synthetic stock-service fixtures; missing-CSRF logout 403; valid logout 200; me after logout 401. The runtime LOGIN was itw_phase4a_runtime. No ports were published for that smoke, and no development DB was used.

Runtime proof also denies CREATE/TEMP/ALTER/TRUNCATE, trigger disabling, SET ROLE owner, review evidence SELECT/DML, business DML, movement UPDATE/DELETE and movement reason reads. Existing adversarial stock tests continue to verify conservation and immutable history even after accidental grants.

Evidence/logs: ~/.local/share/it-warehouse-phase4a/. The final two pagination/query tests and proxy tests were added after the combined baseline run and passed in their final focused reruns (29 and 21 respectively); earlier 27/15 counts are not counted twice.

## Reproduce safely

Use unused disposable names, the existing backend image/dependencies, PostgreSQL 17.11 and sufficient memory. The runner creates no persistent DB volumes, loads no .env and stops on failure.

~~~sh
cd /home/itadmin/projects/it-warehouse
PYTHONDONTWRITEBYTECODE=1 python3 backend/phase4a_validation/run_host.py
docker build -t itw-phase4a-backend-validation backend
docker build -t itw-phase4a-frontend-validation frontend
PYTHONDONTWRITEBYTECODE=1 python3 backend/phase4a_validation/http_smoke.py
cd frontend
npm ci
npm test
npm run build
npm audit
~~~

http_smoke.py follows run_host.py because it uses the isolated phase4a_runtime_test clone and the existing regression harness's synthetic admin credential contract. It uses a shared private network namespace, because Docker containers created with network none cannot be attached to a bridge simultaneously. It restores only a synthetic user's view permission after the revocation test for the separate HTTP scenario.

Disposable cleanup verifies explicit names/creation labels and no database volume before stopping/removing only the four Phase 4A test containers. Development containers/volume are not cleanup targets.

Persistent startup commands are intentionally conditional on resolving runtime readiness and passing existing authorization gates:

~~~sh
# Only after approved role/ACL/configuration readiness and current source review:
docker compose build backend frontend
docker compose up -d --no-deps backend frontend
~~~

Those persistent startup commands were NOT executed. Do not deploy merely because a source bind makes routes visible. The old D.4 verifier's top-level URL allowlist intentionally recognizes only the historical admin/health profile; Phase 4A needs a separately reviewed deployment verification profile, not weakening that old guard.

## Remaining Phase 4B / deployment work

- Resolve the live runtime's direct review-evidence SELECT grant through authorized privilege work; verify the complete supported runtime matrix and startup policy.
- Correct the live malformed proxy URL through configuration review; frontend is currently stopped, not a working deployment.
- Validate a production HTTPS reverse proxy, trusted-client-IP policy and shared atomic throttle cache.
- Provision users and read permissions through the authorized account-administration process; no persistent user was created here.
- Add production server/static hosting and operational observability; Vite dev server/wsgiref are not production hosting.
- Review a Phase 4A deployment manifest/verification profile after source commit. New source changes invalidate the previous HEAD/script-bound rollout assumptions.
- Continue excluding workbook capture, review approval/revocation/promotion and unfinished posting workflows. No changes to protected stock integrity rules are needed for these read APIs.

## Files

Modified: backend/config/settings/base.py, backend/config/urls.py, frontend/package.json, frontend/package-lock.json, frontend/vite.config.js, frontend/src/main.jsx, frontend/src/styles.css.

Created: backend/apps/accounts/session_api.py; backend/apps/inventory/read_api.py; backend/config/api_urls.py; backend/config/test_phase4a.py; backend/phase4a_validation/run_host.py, runtime_probe.py and http_smoke.py; frontend/proxy-target.js; frontend/vitest.config.js; frontend/src/App.jsx, api.js, App.test.jsx, api.test.js, proxy-target.test.js and test-setup.js; docs/phase4a-implementation.md.

The prior untracked docs/phase3b2d5-development-schema-deployment-result.md is preserved as historical work and is not a Phase 4A addition.

Final container state: development PostgreSQL and externally started backend healthy; development frontend exited (1) after its malformed proxy target. Existing backend URL http://127.0.0.1:8000/api/health/ returned 200. No working persistent frontend/full-stack URL is claimed. The four disposable Phase 4A containers and empty test network were removed after retaining evidence; no persistent container or volume was removed.

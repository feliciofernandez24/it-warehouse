"""Standalone synthetic-only proof; never loads .env or installs at app startup."""
import json
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
if os.environ.get("ITW_REVIEW_READ_PROOF")!="1":
    raise RuntimeError("ISOLATED_PROOF_REQUIRED")
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings.development")
import django
django.setup()
from tests import ReadGatewayTests,EVIDENCE,connect
if __name__=="__main__":
    with connect() as c:
        EVIDENCE["postgres_version"]=c.execute("SELECT version()").fetchone()[0]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReadGatewayTests))
    EVIDENCE["tests"]={"ran":result.testsRun,"failed":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped)}
    Path("/tmp/phase3b2d2-evidence.json").write_text(json.dumps(EVIDENCE,indent=2,default=str)+"\n")
    print("READ_GATEWAY_RESULT="+json.dumps(EVIDENCE["tests"]))
    sys.exit(0 if result.wasSuccessful() else 1)
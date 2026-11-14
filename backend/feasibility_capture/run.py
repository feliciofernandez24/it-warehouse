"""Run only inside the documented disposable runner/container. Never loads .env."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import connect, EVIDENCE

if __name__=="__main__":
    with connect() as c:
        EVIDENCE["postgres_version"]=c.execute("SELECT version()").fetchone()[0]
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern="test_*.py")
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    EVIDENCE["tests"]={"ran":result.testsRun,"failed":len(result.failures),
        "errors":len(result.errors),"skipped":len(result.skipped),
        "passed":result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped)}
    Path("/tmp/itw-feasibility-evidence.json").write_text(json.dumps(EVIDENCE,sort_keys=True,indent=2,default=str)+"\n")
    print("FEASIBILITY_COUNTS="+json.dumps(EVIDENCE["tests"]))
    sys.exit(0 if result.wasSuccessful() else 1)
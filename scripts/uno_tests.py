"""Report UNO exceptions without Python 3.14 unittest mutating their proxy fields."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
class UNOResult(unittest.TextTestResult):
    def _clean_tracebacks(self,exctype,value,tb,test):
        # UNO exception objects reject assignment to __traceback__.
        return tb
suite=unittest.defaultTestLoader.discover('tests',pattern='test_office.py')
result=unittest.TextTestRunner(verbosity=2,resultclass=UNOResult).run(suite)
raise SystemExit(not result.wasSuccessful())

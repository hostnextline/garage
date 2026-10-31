"""Runs a browser test as if today were another day (tests written for weekdays): Python's date and the browser's clock both move.
   python3 run_on_day.py 2026-11-04 test_carnet.py"""
import sys, datetime, runpy
day = datetime.date.fromisoformat(sys.argv[1]); script = sys.argv[2]
_RD, _RDT = datetime.date, datetime.datetime
OFF = _RDT.combine(day, _RDT.now().time()) - _RDT.now()
class FDT(_RDT):
    @classmethod
    def now(cls, tz=None): return _RDT.now(tz) + OFF
    @classmethod
    def today(cls): return _RDT.now() + OFF
class FD(_RD):
    @classmethod
    def today(cls): return (_RDT.now() + OFF).date()
datetime.date, datetime.datetime = FD, FDT
from playwright.sync_api._generated import Browser
_nc = Browser.new_context
def new_context(self, *a, **k):
    c = _nc(self, *a, **k)
    c.clock.install(time=_RDT.now() + OFF)
    return c
Browser.new_context = new_context
sys.argv = [script] + sys.argv[3:]
runpy.run_path(script, run_name='__main__')

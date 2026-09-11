"""Atomic SQLite snapshots; maps are paged into a small runtime cache."""
import json
import sqlite3
from pathlib import Path

def dumps(v): return json.dumps(v,ensure_ascii=False,separators=(',',':'),allow_nan=False)
class Store:
 def __init__(self,path):
  if str(path)!=':memory:': Path(path).parent.mkdir(parents=True,exist_ok=True)
  self.db=sqlite3.connect(str(path),check_same_thread=False)
  self.db.execute('PRAGMA journal_mode=WAL')
  self.db.executescript('CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS regions(id TEXT PRIMARY KEY,body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,body TEXT NOT NULL);')
  self.db.commit()
 def load_state(self):
  row=self.db.execute('SELECT body FROM state WHERE id=1').fetchone(); return json.loads(row[0]) if row else None
 def load_region(self,rid):
  row=self.db.execute('SELECT body FROM regions WHERE id=?',(rid,)).fetchone(); return json.loads(row[0]) if row else None
 def commit(self,state,regions=(),events=(),delete_regions=(),reset=False):
  with self.db:
   if reset:
    for table in ('state','regions','events'): self.db.execute('DELETE FROM '+table)
   for rid in delete_regions: self.db.execute('DELETE FROM regions WHERE id=?',(rid,))
   for r in regions: self.db.execute('INSERT OR REPLACE INTO regions VALUES(?,?)',(r['id'],dumps(r)))
   for e in events: self.db.execute('INSERT INTO events(body) VALUES(?)',(dumps(e),))
   self.db.execute('INSERT OR REPLACE INTO state VALUES(1,?)',(dumps(state),))
 def recent_events(self,limit=18):
  rows=self.db.execute('SELECT body FROM events ORDER BY seq DESC LIMIT ?',(min(limit,100),)).fetchall(); return [json.loads(r[0]) for r in reversed(rows)]
 def close(self): self.db.close()

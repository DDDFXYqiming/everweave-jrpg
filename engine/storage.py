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
  self.db.execute('CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY,region TEXT NOT NULL,time INTEGER NOT NULL,text TEXT NOT NULL)')
  if not self.db.execute('SELECT 1 FROM journal LIMIT 1').fetchone():
   previous=self.load_state()
   if previous:
    lines=previous.get('journal',[]);start=previous.get('journal_count',len(lines))-len(lines)+1
    self.db.executemany('INSERT OR IGNORE INTO journal VALUES(?,?,?,?)',[(start+i,previous.get('current',''),previous.get('time',0),line) for i,line in enumerate(lines)])
  self.db.commit()
 def load_state(self):
  row=self.db.execute('SELECT body FROM state WHERE id=1').fetchone(); return json.loads(row[0]) if row else None
 def load_region(self,rid):
  row=self.db.execute('SELECT body FROM regions WHERE id=?',(rid,)).fetchone(); return json.loads(row[0]) if row else None
 def commit(self,state,regions=(),events=(),delete_regions=(),reset=False):
  with self.db:
   if reset:
    for table in ('state','regions','events','journal'): self.db.execute('DELETE FROM '+table)
   count=state.get('journal_count',len(state.get('journal',[])))
   start=count-len(state.get('journal',[]))+1
   recorded=self.db.execute('SELECT COALESCE(MAX(seq),0) FROM journal').fetchone()[0]
   self.db.executemany('INSERT OR IGNORE INTO journal VALUES(?,?,?,?)',
     [(start+i,state.get('current',''),state.get('time',0),line) for i,line in enumerate(state.get('journal',[])) if start+i>recorded])
   for rid in delete_regions: self.db.execute('DELETE FROM regions WHERE id=?',(rid,))
   for r in regions: self.db.execute('INSERT OR REPLACE INTO regions VALUES(?,?)',(r['id'],dumps(r)))
   for e in events: self.db.execute('INSERT INTO events(body) VALUES(?)',(dumps(e),))
   self.db.execute('INSERT OR REPLACE INTO state VALUES(1,?)',(dumps(state),))
 def recent_events(self,limit=18):
  rows=self.db.execute('SELECT body FROM events ORDER BY seq DESC LIMIT ?',(min(limit,100),)).fetchall(); return [json.loads(r[0]) for r in reversed(rows)]
 def close(self): self.db.close()
 def journal_page(self,before=None,limit=30):
  rows=self.db.execute('SELECT seq,region,time,text FROM journal WHERE seq<? ORDER BY seq DESC LIMIT ?',
                       (before if before is not None else 2**63-1,limit+1)).fetchall()
  return dict(entries=[dict(id=str(seq),region=region,time=time,description=text) for seq,region,time,text in rows[:limit]],
              next_cursor=rows[limit-1][0] if len(rows)>limit else None)

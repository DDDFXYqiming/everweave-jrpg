"""Explicit gameplay vocabulary; the model cannot add executable code."""
import hashlib
BIOMES=('forest','coast','snow','desert','ruins','industrial','dream')
LAYOUTS=('village','river','grove','ruins','islands','labyrinth')
WEATHERS=('clear','rain','snow','fireflies','fog')
RULES=('normal','no_magic','healing_rain','volatile','echo')
ROLES=('guide','merchant','healer','wanderer')
KINDS=('npc','enemy','chest','shrine')
MONSTERS=('slime','wolf','sentinel','wisp','mimic')
MOVES=('strike','venom','drain','guard','rage')
LANDMARKS=('house','tower','camp','crystal','tree')
ZONES=('north','south','east','west','center')
EFFECTS=('heal','restore_mp','attack','defense','burn','drain')
GROUND,PATH,WATER,WALL,BRIDGE=range(5)
BLOCKED=frozenset((WATER,WALL))
BASE_ITEMS={
 'potion':dict(id='potion',name='星露药剂',kind='consumable',description='恢复 35 点生命。',effect='heal',power=35,price=12,icon='potion'),
 'ether':dict(id='ether',name='月光瓶',kind='consumable',description='恢复 12 点魔力。',effect='restore_mp',power=12,price=16,icon='ether'),
 'wayfarer_blade':dict(id='wayfarer_blade',name='旅人短剑',kind='weapon',description='带着旧日划痕的短剑。',effect='attack',power=2,price=20,icon='sword')}

def stable_seed(*parts):
 return int.from_bytes(hashlib.sha256('|'.join(map(str,parts)).encode()).digest()[:8],'big')

def clamp(v,lo,hi):
 return max(lo,min(hi,int(v)))

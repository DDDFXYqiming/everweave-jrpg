"""Deterministic offline demo author, explicitly labelled as NOT an LLM."""
import random
from .catalog import BIOMES,LAYOUTS,stable_seed

def make_patch(c,kind):
 setting=c['setting']; revision=c.get('story_revision',0); target=c.get('target','r0'); rng=random.Random(stable_seed(setting,target,revision,kind))
 rescue=any('mercy' in str(x) for x in c.get('recent_events',[]))
 if kind=='reaction':
  t='你的决定让远方的道路改变了方向。' if not rescue else '被你帮助的人点起一盏灯。迷雾中多了一条通向避难所的道路。'
  updates=[dict(id=e['id'],dialogue=['我听说了你的决定。这个地方不会再与从前一样。']) for e in c.get('current_region',{}).get('entities',[]) if e['kind']=='npc'][:1]
  future=[dict(id=f['id'],description=t) for f in c.get('frontier',[]) if not f.get('visited')][:2] if rescue else []
  return dict(kind='reaction',reaction=dict(text=t,weather=rng.choice(('rain','fog','fireflies')),rule=rng.choice(('normal','healing_rain','echo')),npc_lines=updates,future_updates=future),threads=[dict(id=f'echo_{revision}',title='选择的回声',note=t)])
 depth=c.get('target_depth',0)
 if depth==0:
  biome='industrial' if any(x in setting.lower() for x in ('蒸汽','steam','机械','赛博')) else 'snow' if any(x in setting for x in ('冰','雪')) else 'coast' if any(x in setting for x in ('海','岛','港')) else 'forest'; layout='village'
 else: biome=rng.choice(BIOMES); layout=rng.choice(LAYOUTS)
 names=dict(forest='萤森',coast='潮汐渡口',snow='眠雪原',desert='琥珀沙洲',ruins='失语遗迹',industrial='雨锈街',dream='倒影之境')
 name=names[biome]+(f' · {depth+1}' if depth else '')
 if rescue and depth>0: name=f'归人避难所 · {depth+1}'
 return dict(kind='region',world_title='未写之境 · Everweave',region=dict(
  name=name,biome=biome,layout=layout,weather='rain' if '雨' in setting or biome=='industrial' else 'fireflies',rule='normal' if depth==0 else rng.choice(('normal','no_magic','volatile','healing_rain','echo')),
  description=f'这里是{name}。你带着「{setting[:75]}」的念头抵达。沿灯火探索，出口之后的土地仍在生长。',
  landmarks=[dict(type='house',zone='west'),dict(type='tower',zone='north'),dict(type='crystal',zone='east')],
  items=[dict(id='ember_blade',name=rng.choice(('风信之刃','雨中余烬','无名的誓言')),description='旅途中诞生的武器。装备后改变攻击效果。',kind='weapon',effect=rng.choice(('attack','burn','drain')),power=min(3+depth,8),price=30)],
  entities=[
   dict(id='witness',kind='npc',name='提灯的旅人',role='guide',zone='south',appearance=1,dialogue=['你也听见了世界尽头的钟声？','尚未走过的路，并没有固定的模样。'],choices=[dict(id='mercy',text='帮助被追赶的陌生人',reply='你伸出了手。远处忽然多了一盏灯。',tag='mercy'),dict(id='pursue',text='追查钟声与失踪的人',reply='旅人为你指向被雾覆盖的出口。',tag='investigate'),dict(id='reject',text='只相信亲眼见到的事',reply='他把你的回答记在破旧的书页上。',tag='skeptic')]),
   dict(id='trader',kind='npc',name='流动商人',role='merchant',zone='west',appearance=3,dialogue=['金币买不到答案，但能买一点继续前进的勇气。']),
   dict(id='healer',kind='npc',name='星露医师',role='healer',zone='center',appearance=5,dialogue=['坐一会儿，旅人。你不必带着所有伤口上路。']),
   dict(id='cache',kind='chest',name='遗落的旅行箱',zone='east',item_id='ember_blade'),
   dict(id='spring',kind='shrine',name='遗忘之泉',zone='west'),
   dict(id='watcher',kind='enemy',name=rng.choice(('迷路的雾灵','锈蚀守望者','晶化林狼')),zone='north',monster=rng.choice(('wolf','sentinel','wisp')),tier=1,move=rng.choice(('strike','venom','drain'))),
   dict(id='warden',kind='enemy',name='边境守门人',zone='east',monster='sentinel',tier=2 if depth==0 else 3,move='rage')],
  quests=[dict(id='listen',name='听见另一个人的故事',goal='talk',target='witness'),dict(id='recover',name='找到遗落的武器',goal='collect',target='ember_blade'),dict(id='silence',name='让边境重新安静',goal='defeat',target='warden')]),
  lore=[dict(id='place_'+target[:30],text=name+'的住民把重要的约定刻在灯座上。')],threads=[dict(id='bell',title='未抵达的钟声',note='让玩家的选择影响钟声的来源。')])

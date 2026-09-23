"""玩家主动支付的共同约定；环境伤害仍由原来的资源效果处理。"""
from .diagnostics import InvalidPatch


def parse(raw):
    from .schema import ident
    from .content import integer
    if not isinstance(raw,dict) or len(raw)>8:raise InvalidPatch('costs 需要至多八种资源的数量表')
    return {ident(key):integer(value,1,100000,'cost') for key,value in raw.items()}


def balance(state,key):
    from .game_spec import value
    return value(state,key)


def requirements(definition):
    result=dict(definition.get('costs',{}))
    # 旧动作开头的固定非生命扣费也显示为代价，扣费仍由原效果执行。
    for command in definition.get('effects',[]):
        key=command.get('id') if command.get('op')=='resource' else command.get('name') if command.get('op')=='stat' and command.get('target')=='player' else None
        delta=command.get('delta')
        if not key or key=='hp' or type(delta) not in (int,float) or delta>=0:break
        result[key]=result.get(key,0)-delta
    return result


def hint(state,definition):
    from .game_spec import resource
    missing=[]
    for key,amount in requirements(definition).items():
        current=balance(state,key)
        if current<amount:
            label=(resource(state,key) or {}).get('label',{'gold':'金币','mp':'魔力','hp':'生命'}.get(key,key))
            missing.append(f'{label} ×{amount:g}（当前 {current:g}）')
    return '资源不足：'+'、'.join(missing) if missing else ''


def pay(state,declared):
    from .game_spec import BUILTINS
    # 全部检查后才扣除；调用方的事务同时覆盖后续效果。
    for key,amount in declared.items():
        if balance(state,key)<amount:raise InvalidPatch('资源不足，无法支付 '+key,category='gameplay',path='costs.'+key)
    for key,amount in declared.items():
        owner=state['player'] if key in BUILTINS else state['player']['resources']
        owner[key]-=amount


def description(state,definition):
    from .game_spec import resource
    values=requirements(definition)
    labels=[f"{(resource(state,key) or {}).get('label',{'gold':'金币','mp':'魔力','hp':'生命'}.get(key,key))} ×{amount:g}" for key,amount in values.items()]
    base=definition.get('description',definition.get('label',''))
    return base+(' · 消耗：'+'、'.join(labels) if labels else '')

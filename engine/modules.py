"""Optional reviewed abilities expand to the same bounded DSL as authored rules."""
import copy
import hashlib
import json
import re
from pathlib import Path
from .diagnostics import InvalidPatch

FILE=Path(__file__).resolve().parents[1]/'assets/library/modules.json'

def definitions():return json.loads(FILE.read_text(encoding='utf-8'))

def menu():
    return [dict(id=k,description=v['description'],args=v['args'],actions=[a['id'].replace('@id','<id>') for a in v['program'].get('actions',[])]) for k,v in definitions().items()]

def expand(raw,kind):
    """Return independent data; never mutate the rejected response used for repair."""
    if not isinstance(raw,dict) or not isinstance(raw.get(kind),dict):return raw,[]
    result=copy.deepcopy(raw);body=result[kind];specs=body.pop('modules',[])
    if not isinstance(specs,list) or len(specs)>8:raise InvalidPatch('modules must have 0..8 entries',path=kind+'.modules')
    if not specs:return result,[]
    sources=[];known=definitions();program=body.setdefault('program',{}) if specs else body.get('program',{})
    if not isinstance(program,dict):raise InvalidPatch('program must be an object')
    for index,spec in enumerate(specs):
        path=f'{kind}.modules[{index}]'
        if not isinstance(spec,dict) or set(spec)!= {'module','id','args'}:raise InvalidPatch('module needs module/id/args',path=path)
        key=spec['module'];identity=spec['id'];args=spec['args']
        if not isinstance(key,str) or key not in known:raise InvalidPatch('unknown ability module',path=path+'.module',category='reference',value=key)
        if not isinstance(identity,str) or not re.fullmatch('[a-z][a-z0-9_]{0,19}',identity):raise InvalidPatch('module instance id must be a short bare ID',path=path+'.id')
        definition=known[key]
        if not isinstance(args,dict) or set(args)!=set(definition['args']):raise InvalidPatch('module arguments differ',path=path+'.args',expected=str(definition['args']))
        for name,rule in definition['args'].items():
            value=args[name];type_name=rule['type']
            valid=(type(value) is int and rule.get('min',-1000)<=value<=rule.get('max',1000)) if type_name=='integer' else (isinstance(value,str) and bool(re.fullmatch('[a-z][a-z0-9_:]*',value))) if type_name=='reference' else (isinstance(value,list) and len(value)==2 and all(type(n) is int and 0<=n<96 for n in value)) if type_name=='point' else isinstance(value,str) and 0<len(value)<=64
            if not valid:raise InvalidPatch('invalid module argument',path=path+'.args.'+name,value=value,expected=str(rule))
        def substitute(value):
            if isinstance(value,dict):
                if set(value)=={'$arg'}:return copy.deepcopy(args[value['$arg']])
                return {k.replace('@id',identity):substitute(v) for k,v in value.items()}
            if isinstance(value,list):return [substitute(v) for v in value]
            if isinstance(value,str):return value.replace('@id',identity)
            return value
        compiled=substitute(definition['program'])
        for name in ('actions','hooks','objectives'):
            current=program.setdefault(name,[])
            if not isinstance(current,list):raise InvalidPatch('program list required',path=kind+'.program.'+name)
            current.extend(compiled.get(name,[]))
        variables=program.setdefault('vars',{})
        if not isinstance(variables,dict):raise InvalidPatch('program vars must be an object')
        for name,value in compiled.get('vars',{}).items():
            if name in variables:raise InvalidPatch('module variable collides',path=kind+'.program.vars.'+name)
            variables[name]=value
        sources.append(dict(module=key,id=identity,args=args,sha256=hashlib.sha256(json.dumps(definition,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
    return result,sources

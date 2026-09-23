"""Derive a compact director contract, then build gameplay and AV in parallel."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import threading
from .schema import ident,text

GAMEPLAY_COMPONENT='''
COMPONENT BUILD: Follow region_design for the exact region name, recurring cast and allowed sprite/surface slots.
You may invent bounded local entities, landmarks and items, but every sprite field must use an allowed sprite slot.
Bind every required recurring cast entry with its exact actor_id, name and sprite. Focus on playable scene geometry,
dialogue/scenes, choices, program actions/hooks/objectives, combat and rewards. Include every planned route anchor and
required flag write from world_context.
Still return the ordinary complete kind=region envelope, but OMIT region.visuals and region.audio: the parallel
audiovisual worker supplies them. Do not invent extra gameplay identities. Use every region_design surface at least
once in a scene.paint surface/wall_surface/door_surface field so the visual work has an actual spatial role.
Keep the playable result focused: 24..44 by 16..30 tiles, at most 14 paint commands, 10 actions, 8 hooks,
3 objectives and 2 story scenes. Prefer one consequential encounter or negotiation over many tiny mechanisms.
音效引用只使用 region_design.audio_cues，音乐引用只使用 region_design.music_cues。
临时对象的交互音效用 program 中的 op:sound 绑定；视听作者不拥有临时对象 ID。'''

AV_PROMPT='''You are the audiovisual worker for one already designed region. Return JSON only:
{"kind":"region_av","visuals":VISUALS,"audio":AUDIO}.
Implement every allowed sprite and surface slot in region_design as a sprite or binding. Read region_design.slot_briefs
as the identity/function contract for each slot. Use compatible library candidates when they preserve that contract,
compose when useful, and draw distinctive missing focal objects. A listed gap explicitly means original drawing is
preferred; there is no reuse quota. Do not invent entities/items, coordinates, rules, dialogue or story facts.
Visuals has exactly style,terrain,palette,sprites,scenery,density,bindings; never put scene or paint inside visuals.
Audio must include exploration music and suitable sparse cues. Keep <=10 sprite definitions by using bindings and
shared role art where it fits; reuse materials/scenery locally.
按 region_design.audio_cues 定义全部音效，按 music_cues 定义音乐。audio.objects 保持为空，
对象与音效的关联由玩法规则负责。修复输入若含 required_audio_references，须补齐其中的引用。'''


class PipelineError(RuntimeError):
    def __init__(self,message,usage=None,component=None,issues=None):
        super().__init__(message);self.usage=usage or {};self.component=component;self.issues=issues or []


def parsed(raw,label):
    try:value=json.loads(raw) if isinstance(raw,str) else copy.deepcopy(raw)
    except (ValueError,TypeError) as exc:raise PipelineError(label+' returned invalid JSON') from exc
    if not isinstance(value,dict):raise PipelineError(label+' must return an object')
    return value


def contract(context):
    destination=context.get('destination') or {}
    name=text(destination.get('name') or context.get('region_name') or context.get('target'),'region name',48)
    description=text(destination.get('description') or context.get('region_purpose') or name,'region description',450)
    cast=[]
    for actor in (context.get('content_contract') or {}).get('cast',[])[:6]:
        cast.append(dict(id=ident(actor['id']),name=text(actor['name'],'actor name',48),sprite=ident(actor['id']),
                         purpose=text((actor.get('role','')+'; '+actor.get('motive','')).strip('; '),'actor purpose',300)))
    slots=['npc','enemy','object','building','vegetation','item','focal']+[a['sprite'] for a in cast]
    if not context.get('hero_visual'):slots.append('hero')
    shared={'region_identity':description,'visual_direction':(context.get('game_spec') or {}).get('visual_theme') or description}
    briefs={
        'npc':dict(shared,identity='A local non-player character',visual_function='Readable conversational character'),
        'enemy':dict(shared,identity='A local threat or opponent',visual_function='Readable danger silhouette'),
        'object':dict(shared,identity='A general interactive object',visual_function='Readable as an interactable prop'),
        'building':dict(shared,identity='A place-defining structure',visual_function='Readable top-down landmark or structure'),
        'vegetation':dict(shared,identity='Setting-appropriate vegetation',visual_function='Environmental dressing that preserves paths'),
        'item':dict(shared,identity='A portable item',visual_function='Small readable inventory or pickup object'),
        'focal':dict(shared,identity=description,visual_function='The distinctive object that communicates this region purpose'),
        'hero':dict(shared,identity='The player character requested by the setting',visual_function='Readable controllable protagonist'),
        'ground_surface':dict(shared,identity='Large walkable base surface',visual_function='Low-noise ground with character contrast'),
        'path_surface':dict(shared,identity='Walkable route surface',visual_function='Makes routes legible without visual clutter'),
        'wall_surface':dict(shared,identity='Blocking wall surface',visual_function='Clearly separates blocked space from floors'),
        'accent_surface':dict(shared,identity='Small-area accent surface',visual_function='Highlights important local areas'),
    }
    for actor in cast:briefs[actor['sprite']]=dict(shared,identity=actor['name'],visual_function=actor['purpose'])
    return dict(name=name,description=description,cast=cast,sprite_slots=list(dict.fromkeys(slots)),
                surfaces=['ground_surface','path_surface','wall_surface','accent_surface'],
                slot_briefs={slot:briefs[slot] for slot in list(dict.fromkeys(slots))+['ground_surface','path_surface','wall_surface','accent_surface']},
                gameplay_direction=text(context.get('region_purpose') or description,'gameplay direction',450),
                visual_direction=text(((context.get('game_spec') or {}).get('visual_theme') or description),'visual direction',450),
                audio_cues={'interact':'轻微交互反馈','activate':'机关启动或关键动作','success':'目标达成','danger':'危险预告'},
                music_cues={'explore':'地区探索背景','combat':'交战背景'},
                audio_direction=text('Support this region mood, danger and interaction feedback without masking dialogue.','audio direction',300))


def av(raw,contract,context):
    try:value=parsed(raw,'audiovisual worker')
    except PipelineError as exc:exc.component='audiovisual';raise
    if set(value)!={'kind','visuals','audio'} or value['kind']!='region_av':raise PipelineError('audiovisual envelope is invalid',component='audiovisual')
    from .visuals import validate_visuals
    from .audio import validate_audio
    visual_value=value['visuals']
    if isinstance(visual_value,dict) and set(visual_value)-{'style','terrain','palette','sprites','scenery','density','bindings'}=={'scene'}:
        visual_value=copy.deepcopy(visual_value);visual_value.pop('scene')  # AV has no spatial authority; this hint is redundant.
    audio_value=value['audio']
    if isinstance(audio_value,dict) and isinstance(audio_value.get('music'),dict):
        misplaced=set(audio_value['music'])&{'ambience','cues','bindings','objects'}
        if misplaced and not misplaced&set(audio_value):
            audio_value=copy.deepcopy(audio_value)
            for key in misplaced:audio_value[key]=audio_value['music'].pop(key)
    # 与整区解析共享音频简写规则，只做格式归一化，不解析尚未合并的对象身份。
    from .normalization import Normalizer
    normalized_audio=Normalizer({'kind':'region','region':{'audio':copy.deepcopy(audio_value)}},'region',None)
    normalized_audio.formats()
    audio_value=normalized_audio.raw['region']['audio']
    try:visuals=validate_visuals(visual_value);audio=validate_audio(audio_value,context.get('current_audio'))
    except Exception as exc:
        from .diagnostics import InvalidPatch
        if isinstance(exc,InvalidPatch):raise PipelineError(str(exc),component='audiovisual',issues=exc.issues) from None
        raise
    required=set(contract['sprite_slots'])|set(contract['surfaces'])
    missing=required-set(visuals['sprites'])-set(visuals.get('bindings',{}))
    if missing:raise PipelineError('audiovisual worker omitted sprites: '+', '.join(sorted(missing)),component='audiovisual')
    if not audio.get('music',{}).get('explore'):raise PipelineError('audiovisual worker omitted exploration music',component='audiovisual')
    # Validate here for component-local diagnostics, then let the normal region
    # parser perform the single canonical normalization after assembly.
    return visual_value,audio_value


def gameplay(game_raw,contract):
    try:value=parsed(game_raw,'gameplay worker')
    except PipelineError as exc:exc.component='gameplay';raise
    if value.get('kind')!='region' or not isinstance(value.get('region'),dict):raise PipelineError('gameplay envelope is invalid',component='gameplay')
    body=value['region']
    if body.get('name')!=contract['name']:raise PipelineError('gameplay worker changed the region name',component='gameplay')
    allowed=set(contract['sprite_slots'])
    for group in ('entities','landmarks','items'):
        for entry in body.get(group,[]):
            if entry.get('sprite') is not None and entry['sprite'] not in allowed:raise PipelineError('gameplay worker used a sprite outside the binding contract',component='gameplay')
    for actor in contract['cast']:
        matches=[e for e in body.get('entities',[]) if e.get('actor_id')==actor['id']]
        if len(matches)!=1 or matches[0].get('name')!=actor['name'] or matches[0].get('sprite')!=actor['sprite']:
            raise PipelineError('gameplay worker omitted or changed recurring cast '+actor['id'],component='gameplay')
    used=set()
    for paint in body.get('scene',{}).get('paint',[]):
        if isinstance(paint,dict):used.update(paint.get(key) for key in ('surface','wall_surface','door_surface'))
    missing_surfaces=set(contract['surfaces'])-used
    if missing_surfaces:raise PipelineError('gameplay worker did not place surfaces: '+', '.join(sorted(missing_surfaces)),component='gameplay')
    return value


def assemble(game_raw,av_raw,contract,context):
    value=gameplay(game_raw,contract);body=value['region']
    visuals,audio=av(av_raw,contract,context);body['visuals']=visuals;body['audio']=audio
    # 根据实际玩法引用检查两路交集，错误交给能补全定义的视听组件。
    missing=[]
    def walk(value,path):
        if isinstance(value,list):
            for i,child in enumerate(value):walk(child,f'{path}[{i}]')
        elif isinstance(value,dict):
            op=value.get('op');cue=value.get('cue')
            if op in ('sound','music') and not (op=='music' and cue=='default'):
                group='cues' if op=='sound' else 'music'
                if cue not in audio.get(group,{}) and not (op=='music' and 'score' in audio.get('cues',{}).get(cue,{})):
                    missing.append({'path':path+'.cue','message':'缺少玩法引用的音频定义','group':group,'cue':cue})
            for key,child in value.items():walk(child,path+'.'+key)
    for key in ('program','scenes','items','abilities'):walk(body.get(key,[]),'region.'+key)
    ids={e.get('id') for e in body.get('entities',[])}
    for key in audio.get('objects',{}):
        if key not in ids:missing.append({'path':'region.audio.objects.'+key,'message':'音频绑定对象不存在；对象绑定由玩法作者负责'})
    if missing:raise PipelineError('两路音频引用不一致',component='audiovisual',issues=missing)
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def aggregate(usages,effort='high',model='gpt-6-luna'):
    result=dict(input_tokens=0,output_tokens=0,reasoning_tokens=0,cached_input_tokens=0,reasoning_observed=False,
                provider='chatgpt_subscription',model=model,effort=effort,pipeline_requests=sum(int(u.get('model_requests',1)) for u in usages),transport_retries=sum(int(u.get('transport_retries',0)) for u in usages),unknown_usage_attempts=sum(int(u.get('unknown_usage_attempts',0)) for u in usages))
    for usage in usages:
        for key in ('input_tokens','output_tokens','reasoning_tokens','cached_input_tokens'):result[key]+=usage.get(key,0)
        result['reasoning_observed']|=bool(usage.get('reasoning_observed'))
    return result


def worker_contexts(user,contract):
    envelope=parsed(user,'region request');world=envelope.get('world_context',{})
    if not isinstance(world,dict):raise PipelineError('region request omitted world_context')
    game_drop={'library_candidates','hero_visual','current_audio','known_sprites','asset_history'}
    audiovisual_keys={'setting','world_title','target','destination','region_purpose','game_spec','visual_theme',
                      'library_candidates','hero_visual','current_audio','design_history','asset_history','language',
                      'visual_identity','current_visual_identity'}
    game_world={k:v for k,v in world.items() if k not in game_drop}
    library=world.get('library_candidates')
    if isinstance(library,dict) and library.get('modules'):
        game_world['library_candidates']={k:copy.deepcopy(library[k]) for k in ('profile','modules') if k in library}
    game={'world_context':game_world,'region_design':contract}
    audiovisual={'world_context':{k:v for k,v in world.items() if k in audiovisual_keys},'region_design':contract}
    compact=lambda value:json.dumps(value,ensure_ascii=False,separators=(',',':'))
    return compact(game),compact(audiovisual),world


def generate(context,system,user,cfg):
    from .chatgpt_provider import generate as request
    reserve=cfg['_region_subrequest'];usages=[];usage_lock=threading.Lock()
    contract_value=contract(context);game_context,av_context,world_context=worker_contexts(user,contract_value)
    captured=cfg.get('_region_component_output')
    from .content_prompt import HYBRID
    from .visuals import VISUAL_PROMPT
    audit=cfg.get('_audit')
    identity={'version':2,'context':context,'system':system,'user':user,'gameplay_prompt':GAMEPLAY_COMPONENT,
              'av_prompt':AV_PROMPT,'model':cfg.get('model'),'effort':cfg.get('reasoning_effort'),
              'hybrid':cfg.get('hybrid_content',True),'jev':cfg.get('jev_enabled',True)}
    checkpoint_key=hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    responses=cfg.get('_region_checkpoint_load',lambda key:{})(checkpoint_key)
    def stats():
        result=aggregate(usages,cfg.get('reasoning_effort','high'),cfg.get('model','gpt-6-luna'))
        result['usage_recorded']=bool(cfg.get('_region_usage'))
        return result
    if audit:
        library=world_context.get('library_candidates') or {}
        audit.emit('region.context.split',**cfg.get('_request_meta',{}),source_chars=len(user),gameplay_chars=len(game_context),audiovisual_chars=len(av_context),contract_chars=len(json.dumps(contract_value,ensure_ascii=False,separators=(',',':'))),image_candidates=len(library.get('images',[])),audio_candidates=len(library.get('audio',[])),module_candidates=len(library.get('modules',[])),material_candidates=len(library.get('materials',[])))
    def run(component,prompt_text,input_text,outer=False):
        # 兼容独立管线工具；正式导演由每次实际请求领取预算。
        call=cfg.get('_request_meta',{}).get('call') if outer and not cfg.get('_region_reserve_all') else reserve(component)
        local=dict(cfg,_request_meta=dict(cfg.get('_request_meta',{}),component=component,call=call))
        progress=cfg.get('_codex_progress')
        if progress:local['_codex_progress']=lambda value:progress(dict(value,component=component))
        try:raw,usage=request(prompt_text,input_text,local)
        except Exception as exc:
            usage=getattr(exc,'usage',{}) or {}
            with usage_lock:usages.append(usage)
            if cfg.get('_region_usage'):cfg['_region_usage'](component,call,usage,exc)
            raise
        with usage_lock:usages.append(usage)
        if cfg.get('_region_usage'):cfg['_region_usage'](component,call,usage,None)
        if cfg.get('_region_checkpoint_save'):cfg['_region_checkpoint_save'](checkpoint_key,component,raw)
        if captured:captured(component,raw,usage)
        finished=cfg.get('_region_component_done')
        if finished:finished(component)
        return raw
    gameplay_system=system.split('\nHYBRID CONTENT:',1)[0].split('\nFor regions, visuals is REQUIRED;',1)[0]+GAMEPLAY_COMPONENT
    av_system=AV_PROMPT+'\n'+(HYBRID if cfg.get('hybrid_content',True) else VISUAL_PROMPT)
    systems={'gameplay':gameplay_system,'audiovisual':av_system};inputs={'gameplay':game_context,'audiovisual':av_context}
    def run_audiovisual():
        if cfg.get('jev_enabled',True) and cfg.get('hybrid_content',True):
            value=parsed(inputs['audiovisual'],'audiovisual context');av_world=value['world_context']
            from .jev_judgments import rank_assets
            ranked,report=rank_assets(context,contract_value,av_world.get('library_candidates',{}),cfg.get('_cancel_event'))
            av_world['library_candidates']=ranked
            inputs['audiovisual']=json.dumps(value,ensure_ascii=False,separators=(',',':'))
            notify=cfg.get('_jev_event')
            if notify:notify('asset_selection',report)
        return run('audiovisual',av_system,inputs['audiovisual'])
    failures=[]
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='region-component') as pool:
        futures={}
        if 'gameplay' not in responses:futures['gameplay']=pool.submit(run,'gameplay',gameplay_system,game_context,True)
        if 'audiovisual' not in responses:futures['audiovisual']=pool.submit(run_audiovisual)
        for component,future in futures.items():
            try:responses[component]=future.result()
            except Exception as exc:failures.append(exc)
        for component in set(responses)-set(futures):
            if cfg.get('_region_component_done'):cfg['_region_component_done'](component)
    if failures:
        error=failures[0];error.usage=stats()
        if hasattr(error,'diagnostics'):
            error.diagnostics['usage_recorded']=bool(cfg.get('_region_usage'))
            error.diagnostics['retries_exhausted']=any(getattr(e,'diagnostics',{}).get('retries_exhausted') for e in failures)
        raise error
    repaired=set()
    def repair(component,error):
        base=parsed(inputs[component],component+' context')
        try:base['rejected_component']=parsed(responses[component],component+' response')
        except PipelineError:base['rejected_component_text']=str(responses[component])[:128000]
        base['validation_error']=error.issues or [{'path':'$','message':str(error)}]
        if component=='audiovisual':
            base['required_audio_references']=[i for i in error.issues if i.get('cue')]
        repair_system=systems[component]+'\nRepair only rejected_component using validation_error. Preserve valid content and the region_design contract; return the complete corrected component.'
        responses[component]=run(component,repair_system,json.dumps(base,ensure_ascii=False,separators=(',',':')))
        repaired.add(component)
    try:
        while True:
            try:
                assembled=assemble(responses['gameplay'],responses['audiovisual'],contract_value,world_context)
                if cfg.get('_region_validation_context'):
                    from .diagnostics import InvalidPatch
                    from .schema import parse_patch
                    try:parse_patch(assembled,'region',cfg['_region_validation_context'],[])
                    except InvalidPatch as exc:
                        visual=all(i.get('path','').startswith(('region.visuals','region.audio')) for i in exc.issues)
                        raise PipelineError(str(exc),component='audiovisual' if visual else 'gameplay',issues=exc.issues) from None
                return assembled,stats()
            except PipelineError as exc:
                if not exc.component or exc.component in repaired or not cfg.get('_region_can_repair',lambda:False)():raise
                repair(exc.component,exc)
    except Exception as exc:
        exc.usage=stats()
        if hasattr(exc,'diagnostics'):exc.diagnostics['usage_recorded']=bool(cfg.get('_region_usage'))
        raise

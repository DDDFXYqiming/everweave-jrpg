"""Derive a compact director contract, then build gameplay and AV in parallel."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
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
3 objectives and 2 story scenes. Prefer one consequential encounter or negotiation over many tiny mechanisms.'''

AV_PROMPT='''You are the audiovisual worker for one already designed region. Return JSON only:
{"kind":"region_av","visuals":VISUALS,"audio":AUDIO}.
Implement every allowed sprite and surface slot in region_design as a sprite or binding. Use compatible library candidates first, compose when useful,
and draw distinctive missing focal objects. Do not invent entities/items, coordinates, rules, dialogue or story facts.
Visuals has exactly style,terrain,palette,sprites,scenery,density,bindings; never put scene or paint inside visuals.
Audio must include exploration music and suitable sparse cues. Keep <=10 sprite definitions by using bindings and
shared role art where it fits; reuse materials/scenery locally.'''


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
    return dict(name=name,description=description,cast=cast,sprite_slots=list(dict.fromkeys(slots)),
                surfaces=['ground_surface','path_surface','wall_surface','accent_surface'],
                gameplay_direction=text(context.get('region_purpose') or description,'gameplay direction',450),
                visual_direction=text(((context.get('game_spec') or {}).get('visual_theme') or description),'visual direction',450),
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
    return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def aggregate(usages):
    result=dict(input_tokens=0,output_tokens=0,reasoning_tokens=0,cached_input_tokens=0,reasoning_observed=False,
                provider='chatgpt_subscription',model='gpt-5.6-luna',effort='high',pipeline_requests=len(usages))
    for usage in usages:
        for key in ('input_tokens','output_tokens','reasoning_tokens','cached_input_tokens'):result[key]+=usage.get(key,0)
        result['reasoning_observed']|=bool(usage.get('reasoning_observed'))
    return result


def worker_contexts(user,contract):
    envelope=parsed(user,'region request');world=envelope.get('world_context',{})
    if not isinstance(world,dict):raise PipelineError('region request omitted world_context')
    game_drop={'library_candidates','hero_visual','current_audio','known_sprites','asset_history'}
    audiovisual_keys={'setting','world_title','target','destination','region_purpose','game_spec','visual_theme',
                      'library_candidates','hero_visual','current_audio','design_history','asset_history','language'}
    game={'world_context':{k:v for k,v in world.items() if k not in game_drop},'region_design':contract}
    audiovisual={'world_context':{k:v for k,v in world.items() if k in audiovisual_keys},'region_design':contract}
    compact=lambda value:json.dumps(value,ensure_ascii=False,separators=(',',':'))
    return compact(game),compact(audiovisual),world


def generate(context,system,user,cfg):
    from .chatgpt_provider import generate as request
    reserve=cfg['_region_subrequest'];usages=[]
    contract_value=contract(context);game_context,av_context,world_context=worker_contexts(user,contract_value)
    captured=cfg.get('_region_component_output')
    from .content_prompt import HYBRID
    from .visuals import VISUAL_PROMPT
    def run(component,prompt_text,input_text,outer=False):
        call=cfg.get('_request_meta',{}).get('call') if outer else reserve(component)
        local=dict(cfg,_request_meta=dict(cfg.get('_request_meta',{}),component=component,call=call))
        progress=cfg.get('_codex_progress')
        if progress:local['_codex_progress']=lambda value:progress(dict(value,component=component))
        raw,usage=request(prompt_text,input_text,local)
        if captured:captured(component,raw,usage)
        finished=cfg.get('_region_component_done')
        if finished:finished(component)
        return raw,usage
    gameplay_system=system.split('\nHYBRID CONTENT:',1)[0].split('\nFor regions, visuals is REQUIRED;',1)[0]+GAMEPLAY_COMPONENT
    av_system=AV_PROMPT+'\n'+(HYBRID if cfg.get('hybrid_content',True) else VISUAL_PROMPT)
    systems={'gameplay':gameplay_system,'audiovisual':av_system};inputs={'gameplay':game_context,'audiovisual':av_context}
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='region-component') as pool:
        gameplay_future=pool.submit(run,'gameplay',gameplay_system,game_context,True)
        av_future=pool.submit(run,'audiovisual',av_system,av_context)
        gameplay_raw,gameplay_usage=gameplay_future.result();av_raw,av_usage=av_future.result()
    usages.extend((gameplay_usage,av_usage))
    responses={'gameplay':gameplay_raw,'audiovisual':av_raw};repaired=set()
    def repair(component,error):
        base=parsed(inputs[component],component+' context')
        base['rejected_component']=parsed(responses[component],component+' response')
        base['validation_error']=error.issues or [{'path':'$','message':str(error)}]
        repair_system=systems[component]+'\nRepair only rejected_component using validation_error. Preserve valid content and the region_design contract; return the complete corrected component.'
        raw,usage=run(component,repair_system,json.dumps(base,ensure_ascii=False,separators=(',',':')))
        responses[component]=raw;usages.append(usage);repaired.add(component)
    try:
        assembled=assemble(responses['gameplay'],responses['audiovisual'],contract_value,world_context)
    except PipelineError as exc:
        can_repair=cfg.get('_region_can_repair',lambda:False)
        if exc.component and can_repair():
            repair(exc.component,exc)
            try:assembled=assemble(responses['gameplay'],responses['audiovisual'],contract_value,world_context)
            except PipelineError as retry_error:retry_error.usage=aggregate(usages);raise
        else:exc.usage=aggregate(usages);raise
    validation_context=cfg.get('_region_validation_context')
    if validation_context:
        from .diagnostics import InvalidPatch
        from .schema import parse_patch
        try:parse_patch(assembled,'region',validation_context,[])
        except InvalidPatch as exc:
            visual=all(i.get('path','').startswith(('region.visuals','region.audio')) for i in exc.issues)
            component='audiovisual' if visual else 'gameplay';can_repair=cfg.get('_region_can_repair',lambda:False)
            if component not in repaired and can_repair():
                repair(component,PipelineError(str(exc),component=component,issues=exc.issues))
                assembled=assemble(responses['gameplay'],responses['audiovisual'],contract_value,world_context)
    return assembled,aggregate(usages)

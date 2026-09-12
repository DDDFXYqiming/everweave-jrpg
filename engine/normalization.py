"""Correct only unambiguous syntax, with scoped definition/reference maps.

No gameplay fields are discarded. Existing canonical identities and prose are
never globally rewritten, and ambiguous aliases remain validation errors.
"""
import copy
import json
import re
from collections import defaultdict

from .diagnostics import InvalidPatch, issue, brief
from .catalog import BASE_ITEMS

BARE = re.compile(r'[a-z][a-z0-9_]{0,39}\Z')
QUALIFIED = re.compile(r'[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*)+\Z')
RESERVED_OBJECTS = {'player', 'enemy', 'self', 'back', 'forward_0', 'forward_1', 'forward_2', 'forward_3'}


def item_local_id(item, region_id):
    key = item.get('id', '')
    if item.get('origin') != region_id and not key.startswith(region_id + ':'):
        return None
    if item.get('local_id'):
        return item['local_id']
    local = key.removeprefix(region_id + ':')
    # Compatibility for IDs allocated by the runtime before local_id was saved.
    return re.sub(r'^event_[0-9]+_', '', local)


def decode(raw):
    if isinstance(raw, str):
        if len(raw.encode('utf-8')) > 128000:
            raise InvalidPatch('response too large', expected='at most 128000 UTF-8 bytes')
        raw = raw.strip()
        if raw.startswith('```') and raw.endswith('```'):
            raw = raw.split('\n', 1)[-1].rsplit('```', 1)[0]
        try:
            raw = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        except (ValueError, TypeError) as exc:
            raise InvalidPatch('invalid JSON', expected='one finite JSON object') from exc
    return copy.deepcopy(raw)


class Normalizer:
    def __init__(self, raw, expected, context):
        self.raw, self.expected, self.context = raw, expected, context or {}
        self.body = raw.get(expected) if isinstance(raw, dict) else None
        self.target = self.context.get('target', self.context.get('current_region', {}).get('id', ''))
        self.defs = defaultdict(list)
        self.maps = defaultdict(dict)
        self.existing = defaultdict(set)
        self.local = defaultdict(lambda: defaultdict(set))
        self.corrections, self.errors = [], []
        self._existing_ids()

    def record(self, path, operation, old, new):
        if old != new:
            self.corrections.append(dict(path=path, operation=operation, before=brief(old), after=brief(new)))

    def error(self, path, message, value=None, expected=None, category='reference'):
        self.errors.append(issue(path, message, category=category, value=value, expected=expected))

    def _existing_ids(self):
        ctx = self.context
        if self.context.get('item_policy')!='authored':self.existing['items'].update(BASE_ITEMS)
        if ctx.get('hero_visual'):self.existing['sprites'].add('hero')
        for scope in ('lore','threads'):
            for entry in ctx.get(scope, []):
                if isinstance(entry,dict) and isinstance(entry.get('id'),str):
                    self.existing[scope].add(entry['id']);self.local[scope][entry['id']].add(entry['id'])
        for entry in ctx.get('quests',[])+ctx.get('validation_quests',[]):
            if isinstance(entry,dict) and isinstance(entry.get('id'),str):
                self.existing['quests'].add(entry['id'])
        items = list(ctx.get('available_items', [])) + list(ctx.get('validation_items', []))
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str):
                continue
            key = item['id']; self.existing['items'].add(key)
            local = item_local_id(item, self.target)
            if local:
                self.local['items'][local].add(key)
        current = ctx.get('current_region') or {}
        for obj in current.get('entities', []) + ctx.get('validation_props', []):
            if not isinstance(obj, dict) or not isinstance(obj.get('id'), str):
                continue
            key = obj['id']; self.existing['objects'].add(key)
            if current.get('id') == self.target:
                self.local['objects'][obj.get('local_id', key.removeprefix(self.target + ':'))].add(key)
        if self.expected == 'reaction':
            for key in ctx.get('known_sprites', []):
                self.existing['sprites'].add(key); self.local['sprites'][key].add(key)
            program = ctx.get('current_program') or {}
            for scope in ('actions', 'hooks', 'objectives'):
                for entry in program.get(scope, []):
                    self.existing[scope].add(entry['id']); self.local[scope][entry['id']].add(entry['id'])
            for key in (ctx.get('current_runtime') or {}).get('vars', program.get('vars', {})):
                self.existing['vars'].add(key); self.local['vars'][key].add(key)

    def move_field(self, source, destination, field, source_path, destination_path):
        if field not in source:
            return
        if field in destination and destination[field] != source[field]:
            self.error(source_path, 'conflicting field copies; choose one consistent value',
                       expected=destination_path)
            return
        destination[field] = source.pop(field)
        self.record(source_path, 'field_location', source_path, destination_path)

    def alias(self, obj, old, new, path):
        if not isinstance(obj, dict) or old not in obj:
            return
        if new in obj and obj[new] != obj[old]:
            self.error(path + '.' + old, 'conflicting field aliases', expected=path + '.' + new)
            return
        obj[new] = obj.pop(old)
        self.record(path + '.' + old, 'field_alias', old, new)

    def formats(self):
        raw, body, root = self.raw, self.body, self.expected
        if not isinstance(raw, dict) or raw.get('kind') != root or not isinstance(body, dict):
            return
        other = 'reaction' if root == 'region' else 'region'
        if other in raw:
            return
        if raw.get('type')=='json_object':
            raw.pop('type')
            self.record('type','envelope_metadata','json_object',None)
        for field in ('visuals', 'program','audio') + (('scene','starting_loadout') if root == 'region' else ()):
            self.move_field(raw, body, field, field, root + '.' + field)
        # A library ID in a typed sprite/surface field is already unambiguous.
        # Materialize its local sprite definition rather than spend a model
        # repair asking for an otherwise redundant alias declaration.
        from .library import catalog
        art=body.get('visuals')
        if isinstance(art,dict) and isinstance(art.get('sprites'),dict):
            for name,sprite in art['sprites'].items():
                if isinstance(sprite,dict) and not any(k in sprite for k in ('asset','parts','layers')) and isinstance(sprite.get('frames'),list) and sprite['frames'] and isinstance(sprite['frames'][0],list):
                    sprite['layers']=copy.deepcopy(sprite['frames'][0])
                    self.record(root+'.visuals.sprites.'+name+'.layers','first_frame',None,'frames[0]')
            def materialize(value,path):
                if isinstance(value,str) and value not in art['sprites'] and value in catalog() and catalog()[value]['kind']=='image':
                    art['sprites'][value]={'asset':value}
                    self.record(path,'library_reference',value,root+'.visuals.sprites.'+value)
            for group in ('entities','spawns','landmarks','items','object_updates'):
                for i,entry in enumerate(body.get(group,[]) if isinstance(body.get(group),list) else []):
                    if isinstance(entry,dict):
                        self.alias(entry,'sprite_id','sprite',f'{root}.{group}[{i}]')
                        materialize(entry.get('sprite'),f'{root}.{group}[{i}].sprite')
            def surfaces(value,path):
                if isinstance(value,list):
                    for i,entry in enumerate(value):surfaces(entry,f'{path}[{i}]')
                elif isinstance(value,dict):
                    if 'surface' in value:materialize(value['surface'],path+'.surface')
                    if value.get('op')=='sprite':materialize(value.get('value'),path+'.value')
                    for key,entry in value.items():
                        if key not in ('vars','state'):surfaces(entry,path+'.'+key)
            surfaces(body.get('scene',{}),root+'.scene')
            surfaces(body.get('paint',[]),root+'.paint')
            surfaces(body.get('program',{}),root+'.program')
        audio=body.get('audio')
        if isinstance(audio,dict):
            def source_options(value,path):
                if not isinstance(value,dict):return
                for nested in ('synth','score'):
                    if isinstance(value.get(nested),dict):
                        for option in ('delay_ms','pitch','volume','loop'):
                            self.move_field(value[nested],value,option,path+'.'+nested+'.'+option,path+'.'+option)
                for i,layer in enumerate(value.get('layers',[]) if isinstance(value.get('layers'),list) else []):source_options(layer,f'{path}.layers[{i}]')
            for group in ('music','cues'):
                for name,value in audio.get(group,{}).items() if isinstance(audio.get(group),dict) else []:source_options(value,root+'.audio.'+group+'.'+name)
            source_options(audio.get('ambience'),root+'.audio.ambience')
            cues=audio.setdefault('cues',{})
            if isinstance(cues,dict):
                for group in ('bindings','objects'):
                    for name,value in (audio.get(group,{}) or {}).items() if isinstance(audio.get(group,{}),dict) else []:
                        if isinstance(value,str) and value not in cues and value in catalog() and catalog()[value]['kind']=='sfx':
                            cues[value]={'asset':value}
                            self.record(root+'.audio.'+group+'.'+name,'library_reference',value,root+'.audio.cues.'+value)
            if isinstance(audio.get('music'),dict):
                for name,value in list(audio['music'].items()):
                    if isinstance(value,str) and value in catalog() and catalog()[value]['kind']=='music':
                        audio['music'][name]={'asset':value}
                        self.record(root+'.audio.music.'+name,'library_reference',value,audio['music'][name])
        for field in ('lore', 'threads'):
            self.move_field(body, raw, field, root + '.' + field, field)
        if root == 'region' and 'id' in body and isinstance(body['id'], str) and re.fullmatch(r'[a-z][a-z0-9_:]*', body['id']):
            self.record('region.id', 'engine_identity', body['id'], self.target or 'request target')
            body.pop('id')
        for group in ('entities', 'spawns', 'landmarks', 'items', 'object_updates'):
            if isinstance(body.get(group), list):
                for i, entry in enumerate(body[group]):
                    path = f'{root}.{group}[{i}]'
                    self.alias(entry, 'sprite_id', 'sprite', path)
                    if group in ('entities', 'spawns'):
                        self.alias(entry, 'itemId', 'item_id', path)
        for group in ('entities', 'spawns', 'npc_lines'):
            if isinstance(body.get(group), list):
                for i, entry in enumerate(body[group]):
                    if isinstance(entry, dict) and isinstance(entry.get('dialogue'), str):
                        entry['dialogue'] = [entry['dialogue']]
                        self.record(f'{root}.{group}[{i}].dialogue', 'single_text_array', 'string', 'one-element array')

    def define(self, scope, obj, key, path, *, repeated=False):
        if not isinstance(obj, dict) or key not in obj:
            return
        self.defs[scope].append((obj, key, path, obj[key], repeated))

    def define_keys(self, scope, obj, path):
        if isinstance(obj, dict):
            for key in obj:
                self.defs[scope].append((obj, None, f'{path}.{key}', key, False))

    def collect_definitions(self):
        body, root = self.body, self.expected
        if isinstance(self.raw,dict):
            for group in ('lore','threads'):
                values=self.raw.get(group,[])
                if isinstance(values,list):
                    for i,value in enumerate(values):self.define(group,value,'id',f'{group}[{i}].id')
        if not isinstance(body, dict):
            return
        groups = {'entities':'objects', 'spawns':'objects', 'landmarks':'objects',
                  'items':'items', 'quests':'quests', 'destinations':'destinations', 'locations':'destinations'}
        for field, scope in groups.items():
            for i, entry in enumerate(body.get(field, []) if isinstance(body.get(field), list) else []):
                self.define(scope, entry, 'id', f'{root}.{field}[{i}].id')
        art = body.get('visuals')
        if isinstance(art, dict):
            self.define_keys('sprites', art.get('sprites'), root + '.visuals.sprites')
        program = body.get('program')
        if isinstance(program, dict):
            self.define_keys('vars', program.get('vars'), root + '.program.vars')
            for scope in ('actions', 'hooks', 'objectives'):
                entries = program.get(scope, [])
                if isinstance(entries, list):
                    for i, entry in enumerate(entries):
                        self.define(scope, entry, 'id', f'{root}.program.{scope}[{i}].id')
            self._timer_definitions(program, root + '.program')
        for i, item in enumerate(body.get('items', []) if isinstance(body.get('items'), list) else []):
            if isinstance(item, dict):
                self._timer_definitions(item.get('use'), f'{root}.items[{i}].use')

    def _timer_definitions(self, node, path):
        if isinstance(node, list):
            for i, value in enumerate(node): self._timer_definitions(value, f'{path}[{i}]')
        elif isinstance(node, dict):
            if node.get('op') == 'timer': self.define('timers', node, 'id', path + '.id', repeated=True)
            for key, value in node.items(): self._timer_definitions(value, path + '.' + key)

    def identifiers(self):
        locations = {entry.get('id') for entry in self.context.get('known_locations', []) if isinstance(entry, dict)}
        for scope, entries in self.defs.items():
            candidates = defaultdict(list)
            for entry in entries:
                obj, key, path, old, repeated = entry
                if not isinstance(old, str):
                    self.error(path, 'definition ID must be a string', old, 'bare lower_snake_case identifier',category='format'); continue
                clean = old.strip(); new = clean.rsplit(':', 1)[-1] if QUALIFIED.fullmatch(clean) else clean
                if not BARE.fullmatch(new):
                    self.error(path, 'invalid definition ID', old, 'lower_snake_case, at most 40 characters',category='format'); continue
                if scope == 'objects' and new in RESERVED_OBJECTS:
                    self.error(path, 'ID is reserved for the runtime', old, 'a distinct object ID'); continue
                if scope == 'items' and new in BASE_ITEMS and self.context.get('item_policy')!='authored':
                    self.error(path, 'item ID is reserved for an existing base item', old, 'a distinct new item ID'); continue
                if scope=='destinations' and clean in locations and clean not in {d.get('id') for d in self.context.get('existing_destinations',[]) if isinstance(d,dict)}:
                    self.error(path,'an existing region ID is not a new destination definition',old,'a distinct local destination ID');continue
                if clean != new and (clean in self.existing[scope] or (scope in ('items','objects') and clean.split(':')[0] in locations - {self.target})):
                    self.error(path, 'existing or foreign identity cannot be redefined as a new local definition', old,
                               'reference the existing ID, or give the new definition a distinct ID'); continue
                if old != new and self.local[scope].get(new):
                    self.error(path, 'renaming would collide with an installed identity', old, 'a distinct new ID'); continue
                if self.expected == 'reaction' and scope in ('objects','items') and self.local[scope].get(new):
                    self.error(path, 'new definition collides with an existing local identity', old, 'a distinct new ID'); continue
                candidates[new].append(entry)
            for new, same in candidates.items():
                old_names = {entry[3] for entry in same}
                if len(old_names) > 1 or (len(same) > 1 and not all(entry[4] for entry in same)):
                    for entry in same:
                        self.error(entry[2], 'definition IDs collide after normalization', entry[3], 'unique IDs within this definition scope')
                    continue
                old = same[0][3]
                self.maps[scope][old] = new
                self.maps[scope][new] = new
                if self.target and scope in ('objects','items'):
                    qualified=self.target+':'+new
                    if qualified not in self.existing[scope]:self.maps[scope][qualified]=new
                    if self.expected=='reaction':
                        registered=f'{self.target}:event_{self.context.get("story_revision",0)}_{new}'
                        if registered not in self.existing[scope]:self.maps[scope][registered]=new
                for obj, key, path, original, _ in same:
                    if key is None:
                        if original != new: obj[new] = obj.pop(original)
                    else: obj[key] = new
                    self.record(path, 'definition_id', original, new)

    def ref(self, scope, value, path, *, canonical=False, local_event=False):
        if not isinstance(value, str):
            return value  # The typed validator reports non-string references.
        if scope=='sprites' and value not in self.maps[scope] and value not in self.existing[scope]:
            from .library import catalog
            if value in catalog() and catalog()[value]['kind']=='image' and isinstance(self.body,dict):
                art=self.body.get('visuals')
                identity=self.context.get('current_visual_identity')
                if art is None and self.expected=='reaction' and isinstance(identity,dict) and identity.get('palette'):
                    art=copy.deepcopy(identity);art['sprites']={};self.body['visuals']=art
                if isinstance(art,dict) and isinstance(art.get('sprites'),dict):
                    art['sprites'].setdefault(value,{'asset':value})
                    self.maps[scope][value]=value
                    self.record(path,'library_reference',value,self.expected+'.visuals.sprites.'+value)
        if scope=='items' and 'validation_items' in self.context and value not in self.maps[scope] and value not in self.existing[scope]:
            matches=self.local[scope].get(value,set())
            if len(matches)!=1:
                self.error(path,'undefined item reference' if not matches else 'ambiguous item reference',value,
                           f'define the new item in {self.expected}.items or use an exact existing canonical item ID')
        result = self.maps[scope].get(value, value)
        if scope=='objects' and 'validation_items' in self.context:
            known={'player','enemy','self'} | set(self.maps[scope]) | set(self.maps[scope].values())
            if self.expected=='reaction':known |= self.existing[scope] | set(self.local[scope])
            for prop in self.body.get('landmarks',[]) if isinstance(self.body,dict) and isinstance(self.body.get('landmarks'),list) else []:
                if isinstance(prop,dict):
                    identifier=prop.get('id',prop.get('type',''))
                    if isinstance(identifier,str):known.add(identifier)
            if value not in known:
                self.error(path,'undefined object reference in this region',value,'a declared local object or an existing object in the current region')
        if scope=='sprites' and value not in self.maps[scope] and value not in self.existing[scope]:
            from .visuals import resolve_sprite
            art=self.body.get('visuals',{}) if isinstance(self.body,dict) else {}
            bindings=dict(self.context.get('validation_bindings',{})) if self.expected=='reaction' else {}
            if isinstance(art,dict) and isinstance(art.get('bindings'),dict):bindings.update(art['bindings'])
            bindings={key:self.maps[scope].get(target,target) for key,target in bindings.items() if isinstance(target,str)}
            available=self.existing[scope] | set(self.maps[scope].values())
            try:result=resolve_sprite(value,dict(sprites=dict.fromkeys(available),bindings=bindings))
            except InvalidPatch:
                if 'validation_items' in self.context:
                    self.error(path,'undefined visual sprite reference',value,'a defined sprite or explicit semantic binding')
        if value in self.maps[scope] and canonical and self.target:
            if scope == 'objects' and self.expected == 'reaction':
                result = f'{self.target}:event_{self.context.get("story_revision",0)}_{result}'
            elif scope in ('objects', 'items'):
                result = self.target + ':' + result
        elif value not in self.maps[scope] and result==value:
            # Existing canonical item/object references are preserved exactly.
            if scope in ('items','objects') and value in self.existing[scope] and not local_event:
                return value
            prefix = self.target + ':' if self.target else None
            if prefix and value.startswith(prefix):
                suffix = value[len(prefix):]
                matches = self.local[scope].get(suffix, set())
                if len(matches) == 1 and (scope not in ('items','objects') or local_event): result = suffix
            if scope == 'objects' and canonical and value in self.local[scope]:
                matches = self.local[scope][value]
                if len(matches) == 1: result = next(iter(matches))
                elif len(matches) > 1: self.error(path, 'ambiguous object reference', value)
        self.record(path, 'reference_id', value, result)
        return result

    def field_ref(self, obj, key, scope, path, **kwargs):
        if isinstance(obj, dict) and key in obj:
            obj[key] = self.ref(scope, obj[key], path + '.' + key, **kwargs)

    def expression(self, node, path):
        if not isinstance(node, dict): return
        if set(node)=={'not'}:
            previous=copy.deepcopy(node)
            operand=node['not'];node.clear();node.update(op='not',args=[operand])
            self.record(path,'expression_alias',previous,node)
        if 'item' in node: self.field_ref(node, 'item', 'items', path)
        for field in ('get', 'path'):
            value = node.get(field)
            if not isinstance(value, str): continue
            parts = value.split('.')
            if parts[0] == 'vars' and len(parts) == 2:
                parts[1] = self.ref('vars', parts[1], path + '.' + field)
            elif parts[0] == 'objects' and len(parts) >= 3:
                parts[1] = self.ref('objects', parts[1], path + '.' + field)
            node[field] = '.'.join(parts)
        args = node.get('args')
        if isinstance(args, list):
            if node.get('op') in ('eq', 'ne') and len(args) == 2:
                for i in (0, 1):
                    lookup = args[i].get('get') if isinstance(args[i], dict) else None
                    if lookup in ('event.target','event.canonical_target','event.action'):
                        scope = 'actions' if lookup == 'event.action' else 'objects'
                        args[1-i] = self.ref(scope, args[1-i], f'{path}.args[{1-i}]',
                                             canonical=lookup == 'event.canonical_target', local_event=True)
            for i, value in enumerate(args): self.expression(value, f'{path}.args[{i}]')

    def program_refs(self, node, path):
        if isinstance(node, list):
            for i, value in enumerate(node): self.program_refs(value, f'{path}[{i}]')
        elif isinstance(node, dict):
            self.expression(node, path)
            op = node.get('op')
            if op == 'item': self.field_ref(node, 'id', 'items', path)
            if op in ('move','sprite','solid','remove') or 'scope' in node or 'on' in node or ('label' in node and 'effects' in node):
                self.field_ref(node, 'target', 'objects', path)
            if op == 'sprite': self.field_ref(node, 'value', 'sprites', path)
            if 'surface' in node: self.field_ref(node, 'surface', 'sprites', path)
            for key, value in node.items():
                # Plain scalar values and prose are untouched. Reference expressions
                # and effects are handled only at their documented syntax locations.
                if key not in ('vars','state','args'): self.program_refs(value, path + '.' + key)

    def references(self):
        body, root = self.body, self.expected
        if not isinstance(body, dict): return
        audio=body.get('audio')
        if isinstance(audio,dict) and isinstance(audio.get('objects'),dict):
            audio['objects']={self.ref('objects',name,root+'.audio.objects.'+name,local_event=True):cue for name,cue in audio['objects'].items()}
        kit=body.get('starting_loadout')
        if isinstance(kit,dict):
            for slot in ('weapon','charm'):
                if kit.get(slot):self.field_ref(kit,slot,'items',root+'.starting_loadout')
            for i,entry in enumerate(kit.get('inventory',[]) if isinstance(kit.get('inventory'),list) else []):
                self.field_ref(entry,'item_id','items',f'{root}.starting_loadout.inventory[{i}]')
        for group in ('entities','spawns','landmarks','items','object_updates'):
            entries = body.get(group, [])
            if not isinstance(entries, list): continue
            for i, entry in enumerate(entries):
                path = f'{root}.{group}[{i}]'
                self.field_ref(entry, 'sprite', 'sprites', path)
                if group in ('entities','spawns'): self.field_ref(entry, 'item_id', 'items', path)
                if group == 'object_updates': self.field_ref(entry, 'id', 'objects', path, canonical=True)
                if group == 'items' and isinstance(entry, dict): self.program_refs(entry.get('use'), path + '.use')
        for i, entry in enumerate(body.get('npc_lines', []) if isinstance(body.get('npc_lines'), list) else []):
            self.field_ref(entry, 'id', 'objects', f'{root}.npc_lines[{i}]', canonical=True)
        for i,entry in enumerate(body.get('future_updates',[]) if isinstance(body.get('future_updates'),list) else []):
            if not isinstance(entry,dict) or not isinstance(entry.get('id'),str):continue
            value=entry['id'];frontier=self.context.get('frontier',[])
            if any(f.get('id')==value for f in frontier):continue
            matches=[f['id'] for f in frontier if (f.get('outline') or {}).get('id')==value]
            if len(matches)==1:
                entry['id']=matches[0];self.record(f'{root}.future_updates[{i}].id','reference_id',value,matches[0])
            elif len(matches)>1:self.error(f'{root}.future_updates[{i}].id','ambiguous future destination reference',value)
        for i, entry in enumerate(body.get('quests', []) if isinstance(body.get('quests'), list) else []):
            if isinstance(entry, dict):
                self.field_ref(entry, 'target', 'items' if entry.get('goal') == 'collect' else 'objects', f'{root}.quests[{i}]')
        scene = body.get('scene')
        if isinstance(scene, dict):
            anchors = scene.get('anchors')
            if isinstance(anchors, dict):
                rebuilt = {}
                for key, value in anchors.items():
                    new = key if key in ('back','forward_0','forward_1','forward_2','forward_3') else self.ref('objects', key, root + '.scene.anchors.' + key)
                    if new in rebuilt and rebuilt[new] != value:
                        self.error(root + '.scene.anchors.' + key, 'conflicting anchor aliases', value)
                    else: rebuilt[new] = value
                scene['anchors'] = rebuilt
            self.program_refs(scene.get('paint'), root + '.scene.paint')
        self.program_refs(body.get('paint'), root + '.paint')
        self.program_refs(body.get('program'), root + '.program')
        art = body.get('visuals')
        if isinstance(art, dict):
            if isinstance(art.get('bindings'), dict):
                for key in art['bindings']: self.field_ref(art['bindings'], key, 'sprites', root + '.visuals.bindings')
            if isinstance(art.get('scenery'), list):
                art['scenery'] = [self.ref('sprites', value, f'{root}.visuals.scenery[{i}]') for i,value in enumerate(art['scenery'])]

    def run(self):
        self.formats()
        self.collect_definitions()
        self.identifiers()
        self.references()
        return self.raw, self.corrections, self.errors


def normalize_patch(raw, expected, context=None):
    return Normalizer(decode(raw), expected, context).run()

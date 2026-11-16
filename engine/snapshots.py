import copy
import uuid
from collections import OrderedDict
from .runtime import Runtime, RuleError


STATIC_REGION_FIELDS = frozenset((
    'name', 'description', 'biome', 'width', 'height', 'seed', 'spawn',
    'tiles', 'surfaces', 'visuals', 'audio', 'program', 'scene', 'scenes',
))
PRIVATE_REGION_FIELDS = frozenset(('plan', 'pending_lore', 'pending_threads', '_generation_raw'))


def _immutable(*args, **kwargs):
    raise TypeError('地区静态快照只读')


class _FrozenDict(dict):
    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable

    def __deepcopy__(self, memo):
        return self


class _FrozenList(list):
    __setitem__ = __delitem__ = append = clear = extend = insert = pop = remove = reverse = sort = __iadd__ = __imul__ = _immutable

    def __deepcopy__(self, memo):
        return self


def _freeze(value):
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze(item) for item in value)
    return value


class RegionSnapshots:
    def __init__(self):
        self.entries = OrderedDict()
        self.dirty = set()
        self.sequence = 0
        self.instance = uuid.uuid4().hex

    def clear(self):
        self.entries.clear()
        self.dirty.clear()

    def invalidate(self, rid):
        if rid in self.entries:
            self.dirty.add(rid)

    def project(self, region, epoch, known_token=None):
        if region is None:
            return None, '', False, []
        rid = region['id']
        entry = self.entries.get(rid)
        if entry is None or entry[0] is not region or entry[1] != epoch or rid in self.dirty:
            definition = {key: value for key, value in region.items() if key in STATIC_REGION_FIELDS}
            if entry is None or entry[1] != epoch or definition != entry[2]:
                self.sequence += 1
                entry = (region, epoch, _freeze(definition), epoch + ':' + self.instance + ':' + str(self.sequence))
            else:
                entry = (region, epoch, entry[2], entry[3])
            self.entries[rid] = entry
            self.dirty.discard(rid)
        self.entries.move_to_end(rid)
        while len(self.entries) > 6:
            evicted, _ = self.entries.popitem(last=False)
            self.dirty.discard(evicted)
        unchanged = bool(known_token and known_token == entry[3])
        public = {key: value for key, value in region.items()
                  if key not in STATIC_REGION_FIELDS and key not in PRIVATE_REGION_FIELDS}
        if not unchanged:
            public.update(entry[2])
        return public, entry[3], unchanged, list(entry[2])


class RegionRollback:
    def __init__(self, cache):
        self.original = OrderedDict(cache)
        self.objects = {id(region) for region in cache.values()}
        self.before = {}

    def touch(self, region):
        identity = id(region)
        if identity in self.objects and identity not in self.before:
            self.before[identity] = copy.deepcopy(region)

    def restore(self):
        return OrderedDict((rid, self.before.get(id(region), region))
                           for rid, region in self.original.items())


class SnapshotRead(Runtime):
    def __init__(self, world, region):
        runtime = dict(vars={}, used=[], done={}, timers=[], clock=0, history=[])
        runtime.update(region.get('runtime', {}))
        runtime['vars'] = dict(runtime['vars'])
        super().__init__(world, dict(region, runtime=runtime))

    def reset(self):
        self.gas = 4096
        self.actor = 'player'
        self.event = {}
        return self

    def access(self, name, write=False):
        if write:
            raise RuleError('条件视图不可写入世界')
        from .content import path
        path(name, False)
        bits = name.split('.')
        if bits[0] == 'self' and len(bits) == 3:
            return self.entity(self.actor).get('state', {}), bits[2]
        if bits[0] == 'objects' and len(bits) == 4:
            return self.entity(bits[1]).get('state', {}), bits[3]
        return super().access(name)

    def _reject_effect(self, *args, **kwargs):
        raise RuleError('条件视图不可执行效果')

    run = perform = emit = invoke = _reject_effect

import copy
from collections import deque


_LIMITS = dict(cast=16, skills=16, missions=24, jobs=16, known_regions=32)


def _take(keys, known, selected, limit):
    for key in keys:
        if len(selected) >= limit:
            break
        if key in known and key not in selected:
            selected.append(key)


def _missions(missions, jobs, rid):
    active = [key for key, mission in missions.items() if mission['status'] == 'active']
    local = [key for key, mission in missions.items() if mission['region'] == rid]
    required = list(dict.fromkeys(key for job in jobs
                                 if job['region'] == rid and job['status'] == 'queued'
                                 for key in job['missions'] + job['requires']))
    selected = []
    _take([key for key in local if key in active][:4] + active[:4] + required[:4],
          missions, selected, _LIMITS['missions'])

    def dependencies():
        pending = deque(selected)
        seen = set()
        while pending and len(selected) < _LIMITS['missions']:
            key = pending.popleft()
            if key in seen:
                continue
            seen.add(key)
            parents = missions[key]['depends']
            _take(parents, missions, selected, _LIMITS['missions'])
            pending.extend(parent for parent in parents if parent in missions and parent not in seen)

    dependencies()
    for key in required + [key for key in local if key in active] + active + local + list(reversed(missions)):
        if len(selected) >= _LIMITS['missions']:
            break
        _take([key], missions, selected, _LIMITS['missions'])
        dependencies()
    return selected


def _condition_evidence(conditions, chapter):
    flags = chapter.get('flags', {})
    return [dict(flag=condition['flag'], eq=condition['eq'],
                 known=condition['flag'] in flags, actual=flags.get(condition['flag']),
                 source=chapter.get('flag_sources', {}).get(condition['flag']))
            if 'flag' in condition else dict(condition) for condition in conditions]


def _mission_status(keys, missions):
    return [dict(id=key, status=missions[key]['status'] if key in missions else 'unknown')
            for key in keys]


def retrieve(world, rid=None):
    """从权威状态派生有界上下文，较早未兑现目标保留独立名额。"""
    state = world.state or {}
    adventure = state.get('adventure', {})
    rid = rid or state.get('current')
    missions = adventure.get('missions', {})
    jobs = adventure.get('jobs', {})
    cast = adventure.get('cast', {})
    skills = adventure.get('skills', {})
    topology = state.get('topology', {})
    chapters = state.get('campaign', {}).get('chapters', {})
    order = {key: index for index, key in enumerate(jobs)}
    ranked_jobs = sorted(jobs, key=lambda key: (
        0 if jobs[key]['status'] == 'queued' and jobs[key]['region'] == rid else
        1 if jobs[key]['status'] == 'queued' else
        2 if jobs[key]['region'] == rid else 3,
        order[key] if jobs[key]['status'] == 'queued' else -order[key]))
    mission_ids = _missions(missions, [jobs[key] for key in ranked_jobs], rid)
    related_jobs = [key for key in ranked_jobs
                    if any(mission in mission_ids for mission in jobs[key]['missions'] + jobs[key]['requires'])]
    queued_jobs = [key for key in ranked_jobs if jobs[key]['status'] == 'queued']
    job_ids = []
    _take(queued_jobs + related_jobs + ranked_jobs, jobs, job_ids, _LIMITS['jobs'])

    local_jobs = [jobs[key] for key in ranked_jobs if jobs[key]['region'] == rid and jobs[key]['status'] == 'queued']
    current = world.cache.get(rid, {})
    local_cast = [entity.get('actor_id') for entity in current.get('entities', [])]
    local_cast += [key for job in local_jobs for key in job['cast']]
    actor_ids = []
    _take(local_cast + [key for job_id in job_ids for key in jobs[job_id]['cast']]
          + [key for key, actor in cast.items() if not actor['state'].get('alive', True)]
          + list(reversed(cast)), cast, actor_ids, _LIMITS['cast'])
    learned = state.get('player', {}).get('abilities', [])
    skill_ids = []
    _take([key for job in local_jobs for key in job['skills']] + learned
          + [key for job_id in job_ids for key in jobs[job_id]['skills']]
          + list(reversed(skills)), skills, skill_ids, _LIMITS['skills'])

    region_ids = []
    related_regions = [rid] + [missions[key]['region'] for key in mission_ids]
    related_regions += [jobs[key]['region'] for key in job_ids]
    for key in mission_ids:
        mission = missions[key]
        chapter = chapters.get(mission['chapter_id'], {})
        related_regions += [chapter.get('flag_sources', {}).get(condition['flag'])
                            for field in ('when', 'fail_when', 'reveal_when')
                            for condition in mission.get(field, []) if 'flag' in condition]
    _take(related_regions + list(reversed(topology)), topology, region_ids, _LIMITS['known_regions'])

    open_missions = []
    for key in mission_ids:
        mission = missions[key]
        if mission['status'] != 'active':
            continue
        chapter = chapters.get(mission['chapter_id'], {})
        entry = {field: copy.deepcopy(mission[field])
                 for field in ('id', 'name', 'brief', 'region', 'chapter_id', 'status')}
        entry['depends'] = _mission_status(mission['depends'], missions)
        for field in ('when', 'fail_when', 'reveal_when'):
            entry[field] = _condition_evidence(mission.get(field, []), chapter)
        open_missions.append(entry)

    commissions = []
    for key in job_ids:
        job = jobs[key]
        entry = {field: copy.deepcopy(job[field]) for field in
                 ('id', 'kind', 'region', 'brief', 'status', 'cast', 'skills', 'missions')}
        entry['requires'] = _mission_status(job['requires'], missions)
        entry['mission_status'] = _mission_status(job['missions'], missions)
        if job.get('receipt'):
            entry['receipt'] = copy.deepcopy(job['receipt'])
        commissions.append(entry)

    missing_dependencies = {parent for key in mission_ids for parent in missions[key]['depends']
                            if parent not in mission_ids}
    omitted = dict(cast=len(cast) - len(actor_ids), skills=len(skills) - len(skill_ids),
                   missions=len(missions) - len(mission_ids), jobs=len(jobs) - len(job_ids),
                   known_regions=len(topology) - len(region_ids),
                   active_missions=sum(mission['status'] == 'active' and key not in mission_ids
                                       for key, mission in missions.items()),
                   queued_jobs=sum(job['status'] == 'queued' and key not in job_ids for key, job in jobs.items()),
                   dependency_missions=len(missing_dependencies),
                   commission_missions=len({mission for key in job_ids
                                            for mission in jobs[key]['missions'] + jobs[key]['requires']
                                            if mission not in mission_ids}),
                   learned_skills=sum(key not in skill_ids for key in learned))
    causal = dict(source='authoritative_world_state', scope='structured_missions_and_commissions',
                  focus_region=rid, limits=dict(_LIMITS), omitted=omitted, truncated=any(omitted.values()),
                  open_missions=open_missions, commissions=commissions,
                  cast=[{field: copy.deepcopy(cast[key][field]) for field in ('id', 'name', 'state')}
                        for key in actor_ids],
                  skills=[dict(id=key, learned=key in learned, implemented=bool(skills[key].get('rule')))
                          for key in skill_ids])
    return dict(cast=[{field: copy.deepcopy(cast[key][field])
                       for field in ('id', 'name', 'role', 'motive', 'state')} for key in actor_ids],
                skills=[{field: copy.deepcopy(skills[key][field])
                         for field in ('id', 'name', 'description', 'scope')} for key in skill_ids],
                missions=copy.deepcopy([missions[key] for key in mission_ids]),
                jobs=copy.deepcopy([jobs[key] for key in job_ids]),
                known_regions=[dict(id=key, name=topology[key]['name'], visited=topology[key]['visited'],
                                    ready=topology[key]['ready']) for key in region_ids],
                causal_memory=causal)

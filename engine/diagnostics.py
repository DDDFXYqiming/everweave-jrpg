"""Bounded, structured diagnostics shared by model validation and the director."""
import json


def brief(value):
    if value is None or type(value) in (bool, int, float):
        return value
    if isinstance(value, str):
        return value if len(value) <= 180 else value[:177] + '...'
    return json.dumps(value, ensure_ascii=False, default=str)[:180]


def issue(path, message, *, category='format', value=None, expected=None):
    result = dict(path=path or '$', category=category, message=str(message))
    if value is not None:
        result['value'] = brief(value)
    if expected is not None:
        result['expected'] = str(expected)
    return result


def join_path(parent, child):
    if not child or child == '$':
        return parent or '$'
    if not parent or parent == '$':
        return child
    a, b = parent.split('.'), child.split('.')
    for count in range(min(len(a), len(b)), 0, -1):
        if a[-count:] == b[:count]:
            return '.'.join(a + b[count:])
    return parent + ('' if child.startswith('[') else '.') + child


def category_for(message):
    text = str(message).lower()
    if any(word in text for word in ('undefined', 'unknown reaction item', 'unknown/nonliving',
            'ambiguous', 'conflicting', 'already exists', 'duplicate', 'reference', 'declare variable')):
        return 'reference'
    if any(word in text for word in ('blocked', 'footprint', 'outside', 'reachable', 'overlap',
            'no approach', 'no room', 'player/spawn', 'cascade', 'execution budget', 'division by zero',
            'cannot remove', 'cannot rewrite', 'cannot replace', 'preserve existing')):
        return 'gameplay'
    return 'format'


class InvalidPatch(ValueError):
    def __init__(self, message=None, *, path='$', category=None, value=None, expected=None,
                 issues=None, corrections=None):
        self.issues = list(issues) if issues is not None else [
            issue(path, message, category=category or category_for(message), value=value, expected=expected)]
        self.corrections = list(corrections or [])
        super().__init__(self._message())

    def _message(self):
        return '; '.join((entry['path'] + ': ' if entry['path'] != '$' else '') + entry['message']
                         for entry in self.issues[:12])

    def under(self, parent):
        return InvalidPatch(issues=[dict(entry, path=join_path(parent, entry['path']))
                                   for entry in self.issues], corrections=self.corrections)


def as_issues(error, parent='$', category=None):
    if isinstance(error, InvalidPatch):
        entries = error.under(parent).issues
    else:
        entries = [issue(parent, str(error), category=category or 'internal')]
    if category:
        entries = [dict(entry, category=category) for entry in entries]
    return entries


def checked(path, function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except InvalidPatch as error:
        raise error.under(path) from None


def unique_issues(entries, limit=20):
    result, seen = [], set()
    for entry in entries:
        key = (entry['path'], entry['message'])
        if key not in seen:
            seen.add(key)
            result.append(entry)
        if len(result) >= limit:
            break
    return result


def validation_report(error):
    """JSON consumed by the repair prompt; do not truncate away field locations."""
    return json.dumps({'errors': unique_issues(as_issues(error)),
                       'instruction': 'Fix these fields in the supplied rejected_response; retain valid content.'},
                      ensure_ascii=False)

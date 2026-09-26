"""在隔离存档上比较 Go 模型的生成速度与游戏内容契约。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.director import ChatProvider, ProviderError
from engine.schema import InvalidPatch
from engine.storage import Store
from engine.world import World

BASE_URL = 'https://opencode.ai/zen/go/v1'
DEFAULT_MODELS = ('space-bunny-free', 'longcat-2.5-preview-free')


def copy_database(source: Path, destination: Path) -> None:
    original = sqlite3.connect(source)
    isolated = sqlite3.connect(destination)
    try:
        original.backup(isolated)
    finally:
        original.close()
        isolated.close()


def summarize_patch(patch: dict) -> dict:
    kind = patch['kind']
    body = patch[kind]
    if kind == 'region':
        return {'name': body.get('name'), 'entities': len(body.get('entities', [])),
                'actions': len(body.get('program', {}).get('actions', [])),
                'sprites': len(body.get('visuals', {}).get('sprites', {})),
                'quests': len(body.get('quests', [])),
                'description_chars': len(body.get('description', ''))}
    if kind == 'reaction':
        return {'text_chars': len(body.get('text', '')),
                'actions': len(body.get('program', {}).get('actions', [])),
                'spawns': len(body.get('spawns', []))}
    return {'missions': len(body.get('missions', [])),
            'links': len(body.get('links', [])),
            'jobs': len(body.get('jobs', []))}


def evaluate(model: str, kind: str, source: Path, region_id: str, output: Path, key: str, repeat: int, max_seconds: int, effort: str) -> dict:
    stem = model.replace('/', '_') + '-' + effort + '-' + kind + '-' + str(repeat)
    database = output / (stem + '.sqlite3')
    copy_database(source, database)
    world = World(Store(database))
    context = world.context(region_id) if kind == 'region' else world.context(kind=kind)
    config = {'provider': 'chat_completions', 'offline': False, 'base_url': BASE_URL,
              'model': model, 'api_key': key, 'deepseek_options': False,
              'reasoning_effort': effort, 'hybrid_content': True, 'language': 'zh'}
    result = {'model': model, 'kind': kind, 'repeat': repeat, 'effort': effort,
              'context_chars': len(json.dumps(context, ensure_ascii=False))}
    started = time.perf_counter()
    last_progress = started
    def progress(details):
        nonlocal last_progress
        now = time.perf_counter()
        if now - last_progress >= 30:
            print(json.dumps({'model': model, 'kind': kind, 'elapsed_seconds': round(now - started, 1),
                              'content_chars': details['content_chars'], 'wire_bytes': details['wire_bytes']},
                             ensure_ascii=False), flush=True)
            last_progress = now
    config['_task_deadline'] = time.monotonic() + max_seconds
    config['_stream_progress'] = progress
    try:
        raw, usage = ChatProvider(config).generate(context, kind)
        elapsed = time.perf_counter() - started
        result.update(http_ok=True, seconds=round(elapsed, 3), usage=usage,
                      output_tps=round(usage.get('output_tokens', 0) / elapsed, 2),
                      visible_tps=round(max(0,usage.get('output_tokens', 0)-usage.get('reasoning_tokens', 0)) / elapsed, 2))
        (output / (stem + '.json')).write_text(raw, encoding='utf-8')
        try:
            patch = world.validate_patch(raw, context)
            if kind == 'region' and context.get('content_version') == 2:
                region = patch['region']
                if not region.get('scene') or not region.get('program') or not region.get('visuals'):
                    raise InvalidPatch('live region requires scene, program and visuals')
                if not region.get('audio', {}).get('music', {}).get('explore'):
                    raise InvalidPatch('live hybrid region requires exploration music')
            result['contract_ok'] = True
            result['content'] = summarize_patch(patch)
            result['applied'] = bool(world.apply_patch(raw, context, 'qa_benchmark'))
        except InvalidPatch as error:
            result['contract_ok'] = False
            result['issues'] = error.issues[:8]
        except Exception as error:
            result['contract_ok'] = False
            result['issues'] = [{'category': 'internal', 'message': str(error)[:240]}]
    except ProviderError as error:
        result.update(http_ok=False, seconds=round(time.perf_counter() - started, 3),
                      error=str(error)[:240])
    finally:
        world.store.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--early-db', type=Path, required=True)
    parser.add_argument('--region-db', type=Path, required=True)
    parser.add_argument('--region-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--models', nargs='+', default=DEFAULT_MODELS)
    parser.add_argument('--cases', nargs='+', choices=('direction', 'reaction', 'region'),
                        default=('direction', 'reaction', 'region'))
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--max-seconds', type=int, default=600)
    parser.add_argument('--effort', choices=('default', 'none', 'low', 'medium', 'high'), default='default')
    args = parser.parse_args()
    if args.repeat < 1 or args.repeat > 5:
        parser.error('--repeat 必须是 1～5')
    if args.max_seconds < 30 or args.max_seconds > 900:
        parser.error('--max-seconds 必须是 30～900')
    args.output.mkdir(parents=True, exist_ok=True)
    key_file = ROOT / 'userdata/provider-keys.local.json'
    key = json.loads(key_file.read_text(encoding='utf-8'))['chat_completions'][BASE_URL]
    results = []
    for kind in args.cases:
        source = args.region_db if kind == 'region' else args.early_db
        for model in args.models:
            for repeat in range(1, args.repeat + 1):
                print(f'开始 {model} / {kind} / {repeat}', flush=True)
                result = evaluate(model, kind, source, args.region_id, args.output, key, repeat, args.max_seconds, args.effort)
                results.append(result)
                (args.output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
                summary = {k: result.get(k) for k in ('model', 'kind', 'effort', 'repeat', 'http_ok', 'contract_ok', 'seconds', 'output_tps', 'visible_tps', 'error')}
                summary['issues'] = [{k: issue.get(k) for k in ('path', 'category', 'message')}
                                     for issue in result.get('issues', [])[:3]]
                print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

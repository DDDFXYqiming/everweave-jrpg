#!/usr/bin/env python3
"""Create/verify a PRIVATE GitHub repository, commit this project and push normally.
Uses the user's existing GitHub CLI login. Never reads or prints a GitHub token.
No public fallback, no force push, no changes to global git configuration.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
ALLOWED_ROOTS={'engine','client','assets','docs','tests','tools','.github'}
ALLOWED_FILES={'project.godot','README.md','LICENSE-NOTICE.md','launch.py','Start.ps1','Start.cmd','Publish-Private.ps1','.gitignore','.gitattributes','.editorconfig'}
SKIP_DIRS={'.git','.godot','__pycache__','.pytest_cache','.venv','venv','saves','userdata','build','dist','exports'}


def command(args, check=True):
    result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,encoding='utf-8',errors='replace')
    if check and result.returncode:
        raise RuntimeError(f'Command failed: {args[0]} {args[1]}\n{result.stderr.strip()}')
    return result


def source_files():
    result=[]
    for file in ROOT.rglob('*'):
        if not file.is_file():continue
        rel=file.relative_to(ROOT)
        if any(p in SKIP_DIRS for p in rel.parts):continue
        if rel.parts[:3]==('assets','library','blobs'):continue
        if rel.parts[0] not in ALLOWED_ROOTS and str(rel) not in ALLOWED_FILES:continue
        if file.name in ('runtime.json','instance.lock') or file.suffix.lower() in ('.sqlite3','.sqlite','.db','.key','.pem','.exe','.zip','.log','.pyc'):
            continue
        if file.name.startswith('.env') or 'credentials' in file.name.lower() or 'secrets' in file.name.lower():continue
        if file.is_symlink():raise RuntimeError(f'Refusing symlink: {rel}')
        if file.stat().st_size>15_000_000:raise RuntimeError(f'Unexpectedly large source file: {rel}')
        if file.suffix.lower() in ('.py','.gd','.json','.md','.yml','.yaml','.ps1','.cmd'):
            body=file.read_text(encoding='utf-8')
            if re.search(r'(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{35,})',body):
                raise RuntimeError(f'Possible embedded credential in {rel}; remove it before publishing.')
        result.append(rel.as_posix())
    return sorted(result)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner',default='DDDFXYqiming')
    parser.add_argument('--name',default='everweave-jrpg')
    parser.add_argument('--existing-empty',action='store_true',help='Allow an existing private repo ONLY if GitHub confirms it has no commits')
    parser.add_argument('--dry-run',action='store_true',help='Validate and list files only; no GitHub or git writes')
    args=parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}',args.owner) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}',args.name):
        raise RuntimeError('Invalid GitHub owner or repository name.')
    files=source_files()
    if not files or 'project.godot' not in files:raise RuntimeError('Not an Everweave project folder.')
    repo=f'{args.owner}/{args.name}'
    if args.dry_run:
        print(f'PRIVATE target: {repo}\nFiles: {len(files)}')
        print('\n'.join(files))
        return 0
    if not shutil.which('gh') or not shutil.which('git'):
        raise RuntimeError('Install Git and GitHub CLI, then run `gh auth login` before publishing.')
    profile=json.loads(command(['gh','api','user']).stdout)
    if profile['login'].casefold()!=args.owner.casefold():
        raise RuntimeError(f'Authenticated as {profile["login"]}, not {args.owner}. Select the correct gh account first.')
    found=command(['gh','api',f'repos/{repo}'],check=False)
    if found.returncode==0:
        meta=json.loads(found.stdout)
        if meta.get('private') is not True:raise RuntimeError('REFUSED: the repository is not private. Nothing was uploaded.')
        if not args.existing_empty:raise RuntimeError('Repository exists. Nothing was overwritten. Use --existing-empty only for a confirmed empty private repository.')
        commits=command(['gh','api',f'repos/{repo}/commits?per_page=1'],check=False)
        if commits.returncode==0 or '409' not in commits.stderr+commits.stdout:
            raise RuntimeError('Cannot confirm that the existing private repository is empty. Refusing to push.')
    elif '404' in found.stderr+found.stdout:
        command(['gh','repo','create',repo,'--private','--description','Live LLM-directed pixel JRPG with a Godot client and persistent local world runtime'])
    else:
        raise RuntimeError('Repository lookup failed; this is not a confirmed 404. Nothing was created.\n'+found.stderr)
    meta=json.loads(command(['gh','api',f'repos/{repo}']).stdout)
    if meta.get('private') is not True:raise RuntimeError('Privacy verification failed. No files were pushed.')
    expected='https://github.com/'+repo+'.git'
    if not (ROOT/'.git').exists():command(['git','init','-b','main'])
    else:
        git_root=command(['git','rev-parse','--show-toplevel']).stdout.strip()
        if Path(git_root).resolve()!=ROOT:raise RuntimeError('Refusing to publish a parent repository.')
        if command(['git','branch','--show-current']).stdout.strip()!='main':
            raise RuntimeError('Refusing to switch an existing branch automatically. Use a clean project copy on main.')
    remote=command(['git','remote','get-url','origin'],check=False)
    if remote.returncode==0:
        if remote.stdout.strip() not in (expected,expected.removesuffix('.git'),'git@github.com:'+repo+'.git'):
            raise RuntimeError('origin points somewhere else. It was not changed.')
    else:command(['git','remote','add','origin',expected])
    # Local-only author identity; never change the user's global Git settings.
    if command(['git','config','user.name'],check=False).returncode:
        command(['git','config','--local','user.name',profile['login']])
    if command(['git','config','user.email'],check=False).returncode:
        command(['git','config','--local','user.email',str(profile['id'])+'+'+profile['login']+'@users.noreply.github.com'])
    # Remove any stale staging selection from a reused project clone before staging our explicit allow-list.
    # Refuse rather than silently unstage other work.
    staged=command(['git','diff','--cached','--name-only'],check=False).stdout.splitlines()
    if any(path not in files for path in staged):raise RuntimeError('Unexpected files are already staged. Review them manually first.')
    command(['git','add','--',*files])
    changes=command(['git','diff','--cached','--quiet'],check=False)
    if changes.returncode==1:
        command(['git','commit','-m','Implement live-directed pixel JRPG runtime, Godot client, original assets and tests'])
    elif changes.returncode!=0:raise RuntimeError('Could not inspect the staged changes.')
    # Per-command credential helper, no persistent global credential configuration.
    command(['git','-c','credential.helper=','-c','credential.helper=!gh auth git-credential','push','--set-upstream','origin','main'])
    final=json.loads(command(['gh','api',f'repos/{repo}']).stdout)
    if final.get('private') is not True:raise RuntimeError('Repository privacy changed during the operation; inspect it immediately.')
    print('Pushed to PRIVATE repository: '+final['html_url'])
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,OSError,ValueError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)

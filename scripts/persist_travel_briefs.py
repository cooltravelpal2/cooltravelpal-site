#!/usr/bin/env python3
"""Persist validated archive snapshots in the existing CI checkout before deploy."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, text=True, capture_output=True).stdout


def persist():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise RuntimeError('Snapshot persistence requires the main GitHub Actions checkout')
    if os.environ.get('TRAVEL_BRIEF_PERSIST_ENABLED') != 'true':
        raise RuntimeError('Snapshot persistence is not enabled')
    directory = ROOT / 'data/travel-briefs'
    if not directory.exists() or not any(directory.glob('*.json')):
        print('No archive snapshots to persist')
        return
    git('add', '--', 'data/travel-briefs')
    changed = git('diff', '--cached', '--name-only').splitlines()
    if not changed:
        print('No archive changes')
        return
    if any(not name.startswith('data/travel-briefs/') or not name.endswith('.json') for name in changed):
        raise RuntimeError('Unrelated staged files; refusing snapshot commit')
    from daily_travel_brief import load_editions
    load_editions(ROOT / 'data/travel-briefs')
    git('config', 'user.name', 'github-actions[bot]')
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    git('commit', '-m', 'Archive TravelPal.now daily travel editions')
    # A non-fast-forward rejection aborts the workflow before deployment.
    # Never overwrite a concurrent human commit or assume this push triggers CI.
    git('push', 'origin', 'HEAD:main')
    print('Persisted archive snapshots:', len(changed))


if __name__ == '__main__':
    persist()

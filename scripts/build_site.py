#!/usr/bin/env python3
"""Deploy static TravelPal content plus a separate, synchronized DongDong teaser."""
import argparse
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from daily_exercise import load_current

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.github', 'scripts', 'tests', 'dist', 'templates', '__pycache__', '.preview'}


def teaser_html(data):
    esc = html.escape
    return f'''<section class="dongdong-teaser" data-daily-release="{esc(data['releaseId'], quote=True)}">
<div><p class="eyebrow">Featured {esc(data['date'])} · Pacific time</p><h2>{esc(data['name']['en'])}</h2>
<p><strong>What you need:</strong> {esc(data['equipment']['en'])}</p>
<p>Watch the demonstration and read the full steps on DongDong. The featured movement changes each day.</p>
<p lang="zh-Hans">今日动作：{esc(data['name']['zh-Hans'])}。所需器材：{esc(data['equipment']['zh-Hans'])}。前往咚咚网站观看示范并阅读完整步骤。</p>
<a class="btn btn-primary" href="{esc(data['url'], quote=True)}">See today's exercise on DongDong ↗</a></div>
<a href="{esc(data['url'], quote=True)}" aria-label="Watch {esc(data['name']['en'], quote=True)} on DongDong"><img src="{esc(data['posterUrl'], quote=True)}" alt="Animated demonstration preview of {esc(data['name']['en'], quote=True)}" width="240" height="427"></a></section>'''


def build(output, data):
    if output.resolve() == ROOT or ROOT not in output.resolve().parents:
        raise ValueError('Output must be a build directory inside this repository')
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for item in ROOT.iterdir():
        if item.name in EXCLUDED or item.name.startswith('.') or item.suffix in {'.md', '.yml', '.yaml'}:
            continue
        if item.is_dir():
            shutil.copytree(item, output / item.name, ignore=shutil.ignore_patterns('__pycache__', '.DS_Store'))
        else:
            shutil.copy2(item, output / item.name)
    (output / '.nojekyll').touch()
    page = output / 'dongdong/index.html'
    source = page.read_text()
    source = re.sub(r'<!-- DAILY_TEASER_START -->.*?<!-- DAILY_TEASER_END -->',
                    lambda match: '<!-- DAILY_TEASER_START -->' + teaser_html(data) + '<!-- DAILY_TEASER_END -->', source, flags=re.S)
    source = source.replace('<!-- DAILY_MODIFIED -->', data['date'])
    page.write_text(source)
    (output / 'dongdong/daily-exercise.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    sitemap = output / 'sitemap.xml'
    source = sitemap.read_text()
    source = re.sub(r'(<loc>https://travelpal.now/dongdong/</loc><lastmod>)[^<]+', lambda match: match[1] + data['date'], source)
    sitemap.write_text(source)
    print('Built separate DongDong teaser:', data['releaseId'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path, help='Local preview/test only; never used by deployment workflow')
    parser.add_argument('--output', default='dist')
    args = parser.parse_args()
    day = datetime.now(ZoneInfo('America/Los_Angeles')).date()
    data = json.loads(args.fixture.read_text()) if args.fixture else load_current(day)
    build(ROOT / args.output, data)

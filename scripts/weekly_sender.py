"""Saturday cloud sender. EmailOctopus fields provide a private write-ahead ledger."""
import argparse
import hashlib
import html
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from weekly_digest import collect, render, select_highlights, short_copy
from daily_travel_brief import load_editions, SECTIONS

LIST_ID = 'de2bac34-80c4-11f1-ad85-1b83433e3fd4'
AUTOMATION_ID = '69b368be-bf90-11f1-a32d-2fff2da0bbd9'
FIELD_LIMIT = 600


def payload(digest):
    selected = select_highlights(digest, limit=5)
    fields = {'WeeklyPeriod': digest['weekEnding'], 'WeeklyHighlight5': str(1 + int(hashlib.sha256(digest['weekEnding'].encode()).hexdigest()[:8], 16) % 3)}
    for n, section in enumerate(SECTIONS, 1):
        stories = [s for s in selected if s['section'] == section]
        blocks = []
        for story in stories:
            copy = short_copy(story)
            # Never truncate structured offer terms. News summaries use whole sentences
            # where possible; the full weekly page retains the longer approved excerpt.
            budget = (FIELD_LIMIT - sum(len(s['title']) + 4 for s in stories)) // max(len(stories), 1)
            if len(copy) > budget and not story.get('terms'):
                import re
                sentences = re.split(r'(?<=[.!?])\s+', copy)
                copy = sentences[0]
                for sentence in sentences[1:]:
                    if len(copy) + len(sentence) + 1 > budget:
                        break
                    copy += ' ' + sentence
                if len(copy) > budget:
                    copy = copy[:budget - 1].rsplit(' ', 1)[0].rstrip(',.') + '…'
            blocks.append(story['title'] + '\n' + copy)
        text = '\n\n'.join(blocks)
        if len(text) > FIELD_LIMIT:
            raise ValueError('Highlight exceeds free-tier field limit; editorial review required')
        fields[f'WeeklyHighlight{n}'] = text
    return fields


class Provider:
    def __init__(self, key, list_id=LIST_ID, automation_id=AUTOMATION_ID):
        self.key, self.list_id, self.automation_id = key, list_id, automation_id

    def call(self, method, path, data=None):
        req = Request('https://api.emailoctopus.com' + path,
                      data=None if data is None else json.dumps(data).encode(),
                      method=method, headers={'Authorization': 'Bearer ' + self.key,
                      'Content-Type': 'application/json', 'Accept': 'application/json',
                      'User-Agent': 'TravelPal-Newsletter/1.0'})
        with urlopen(req, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else None

    def contacts(self):
        contacts, cursor, cursors = [], None, set()
        while True:
            query = {'status': 'subscribed', 'limit': 100}
            if cursor:
                query['starting_after'] = cursor
            page = self.call('GET', f'/lists/{self.list_id}/contacts?' + urlencode(query))
            contacts.extend(page['data'])
            if len(contacts) > 2500:
                raise ValueError('Starter subscriber limit exceeded; do not send or upgrade')
            cursor = (page.get('paging', {}).get('next') or {}).get('starting_after')
            if not cursor:
                break
            if cursor in cursors:
                raise ValueError('Repeated pagination cursor')
            cursors.add(cursor)
        return contacts

    def get(self, contact_id):
        return self.call('GET', f'/lists/{self.list_id}/contacts/{contact_id}')

    def update(self, contact_id, fields):
        # Existing-contact update only. Never changes subscription status or email.
        return self.call('PUT', f'/lists/{self.list_id}/contacts/{contact_id}', {'fields': fields})

    def quota(self):
        account_list = self.call('GET', f'/lists/{self.list_id}')
        field = next(f for f in account_list['fields'] if f['tag'] == 'WeeklyPeriod')
        if not field.get('fallback'):
            raise ValueError('Private quota baseline is not initialized')
        return json.loads(field['fallback'])

    def save_quota(self, state):
        self.call('PUT', f'/lists/{self.list_id}/fields/WeeklyPeriod', {'fallback': json.dumps(state, separators=(',', ':'))})

    def queue(self, contact_id):
        return self.call('POST', f'/automations/{self.automation_id}/queue', {'contact_id': contact_id})


def deliver(provider, digest, send=False, test=False):
    fields = payload(digest)
    if not any(fields[f'WeeklyHighlight{i}'] for i in range(1, 5)):
        return {'queued': 0, 'skipped': 0, 'eligible': 0, 'empty': True}
    contacts = provider.contacts()
    if test:
        allowed = set(filter(None, os.environ.get('EMAILOCTOPUS_TEST_CONTACT_IDS', '').split(',')))
        if not allowed or len(allowed) > 2:
            raise ValueError('Test recipients must be explicitly configured')
        contacts = [c for c in contacts if c['id'] in allowed]
    # Five weekly sends plus a welcome per contact fit Starter's 10,000 allowance
    # with a conservative 1,500-contact ceiling. No paid upgrade API is used.
    if len(contacts) > 1500:
        raise ValueError('Conservative free-tier headroom exceeded; manual quota review required')
    issue = ('weekly-test:' if test else 'weekly:') + digest['weekEnding']
    result = {'queued': 0, 'skipped': 0, 'eligible': len(contacts)}
    quota = provider.quota()
    today = date.fromisoformat(digest['weekEnding'])
    period = today.replace(day=16)
    if today.day < 16:
        period = (today.replace(day=1) - timedelta(days=1)).replace(day=16)
    if quota.get('period') != period.isoformat():
        if date.fromisoformat(quota['period']) > period:
            raise ValueError('Quota period would move backward')
        quota = {'period': period.isoformat(), 'reserved': 0, 'otherAllowance': 2500}
    if not isinstance(quota.get('reserved'), int) or not isinstance(quota.get('otherAllowance'), int):
        raise ValueError('Invalid quota baseline')
    if quota['reserved'] < 0 or quota['otherAllowance'] < 2500:
        raise ValueError('Invalid quota reservation')
    if quota['reserved'] + quota['otherAllowance'] + len(contacts) > 10000:
        raise ValueError('Monthly free-tier reservation would be exceeded; do not upgrade')
    for contact in contacts:
        current = provider.get(contact['id'])
        if current.get('status') != 'subscribed':
            result['skipped'] += 1
            continue
        state = current.get('fields', {}).get('WeeklySendState') or ''
        if state.startswith(issue + ':'):
            if not state.endswith(':queued'):
                raise ValueError('Unresolved send reservation; inspect provider before retrying')
            result['skipped'] += 1
            continue
        if state and not state.endswith(':queued'):
            raise ValueError('Unresolved prior send reservation; inspect provider before retrying')
        if not send:
            continue
        # Reserve capacity before making any queue request. An ambiguous attempt
        # consumes this reservation even if it later proves unsent.
        quota['reserved'] += 1
        provider.save_quota(quota)
        reserved = issue + ':pending' 
        provider.update(contact['id'], {**fields, 'WeeklySendState': reserved})
        check = provider.get(contact['id'])
        if check.get('fields', {}).get('WeeklySendState') != reserved:
            raise ValueError('Send reservation was not persisted')
        if check.get('status') != 'subscribed':
            # No status mutation. Clear the reservation because no queue was attempted.
            provider.update(contact['id'], {'WeeklySendState': state})
            result['skipped'] += 1
            continue
        # Never retry queue on timeouts or uncertain responses. Pending remains durable.
        provider.queue(contact['id'])
        provider.update(contact['id'], {'WeeklySendState': issue + ':queued'})
        result['queued'] += 1
    return result


def due(now):
    return now.weekday() == 5 and now.hour >= 9


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    now = datetime.now(ZoneInfo('America/Los_Angeles'))
    if args.send and not args.test and (not due(now) or now.date() < date(2026, 10, 10)):
        print('Not due: regular delivery begins October 10, Saturdays after 09:00 Pacific')
        return
    digest = collect(load_editions(Path('data/travel-briefs')), now.date())
    render(digest)
    provider = Provider(os.environ['EMAILOCTOPUS_API_KEY'])
    # Counts only; subscriber identifiers and addresses never enter public artifacts/logs.
    print(json.dumps(deliver(provider, digest, send=args.send, test=args.test)))

if __name__ == '__main__':
    main()

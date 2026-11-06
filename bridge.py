# The Discord bridge (run by .github/workflows/discord.yml every 30 minutes, in this repository):
# The server (The Long Dark Multiplayer, Karol 06.11): #updates (the bot's news: what was done, the dll), #błędy (game
# logs), #pomysły (mods to add), #claude-komendy (players' requests: big changes wait for Karol's yes, small fixes go
# ahead; commands !status !dll !zmiany !test !stop; questions about the mod, answered there).
#   in:  every new message on the server's text channels the bot can read, with its attachments (logs), saved as
#        inbox/<channel>/<date>/<message id>.json (+ the files in a folder beside it); inbox/state.json keeps where each
#        channel was read up to.
#   out: every outbox/*.txt is posted by the bot and removed. A file's first line "#channel-name" picks the channel
#        (default: DISCORD_DEFAULT_CHANNEL, else #updates, else the first text channel); files named in "attach: a, b" lines (paths in the
#        repo checkout) go along. outbox/reactions.lst: status reactions (react());
#        outbox/delete.lst: "#channel message_id" lines: the bot's own messages taken down.
# Standard library only. The token comes from the DISCORD_BOT_TOKEN secret; nothing here ever prints it.
import json, os, re, sys, time, uuid, urllib.request, urllib.error, urllib.parse

API = 'https://discord.com/api/v10'
TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '').strip()
ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
MAX_FILE = 25 * 1024 * 1024


def call(method, path, body=None, files=None, raw=False):
    url = API + path
    headers = {'Authorization': 'Bot ' + TOKEN, 'User-Agent': 'TLDCoopBridge (github actions, 1.0)'}
    data = None
    if files:
        boundary = uuid.uuid4().hex
        parts = [b'--' + boundary.encode() + b'\r\nContent-Disposition: form-data; name="payload_json"\r\n'
                 b'Content-Type: application/json\r\n\r\n' + json.dumps(body or {}).encode() + b'\r\n']
        for i, (name, blob) in enumerate(files):
            parts.append(b'--' + boundary.encode() + ('\r\nContent-Disposition: form-data; name="files[%d]"; '
                         'filename="%s"\r\nContent-Type: application/octet-stream\r\n\r\n' % (i, name)).encode() + blob + b'\r\n')
        data = b''.join(parts) + b'--' + boundary.encode() + b'--\r\n'
        headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
    elif body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = r.read()
                return out if raw else (json.loads(out) if out else None)
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limited: wait as told
                wait = float(json.loads(e.read() or b'{}').get('retry_after', 2))
                time.sleep(min(wait, 30) + 0.5)
                continue
            raise RuntimeError('%s %s -> HTTP %d: %s' % (method, path, e.code, e.read()[:300].decode('utf8', 'replace')))
    raise RuntimeError('%s %s: still rate limited' % (method, path))


def download(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'TLDCoopBridge (github actions, 1.0)'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def safe(name):
    # Polish letters as plain ones (#błędy -> bledy), anything else odd as _
    name = name.translate(str.maketrans('ąćęłńóśźżĄĆĘŁŃÓŚŹŻ', 'acelnoszzACELNOSZZ'))
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name)[:120] or 'file'


def text_channels():
    out = []
    only = os.environ.get('DISCORD_GUILD', '').strip() or 'The Long Dark Multiplayer'
    for g in call('GET', '/users/@me/guilds'):
        if g['name'] != only:  # (only the players' server, should the bot be added anywhere else)
            print('skip server %s' % g['name'])
            continue
        for c in call('GET', '/guilds/%s/channels' % g['id']):
            if c.get('type') in (0, 5):  # text, announcement
                out.append({'id': c['id'], 'name': c['name'], 'guild': g['name'], 'position': c.get('position', 0)})
    return sorted(out, key=lambda c: c['position'])


def pull(channels, state):
    new = 0
    for c in channels:
        after = state.get(c['id'])
        while True:
            q = '?limit=100' + ('&after=%s' % after if after else '')
            try:
                msgs = call('GET', '/channels/%s/messages%s' % (c['id'], q))
            except RuntimeError as e:  # a channel the bot can't read
                print('skip #%s: %s' % (c['name'], e))
                break
            if not msgs:
                break
            msgs.sort(key=lambda m: int(m['id']))
            if after is None:  # first run on a channel: the last 50 messages only
                msgs = msgs[-50:]
            for m in msgs:
                day = m['timestamp'][:10]
                folder = os.path.join(ROOT, 'inbox', safe(c['name']), day)
                os.makedirs(folder, exist_ok=True)
                rec = {'id': m['id'], 'channel': c['name'], 'time': m['timestamp'],
                       'author': m['author'].get('global_name') or m['author']['username'],
                       'username': m['author']['username'], 'bot': m['author'].get('bot', False),
                       'content': m.get('content', ''),
                       'reply_to': (m.get('referenced_message') or {}).get('id'),
                       'attachments': []}
                for a in m.get('attachments', []):
                    item = {'name': a['filename'], 'size': a['size']}
                    if a['size'] <= MAX_FILE:
                        path = os.path.join(folder, m['id'], safe(a['filename']))
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        try:
                            open(path, 'wb').write(download(a['url']))
                            item['saved'] = os.path.relpath(path, ROOT)
                        except Exception as e:
                            item['error'] = str(e)[:200]
                    rec['attachments'].append(item)
                json.dump(rec, open(os.path.join(folder, m['id'] + '.json'), 'w'), ensure_ascii=False, indent=1)
                new += 1
            after = msgs[-1]['id']
            state[c['id']] = after
            if len(msgs) < 50:
                break
    return new


def push(channels):
    out_dir = os.path.join(ROOT, 'outbox')
    if not os.path.isdir(out_dir):
        return 0
    default = os.environ.get('DISCORD_DEFAULT_CHANNEL', '').strip().lstrip('#') or 'updates'  # (Karol: news of changes go to #updates)
    by_name = {c['name']: c for c in channels}
    sent = 0
    for name in sorted(os.listdir(out_dir)):
        if not name.endswith('.txt'):
            continue
        path = os.path.join(out_dir, name)
        lines = open(path, encoding='utf8').read().split('\n')
        target = by_name.get(default) or (channels[0] if channels else None)
        if lines and lines[0].startswith('#'):
            target = by_name.get(lines[0][1:].strip(), target)
            lines = lines[1:]
        files = []
        body_lines = []
        for l in lines:
            if l.startswith('attach:'):
                for f in l[7:].split(','):
                    f = f.strip()
                    p = os.path.join(ROOT, f)
                    if f and os.path.isfile(p) and os.path.getsize(p) <= MAX_FILE:
                        files.append((os.path.basename(f), open(p, 'rb').read()))
            else:
                body_lines.append(l)
        text = '\n'.join(body_lines).strip()
        if not target or (not text and not files):
            os.remove(path)
            continue
        chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)] or ['']
        for i, chunk in enumerate(chunks):
            last = i == len(chunks) - 1
            call('POST', '/channels/%s/messages' % target['id'], {'content': chunk}, files if last and files else None)
        os.remove(path)
        sent += 1
        print('posted %s to #%s' % (name, target['name']))
    return sent


STATUS = ['👀', '⏳', '✅', '❌']  # read, in progress, done, turned down: one at a time, the bot's own


def react(channels):
    """outbox/reactions.lst: lines "#channel message_id emoji" set the bot's status reaction on that message (its other
    status reactions there are taken off); "-" as the emoji takes them all off."""
    path = os.path.join(ROOT, 'outbox', 'reactions.lst')
    if not os.path.isfile(path):
        return 0
    by_name = {c['name']: c for c in channels}
    done = 0
    for line in open(path, encoding='utf8').read().split('\n'):
        parts = line.split()
        if len(parts) != 3 or not parts[0].startswith('#'):
            continue
        ch, mid, emoji = by_name.get(parts[0][1:]), parts[1], parts[2]
        if not ch:
            print('reaction: no channel %s' % parts[0])
            continue
        q = urllib.parse.quote
        try:
            for other in STATUS:
                if other != emoji:
                    try:
                        call('DELETE', '/channels/%s/messages/%s/reactions/%s/@me' % (ch['id'], mid, q(other)))
                    except RuntimeError:
                        pass  # (not there)
            if emoji != '-':
                call('PUT', '/channels/%s/messages/%s/reactions/%s/@me' % (ch['id'], mid, q(emoji)))
            done += 1
        except RuntimeError as e:
            print('reaction %s on %s: %s' % (emoji, mid, e))
    os.remove(path)
    return done


def delete(channels):
    path = os.path.join(ROOT, 'outbox', 'delete.lst')
    if not os.path.isfile(path):
        return 0
    by_name = {c['name']: c for c in channels}
    done = 0
    for line in open(path, encoding='utf8').read().split('\n'):
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith('#') and parts[0][1:] in by_name:
            try:
                call('DELETE', '/channels/%s/messages/%s' % (by_name[parts[0][1:]]['id'], parts[1]))
                done += 1
            except RuntimeError as e:
                print('delete %s: %s' % (parts[1], e))
    os.remove(path)
    return done


def main():
    if not TOKEN:
        print('DISCORD_BOT_TOKEN is not set: nothing to do')
        return
    state_path = os.path.join(ROOT, 'inbox', 'state.json')
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    channels = text_channels()
    json.dump(channels, open(os.path.join(ROOT, 'inbox', 'channels.json'), 'w'), ensure_ascii=False, indent=1)
    sent = push(channels)
    reacted = react(channels)
    deleted = delete(channels)
    new = pull(channels, state)
    json.dump(state, open(state_path, 'w'), indent=1)
    print('channels %d, new messages %d, posted %d, reactions %d, deleted %d' % (len(channels), new, sent, reacted, deleted))


if __name__ == '__main__':
    main()

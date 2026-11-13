#!/usr/bin/env python3
"""The Discord bridge run on the server PC instead of GitHub Actions (Karol 14.11: "całego tego bota na ten serwer
przerzucić z githuba").

What the workflow did on demand, this does all the time, every INTERVAL_S seconds, in a clone of this repository:
  git pull  ->  bridge.py (post outbox/, reactions, read the channels into inbox/)  ->  crypt.py seal (inbox -> vault)
  ->  git commit + push (only when something changed)
The repository stays the mailbox between Discord and the Claude chats: they still read vault/ and write outbox/.
Nothing about bridge.py or the vault changes; the workflow stays for a manual run when this PC is off.

Needs: Python 3 with `cryptography` (py -3 -m pip install cryptography), Git signed in to GitHub with write access to
this repository (the first push opens GitHub's sign-in in the browser), and the bot's token in the environment
(DISCORD_BOT_TOKEN) or in a file: discord_bot_token.txt beside this script, in the clone's parent folder (so
C:\\tldserver\\discord_bot_token.txt when the clone is C:\\tldserver\\tldcoop-discord), or the path in
DISCORD_BOT_TOKEN_FILE. Nothing here prints the token. Log: local/run_bridge.log (not in git).

Unsealed messages never go to git: inbox/ is ignored but for its three index files, and a run whose seal failed
commits nothing of that run's messages (they wait, plain, on this disk for the next seal).
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LOG = os.path.join(HERE, 'run_bridge.log')
INTERVAL_S = int(os.environ.get('BRIDGE_INTERVAL_S', '60'))
BRANCH = os.environ.get('BRIDGE_BRANCH', 'main')


def log(text):
    line = time.strftime('[%Y-%m-%d %H:%M:%S] ') + text
    print(line, flush=True)
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 5 * 1024 * 1024:
            os.replace(LOG, LOG + '.old')
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def read_token():
    token = os.environ.get('DISCORD_BOT_TOKEN', '').strip()
    if token:
        return token
    places = [os.environ.get('DISCORD_BOT_TOKEN_FILE', ''), os.path.join(HERE, 'discord_bot_token.txt'),
              os.path.join(os.path.dirname(REPO), 'discord_bot_token.txt')]
    for path in places:
        if not path:
            continue
        try:
            with open(path, encoding='utf-8-sig') as f:
                token = f.read().strip().strip('"').strip()
            if token:
                return token
        except OSError:
            pass
    return ''


def run(args, env=None, timeout=600):
    """(exit code, output's last lines). Never raises."""
    try:
        p = subprocess.run(args, cwd=REPO, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=timeout)
        out = (p.stdout or '') + (p.stderr or '')
        return p.returncode, out.strip()[-600:]
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)[-300:]


def git(*args, timeout=180):
    return run(['git'] + list(args), timeout=timeout)


def pull():
    code, out = git('pull', '-q', '--rebase', 'origin', BRANCH)
    if code == 0:
        return True
    git('rebase', '--abort')
    log('git pull failed (%s)' % out.replace('\n', ' | ')[-300:])
    return False


def cycle(token):
    pulled = pull()  # (without it we still read Discord; what Claude left in outbox/ waits for the next pull)
    env = dict(os.environ)
    env['DISCORD_BOT_TOKEN'] = token
    env['PYTHONIOENCODING'] = 'utf-8'
    code, out = run([sys.executable, os.path.join(REPO, 'bridge.py'), REPO], env=env)
    summary = out.split('\n')[-1] if out else ''
    if code != 0:
        log('bridge.py failed: %s' % out.replace('\n', ' | ')[-400:])
    code, out = run([sys.executable, os.path.join(REPO, 'crypt.py'), 'seal', REPO])
    if code != 0:
        log('crypt.py seal failed (is `cryptography` installed? py -3 -m pip install cryptography): %s' % out[-200:])
    git('add', '-A', 'inbox', 'outbox', 'vault')
    code, _ = git('diff', '--cached', '--quiet')
    if code == 0:
        return summary, False
    code, out = git('commit', '-q', '-m', 'discord: ' + time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime()) + ' (server)')
    if code != 0:
        log('git commit failed: %s' % out[-200:])
        return summary, False
    for attempt in range(3):
        code, out = git('push', '-q', 'origin', 'HEAD:' + BRANCH)
        if code == 0:
            return summary, True
        pull()
        time.sleep(5)
    log('git push failed (signed in to GitHub with write access here? %s)' % out.replace('\n', ' | ')[-300:])
    return summary, False


def main():
    token = read_token()
    if not token:
        log('no bot token (discord_bot_token.txt beside the clone, or DISCORD_BOT_TOKEN): nothing to do')
        return 2
    if not os.path.isdir(os.path.join(REPO, '.git')):
        log('%s is not a git clone of the bridge repository' % REPO)
        return 2
    git('config', 'user.name', 'TLDCoop bridge')
    git('config', 'user.email', 'bridge@users.noreply.github.com')
    log('bridge on this PC: every %d s, repository %s, branch %s' % (INTERVAL_S, REPO, BRANCH))
    last = ''
    while True:
        started = time.time()
        try:
            summary, pushed = cycle(token)
            if pushed or (summary and summary != last and 'new messages 0, posted 0, reactions 0, deleted 0' not in summary):
                log('%s%s' % (summary or 'done', '; saved to GitHub' if pushed else ''))
            last = summary
        except Exception as e:  # (a cycle never ends the loop)
            log('cycle failed: %r' % e)
        if os.environ.get('BRIDGE_ONCE'):
            return 0
        time.sleep(max(5, INTERVAL_S - (time.time() - started)))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)

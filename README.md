# tldcoop-discord

The Discord bridge for TLDCoop_DLC (server "The Long Dark Multiplayer"): a bot run by GitHub Actions every 30 minutes.

- `inbox/<channel>/<date>/<id>.json` — the server's messages (author, text, attachments saved beside them in
  `<id>/`); `inbox/state.json` — where each channel was read up to; `inbox/channels.json` — the channels.
- `outbox/*.txt` — messages for the bot to post (first line `#channel`, default `#updates`; `attach: path` lines for
  files); posted and removed on the next run.
- Channels: `#updates` (news of changes and the dll), `#błędy` (game logs), `#pomysły` (mods to add),
  `#claude-komendy` (players' requests, commands `!status !dll !zmiany !test !stop`, questions), `#chat`.
- Status reactions (outbox/reactions.lst, "#channel message_id emoji"): 👀 read, ⏳ in progress, ✅ done, ❌ turned down.
- Secret: `DISCORD_BOT_TOKEN`.
- **Public repo (Karol 11.11): the players' messages, logs and files are kept only ENCRYPTED** in `vault/*.bin`
  (`crypt.py seal`, with the public key `vault.pub`, after every run). Only `inbox/state.json`, `inbox/channels.json`
  and `inbox/users.json` (ids, channel and user names) stay readable. `crypt.py open . KEYFILE` opens them with the
  private key (not on GitHub). The old history with readable messages was removed (11.11).

## On the server PC instead of GitHub Actions (Karol 14.11)

`local/run_bridge.py` does what the workflow does, all the time (every 60 s), in a clone of this repository on the
game server's PC: `git pull` -> `bridge.py` -> `crypt.py seal` -> commit + push when something changed. The repository
stays the mailbox: Claude still reads `vault/` and writes `outbox/`; **no workflow run is needed before reading or
after writing any more** (pull, and wait about a minute after a push). The workflow stays for a manual run when
that PC is off; don't run it while the PC's loop is up (both would post the same outbox file).

Setup there (once): Git, Python 3, `py -3 -m pip install cryptography`; clone into `C:\tldserver\tldcoop-discord`;
the bot's token in `C:\tldserver\discord_bot_token.txt` (never in git); the first push asks for the GitHub sign-in.
The game server's launcher (`server_bot.py`, polar-link-server) starts `local/run_bridge.py` by itself and restarts
it; by hand: `py -3 local\run_bridge.py`. Logs: `local/run_bridge.log`, `C:\tldserver\discord_bridge.log`.

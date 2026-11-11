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

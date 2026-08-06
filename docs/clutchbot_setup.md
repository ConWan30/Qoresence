# ClutchBot — Twitch Agent Setup

ClutchBot is a local, game-state-aware Twitch agent that consumes Qoresence
events and acts on Twitch: chat narration, auto-clips, channel-point
predictions, chat commands, follow/sub/redemption alerts, and a viewer panel.

## 1. Create a Twitch application

1. Go to https://dev.twitch.tv/console.
2. Click **Register Your Application**.
3. Set **OAuth Redirect URLs** to `http://localhost:3000` (or your own).
4. Choose **Category** "Application Integration".
5. Save the **Client ID** and generate a **Client Secret**.

## 2. Get tokens

The simplest path for local development is the
[Twitch Token Generator](https://twitchtokengenerator.com/) or the official
OAuth flow. ClutchBot needs one or two tokens:

- **IRC token** — any user access token works for IRC. This is the bot account.
- **Helix token** — by default ClutchBot falls back to the IRC token. For clips,
  predictions, and EventSub alerts the token must belong to the broadcaster or
  an account with the required permissions (editor / moderator).

### Scopes

| Feature | Scope | Notes |
|---------|-------|-------|
| Chat | `chat:read`, `chat:edit` | Bot account |
| Clips | `clips:edit` | Broadcaster or editor |
| Predictions | `channel:manage:predictions` | Broadcaster |
| Follow alerts (EventSub) | `moderator:read:followers` | Bot must be a moderator |
| Sub alerts (EventSub) | `channel:read:subscriptions` | Broadcaster |
| Redemption alerts (EventSub) | `channel:read:redemptions` | Broadcaster |

## 3. Create a dedicated bot account

- Make a new Twitch account for the bot.
- Make the bot a **moderator** in the broadcaster's channel. This increases IRC
  rate limits and allows it to subscribe to follow EventSub events.

## 4. Configure Qoresence

### CLI

```bash
python -m qoresence.cli \
  --clutchbot \
  --clutchbot-channel mychannel \
  --clutchbot-username clutchbot_qoresence \
  --clutchbot-token-file /path/to/bot_oauth.txt \
  --clutchbot-client-id <client_id> \
  --clutchbot-broadcaster-username mychannel \
  --clutchbot-enable-clips \
  --clutchbot-enable-predictions \
  --clutchbot-enable-follow-alerts \
  --clutchbot-enable-sub-alerts \
  --clutchbot-enable-redemption-alerts
```

### Integration test

```bash
python scripts/integration_test.py \
  --clutchbot \
  --clutchbot-channel mychannel \
  ...
```

## 5. Tokens file

Create a plain text file with the OAuth token (with or without the `oauth:`
prefix):

```
oauth:abcdefghijklmnopqrstuvwxyz
```

Pass it with `--clutchbot-token-file`. For separate Helix token:

```
--clutchbot-helix-token-file /path/to/broadcaster_oauth.txt
```

## 6. Run

Start Qoresence. When the agent joins IRC and Helix is ready, ClutchBot will
post a greeting and begin watching for game events.

## 7. Viewer panel

Two panels are provided:

- `tools/obs/presence_overlay.html` — OBS Browser Source overlay.
- `tools/twitch-extension/panel.html` — Twitch Extension / Browser Source panel.

For a real Twitch Extension the local `ws://` endpoint must be served over
`https/wss` (e.g., ngrok or Cloudflare tunnel) and registered at
https://dev.twitch.tv/console.

## 8. Chat commands

Viewers can type:

- `!state` — current game situation
- `!score` — current score
- `!lastclip` — URL of the last clutch clip
- `!help` — command list

## 9. Troubleshooting

| Symptom | Fix |
|---------|-----|
| Bot never joins chat | Check token and that the bot name matches the token's user. Verify `chat:edit` scope. |
| Clips fail | Confirm the channel is live and the Helix token has `clips:edit`. |
| Predictions fail | Use the broadcaster's token with `channel:manage:predictions`. |
| EventSub never fires | Bot must be moderator for `channel.follow`; broadcaster token is needed for subs/redemptions. |
| `broadcaster_id` missing | Provide `--clutchbot-broadcaster-id` or `--clutchbot-broadcaster-username`. |

## 10. Security

- Never commit tokens, secrets, or token files.
- Keep token files outside the repo and restrict permissions.
- Client secrets are optional for the current feature set but required if you
  add token refresh.

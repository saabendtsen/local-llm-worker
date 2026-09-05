# Agentic chatbot

Open WebUI provides a conversational, phone-friendly surface over the same independent
`llama-server` runtime used by the worker harness. It adds chat history and optional agentic web
search; it does not give the model terminal, filesystem, or delegation tools.

## Installed layout

| Component | Location |
| --- | --- |
| Open WebUI Desktop | `%LOCALAPPDATA%\Programs\open-webui\open-webui.exe` |
| Managed Python and packages | `D:\OpenWebUI\python` |
| Persistent Open WebUI data | `D:\OpenWebUI\data` |
| Package cache and temporary files | `D:\OpenWebUI\uv-cache`, `D:\OpenWebUI\tmp` |
| llama.cpp API | `http://127.0.0.1:8000/v1` (`local-worker`) |
| Open WebUI | `http://127.0.0.1:8080` |
| Private phone URL | `https://desktop-tmepd7d.tail9fe35c.ts.net/` |

The Desktop configuration keeps its bundled llama.cpp and Open Terminal features disabled. Both
HTTP services bind to loopback. Tailscale Serve proxies only Open WebUI, never the unauthenticated
llama.cpp API.

## Start and check

For a new workstation, reproduce the installed Desktop configuration and private route first:

```cmd
scripts\setup-chatbot.cmd
```

This pins Open WebUI Desktop 0.0.20, moves its heavyweight runtime/data/cache to `D:\OpenWebUI`,
disables the bundled llama.cpp server and Open Terminal, keeps port 8080 on loopback, and creates
the Tailscale Serve route. Open WebUI completes its managed backend installation on first launch.
The script preserves unrelated Desktop preferences when updating its JSON configuration.

For ordinary use after setup:

```cmd
scripts\start-chatbot.cmd
scripts\check-chatbot.cmd
```

The start script starts the existing model runtime when needed and launches Open WebUI Desktop.
The check script exits non-zero unless the `local-worker` model is available, both services are
healthy and loopback-only, and an exact Tailscale HTTPS route proxies to the UI without routing
the llama.cpp API.

Inspect or disable phone access:

```cmd
tailscale serve status
tailscale serve --https=443 off
```

## First-time Open WebUI setup

1. Create the first local account. It becomes the administrator; keep Open WebUI authentication
   enabled even though Tailscale also restricts network access.
2. Open **Admin Settings > Connections > OpenAI-compatible** and add:
   - URL: `http://127.0.0.1:8000/v1`
   - API key: blank or `none`
   - Provider: `llama.cpp`
   - Model: `local-worker` (normally discovered through `/v1/models`)
3. Open **Admin Settings > Web Search**, enable the feature, and choose **DDGS** with its `Auto`
   backend. It needs no key or separate service.
4. Edit the `local-worker` model: enable the **Web Search** capability and keep function calling
   on **Native**. Leave Web Search out of **Default Features** so new chats start offline.
5. Leave Open Terminal, code interpreter, and filesystem integrations disabled for this chatbot
   experiment.

## Acceptance check

Use a fresh chat for each state:

1. **Search off:** ask a timeless question and confirm no `search_web` or `fetch_url` call appears.
2. **Search on:** enable the prompt-bar Web Search toggle, ask for today's llama.cpp release, and
   require a source link. Confirm the model searches and fetches the release page.
3. **Search off again:** disable the toggle, ask a current-events question, and confirm no web tool
   is made available to the model.

On a phone connected to the same tailnet, open the private HTTPS URL. On iPhone use Safari's
**Share > Add to Home Screen**; on Android use the browser's **Install app** action.

## Operational notes

- Phone access requires the Windows PC, Tailscale, Open WebUI, and `llama-server` to be running.
- DDGS is the minimal zero-key trial provider. If it proves unreliable, add a self-hosted SearXNG
  service as a separate follow-up rather than adding a paid search API.
- The model holds substantial RAM and VRAM while loaded. Start it explicitly rather than turning
  this experiment into an always-on workstation dependency.
- C: was full during installation, so heavyweight runtime and mutable data intentionally live on
  D:. Do not reset the Desktop install/data paths to their AppData defaults.

See [chatbot-ui-options.md](chatbot-ui-options.md) for the initial alternatives research. The
implemented design uses its documented native fallback because that preserves loopback-only access
between both Windows processes and avoids Docker bridge ambiguity.

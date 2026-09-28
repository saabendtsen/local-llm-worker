# Phone-friendly chatbot UI for `local-worker`

Research date: 2026-09-05. This records the initial options analysis, not the final runbook.

## Implementation decision

The trial ultimately uses **Open WebUI Desktop with its native managed backend**, not Docker.
The Docker-to-loopback caveat below was material on this Windows host, while rebinding the
unauthenticated llama.cpp API would weaken the intended boundary. The Desktop fallback keeps both
services on `127.0.0.1`, puts heavyweight data on `D:\OpenWebUI`, and exposes only the UI through
Tailscale Serve. See [agentic-chatbot.md](agentic-chatbot.md) for authoritative setup and operation.

## Initial recommendation

Use **Open WebUI in one Docker container**, connect it to the existing llama.cpp endpoint, and
publish only the UI to the phone through **Tailscale Serve**. Start with Open WebUI's built-in
**DDGS** search provider: it needs no account, API key, or additional container. This is the
smallest zero-incremental-cost setup that meets all four requirements:

- ordinary conversational use of the existing `local-worker` model;
- native multi-step tool use when the model chooses to search or fetch a page;
- a user-controlled Web Search switch in each chat; and
- an installable phone PWA over a private HTTPS URL.

Open WebUI officially supports llama.cpp's OpenAI-compatible API. When Open WebUI runs in Docker,
its documented host URL form is `http://host.docker.internal:8000/v1`; a native Open WebUI process
would instead use `http://127.0.0.1:8000/v1`. The connection is configured in the browser under
Settings > Admin > Connections > OpenAI, with the API key blank or `none` and Provider optionally
set to `llama.cpp`.[^owui-llama]

## Minimal trial shape

These are proposed steps, not commands that were run.

1. Start the existing worker with `scripts\start-worker.cmd`.
2. Start Open WebUI using the official non-GPU image and a persistent volume. Bind the published
   port to loopback so the UI is not exposed directly on every LAN interface:

   ```cmd
   docker run -d -p 127.0.0.1:3000:8080 -v open-webui:/app/backend/data --name open-webui --restart unless-stopped ghcr.io/open-webui/open-webui:main
   ```

   Open WebUI's official quick start uses the same image, container port, and persistent data
   volume; the explicit `127.0.0.1` host bind is the local-access restriction for this design.[^owui-quick]

3. Open `http://localhost:3000`, create the first account, and add the llama.cpp connection:
   `http://host.docker.internal:8000/v1`, no real API key, model `local-worker`.
4. In Admin > Web Search, enable Web Search and choose **DDGS**, initially with its `Auto`
   backend. DDGS ships inside Open WebUI and requires neither a key nor a separate service.[^ddgs]
5. In the `local-worker` model settings, enable the Web Search capability and keep Function
   Calling set to `Native`. Do **not** make Web Search a default feature initially. The user can
   then turn it on only when wanted using the prompt-bar feature toggle.[^agentic-search]
6. Expose the UI, not the unauthenticated llama.cpp API, through Tailscale Serve:

   ```cmd
   tailscale serve --bg 3000
   ```

   Tailscale Serve reverse-proxies a localhost web service to a tailnet-only HTTPS URL, to which
   tailnet access rules still apply.[^tailscale-serve] Open that URL from the phone, then install
   the PWA: Safari > Share > Add to Home Screen on iPhone/iPad, or Chrome > Install/Add to Home
   Screen on Android.[^owui-pwa]

Keep Open WebUI's own authentication enabled for this first trial. Tailscale trusted-header SSO
is available later, but it adds configuration and requires preventing any route that bypasses the
trusted proxy.[^owui-tailscale]

## What “enable and disable web search” means

There are three gates in current Open WebUI: the administrator enables the feature globally, the
model is granted the Web Search capability, and the user enables it for the chat in the input
bar. If the chat toggle is off, `search_web` and `fetch_url` are not injected into the model's
tool set. Even if an administrator makes search on by default for new chats, a user can turn it
off per chat.[^owui-tools]

With Native function calling, this is genuinely agentic search rather than a single forced lookup:
the model may search, inspect snippets, fetch full pages, refine the query, and repeat. This relies
on the model emitting correct OpenAI-format tool calls and deciding when another step is useful.[^agentic-search]

## Important caveats

### Verify Docker-to-worker connectivity before changing the worker

The current worker binds to `127.0.0.1:8000`. Open WebUI documents
`host.docker.internal` for reaching a host-side llama.cpp server from Docker, but a loopback-only
Windows listener may not be reachable through that bridge in every Docker Desktop/networking
configuration. Test the connection first.

If it fails, the safest low-effort fallback is to run Open WebUI natively with Python 3.11 so both
processes use `127.0.0.1`. Do not expose llama.cpp on `0.0.0.0` merely to fix container routing:
this worker has no meaningful API authentication, and the phone never needs direct access to it.
If rebinding is eventually chosen, restrict port 8000 with Windows Firewall to only the necessary
local/container path.

### “Agentic” quality is still model-dependent

The UI supplies the loop and tools; it cannot make a checkpoint reliably use them. Open WebUI's
troubleshooting guide notes that weaker local models may ignore the search tool, produce malformed
calls, or fail multi-step chains.[^owui-search-troubleshooting] This repository has already observed
well-formed tool calls from this Qwen model in the Pi harness, so the combination is promising,
but Open WebUI's exact tool schema and loop still need a small acceptance test. Start with:

- search disabled: ask a timeless question and confirm there are no search calls;
- search enabled: ask for today's llama.cpp release and require it to fetch the release page;
- search disabled again: ask a current-events question and confirm it says it cannot verify live.

### Free built-in search trades setup ease for reliability

DDGS scrapes public search pages and the official documentation warns that providers may return
empty results or begin refusing automated requests. `Auto` distributes requests among backends and
is the recommended first setting.[^ddgs] If this proves unreliable, the next zero-cost step is a
self-hosted SearXNG container; Open WebUI supports it directly, but it is additional service and
configuration overhead.[^searxng]

### Remote availability follows the PC and worker

The phone UI can load only while the Windows PC, Open WebUI, Tailscale, and `llama-server` are
running. The current worker consumes substantial RAM/VRAM while loaded, so this is best treated as
an explicitly started personal service, not an always-on dependency.

## One credible alternative: LibreChat

LibreChat can connect to an OpenAI-compatible custom endpoint and offers a Web Search button for
the current conversation.[^librechat-endpoint][^librechat-search] It is a good option if its broader
agent/MCP environment is the experiment itself.

It is not the easiest option here. A custom endpoint requires `librechat.yaml`, an `.env` file,
and a Docker Compose override; the standard Docker deployment also brings multiple supporting
services.[^librechat-endpoint][^librechat-docker] Its documentation covers mobile navigation and
cross-device resumable streams, but unlike Open WebUI it does not currently provide a clear
first-party phone-PWA installation path.[^librechat-mobile] For a single existing llama.cpp model,
that is extra machinery without a compensating benefit.

| Requirement | Open WebUI | LibreChat |
| --- | --- | --- |
| Existing OpenAI-compatible endpoint | Add in admin UI | YAML + environment + Compose mount |
| Per-chat web-search control | Explicitly documented | Explicitly documented |
| Zero-key search trial | Built-in DDGS | Keyless Keenable, or self-hosted SearXNG |
| Phone experience | Documented installable PWA | Documented responsive browser UI |
| Setup footprint | One UI container | Multi-service Compose stack |

## Sources

[^owui-llama]: [Open WebUI: connect llama.cpp](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-llama-cpp/)
[^owui-quick]: [Open WebUI: Docker quick start](https://docs.openwebui.com/getting-started/quick-start/)
[^ddgs]: [Open WebUI: DDGS provider](https://docs.openwebui.com/features/chat-conversations/web-search/providers/ddgs/)
[^agentic-search]: [Open WebUI: agentic search and URL fetching](https://docs.openwebui.com/features/chat-conversations/web-search/agentic-search/)
[^owui-tools]: [Open WebUI: native tools and per-chat feature toggles](https://docs.openwebui.com/features/extensibility/plugin/tools/)
[^owui-search-troubleshooting]: [Open WebUI: web-search troubleshooting](https://docs.openwebui.com/troubleshooting/web-search/)
[^owui-pwa]: [Open WebUI as an app (PWA)](https://docs.openwebui.com/getting-started/open-webui-as-app/)
[^owui-tailscale]: [Open WebUI: Tailscale integration](https://docs.openwebui.com/tutorials/auth-sso/tailscale/)
[^tailscale-serve]: [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)
[^searxng]: [Open WebUI: SearXNG provider](https://docs.openwebui.com/features/chat-conversations/web-search/providers/searxng/)
[^librechat-endpoint]: [LibreChat: custom OpenAI-compatible endpoints](https://www.librechat.ai/docs/quick_start/custom_endpoints)
[^librechat-search]: [LibreChat: Web Search](https://www.librechat.ai/docs/features/web_search)
[^librechat-docker]: [LibreChat: Docker installation](https://www.librechat.ai/docs/local/docker)
[^librechat-mobile]: [LibreChat: navigation](https://www.librechat.ai/docs/features/navigation) and [resumable streams](https://www.librechat.ai/docs/features/resumable_streams)

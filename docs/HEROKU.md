# Heroku deployment plan

The repository includes a Gunicorn WSGI entry point, a `Procfile`, pinned server
dependency and `.python-version`. The browser, API and small bundled dataset
run together in one Heroku app. SQLite stores record edits and CSV additions locally; no separate frontend host
is required. Durable hosted writes need persistent storage as described below.

## 1. Remove the local Cloudflare connector

On the Mac where the service was installed, run these in your own terminal:

```sh
sudo /opt/homebrew/bin/cloudflared service uninstall
brew uninstall cloudflared
```

The first command needs your Mac administrator password. Only uninstall the
Homebrew package after the service has been removed. If a separate foreground
tunnel is running in a terminal, stop it with Ctrl+C as well.

In Cloudflare, remove the `211.24.49.0/24` CIDR route created for this project,
then delete the `space-ai-workshop` tunnel if nothing else uses it. These are
account-side objects and are not deleted by uninstalling the local connector.

## 2. Deploy the excerpt-based app first

Commit the deployment files before pushing. With the Heroku CLI authenticated:

```sh
heroku login
heroku create YOUR-UNIQUE-APP-NAME
git push heroku main
heroku ps:scale web=1
heroku open
```

Replace the placeholder with an available name. For an existing Heroku app,
use `heroku git:remote -a YOUR-EXISTING-APP` instead of `heroku create`.
Choose a web dyno plan appropriate to the app; charges depend on your account
and plan. No Heroku resources are created by adding these files locally.

Heroku detects Python from `requirements.txt`, installs Gunicorn, selects
Python 3.14 from `.python-version`, and runs the `web` process bound to `$PORT`.
The entry point is `backend.webapp:application`. `python3 -m backend.server` remains available
as the dependency-free local development server.

Verify after deployment:

- `/api/health` reports `ok` and 103 records for the bundled dataset.
- The assistant answers `What do the flood observations in Klang show?` with
  source `FLOOD-001` and the synthetic 142 ha value.
- Data Explorer shows application groups with counts; search and filters update
  both records and map markers. CSV/JSON/GeoJSON downloads reflect current data.
- With a disposable teaching CSV, verify the upload summary shows updated/added
  counts, new IDs appear in the correct group, and downloads include them.
  An invalid row should reject the whole upload without saving other rows.
- Response JSON downloads still include the retrieved sources.

Inspect errors using `heroku logs --tail`. Bundled sample files change through
deployment; Data Explorer edits and CSV additions are stored separately in a local SQLite file
under `SPACELAB_DATA_DIR` (default `data/database`). They are immediately shared by workers
on the same filesystem. Heroku dyno filesystems are temporary and separate:
these edits and imported additions do not survive dyno replacement and are not shared across dynos.
Use persistent storage before relying on durable edits or CSV imports in a hosted deployment.

CSV uploads use `POST /api/records/import` with `text/csv`, limited to 2 MB and
2,000 rows. The backend validates all rows, then commits updates and additions
by ID in one SQLite transaction. Importing a CSV does not change the deployed
sample files. Backing up CSV/JSON exports captures the merged dataset; the
SQLite file retains the saved overrides and additions.

## 3. Connect hosted Qwen separately

**Heroku cannot reach your laptop's Ollama through `127.0.0.1`.** The current
configuration is not a plan to install Ollama or run model weights in the web
dyno. Keep **Offline · retrieved excerpts** selected until an externally reachable
model endpoint has been configured.

The existing adapter accepts an **Ollama-compatible `/api/chat` service**:

| Config variable | Meaning |
| --- | --- |
| `OLLAMA_URL` | HTTPS base URL of your hosted Ollama-compatible service, without `/api/chat` |
| `OLLAMA_MODEL` | A Qwen model identifier actually served by that endpoint |
| `OLLAMA_API_KEY` | Optional Bearer token if required by that service; store as a Heroku config var |
| `OLLAMA_WEB_SEARCH_API_KEY` | Optional dedicated Ollama Cloud web-search key; existing Ollama Cloud model credentials can also be used |
| `OLLAMA_TIMEOUT_SECONDS` | Socket timeout; defaults to 20 on Heroku and 60 locally |

Set credentials through Heroku Settings → Config Vars. Do not commit them or
put them in browser code. Authenticated model requests require HTTPS. A provider
that exposes only an OpenAI-compatible API needs a separate adapter; changing
the URL alone will not work.

The model call is synchronous. Heroku has an initial 30-second router timeout,
so the hosted model should reliably return within that window. The 20-second
setting is a socket timeout, not a strict total execution deadline; a slow or
trickling service can still exceed the router limit. For slower generation,
plan a background-job/polling or streaming implementation before enabling it.
Model errors and citation failures fall back to labelled excerpts when the
request completes within the router deadline.

## Local production-server smoke check

Use Python 3.14 for parity with Heroku:

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/gunicorn backend.webapp:application --bind 127.0.0.1:8081 --workers 2 --threads 4
```

Visit http://127.0.0.1:8081 and test the assistant, grouped Data Explorer with CSV import, and Architecture views. Stop with Ctrl+C.

References: [Heroku Python versions](https://devcenter.heroku.com/articles/python-runtimes),
[Heroku request timeouts](https://devcenter.heroku.com/articles/request-timeout),
[Cloudflare macOS service management](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/as-a-service/macos/).

# SpaceLab · Space-tech RAG starter

A local geospatial intelligence app for exploring space-tech data with
retrieval-augmented generation. It includes a searchable synthetic knowledge
base, source inspection, response downloads and optional local Qwen generation.

For hosting, follow the [Heroku deployment plan](docs/HEROKU.md). The app includes
a Gunicorn production entry point; local Ollama must be replaced with a hosted
Ollama-compatible endpoint when running on Heroku.

## Start

Requires Python **3.9 or newer**. The offline excerpt mode needs no additional
Python packages, API key, model download, internet connection or Node installation.

```sh
python3 -m backend.server
```

Open **http://127.0.0.1:8080**. Keep the terminal running; press Ctrl+C to stop.
The assistant initially selects **AI Ollama**. Choose **Offline · retrieved
excerpts** to use retrieval without a model connection. Press Enter to submit
a question or Shift+Enter for a new line; the Find insights button also submits.
On Windows, use `py -3 -m backend.server` if `python3` is unavailable.
For a different port, run `python3 -m backend.server --port 8081`.

To share the app on a trusted local network:

```sh
python3 -m backend.server --host 0.0.0.0 --port 8080
```

Other devices visit `http://<server-LAN-IP>:8080`. Check firewall and network
client-isolation settings. The default binds to loopback only. This development
server has no authentication and is not intended for public internet hosting.

## Features

- **Intelligence assistant:** natural-language questions, topic filters, automatic
  evidence selection and answer style, with inspectable source IDs, values, dates
  and limits.
- **Data explorer:** browse collapsible application groups, search and edit records,
  import CSV updates or new observations, inspect location markers on a
  Malaysia outline map, and download the current corpus as CSV, JSON or GeoJSON.
- **Response export:** download an answer and its retrieved sources as JSON.
- **Architecture:** view the system architecture and request process flow, with
  downloadable SVG diagrams covering deployment, retrieval and model fallback,
  plus a plain-language diagram and BM25 learning links.
- **Optional web context:** a Web search switch beside the prompt adds external
  search excerpts to the model context, with clickable web references.
- **Optional Qwen:** generate cited answers from retrieved records through Ollama.

Numeric ranking questions (for example, “top 5 worst flood in Malaysia”) sort
all matching records by their metric before selecting the requested results.
Flood rankings use inundated area, not overall severity. “List all flood
observations” returns every matching record. These results are computed in
Python, including when AI Ollama is selected. Other questions send all matching
retrieved evidence to the model; there is no fixed source-count cap.

## Optional web search

The **Web search** switch above the prompt is off by default. Off uses only the
existing dataset. On selects **AI Ollama**, searches the question using
[Ollama’s web-search API](https://docs.ollama.com/capabilities/web-search), and
supplies up to five external search excerpts to the model alongside dataset
records. Choosing Offline turns the switch off. The API also accepts a boolean
`web_search` field, defaulting to false.

If `OLLAMA_URL=https://ollama.com` and `OLLAMA_API_KEY` are already configured,
web search uses that Ollama Cloud key. With a local model or another hosted
provider, set **`OLLAMA_WEB_SEARCH_API_KEY`** to an Ollama account API key on the
server. A dedicated search key takes precedence; model keys for other providers
are never sent to the search service. Keys stay on the server.

When enabled, the question is sent to Ollama’s hosted search service. Search adds
network latency and is subject to the account’s search availability and limits.
The adapter uses returned excerpts, not complete articles; retrieval timestamps
are not publication dates. The References section separates synthetic dataset
records from external links and excerpts. Response downloads include both source
sets and search status. Web evidence does not validate invented measurements.

Dataset rankings/listings remain computed in Python. The model can add external
context below those results. Search errors or no results are explicitly labelled;
model errors or invalid web citations fall back to labelled source excerpts.
Web search has an eight-second socket timeout. On Heroku the combined search and
model path allocates the remaining part of a 25-second request budget to the
model; socket timeouts do not guarantee a strict wall-clock deadline.

## Edit observations

In Data Explorer, expand a record and select **Edit record**. Change its title,
location, state, coordinates, dates, sensor, metric value, optical cloud cover or
limitations, then select **Save changes** or **Cancel**. Observation summaries
and quality labels update automatically from the saved measurements and dates.
Citation IDs, applications, metric units and synthetic provenance remain stable.

Saved edits are shared by users of this app and take effect in new answers,
rankings, map markers and all download formats without restarting. Previously
shown answers are cleared after a save. Stale edits return a conflict instead of
overwriting newer changes; cancel and reopen the editor to refresh the record.

Edits are stored in `data/database/record-edits.sqlite3`, separate from the generated
sample files. Set `SPACELAB_DATA_DIR` to choose another storage directory.
Back up that directory to preserve edits. Regenerating the sample files preserves
saved overrides and CSV-added records. Heroku's local filesystem is temporary; durable hosted editing
requires persistent storage before relying on saves across dyno replacements.

## Import observations from CSV

In Data Explorer, expand **Upload CSV**, choose a file, then select **Upload and
save**. Download the current CSV as a template. Upload only the rows you want to
change: matching `id` values update existing records, new IDs add observations,
and omitted records stay unchanged. An import is atomic: an invalid row rejects
the entire file with a row number. Duplicate IDs within a file are rejected.

For existing records, `id` and the editable columns being changed are enough
(for example, `id,value`). For new records, include `id`, `theme`, `synthetic`
and every editable column: `title`, `location`, `state`, `latitude`, `longitude`,
`observation_date`, `baseline_date`, `sensor`, `value`, `cloud_cover_pct`, and
`limitations`. Blank baseline dates apply to flood and vegetation; land-use and
coastal observations require an earlier baseline date. Use UTF-8 CSV with a
header, up to 2 MB and 2,000 rows per upload.

IDs use `FLOOD-029`, `VEGETATION-029`, `LANDUSE-029` or `COASTAL-029` format
(uppercase prefix and three digits). Application, metric and units must match
the supported schema. This app accepts synthetic teaching data only; include
`synthetic=True` for new observations. Description and quality are recalculated;
existing provenance is retained and new observations are labelled user-uploaded
synthetic data. Uploaded description, quality and provenance columns are ignored.

Imported records share the existing SQLite store and immediately appear in maps,
answers, rankings, editing and downloads. Matching IDs overwrite current values
for the supplied editable columns. Individual record edits still detect stale
versions. The same Heroku persistence limitations described above apply to imports.

## Optional local Qwen

Install [Ollama](https://ollama.com/download), then download the model:

```sh
ollama pull qwen3:4b
ollama serve
```

If the Ollama desktop service is already running, skip `ollama serve`. Select
**Qwen · Ollama** in the app. Local inference needs no API key. When the
app is shared, generation runs on the server machine.

The backend uses [Ollama's chat endpoint](https://docs.ollama.com/api/chat).
Configure the model or endpoint when starting the server:

```sh
OLLAMA_MODEL=qwen3:4b OLLAMA_URL=http://127.0.0.1:11434 python3 -m backend.server
```

The adapter expects Ollama's API format. Changing the endpoint alone does not
add support for another provider's authentication or API schema. A different
Ollama model may require adjustments to the `think` option and prompt in `rag_server/rag.py`.

Allow sufficient memory for your selected model. The model socket timeout is 60
seconds locally and 20 seconds on Heroku. Requests fall back to labelled excerpts if the model is unavailable or its
citations fail validation. Concurrent generation can overload one model host.

**Offline mode is lexical retrieval with deterministic excerpts, not an LLM.**
It remains available without Ollama or internet access.

## Architecture

```text
Browser question + retrieval settings
          ↓ POST /api/ask
Python retrieval service (BM25 + place/topic constraints)
          ↓
Bundled JSON + SQLite edits / CSV additions → reference records
          ↓
Excerpt composer OR local Qwen via Ollama
          ↓
Answer + inspectable source cards → JSON response export
```

Data Explorer groups observations into collapsible application sections with
counts. Search and application filters narrow both groups and map markers;
matching groups open automatically when searching or filtering.

The shared data path is:

```text
Record editor → POST /api/records/{id} → validate + stale-version check
CSV upload    → POST /api/records/import → validate all rows + atomic upsert
                                      ↓
                   SQLite edits and added observations
                                      ↓
          Merge with bundled JSON on each data-reading request
                                      ↓
              Questions · rankings · Explorer · downloads
```

| Route | Purpose |
| --- | --- |
| `GET /api/records` | Current merged observations, including imported additions |
| `POST /api/records/{id}` | Save editable fields with the original record for conflict detection |
| `POST /api/records/import` | UTF-8 `text/csv`; returns `added`, `updated` and current `records` |
| `GET /sample-data/observations.{csv,json,geojson}` | Export current merged data; CSV also provides the import template |

The upload transaction locks writes while reading the current dataset,
validating rows and saving the batch. Imports overwrite supplied editable
fields for matching IDs; omitted columns and records are preserved. Failed
validation rolls back the batch. Imports and edits share one SQLite table.
Only the importing browser refreshes automatically; other open browsers must
reload to display the latest records.

The Architecture page lists the component folders and their responsibilities:
`frontend/` for the browser, `backend/` for the API gateway, `rag_server/` for
retrieval and AI context, `data/` for datasets, CSV validation and SQLite storage, `docs/` for diagrams
and guides, and `tests/` for shared verification. The backend serves the frontend
and calls the RAG engine in the same Python process.

Retrieval runs before generation. No model training or vector database is
required. BM25 scores indicate lexical relevance, not factual confidence.

## Reuse for another space-tech project

The separate [sample-data folder](data/sample-data/README.md) contains 103 invented
observations across 28 locations across all 13 Malaysian states and three federal territories and four themes. These are example
inputs, not real satellite measurements or imagery.

1. Use `data/sample-data/observations.json` and its data dictionary as the record
   schema. The server reads the dataset, saved edits and CSV additions for each request.
2. Edit `data/generate_data.py` and regenerate JSON, CSV and GeoJSON together:

   ```sh
   python3 data/generate_data.py
   ```

3. Adapt `SYSTEM_PROMPT`, topic aliases and `THEME_TOKENS` in `rag_server/rag.py` to your
   domain. Keep the citation and insufficient-evidence rules.
4. Update validation in `backend/webapp.py` and the topic dropdowns in `frontend/index.html`
   when introducing new themes. Update example questions, dataset statistics,
   labels and coordinate-plot bounds in `frontend/index.html` and `frontend/app.js` for a
   different region or corpus.
5. Update practice queries and tests to match the new corpus and expected sources.

The starter currently accepts **synthetic records only**. For actual observations,
deliberately update validation, provenance handling, prompts, answer disclaimers
and export metadata; replacing files alone does not support real-data ingestion.
Current citation validation expects IDs such as `FLOOD-001` (uppercase letters,
hyphen, three digits). Extend that validation if your IDs use a different format.

## Branding and search metadata

SpaceLab uses the supplied ADL Space Academy black and blue logos, stored locally in
`frontend/assets/`. See the [asset sources](frontend/assets/README.md).
The sidebar links to the academy while retaining the SpaceLab application name.

The public URL is **https://spacelab.adlspace.academy/**. The HTML head includes
an app-specific title and description, canonical URL, Open Graph and Twitter
sharing tags, and WebApplication JSON-LD naming ADL Space Academy as publisher.
`frontend/site.webmanifest` provides the app name, icon and navy theme.
`frontend/robots.txt` points to `frontend/sitemap.xml`; the sitemap lists the
homepage because application views use URL fragments. API and dataset download
paths are excluded from crawling. Robots rules are crawler guidance, not access
controls.

When changing the public domain, update the canonical URL, social image URLs and
JSON-LD in `frontend/index.html`, plus the domain in `robots.txt` and `sitemap.xml`.
The backend explicitly serves these assets through its static-file allowlist.

## Checks

```sh
python3 -m unittest discover -s tests -v
node --check frontend/app.js
```

The Python suite covers retrieval constraints, comparisons, missing evidence,
live-data abstention, model failure/citation handling, data consistency and HTTP
input validation. Node is needed only for the JavaScript syntax check. Model
responses are mocked; the automated suite does not require live Qwen inference.

## Shared conversation history

The assistant saves each completed question and answer automatically, including
the original dataset/web references, engine settings and timestamps. A session
contains many question/answer conversations. **Shared history** lists saved sessions
for everyone; select one to read its transcript and download individual responses.
Assistant help and explanatory notes appear in information tooltips on hover,
keyboard focus or tap; press Escape or click elsewhere to dismiss them.
Saved transcripts open for browsing; **Continue this session** resumes a saved
conversation with its recent context. Conversations appear newest first beneath
the prompt composer. **New chat** starts a fresh session, as does
refreshing or reopening the page. Empty sessions are never saved. Saving happens
on the server before an answer is returned, so a refresh needs no browser unload
request. An in-flight question may not complete if its request is interrupted.

History is stored in the same SQLite file as record edits, under
`SPACELAB_DATA_DIR` (default `data/database/record-edits.sqlite3`). It survives
local server restarts. Back up this file to retain chat transcripts; dataset
CSV/JSON exports do not include history. Heroku's temporary filesystem does not
preserve history across dyno replacement or share it across dynos; hosted durable
history requires persistent storage.

Follow-up questions use the latest six conversations from the same session, with
each prior answer limited to 2,000 characters in the model prompt. Questions
such as "What are its limitations?" retain the preceding place/application;
"What about Kuching?" changes the place while keeping the application. Explicit
new places, applications and nationwide scope take precedence. Evidence is
retrieved again for every question. Earlier answers provide conversational
background, not verified evidence, and citation checks still apply to current
sources. Offline mode carries place/topic context forward but displays excerpts
rather than generating conversational analysis. Long sessions retain their full
saved transcript even though only recent conversations are sent to the model.

API: `POST /api/ask` returns a `session_id`; send it with subsequent questions
to group them in that session. Omit it to start another session.
`GET /api/history?offset=0` returns up to 30 session summaries and a `next_offset`;
`GET /api/history/<session_id>` returns the complete saved transcript. No login
is needed to browse this shared workshop history.

## Limits

Citation checks establish that source IDs exist, not that a claim follows from
them. Verify generated claims against the retrieved records. Lexical retrieval
may miss paraphrases or return related evidence for an unsupported question.
English and a few Malay topic aliases are supported; this is not multilingual
semantic search. Unknown locations are not geocoded. Numeric rankings cover
matching records in the bundled dataset, not every real-world location.

The sample corpus cannot establish live conditions or predict events. The
map uses bundled Natural Earth outlines with separate scales for Peninsular and
East Malaysia. It provides geographic context, not a spatial-analysis engine.
See [map data attribution](frontend/maps/README.md).

## Project layout

```text
frontend/                  Browser UI, pages, styles, JavaScript and map assets
backend/
  server.py                Dependency-free local development server
  webapp.py                HTTP/API gateway and production WSGI entry point
rag_server/
  rag.py                   Retrieval, prompts, excerpt answers and Ollama adapter
  web_context.py           Web-search evidence and AI context builder
data/
  sample-data/             Datasets, dictionary and practice queries
  generate_data.py         Reproducible synthetic data generator
  record_store.py          SQLite persistence, CSV imports and current-data exports
  database/                Local SQLite database (ignored by Git)
docs/
  diagrams/                Architecture and process-flow SVG documents
  HEROKU.md                Deployment plan
tests/                     Unit and HTTP integration checks
Procfile                   Heroku web process using Gunicorn
requirements.txt           Production server dependency
```

Run commands from the repository root. The Python components are packages;
start the local server with `python3 -m backend.server`. These folders separate
responsibilities within the existing application; the backend still serves the
frontend and calls the RAG engine in the same process. API, diagram and dataset
download URLs remain unchanged. Deployment keeps `docs/diagrams/` available
because the Architecture page serves those SVG documents.


## AI Showdown quiz

The **AI Showdown** section is disabled by default. Sign in through the existing
Admin entry (hold the SpaceLab brand, or press Ctrl/Cmd + Shift + U), then use
**AI Showdown · Quiz control**:

1. **Enable quiz** to show the navigation section to every visitor and open the
   registration lobby. Visitors enter a name and keep that browser open.
2. **Start quiz** to close registration and start all registered players after a
   shared three-second countdown. At least one player must be registered.
3. Each of the PDF's 15 questions lasts **10 seconds** (150 seconds total).
   Clicking an option saves the choice immediately; players can change it until
   the server deadline. At the deadline, the latest saved choice is final and
   the next question appears automatically. Missing answers score zero, including
   questions missed while disconnected or away. Each correct answer earns one
   point; there is no speed bonus. The PDF's “15-minute” heading does not override
   this requested 10-second-per-question schedule.
4. After the final deadline, players automatically see their score and an answer
   review. Admin shows every player's final score, leaderboard and answer review;
   while playing, it shows registration and answered-question counts.
5. **Reset round & all results** deletes all player entries, answers and scores
   after confirmation. It reopens registration if the quiz is enabled. Players
   must register again, and the admin must start the new round.

Disabling hides the section and rejects new answers, but does not pause or reset
an active round. Enabling an existing round restores its current state. Visitors
receive visibility changes through polling, normally within a second. Timers,
registration closure and scores are enforced by the server across browser tabs
and application workers. Only the current question is sent during play; answer
keys and explanations are withheld until the full round ends.

Player names are normalized and unique within a round. A random participant
credential is saved in browser local storage, while only its hash is stored on
the server. Refreshing or reopening the same browser resumes its entry. This is
name-based workshop participation, not verified identity: another browser using
a distinct name can register during the lobby. Clearing browser storage loses
access to that entry until the admin resets the round. Browser storage must be
available before registering.

Questions and explanations were transcribed from
`SpaceLab_AI_Showdown_15_Questions_Answers_3pages.pdf` into the server-only
`data/quiz_questions.json`. Quiz state uses the existing shared SQLite database
under `SPACELAB_DATA_DIR`. The deployment must provide persistent storage and a
single shared database for all workers; as with existing records and sessions,
Heroku's ephemeral filesystem does not retain SQLite data across dyno restarts
and separate dynos do not share it. Use a persistent single-instance deployment
for a live workshop; a multi-dyno deployment needs shared database storage.

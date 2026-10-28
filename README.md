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
python3 server.py
```

Open **http://127.0.0.1:8080**. Keep the terminal running; press Ctrl+C to stop.
The assistant initially selects **AI Ollama**. Choose **Offline · retrieved
excerpts** to use retrieval without a model connection. Press Enter to submit
a question or Shift+Enter for a new line; the Find insights button also submits.
On Windows, use `py -3 server.py` if `python3` is unavailable.
For a different port, run `python3 server.py --port 8081`.

To share the app on a trusted local network:

```sh
python3 server.py --host 0.0.0.0 --port 8080
```

Other devices visit `http://<server-LAN-IP>:8080`. Check firewall and network
client-isolation settings. The default binds to loopback only. This development
server has no authentication and is not intended for public internet hosting.

## Features

- **Intelligence assistant:** natural-language questions, topic filters, source
  count and answer style, with inspectable source IDs, values, dates and limits.
- **Data explorer:** search records, inspect a schematic coordinate plot, and
  download the sample corpus as CSV, JSON or GeoJSON.
- **Response export:** download an answer and its retrieved sources as JSON.
- **Architecture:** view the system architecture and request process flow, with
  downloadable SVG diagrams covering deployment, retrieval and model fallback.
- **Optional Qwen:** generate cited answers from retrieved records through Ollama.

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
OLLAMA_MODEL=qwen3:4b OLLAMA_URL=http://127.0.0.1:11434 python3 server.py
```

The adapter expects Ollama's API format. Changing the endpoint alone does not
add support for another provider's authentication or API schema. A different
Ollama model may require adjustments to the `think` option and prompt in `rag.py`.

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
JSON knowledge base → retrieved reference records
          ↓
Excerpt composer OR local Qwen via Ollama
          ↓
Answer + inspectable source cards → JSON response export
```

Retrieval runs before generation. No model training or vector database is
required. BM25 scores indicate lexical relevance, not factual confidence.

## Reuse for another space-tech project

The separate [sample-data folder](sample-data/README.md) contains 22 invented
observations across six Selangor locations and four themes. These are example
inputs, not real satellite measurements or imagery.

1. Use `sample-data/observations.json` and its data dictionary as the record
   schema. The server loads records at startup; restart it after changing data.
2. Edit `scripts/generate_data.py` and regenerate JSON, CSV and GeoJSON together:

   ```sh
   python3 scripts/generate_data.py
   ```

3. Adapt `SYSTEM_PROMPT`, topic aliases and `THEME_TOKENS` in `rag.py` to your
   domain. Keep the citation and insufficient-evidence rules.
4. Update validation in `webapp.py` and the topic dropdowns in `app/index.html`
   when introducing new themes. Update example questions, dataset statistics,
   labels and coordinate-plot bounds in `app/index.html` and `app/app.js` for a
   different region or corpus.
5. Update practice queries and tests to match the new corpus and expected sources.

The starter currently accepts **synthetic records only**. For actual observations,
deliberately update validation, provenance handling, prompts, answer disclaimers
and export metadata; replacing files alone does not support real-data ingestion.
Current citation validation expects IDs such as `FLOOD-001` (uppercase letters,
hyphen, three digits). Extend that validation if your IDs use a different format.

## Checks

```sh
python3 -m unittest discover -s tests -v
node --check app/app.js
```

The Python suite covers retrieval constraints, comparisons, missing evidence,
live-data abstention, model failure/citation handling, data consistency and HTTP
input validation. Node is needed only for the JavaScript syntax check. Model
responses are mocked; the automated suite does not require live Qwen inference.

## Limits

Citation checks establish that source IDs exist, not that a claim follows from
them. Verify generated claims against the retrieved records. Lexical retrieval
may miss paraphrases or return related evidence for an unsupported question.
English and a few Malay topic aliases are supported; this is not multilingual
semantic search. Unknown locations are not geocoded, and top-k retrieval cannot
establish complete regional rankings.

The sample corpus cannot establish live conditions or predict events. The
coordinate plot is a schematic with fixed bounds for the included Selangor data,
not a geographic basemap or a spatial-analysis engine.

## Project layout

```text
server.py                  Dependency-free local development server
webapp.py                  Shared HTTP routes and production WSGI entry point
Procfile                   Heroku web process using Gunicorn
requirements.txt           Production server dependency
rag.py                     Retrieval, excerpt answers and optional Ollama adapter
app/                       HTML, CSS and browser JavaScript
sample-data/               JSON, CSV, GeoJSON, dictionary and practice queries
scripts/generate_data.py   Reproducible synthetic data generator
tests/                     Python unit and HTTP integration checks
docs/HEROKU.md             Deployment plan and Cloudflare connector removal
```

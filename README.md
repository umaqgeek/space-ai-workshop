# SpaceLab · AI for Space

A small, local geospatial intelligence workshop app for university students and
graduates. Built around **From Space Data to AI: Build a Geospatial Intelligence
Assistant**, the supplied three-hour Selangor Education Summit proposal.

## Start in one command

Requires Python **3.9 or newer**. The default mode needs no Python packages,
API keys, model download, internet connection, or Node installation.

```sh
python3 server.py
```

Open **http://127.0.0.1:8080**. Keep the terminal running; press Ctrl+C to stop.
On Windows, use `py -3 server.py` if `python3` is unavailable.
Run the command from this project folder. A different port is supported:

```sh
python3 server.py --port 8081
```

Participants can each run their own copy. Alternatively, on a trusted workshop
Wi-Fi network, the facilitator can serve one copy:

```sh
python3 server.py --host 0.0.0.0 --port 8080
```

Participants visit `http://<facilitator-LAN-IP>:8080`. Check firewall permissions
and Wi-Fi client isolation with the venue beforehand. The default remains
loopback-only. This is a classroom server with no authentication, not an
internet-facing deployment. Qwen requests run on the facilitator's machine.
Notebook entries stay in each participant's browser until downloaded; sharing
the server does not create a central submissions dashboard.

## What participants can do

- Ask natural-language questions and inspect source IDs, values, dates and limits.
- Explore 22 synthetic records across six Selangor locations and four themes.
- Inspect a schematic coordinate plot and download CSV, JSON or GeoJSON.
- Change topic filters, source count and answer style.
- Compare retrieved excerpts with optional Qwen-generated answers.
- Complete one of three missions and download a verified-source team notebook.
- Record a SkillsBuild next step and workshop feedback.

**Start facilitating with [the segment-by-segment guide](docs/FACILITATOR_GUIDE.md).**
Hand participants [the short participant guide](docs/PARTICIPANT_GUIDE.md).

## Optional: enable real Qwen generation

Install [Ollama](https://ollama.com/download) separately, then download the
[Qwen3 4B model](https://ollama.com/library/qwen3:4b) before the event:

```sh
ollama pull qwen3:4b
ollama serve
```

If Ollama is already running as a desktop service, a second `ollama serve` is
unnecessary. In the app, select **Qwen · local Ollama** and ask a question.
The backend calls [Ollama's `/api/chat` endpoint](https://docs.ollama.com/api/chat),
using a non-streaming response and the retrieved records as context. No
participant-side Ollama installation is needed when sharing one server.

Optional backend settings, applied when starting the Python server:

```sh
OLLAMA_MODEL=qwen3:4b OLLAMA_URL=http://127.0.0.1:11434 python3 server.py
```

The model download is several GB and inference needs suitable memory; rehearse
on the actual laptop. Qwen requests time out after 60 seconds and fall back to
clearly labelled excerpts if unavailable or if source citation checks fail.
Several simultaneous teams can overload one model host; stagger generated
answers and use offline mode for most exercises.

**Offline mode is lexical retrieval plus deterministic excerpts; it is not an
LLM.** It teaches search, grounding, provenance and evaluation. To demonstrate
the complete LLM + RAG pipeline, have Ollama and Qwen running. Actual inference
depends on that optional local service and is not required to start the app.

## Architecture

```text
Browser question + topic + source count
          ↓ POST /api/ask
Python retrieval service (BM25 + explicit place/topic constraints)
          ↓
Prepared synthetic JSON knowledge base
          ↓ retrieved records
Excerpt composer OR local Qwen via Ollama
          ↓
Answer + inspectable source cards → participant verification → JSON evidence
```

Retrieval happens **before** generation. This implements the proposal's LLM,
RAG service and knowledge base components without training or a vector database.
The BM25 scores indicate lexical relevance, **not factual confidence**. Search
supports English and a few explicit Malay topic aliases, not multilingual
semantic understanding. The diagram in the proposal is conceptual; actual
grounding requires that retrieved evidence reach the model before it answers.

## Data and modifications

The separate [sample-data folder](sample-data/README.md) contains the dataset,
data dictionary, and practice queries with expected sources. Values and sensor
descriptions are **invented**, not real satellite products. No satellite imagery,
live feeds or flood forecasts are included. Place names and approximate
coordinates anchor the classroom scenarios.

Regenerate all three data formats deterministically:

```sh
python3 scripts/generate_data.py
```

For the guided content-edit exercise, change the Klang flood value in
`scripts/generate_data.py`, regenerate, restart the server and repeat the query.
The server loads its corpus at startup. Keep JSON, CSV and GeoJSON aligned by
using the generator. No participant upload or shared data mutation is needed.
Edit `SYSTEM_PROMPT` in `rag.py` to experiment with Qwen's instructions, then
restart. Preserve the synthetic-data and citation rules.

## Checks

```sh
python3 -m unittest discover -s tests -v
node --check app/app.js
```

The Python suite covers retrieval constraints, comparisons, missing evidence,
live-data abstention, Qwen failure/citation handling, data consistency and HTTP
input validation. Node is needed only for the JavaScript syntax check.
No live Qwen call is needed in the automated suite.

## Limits and workshop evidence

Qwen citations are checked for existence, not entailment. A cited claim may
still be wrong; participants must compare it against the source. Lexical
retrieval may miss paraphrases or retrieve related material for an unsupported
question. Unknown locations are not automatically geocoded. An answer about
retrieved places does not establish coverage of another place in the question.
Top-k retrieval cannot establish a complete regional ranking. Dates do not
turn fictional observations into live information.

Notebook verification and SkillsBuild progress are self-reported. Feedback is
not centrally collected. Use downloaded team files and a roster to assess the
proposal's engagement, learning, activation and feedback indicators; see the
facilitator guide for denominators and suggested collection steps. No
registration or course-completion claim is automatically verified.

## Project layout

```text
server.py                  HTTP API and static file allowlist
rag.py                     Retrieval, excerpt answers and optional Qwen adapter
app/                       HTML, CSS and browser JavaScript
sample-data/               JSON, CSV, GeoJSON, dictionary and practice queries
scripts/generate_data.py   Reproducible synthetic data generator
docs/                      Facilitator and participant guides
tests/                     Python unit and HTTP integration checks
```

Reference links for continued learning: [IBM SkillsBuild for university
students](https://skillsbuild.org/university/students) and the [university
learning catalog](https://skillsbuild.org/learning-catalog/university-catalog).
Links were checked on 28 October 2026; available courses and sign-up flows may change.

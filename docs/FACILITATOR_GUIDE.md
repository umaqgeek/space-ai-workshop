# AI for Space: three-hour facilitator runbook

Based on the supplied workshop outcomes proposal for **13 November 2026**,
Setia City Convention Centre, Shah Alam. Audience: university students and
graduates. Facilitator: Omar Mukhtar bin Hambaran, AFED Digital.

The PDF is the workshop content reference. This app implements its six learning
outcomes using a deliberately small synthetic knowledge base. It does not
process raw satellite imagery or train a model.

## Before participants arrive

- Rehearse on the actual laptop and projector. Use a modern browser and Python
  3.9+. Start `python3 server.py`, open http://127.0.0.1:8080 and run the first
  three questions from `sample-data/practice-queries.json`.
- For a full LLM demo, install Ollama, download `qwen3:4b`, and test a question
  with **Qwen · local Ollama** before the event. Keep the model loaded. Record
  one successful answer using **Download response** as a labelled replay backup.
- If one machine hosts the class, start with `--host 0.0.0.0`. Test from a second
  laptop on the venue Wi-Fi, verify the facilitator's LAN IP, and check client
  isolation. Prefer local copies when networking is unreliable.
- Share the project and the participant guide ahead of time. Downloading the
  optional model during the workshop is not part of the three-hour plan.
- Prepare a roster of teams and your chosen submission channel. This app does
  not centrally collect files; ask teams to download and submit their evidence.
- Check the SkillsBuild university links. Provide an alternative written next
  step when internet or participant registration access is unavailable.
- Keep this guide and the dataset available offline. All default app assets
  are local, with no CDNs, map tiles, fonts or API-key dependencies.

## 0–20 minutes · AI for space

**Learning outcome 1: identify at least two space/AI applications.**

- **0–5:** Frame the question: “How can a student use satellite-related data
  without building a satellite?” Explain that the records are invented.
- **5–12, demo:** Open **Intelligence assistant**. Ask
  `What do the flood observations in Klang show?` Keep offline mode selected.
  Expand `FLOOD-001`: 142 ha, 2026-10-15. Point out the synthetic label and
  limitation. This is a prepared record, not analysis of a live radar image.
- **12–17:** Open **Data explorer** and show vegetation and land-use themes.
  Connect observation data to environmental monitoring, then AI skills to data
  analyst, geospatial developer, domain specialist and product roles.
- **17–20, participant checkpoint:** Each pair names two applications and one
  limitation. Do not describe possible water area as actual flood severity.

## 20–45 minutes · LLM + RAG essentials

**Learning outcome 2: explain LLM, retrieval service and knowledge base.**

- **20–28, demo:** Use **From question to evidence** on the assistant page.
  Explain: question → retrieval from the JSON knowledge base → excerpts or
  Qwen answer → human verification. No training occurs when records are loaded.
- **28–35, demo:** Ask `Compare vegetation in Hulu Langat and Shah Alam.`
  Expand `VEGETATION-005` and `VEGETATION-002`. The invented NDVI values are
  0.78 and 0.51. Explain that the displayed BM25 score measures text match,
  not truth or confidence.
- **35–40, demo:** Click **Inspect the Qwen system prompt**. If Ollama is ready,
  select Qwen and repeat the query. Identify the engine badge and citations.
  Explain that the LLM turns supplied evidence into prose and can still err.
- **40–45, participant checkpoint:** Ask participants to point to where
  reference facts live, what retrieves them and what writes the generated answer.

**Fallback:** Use excerpt mode, which demonstrates retrieval but is not an LLM.
Show a previously exported Qwen response as a clearly labelled recorded example
if prepared. Do not present a fallback or replay as live Qwen inference.

## 45–75 minutes · Geospatial data

**Learning outcome 3: inspect sample records and searchable reference material.**

- **45–53, demo:** Open **Data explorer**, filter by vegetation and expand Hulu
  Langat. Identify ID, place, latitude/longitude, date, sensor label, NDVI, unit,
  cloud cover, quality and limitation.
- **53–60, demo:** Show the schematic coordinate plot. It has no basemap and
  no flood polygons. Download CSV and GeoJSON; explain that GeoJSON coordinates
  are `[longitude, latitude]`, whereas the UI displays latitude first.
- **60–70, participants:** Find Sepang's land-use record (`LANDUSE-004`), its
  46 ha value and dates 2025-10-15 → 2026-10-15. Find its limited quality label.
  Discuss why a classification change does not establish legal land use.
- **70–75, checkpoint:** Ask each team to identify five fields and one caution.

Explain what is missing: no raw raster, rainfall series, elevation, ground-truth
survey or current conditions. The records support record interpretation, not
pixel processing or real-world operational decisions.

## 75–140 minutes · Guided build and testing

**Learning outcomes 4–5: run the assistant and verify an answer.**

- **75–90, run:** Teams start a local copy or open the facilitator's shared URL.
  Ask the Klang flood question and locate the underlying JSON record.
- **90–105, test retrieval:** Repeat the vegetation comparison. Change source
  count from **1** to **3**. One record is insufficient to compare two places;
  the source cards make the omission visible. Try a theme filter and clear it.
- **105–115, change something:** Select **Field briefing** and compare output.
  For teams editing code, change the first flood value in
  `scripts/generate_data.py` from 142 to 150, run the generator, restart the
  server and repeat the question. Confirm both excerpt and source now show
  150. Restore 142 and regenerate/restart before the challenge so the supplied
  answer key remains valid. This changes the knowledge base, not model weights.
- **115–125, optional Qwen:** Repeat one query in Qwen mode. Inspect all cited
  sources. A valid citation ID does not guarantee that the associated claim
  is supported. Avoid having every team request inference simultaneously.
- **125–133, limits demo:** Ask `Will Klang flood tomorrow?` Expect explicit
  insufficiency. Ask `What do coastal observations show in Shah Alam?` Expect
  no matching record. Ask `What is the mass of Jupiter?` to test off-topic input.
- **133–140, capture:** Use **Use this source in my notebook**. Write a finding
  in your own words, state the observation date and units, and check the source.

Expected examples on the unmodified corpus:

| Prompt | Supporting evidence / expected behaviour |
| --- | --- |
| Flood observations in Klang | `FLOOD-001`: 142 ha, fictional snapshot |
| Vegetation in Hulu Langat and Shah Alam | `VEGETATION-005`: 0.78; `VEGETATION-002`: 0.51 |
| Land-use change in Sepang | `LANDUSE-004`: 46 ha; limited optical quality |
| Coastal observations in Kuala Selangor | `COASTAL-003`: 7.8 m; tide/resolution caveats |
| Coastal observations in Shah Alam | No matching source; missing evidence is not zero erosion |
| Will Klang flood tomorrow? | Abstains from forecasting; related cards are classroom examples |

Lexical search is intentionally inspectable and has limits. Unsupported place
names are not geocoded, paraphrases can be missed, and related excerpts may not
answer the exact question. Have teams flag these failures rather than assuming
the search score or a polished answer proves correctness.

## 140–160 minutes · Mini challenge

**Deliverable: question + answer/finding + checked source + limitation.**

- **140–143:** Open **Team mission**. Allocate one of the three missions.
- **143–153:** Teams retrieve evidence and complete their notebook.
- **153–158:** Two or three teams give a 60-second evidence briefing.
- **158–160:** Everyone downloads `spacelab-team-evidence.json` and submits it
  through the selected workshop collection channel.

Facilitator answer key:

1. **Flood evidence:** Klang 142 ha (`FLOOD-001`), Hulu Langat 119 ha
   (`FLOOD-005`). Both are synthetic possible-water observations. Require a
   limitation; do not accept a safety or forecast conclusion.
2. **Vegetation:** Hulu Langat 0.78 (`VEGETATION-005`), Shah Alam 0.51
   (`VEGETATION-002`). A supported greenness comparison does not prove health.
3. **Missing coastline:** No Shah Alam coastal record. Kuala Selangor's
   `COASTAL-003` supplies the alternative 7.8 m example. A team must explain
   why inventing Shah Alam's value would be wrong.

Give one point each for a clear question, correct factual finding with date and
unit, valid source verification, and a relevant limitation. A suggested pass is
3/4 **with both factual finding and verification present**. Evaluation is human;
the app checks source existence and required fields, not factual entailment.

## 160–180 minutes · SkillsBuild + wrap-up

**Learning outcome 6: identify an appropriate next learning step.**

- **160–165, demo:** Open **Workshop guide** → **Explore SkillsBuild** at
  https://skillsbuild.org/university/students. Use the university learning catalog
  at https://skillsbuild.org/learning-catalog/university-catalog.
- **165–173, participants:** Explore an AI fundamentals or data learning
  activity. Register where access allows, or record the course/topic they plan
  to pursue and a target date. Avoid promising a particular credential or
  registration outcome. The external site can change independently of this app.
- **173–177:** Add the next step, self-reported SkillsBuild progress and feedback
  in **Team mission**. Download and submit the final evidence file again.
- **177–180:** Ask: “What does RAG add? What must you still verify?” Take Q&A.

## Measure the proposal's success indicators

These are proposed workshop targets, not claims of achieved results. Count once
per team, keeping the roster denominator explicit. The app deliberately avoids
personal registration information and has no central analytics dashboard.

| Indicator | Suggested measurement |
| --- | --- |
| ≥80% guided demo completion | Teams submitting a complete deliverable ÷ teams attending |
| ≥80% learning demonstration | Teams passing the rubric **and** explaining retrieval vs generation ÷ teams attending |
| 80% SkillsBuild activation / intent | Teams documenting registration/access or a concrete next step ÷ teams attending; identify this as team-level self-report |
| 85% positive feedback | Positive ratings ÷ answered feedback items; separately report response rate |

If the organiser requires individual rather than team KPIs, collect an
individual exit ticket separately; team evidence cannot establish individual
registration or learning completion. Count duplicate updated submissions once.

## Recovery and troubleshooting

| Symptom | Action |
| --- | --- |
| Qwen unavailable / citation fallback notice | Use offline excerpts; verify Ollama service, model name and prior download |
| Model is slow | Stagger requests, reduce sources, or use offline mode; requests time out after 60 seconds |
| Port already in use | Start with `--port 8081` and use that URL |
| Participants cannot reach shared server | Check bind address, LAN IP, firewall and Wi-Fi isolation; switch to individual local copies |
| Edited data not reflected | Regenerate all formats, restart Python, refresh the browser |
| A source appears missing | Clear topic filter, inspect place spelling, increase source count and check Data explorer |
| Browser notebook not retained | Download evidence immediately; storage may be blocked or private browsing cleared |
| Internet unavailable | All core app activities work locally; document a SkillsBuild next-step intent for later |

## Outcome-to-feature mapping

| PDF outcome | App / workshop evidence |
| --- | --- |
| Connect AI to space applications | Four themes, opening discussion, use-case examples |
| Explain LLM + RAG + knowledge base | Pipeline, inspectable prompt, excerpt/Qwen comparison |
| Load and explore dataset | Startup JSON load, Data explorer, CSV/GeoJSON downloads |
| Run guided assistant | Question form, filters, top-k and answer-style changes |
| Evaluate answer | Source cards, missing/live-data tests, checked-source notebook |
| Continue through SkillsBuild | Official links, next-step field and self-reported intent |

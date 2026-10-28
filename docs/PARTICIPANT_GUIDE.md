# SpaceLab participant guide

Your goal: produce one answer you can trace to evidence and explain one limit.

1. Start `python3 server.py` in the project folder and visit
   http://127.0.0.1:8080, or use the workshop URL supplied by your facilitator.
2. In **Intelligence assistant**, keep **Offline · retrieved excerpts** selected.
   Ask: `What do the flood observations in Klang show?`
3. Expand `FLOOD-001`. Check **142 ha**, **2026-10-15**, the radar-like sensor
   label and the limitation. Everything is fictional teaching data.
4. In **Data explorer**, find the same record. Download the CSV and identify
   coordinates, metric, units, quality and provenance.
5. Ask `Compare vegetation in Hulu Langat and Shah Alam.` Try source counts 1
   and 3. Does the answer include enough evidence to compare both places?
6. If the facilitator has prepared Ollama, select **Qwen · local Ollama** and
   repeat. An LLM drafts the answer, while retrieval supplies its evidence.
   Check the returned mode badge: connection failures use labelled excerpts.
7. Ask `Will Klang flood tomorrow?` Explain why the dataset cannot answer.
8. In **Team mission**, choose a scenario. Write your own finding and limitation.
   Use exact IDs, e.g. `FLOOD-001, FLOOD-005` when checking two records.
9. Check the verification box only after comparing your claim with the records.
   Download team evidence and submit the file through the facilitator's chosen
   collection method. A downloaded JSON file is your workshop deliverable.
10. Open SkillsBuild from **Workshop guide**, explore an AI or data pathway,
    and record a concrete next step. Registration is optional and depends on access.

Notebook entries are saved only in the current browser when storage is available.
Do not depend on browser storage on shared or private-browsing devices; download
your evidence. The server does not receive or grade your notebook.

Try making a small change: switch the answer style to **Field briefing**. For
a code/data activity, follow the generator-edit instructions in the README.

Explain to a partner: the knowledge base stores reference records, retrieval
selects relevant ones, Qwen writes from them, and a person checks the answer.

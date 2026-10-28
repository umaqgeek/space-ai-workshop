'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const titles = {assistant:'Intelligence assistant', explorer:'Data explorer', architecture:'Architecture'};
let records = [], latest = null;
function showView(view) {
  if (!titles[view]) view = 'assistant';
  document.querySelectorAll('.view').forEach(section => {section.hidden = section.id !== `view-${view}`;});
  document.querySelectorAll('[data-view]').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
    if (button.dataset.view === view) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  $('breadcrumb').textContent = titles[view];
  history.replaceState(null, '', `#${view}`);
  window.scrollTo({top:0, behavior:'instant'});
}
document.querySelectorAll('[data-view], [data-go]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view || button.dataset.go)));
document.querySelectorAll('[data-architecture-target]').forEach(button => button.addEventListener('click', () => {
  const section = $(button.dataset.architectureTarget);
  section.open = true;
  section.querySelector('summary').focus({preventScroll:true});
  section.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block:'start'});
}));
function resizeQuestion() {
  const field = $('question');
  field.style.height = 'auto';
  field.style.height = `${Math.min(field.scrollHeight, 140)}px`;
  field.style.overflowY = field.scrollHeight > 140 ? 'auto' : 'hidden';
}
function setQuery(question) {showView('assistant'); $('question').value = question; $('question').setCustomValidity(''); resizeQuestion(); $('question').focus();}
document.querySelectorAll('[data-query]').forEach(button => button.addEventListener('click', () => setQuery(button.dataset.query)));

async function api(path, options) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}
function sourceCard(record, inAnswer = false) {
  const r = Object.fromEntries(Object.entries(record).map(([key, value]) => [key, escapeHtml(value)]));
  return `<details class="source"><summary><span class="tag">${r.id}</span>${r.title}</summary>
    <p>${r.description}</p><dl><dt>Observation date</dt><dd>${r.observation_date}</dd>
    <dt>Baseline date</dt><dd>${r.baseline_date || 'Not applicable'}</dd><dt>Coordinates</dt><dd>${r.latitude}° N, ${r.longitude}° E</dd>
    <dt>Sensor example</dt><dd>${r.sensor}</dd><dt>Metric</dt><dd>${r.metric}: <strong>${r.value} ${r.unit}</strong></dd>
    <dt>Cloud cover</dt><dd>${r.cloud_cover_pct}%${record.theme === 'flood' ? ' (not used for radar; placeholder)' : ''}</dd>
    <dt>Quality</dt><dd>${r.quality}</dd>${inAnswer ? `<dt>BM25 score</dt><dd>${r.retrieval_score} (match strength, not confidence)</dd>` : ''}</dl>
    <p><strong>Limit:</strong> ${r.limitations}</p><p class="muted">Synthetic · ${r.provenance}</p>
    </details>`;
}

function responseContent(result) {
  // Move only our own presentation wrappers; preserve model prose and citations.
  const wrappers = [
    'Synthetic sample data. AI-generated answer; verify claims against the source cards.',
    'These are synthetic sample observations, not real-world measurements.',
    'These are retrieved excerpts, not an LLM-generated analysis. Verify each claim against the source cards. Only the displayed records were retrieved; this is not a complete regional ranking.',
  ];
  let answer = result.answer;
  for (const wrapper of wrappers) {
    if (answer.startsWith(wrapper)) answer = answer.slice(wrapper.length).trim();
    if (answer.endsWith(wrapper)) answer = answer.slice(0, -wrapper.length).trim();
  }
  return answer;
}

function renderResponse(result) {
  const generated = result.mode === 'qwen';
  const title = result.status === 'insufficient' ? 'Insufficient evidence' : generated ? 'AI response' : 'Retrieved excerpts';
  return `<article class="response-primary" aria-labelledby="response-title">
      <div class="answer-header"><div><span class="eyebrow">YOUR ANSWER</span><h2 id="response-title">${title}</h2></div><span class="tag response-mode ${generated ? 'generated' : ''}">${generated ? 'AI GENERATED' : 'EXCERPT MODE'}</span></div>
      <p class="response-question">${escapeHtml(result.question)}</p>
      <div class="answer-text">${escapeHtml(responseContent(result))}</div>
      <div class="response-context"><span class="tag">SYNTHETIC DATA</span><span>${result.sources.length} reference${result.sources.length === 1 ? '' : 's'} retrieved</span>${result.notice && result.status === 'matched' ? '<span class="fallback-label">Model unavailable or citation check failed · excerpts shown</span>' : ''}</div>
    </article>
    <div class="response-support" aria-label="Answer details">
      <details class="response-detail"><summary><span>Clarification</span><span class="detail-hint">Mode, coverage and limitations</span></summary><div class="detail-content">
        ${result.notice ? `<div class="notice">${escapeHtml(result.notice)}</div>` : ''}
        <p>${generated ? 'The configured Ollama model generated this answer from the retrieved records. Valid source IDs do not guarantee that every claim is supported.' : 'This response contains retrieved excerpts, without LLM-generated analysis.'}</p>
        <p>All observations are synthetic examples, not real-world measurements. Verify dates, values and limitations against the references. Retrieved records may cover only part of your question; they do not establish a complete regional ranking.</p>
        </div></details>
      <details class="response-detail"><summary><span>References <span class="reference-count">${result.sources.length}</span></span><span class="detail-hint">Inspect the source records</span></summary><div class="detail-content">
        ${result.sources.length ? result.sources.map(r => sourceCard(r, true)).join('') : '<p>No matching reference records were retrieved.</p>'}
        </div></details>
      <div class="answer-actions"><button id="export-answer" class="text-button">Download response and references ↓</button></div>
    </div>`;
}
$('question-form').addEventListener('submit', async event => {
  event.preventDefault();
  if ($('ask-button').disabled) return;
  const question = $('question').value.trim();
  if (question.length < 3) {$('question').setCustomValidity('Please enter at least 3 characters.'); $('question').reportValidity(); return;}
  $('ask-button').disabled = true;
  $('ask-button').textContent = 'Retrieving…';
  $('answer-panel').setAttribute('aria-busy','true');
  $('answer-panel').innerHTML = '<div class="loading">Retrieving source records and preparing your answer…</div>';
  latest = null;
  try {
    latest = await api('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question, mode:$('engine').value, theme:$('topic').value, top_k:Number($('source-count').value), style:$('style').value})});
    $('answer-panel').innerHTML = renderResponse(latest);
    $('export-answer').addEventListener('click', () => download('spacelab-response.json', {...latest, synthetic:true, exported_at:new Date().toISOString()}));
  } catch (error) {
    $('answer-panel').innerHTML = `<div class="response-primary"><h2>Could not retrieve an answer</h2><p class="error">${escapeHtml(error.message)}</p><p class="muted">Check that the Python server is running, then submit your question again.</p></div>`;
  } finally {
    $('ask-button').disabled = false; $('ask-button').innerHTML = 'Find insights <span>↗</span>';
    $('answer-panel').removeAttribute('aria-busy');
    if (!$('view-assistant').hidden) {
      $('answer-panel').focus({preventScroll:true});
      $('answer-panel').scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block:'start'});
    }
  }
});
$('question').addEventListener('input', () => { $('question').setCustomValidity(''); resizeQuestion(); });
$('question').addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    if (!$('ask-button').disabled) $('question-form').requestSubmit();
  }
});
$('show-prompt').addEventListener('click', async () => {
  const output = $('prompt-content');
  if (!output.hidden) {output.hidden = true; return;}
  try {output.textContent = (await api('/api/prompt')).system_prompt; output.hidden = false;}
  catch (error) {output.textContent = error.message; output.hidden = false;}
});

function renderExplorer() {
  const query = $('data-search').value.toLowerCase();
  const theme = $('data-theme').value;
  const filtered = records.filter(r => (theme === 'all' || r.theme === theme) && JSON.stringify(r).toLowerCase().includes(query));
  $('record-summary').textContent = `${filtered.length} of ${records.length} observations · expand a record to inspect it`;
  $('records-list').innerHTML = filtered.map(r => sourceCard(r)).join('') || '<div class="card">No records match. Try another search or application.</div>';
  const sites = [...new Map(filtered.map(r => [r.location,r])).values()];
  const points = sites.map(r => {
    const x = 85 + (r.longitude - 100.9) / 1.1 * 340;
    const y = 405 - (r.latitude - 2.5) / 1.5 * 340;
    const labelX = x > 340 ? x-10 : x+11;
    return `<g><title>${escapeHtml(r.location)}: ${r.latitude}, ${r.longitude}</title><circle cx="${x}" cy="${y}" r="7" fill="#507648" stroke="white" stroke-width="3"/><text x="${labelX}" y="${y-13}" text-anchor="${x>340?'end':'start'}" fill="#3c5738" font-size="13">${escapeHtml(r.location)}</text></g>`;
  }).join('');
  $('location-map').innerHTML = `<defs><pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M 50 0 L 0 0 0 50" fill="none" stroke="#dce5d3" stroke-width="1"/></pattern></defs><rect width="500" height="480" fill="url(#grid)"/><text x="25" y="32" font-size="11" fill="#7a8f6b">N ↑</text><text x="25" y="458" font-size="10" fill="#7a8f6b">100.9° E → 102.0° E / 2.5° N → 4.0° N</text>${points}`;
}
$('data-search').addEventListener('input',renderExplorer);
$('data-theme').addEventListener('change',renderExplorer);

function download(name, data) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}));
  const link = document.createElement('a'); link.href=url; link.download=name; link.click();
  setTimeout(() => URL.revokeObjectURL(url),1000);
}
async function init() {
  showView(location.hash.slice(1) || 'assistant');
  resizeQuestion();
  try {
    records = await api('/api/records');
    document.querySelectorAll('.record-count').forEach(el => {el.textContent=records.length;});
    $('connection').textContent='Dataset ready';
    renderExplorer();
  } catch (error) {
    $('connection').textContent='Server unavailable';
    $('records-list').textContent=error.message;
    $('answer-panel').innerHTML='<div class="response-primary"><p class="error">Could not load the dataset. Start the Python server and reload this page.</p></div>';
  }
}
init();

'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const titles = {assistant:'Intelligence assistant', explorer:'Data explorer'};
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
function setQuery(question) {showView('assistant'); $('question').value = question; $('question').focus();}
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
$('question-form').addEventListener('submit', async event => {
  event.preventDefault();
  const question = $('question').value.trim();
  if (question.length < 3) {$('question').setCustomValidity('Please enter at least 3 characters.'); $('question').reportValidity(); return;}
  $('ask-button').disabled = true;
  $('ask-button').textContent = 'Retrieving…';
  $('answer-panel').setAttribute('aria-busy','true');
  $('answer-panel').innerHTML = '<div class="loading">Retrieving source records… Qwen may take up to 60 seconds.</div>';
  latest = null;
  try {
    latest = await api('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question, mode:$('engine').value, theme:$('topic').value, top_k:Number($('source-count').value), style:$('style').value})});
    $('answer-panel').innerHTML = `<div class="answer-header"><h2>${latest.status === 'matched' ? 'Your evidence-backed response' : 'Evidence is insufficient'}</h2><span class="tag pale">${latest.mode === 'qwen' ? 'QWEN · AI GENERATED' : 'RETRIEVED EXCERPTS'}</span></div>
      ${latest.notice ? `<div class="notice">${escapeHtml(latest.notice)}</div>` : ''}<div class="answer-text">${escapeHtml(latest.answer)}</div>
      <div class="sources-heading">RETRIEVED SOURCES · ${latest.sources.length}</div>${latest.sources.map(r => sourceCard(r, true)).join('')}
      <div class="answer-actions"><button id="export-answer" class="text-button">Download response ↓</button></div>`;
    $('export-answer').addEventListener('click', () => download('spacelab-response.json', {...latest, synthetic:true, exported_at:new Date().toISOString()}));
  } catch (error) {
    $('answer-panel').innerHTML = `<h2>Could not retrieve an answer</h2><p class="error">${escapeHtml(error.message)}</p><p class="muted">Check that the Python server is running, then submit your question again.</p>`;
  } finally {
    $('ask-button').disabled = false; $('ask-button').innerHTML = 'Find insights <span>↗</span>';
    $('answer-panel').removeAttribute('aria-busy');
  }
});
$('question').addEventListener('input', () => $('question').setCustomValidity(''));
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
  try {
    records = await api('/api/records');
    document.querySelectorAll('.record-count').forEach(el => {el.textContent=records.length;});
    $('connection').textContent='Offline mode ready';
    renderExplorer();
  } catch (error) {
    $('connection').textContent='Server unavailable';
    $('records-list').textContent=error.message;
    $('answer-panel').innerHTML='<p class="error">Could not load the dataset. Start the Python server and reload this page.</p>';
  }
}
init();

'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const titles = {assistant:'Intelligence assistant', explorer:'Data explorer', architecture:'Architecture'};
let records = [], latest = null, malaysiaOutline = null;
let editingRecord = null, editDraft = null, savingRecord = false, dataVersion = 0;
const malaysianStates = ['Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang', 'Penang', 'Perak', 'Perlis', 'Sabah', 'Sarawak', 'Selangor', 'Terengganu', 'Kuala Lumpur', 'Putrajaya', 'Labuan'];
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
  if (!inAnswer && editingRecord?.id === record.id) {
    return `<details class="source" open><summary><span class="tag">${r.id}</span>${r.title}</summary>${recordEditor(record)}</details>`;
  }
  return `<details class="source"><summary><span class="tag">${r.id}</span>${r.title}</summary>
    <p>${r.description}</p><dl><dt>State / federal territory</dt><dd>${r.state}</dd><dt>Observation date</dt><dd>${r.observation_date}</dd>
    <dt>Baseline date</dt><dd>${r.baseline_date || 'Not applicable'}</dd><dt>Coordinates</dt><dd>${r.latitude}° N, ${r.longitude}° E</dd>
    <dt>Sensor example</dt><dd>${r.sensor}</dd><dt>Metric</dt><dd>${r.metric}: <strong>${r.value} ${r.unit}</strong></dd>
    <dt>Cloud cover</dt><dd>${r.cloud_cover_pct}%${record.theme === 'flood' ? ' (not used for radar; placeholder)' : ''}</dd>
    <dt>Quality</dt><dd>${r.quality}</dd>${inAnswer ? `<dt>Selection</dt><dd>${record.retrieval_score === undefined ? 'Dataset query' : `BM25 score: ${r.retrieval_score} (match strength, not confidence)`}</dd>` : ''}</dl>
    <p><strong>Limit:</strong> ${r.limitations}</p><p class="muted">Synthetic · ${r.provenance}</p>
    ${inAnswer ? '' : `<button type="button" class="text-button" id="edit-${r.id}" data-edit-record="${r.id}" ${editingRecord ? 'disabled' : ''}>Edit record</button>`}
    </details>`;
}

function recordEditor(record) {
  const field = (key, label, type = 'text', attributes = '') => `<label for="record-${key}">${label}<input id="record-${key}" name="${key}" type="${type}" value="${escapeHtml(editDraft[key])}" ${attributes} required></label>`;
  return `<form class="record-editor" data-record-editor="${escapeHtml(record.id)}">
    <p>Edit this synthetic observation. Changes are shared with everyone using this app.</p>
    <div class="record-fields">
      ${field('title', 'Title', 'text', 'maxlength="200"')}
      ${field('location', 'Location', 'text', 'maxlength="100"')}
      <label for="record-state">State / federal territory<select id="record-state" name="state" required>${malaysianStates.map(state => `<option ${editDraft.state === state ? 'selected' : ''}>${escapeHtml(state)}</option>`).join('')}</select></label>
      ${field('observation_date', 'Observation date', 'date')}
      ${record.baseline_date ? field('baseline_date', 'Baseline date', 'date') : ''}
      ${field('latitude', 'Latitude', 'number', 'min="-90" max="90" step="any"')}
      ${field('longitude', 'Longitude', 'number', 'min="-180" max="180" step="any"')}
      ${field('sensor', 'Sensor example', 'text', 'maxlength="200"')}
      ${field('value', `Value (${escapeHtml(record.unit)}) · ${escapeHtml(record.metric)}`, 'number', `step="any" min="${record.theme === 'vegetation' ? -1 : 0}" max="${record.theme === 'vegetation' ? 1 : 1e12}"`)}
      ${record.theme === 'flood' ? '' : field('cloud_cover_pct', 'Cloud cover (%)', 'number', 'min="0" max="100" step="any"')}
      <label class="record-wide" for="record-limitations">Limitations<textarea id="record-limitations" name="limitations" rows="4" maxlength="2000" required>${escapeHtml(editDraft.limitations)}</textarea></label>
    </div>
    <p class="muted">The observation summary and quality label update automatically when you save. Citation ID: ${escapeHtml(record.id)} · Application: ${escapeHtml(record.theme)} · Synthetic teaching data.</p>
    <p class="error edit-error" role="alert"></p>
    <div class="record-edit-actions"><button class="primary" type="submit">Save changes</button><button class="text-button" type="button" data-cancel-edit>Cancel</button></div>
  </form>`;
}

function responseContent(result) {
  // References are displayed separately in the collapsible source section.
  const wrappers = [
    'Synthetic sample data. AI-generated answer; verify claims against the source cards.',
    'These are synthetic sample observations, not real-world measurements.',
    'These are retrieved excerpts, not an LLM-generated analysis. Verify each claim against the source cards. Only the displayed records were retrieved; this is not a complete regional ranking.',
  ];
  const refs = result.answer.match(/\n\n(Refs: [^\n]+)$/);
  let answer = refs ? result.answer.slice(0, refs.index) : result.answer;
  for (const wrapper of wrappers) {
    if (answer.startsWith(wrapper)) answer = answer.slice(wrapper.length).trim();
    if (answer.endsWith(wrapper)) answer = answer.slice(0, -wrapper.length).trim();
  }
  return answer;
}

function safeWebUrl(value) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null;
  } catch (error) { return null; }
}
function webSourceCard(source) {
  const url = safeWebUrl(source.url);
  if (!url) return '';
  return `<details class="source web-source"><summary><span class="tag">${escapeHtml(source.id)}</span>${escapeHtml(source.title)}</summary>
    <p><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)} ↗</a></p>
    <p>${escapeHtml(source.content)}</p><p class="muted">External search excerpt · retrieved ${escapeHtml(source.retrieved_at)}. Retrieval time is not a publication date.</p></details>`;
}

function renderResponse(result) {
  const generated = result.mode === 'qwen';
  const webSources = result.web_sources || [];
  const webEnabled = Boolean(result.web_search?.enabled);
  const referenceCount = result.sources.length + webSources.length;
  const computed = result.mode === 'data';
  const title = result.status === 'insufficient' ? 'Insufficient evidence' : generated ? 'AI response' : computed ? 'Dataset results' : 'Retrieved excerpts';
  return `<article class="response-primary" aria-labelledby="response-title">
      <div class="answer-header"><div><span class="eyebrow">YOUR ANSWER</span><h2 id="response-title">${title}</h2></div><span class="tag response-mode ${generated ? 'generated' : ''}">${generated ? 'AI GENERATED' : computed ? 'DATASET RESULTS' : 'EXCERPT MODE'}</span></div>
      <p class="response-question">${escapeHtml(result.question)}</p>
      <div class="answer-text">${escapeHtml(responseContent(result))}</div>
      <div class="response-context"><span class="tag">${webSources.length ? result.sources.length ? 'DATASET + WEB' : 'WEB REFERENCES' : 'SYNTHETIC DATA'}</span><span>${referenceCount} reference${referenceCount === 1 ? '' : 's'} retrieved</span>${webEnabled ? `<span class="web-search-status">${webSources.length ? 'Web search completed' : 'Web search unavailable or no results'}</span>` : ''}${result.notice ? '<span class="fallback-label">See clarification for details</span>' : ''}</div>
    </article>
    <div class="response-support" aria-label="Answer details">
      <details class="response-detail"><summary><span>Clarification</span><span class="detail-hint">Mode, coverage and limitations</span></summary><div class="detail-content">
        ${result.notice ? `<div class="notice">${escapeHtml(result.notice)}</div>` : ''}
        <p>${generated ? 'The configured Ollama model generated this answer from the supplied dataset and any external references shown below. Valid source IDs do not guarantee that every claim is supported.' : computed ? 'This response was computed directly from all matching dataset records. Rankings use numeric metric values.' : 'This response contains retrieved excerpts, without LLM-generated analysis.'}</p>
        <p>Dataset observations are synthetic examples. External web references provide separate context and do not validate the invented measurements. Check source dates, values and limitations; dataset rankings describe only the bundled sample records.</p>
        </div></details>
      <details class="response-detail"><summary><span>References <span class="reference-count">${referenceCount}</span></span><span class="detail-hint">Inspect dataset and web sources</span></summary><div class="detail-content">
        ${result.sources.length ? `<h3 class="reference-section-title">Dataset records · synthetic</h3>${result.sources.map(r => sourceCard(r, true)).join('')}` : '<p>No matching dataset records were retrieved.</p>'}
        ${webSources.length ? `<h3 class="reference-section-title">Web references · external search excerpts</h3>${webSources.map(webSourceCard).join('')}` : ''}
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
  const useWeb = $('web-search').checked;
  $('ask-button').textContent = useWeb ? 'Searching…' : 'Retrieving…';
  $('answer-panel').setAttribute('aria-busy','true');
  $('answer-panel').innerHTML = `<div class="loading">${useWeb ? 'Searching the web and retrieving dataset evidence…' : 'Retrieving source records and preparing your answer…'}</div>`;
  latest = null;
  const requestVersion = dataVersion;
  try {
    latest = await api('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question, mode:$('engine').value, theme:$('topic').value, style:$('style').value, web_search:useWeb})});
    if (requestVersion !== dataVersion) {
      latest = null;
      $('answer-panel').innerHTML = '<p class="muted">The dataset changed. Submit your question again for an updated answer.</p>';
      return;
    }
    $('answer-panel').innerHTML = renderResponse(latest);
    $('export-answer').addEventListener('click', () => download('spacelab-response.json', {...latest, synthetic:!(latest.web_sources?.length), dataset_synthetic:true, exported_at:new Date().toISOString()}));
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
function updateWebSearchHint() {
  $('web-search-hint').textContent = $('web-search').checked ? 'On · add external context' : 'Off · dataset only';
}
$('web-search').addEventListener('change', () => {
  if ($('web-search').checked) $('engine').value = 'qwen';
  updateWebSearchHint();
});
$('engine').addEventListener('change', () => {
  if ($('engine').value === 'offline') $('web-search').checked = false;
  updateWebSearchHint();
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

function projectLocation(longitude, latitude) {
  const east = longitude > 108;
  const scale = east ? 210 / 11 : 210 / 6;
  const x = (east ? 270 : 30) + (longitude - (east ? 109 : 99)) * scale;
  const y = (east ? 310 : 365) - (latitude - 0.5) * scale / Math.cos(4 * Math.PI / 180);
  return [x, y];
}

function outlinePaths() {
  if (!malaysiaOutline) return '';
  return malaysiaOutline.geometry.coordinates.map(polygon => {
    const path = polygon.map(ring => ring.map(([lon, lat], index) => {
      const [x, y] = projectLocation(lon, lat);
      return `${index ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ') + ' Z').join(' ');
    return `<path d="${path}" fill="#dce6cb" stroke="#a0b58a" stroke-width="0.8" fill-rule="evenodd" stroke-linejoin="round"/>`;
  }).join('');
}

function renderExplorer() {
  const query = $('data-search').value.toLowerCase();
  const theme = $('data-theme').value;
  const filtered = records.filter(r => (theme === 'all' || r.theme === theme) && JSON.stringify(r).toLowerCase().includes(query));
  $('record-summary').textContent = `${filtered.length} of ${records.length} observations · expand a record to inspect it`;
  $('records-list').innerHTML = filtered.map(r => sourceCard(r)).join('') || '<div class="card">No records match. Try another search or application.</div>';
  const sites = [...new Map(filtered.map(r => [JSON.stringify([r.location, r.state, r.longitude, r.latitude]), r])).values()];
  const points = sites.map(r => {
    const [x, y] = projectLocation(r.longitude, r.latitude);
    const labelX = x > 390 ? x-9 : x+9;
    const label = escapeHtml(`${r.location}, ${r.state}`);
    return `<g class="map-point" tabindex="0" role="img" aria-label="${label}: ${r.latitude}, ${r.longitude}"><title>${label}: ${r.latitude}, ${r.longitude}</title><circle cx="${x}" cy="${y}" r="5" fill="#507648" stroke="white" stroke-width="2"/><text class="map-label" x="${labelX}" y="${y-10}" text-anchor="${x>390?'end':'start'}" fill="#3c5738" font-size="12" stroke="white" stroke-width="3" paint-order="stroke">${label}</text></g>`;
  }).join('');
  $('location-map').innerHTML = `<defs><pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M 50 0 L 0 0 0 50" fill="none" stroke="#dce5d3" stroke-width="1"/></pattern></defs><rect width="500" height="480" fill="url(#grid)"/><text x="25" y="25" font-size="11" fill="#7a8f6b">N ↑</text><text x="25" y="50" font-size="12" fill="#3c5738">Peninsular Malaysia</text><text x="275" y="50" font-size="12" fill="#3c5738">East Malaysia</text><path d="M250 65V430" stroke="#dce5d3" stroke-dasharray="4 4"/><text x="25" y="458" font-size="10" fill="#7a8f6b">99–105° E · 0.5–7.5° N</text><text x="275" y="458" font-size="10" fill="#7a8f6b">109–120° E · 0.5–7.5° N</text><g aria-hidden="true" pointer-events="none">${outlinePaths()}</g>${points}`;
}
function setEditorControls() {
  $('data-search').disabled = Boolean(editingRecord);
  $('data-theme').disabled = Boolean(editingRecord);
}

$('records-list').addEventListener('input', event => {
  if (editingRecord && event.target.name) editDraft[event.target.name] = event.target.value;
});
$('records-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-edit-record], [data-cancel-edit]');
  if (!button || savingRecord) return;
  if (button.hasAttribute('data-cancel-edit')) {
    savingRecord = true;
    const id = editingRecord.id;
    editingRecord = null;
    editDraft = null;
    $('edit-status').textContent = 'Changes cancelled.';
    // Refresh after a conflict so reopening the editor loads the saved version.
    try { records = await api('/api/records'); } catch (error) {
      $('edit-status').textContent = 'Changes cancelled. Could not refresh records; reload the page to get the latest saved version.';
    }
    savingRecord = false;
    setEditorControls();
    renderExplorer();
    $(`edit-${id}`)?.closest('details').setAttribute('open', '');
    $(`edit-${id}`)?.focus();
    return;
  }
  if (editingRecord) return;
  editingRecord = {...records.find(record => record.id === button.dataset.editRecord)};
  editDraft = {...editingRecord};
  $('edit-status').textContent = '';
  setEditorControls();
  renderExplorer();
  $('record-title').focus();
});
$('records-list').addEventListener('submit', async event => {
  const form = event.target.closest('[data-record-editor]');
  if (!form) return;
  event.preventDefault();
  if (savingRecord || !form.reportValidity()) return;
  const original = editingRecord;
  const changes = Object.fromEntries(new FormData(form));
  for (const key of ['latitude', 'longitude', 'value', 'cloud_cover_pct']) {
    if (key in changes) changes[key] = Number(changes[key]);
  }
  savingRecord = true;
  form.setAttribute('aria-busy', 'true');
  form.querySelector('.edit-error').textContent = '';
  form.querySelectorAll('input, select, textarea, button').forEach(control => {control.disabled = true;});
  try {
    const result = await api(`/api/records/${original.id}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({changes, original})});
    records = records.map(record => record.id === original.id ? result.record : record);
    editingRecord = null;
    editDraft = null;
    dataVersion += 1;
    latest = null;
    $('answer-panel').innerHTML = '<p class="muted">The dataset was updated. Submit your question again to use the saved values.</p>';
    $('edit-status').textContent = `${original.id} saved. Answers, rankings and downloads now use the updated values.`;
    document.querySelectorAll('.location-count').forEach(el => {el.textContent=new Set(records.map(r => r.location)).size;});
    renderExplorer();
    $(`edit-${original.id}`)?.closest('details').setAttribute('open', '');
    $(`edit-${original.id}`)?.focus();
  } catch (error) {
    form.querySelector('.edit-error').textContent = error.message;
  } finally {
    savingRecord = false;
    form.removeAttribute('aria-busy');
    form.querySelectorAll('input, select, textarea, button').forEach(control => {control.disabled = false;});
    setEditorControls();
  }
});
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
    document.querySelectorAll('.location-count').forEach(el => {el.textContent=new Set(records.map(r => r.location)).size;});
    $('connection').textContent='Dataset ready';
    renderExplorer();
    try {
      malaysiaOutline = await api('/maps/malaysia.geojson');
      if (!editingRecord) renderExplorer();
    } catch (error) {
      $('map-caption').textContent = 'Map outline unavailable. Location dots remain visible; hover or focus a point for its place name.';
    }
  } catch (error) {
    $('connection').textContent='Server unavailable';
    $('records-list').textContent=error.message;
    $('answer-panel').innerHTML='<div class="response-primary"><p class="error">Could not load the dataset. Start the Python server and reload this page.</p></div>';
  }
}
init();

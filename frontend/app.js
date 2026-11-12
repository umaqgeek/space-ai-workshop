'use strict';
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function noteTooltip(note, label = 'More information') {
  return `<button type="button" class="note-trigger" data-tooltip="${escapeHtml(note)}" aria-label="${escapeHtml(label)}">ⓘ</button>`;
}
// One floating tooltip avoids clipping inside cards, source lists and the composer.
const assistantTooltip = document.createElement('div');
assistantTooltip.id = 'assistant-tooltip';
assistantTooltip.className = 'assistant-tooltip';
assistantTooltip.setAttribute('role', 'tooltip');
assistantTooltip.hidden = true;
document.body.append(assistantTooltip);
let tooltipTrigger = null, tooltipTimer = null;
const noteSelector = '#view-assistant [data-tooltip], #view-assistant [data-tooltip-source]';
function hideNote() {
  clearTimeout(tooltipTimer);
  if (tooltipTrigger && !tooltipTrigger.dataset.tooltipSource) tooltipTrigger.removeAttribute('aria-describedby');
  tooltipTrigger = null;
  assistantTooltip.hidden = true;
}
function positionNote() {
  if (!tooltipTrigger?.isConnected) { hideNote(); return; }
  const anchor = tooltipTrigger.getBoundingClientRect();
  const box = assistantTooltip.getBoundingClientRect();
  assistantTooltip.style.left = `${Math.max(12, Math.min(anchor.right - box.width, window.innerWidth - box.width - 12))}px`;
  const below = anchor.bottom + 8;
  assistantTooltip.style.top = `${Math.max(12, below + box.height <= window.innerHeight - 12 ? below : anchor.top - box.height - 8)}px`;
}
function showNote(trigger) {
  hideNote();
  const content = trigger.dataset.tooltipSource ? $(trigger.dataset.tooltipSource)?.textContent : trigger.dataset.tooltip;
  if (!content?.trim()) return;
  tooltipTrigger = trigger;
  assistantTooltip.textContent = content;
  assistantTooltip.hidden = false;
  if (!trigger.dataset.tooltipSource) trigger.setAttribute('aria-describedby', assistantTooltip.id);
  positionNote();
}
function scheduleHideNote() {
  clearTimeout(tooltipTimer);
  tooltipTimer = setTimeout(() => {
    if (!assistantTooltip.matches(':hover') && !tooltipTrigger?.matches(':hover') && document.activeElement !== tooltipTrigger) hideNote();
  }, 150);
}
document.addEventListener('pointerover', event => {
  const trigger = event.target.closest(noteSelector);
  if (trigger && trigger !== tooltipTrigger) showNote(trigger);
});
document.addEventListener('pointerout', event => {
  if (event.target.closest(noteSelector)) scheduleHideNote();
});
assistantTooltip.addEventListener('pointerenter', () => clearTimeout(tooltipTimer));
assistantTooltip.addEventListener('pointerleave', scheduleHideNote);
document.addEventListener('focusin', event => {
  const trigger = event.target.closest(noteSelector);
  if (trigger) showNote(trigger); else hideNote();
});
document.addEventListener('focusout', event => {
  if (event.target === tooltipTrigger) scheduleHideNote();
});
document.addEventListener('keydown', event => { if (event.key === 'Escape') hideNote(); });
document.addEventListener('click', event => {
  const trigger = event.target.closest(noteSelector);
  if (trigger) { event.preventDefault(); showNote(trigger); }
  else if (!assistantTooltip.contains(event.target)) hideNote();
});
window.addEventListener('resize', hideNote);
document.addEventListener('scroll', event => { if (!assistantTooltip.contains(event.target)) hideNote(); }, true);
const titles = {assistant:'Intelligence assistant', explorer:'Data explorer', architecture:'Architecture', admin:'Admin'};
let records = [], latest = null, malaysiaOutline = null;
// Deliberately kept in memory: every page load starts a fresh session.
let chatSessionId = null, conversations = [], viewingHistory = false, chatBusy = false;
let historyOffset = null, historyLoading = false;
let editingRecord = null, editDraft = null, savingRecord = false, dataVersion = 0, importingCsv = false, datasetReady = false;
const ADMIN_STORAGE_KEY = 'spacelab.adminSession';
let adminToken = '', isAdmin = false, permissionsReady = false;
let permissions = {excerpt_only:true, allow_record_updates:false};
try { adminToken = localStorage.getItem(ADMIN_STORAGE_KEY) || ''; } catch (error) { /* Storage may be unavailable. */ }
const canUpdateRecords = () => permissionsReady && (isAdmin || permissions.allow_record_updates);
const malaysianStates = ['Johor', 'Kedah', 'Kelantan', 'Melaka', 'Negeri Sembilan', 'Pahang', 'Penang', 'Perak', 'Perlis', 'Sabah', 'Sarawak', 'Selangor', 'Terengganu', 'Kuala Lumpur', 'Putrajaya', 'Labuan'];
function showView(view) {
  hideNote();
  if (!titles[view]) view = 'assistant';
  document.querySelectorAll('.view').forEach(section => {section.hidden = section.id !== `view-${view}`;});
  document.querySelectorAll('[data-view]').forEach(button => {
    button.classList.toggle('active', button.dataset.view === view);
    if (button.dataset.view === view) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  $('breadcrumb').textContent = titles[view];
  history.replaceState(null, '', `#${view}`);
  window.scrollTo({top:0, behavior:'instant'});
  if (view === 'admin' && !isAdmin) $('admin-password').focus();
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
function setQuery(question) {if (viewingHistory && !chatBusy) newChat(); showView('assistant'); $('question').value = question; $('question').setCustomValidity(''); resizeQuestion(); $('question').focus();}
document.querySelectorAll('[data-query]').forEach(button => button.addEventListener('click', () => setQuery(button.dataset.query)));

async function api(path, options) {
  const headers = {...options?.headers};
  if (adminToken) headers.Authorization = `Bearer ${adminToken}`;
  const response = await fetch(path, {...options, headers});
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
    ${inAnswer ? noteTooltip(`Limit: ${record.limitations}\nSynthetic · ${record.provenance}`, 'Source notes') : `<p><strong>Limit:</strong> ${r.limitations}</p><p class="muted">Synthetic · ${r.provenance}</p>`}
    ${inAnswer || !canUpdateRecords() ? '' : `<button type="button" class="text-button" id="edit-${r.id}" data-edit-record="${r.id}" ${editingRecord ? 'disabled' : ''}>Edit record</button>`}
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

function formatAnswer(value) {
  // Escape model output before adding the small set of supported HTML tags.
  const inline = text => escapeHtml(text).replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  const blocks = [];
  let paragraph = [], items = [], listType = null;
  const flushParagraph = () => {
    if (paragraph.length) blocks.push(`<p>${paragraph.map(inline).join('<br>')}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (items.length) blocks.push(`<${listType}>${items.map(item => `<li>${inline(item)}</li>`).join('')}</${listType}>`);
    items = [];
    listType = null;
  };
  for (const line of String(value ?? '').replace(/\r\n?/g, '\n').split('\n')) {
    const bullet = line.match(/^\s*[-*+]\s+(.+)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (bullet || numbered) {
      flushParagraph();
      const type = bullet ? 'ul' : 'ol';
      if (listType && listType !== type) flushList();
      listType = type;
      items.push((bullet || numbered)[1]);
    } else if (!line.trim()) {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line);
    }
  }
  flushParagraph();
  flushList();
  return blocks.join('');
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
    <p>${escapeHtml(source.content)}</p>${noteTooltip(`External search excerpt · retrieved ${source.retrieved_at}. Retrieval time is not a publication date.`, 'Web source notes')}</details>`;
}

function renderResponse(result) {
  const generated = result.mode === 'qwen';
  const webSources = result.web_sources || [];
  const webEnabled = Boolean(result.web_search?.enabled);
  const referenceCount = result.sources.length + webSources.length;
  const computed = result.mode === 'data';
  const title = result.status === 'insufficient' ? 'Insufficient evidence' : generated ? 'AI response' : computed ? 'Dataset results' : 'Retrieved excerpts';
  const answerNotes = [
    generated ? 'The configured Ollama model generated this answer from the supplied dataset and any external references shown below. Valid source IDs do not guarantee that every claim is supported.' : computed ? 'This response was computed directly from all matching dataset records. Rankings use numeric metric values.' : 'This response contains retrieved excerpts, without LLM-generated analysis.',
    result.context_turns ? `This answer used ${result.context_turns} previous conversation${result.context_turns === 1 ? '' : 's'} from this session for context. Evidence was retrieved again for this question.` : '',
    'Dataset observations are synthetic examples. External web references provide separate context and do not validate the invented measurements. Check source dates, values and limitations; dataset rankings describe only the bundled sample records.',
  ].filter(Boolean).join('\n\n');
  return `<article class="response-primary" aria-label="${title}">
      <div class="answer-header"><div><span class="eyebrow">YOUR ANSWER</span><h2>${title}</h2></div><span class="tag response-mode ${generated ? 'generated' : ''}">${generated ? 'AI GENERATED' : computed ? 'DATASET RESULTS' : 'EXCERPT MODE'}</span></div>
      <p class="response-question">${escapeHtml(result.question)}</p>
      <div class="answer-text">${formatAnswer(responseContent(result))}</div>
      <div class="response-context"><span class="tag">${webSources.length ? result.sources.length ? 'DATASET + WEB' : 'WEB REFERENCES' : 'SYNTHETIC DATA'}</span><span>${referenceCount} reference${referenceCount === 1 ? '' : 's'} retrieved</span>${noteTooltip(answerNotes, 'About this answer')}${webEnabled ? noteTooltip(webSources.length ? 'Web search completed.' : 'Web search unavailable or no results.', 'Web search status') : ''}${result.notice ? noteTooltip(result.notice, 'Response notice') : ''}</div>
    </article>
    <div class="response-support" aria-label="Answer details">
      <details class="response-detail"><summary><span>References <span class="reference-count">${referenceCount}</span></span>${noteTooltip('Inspect the dataset records and external web sources used for this answer.', 'About references')}</summary><div class="detail-content">
        ${result.sources.length ? `<h3 class="reference-section-title">Dataset records · synthetic</h3>${result.sources.map(r => sourceCard(r, true)).join('')}` : '<p>No matching dataset records were retrieved.</p>'}
        ${webSources.length ? `<h3 class="reference-section-title">Web references · external search excerpts</h3>${webSources.map(webSourceCard).join('')}` : ''}
        </div></details>
      <div class="answer-actions"><button type="button" data-export-answer class="text-button">Download response and references ↓</button></div>
    </div>`;
}
const emptyChat = $('answer-panel').innerHTML;
function renderConversations() {
  $('answer-panel').innerHTML = conversations.length ? conversations.map((result, index) =>
    `<section class="chat-exchange" data-exchange="${index}" aria-label="Conversation ${index + 1}">${renderResponse(result)}</section>`).reverse().join('') : emptyChat;
}
function setChatBusy(busy) {
  chatBusy = busy;
  $('ask-button').disabled = busy;
  $('new-chat').disabled = busy;
  $('continue-chat').disabled = busy;
  $('history-list').inert = busy;
}
function newChat() {
  if (chatBusy) return;
  chatSessionId = null;
  conversations = [];
  latest = null;
  viewingHistory = false;
  $('continue-chat').hidden = true;
  $('question-form').hidden = false;
  document.querySelector('.suggestions').hidden = false;
  $('chat-status').textContent = 'New session · ask a question to begin.';
  $('question').value = '';
  resizeQuestion();
  renderConversations();
  $('question').focus();
}
async function loadHistory(append = false) {
  if (historyLoading) return;
  historyLoading = true;
  $('history-status').classList.add('sr-only');
  $('history-status').textContent = 'Loading history…';
  try {
    const page = await api(`/api/history?offset=${append ? historyOffset : 0}`);
    const html = page.sessions.map(session => `<button type="button" class="history-entry" data-history-id="${escapeHtml(session.id)}">
      <strong>${escapeHtml(session.title)}</strong><span>${escapeHtml(new Date(session.updated_at).toLocaleString())} · ${session.conversation_count} conversation${session.conversation_count === 1 ? '' : 's'}</span></button>`).join('');
    if (append) $('history-list').insertAdjacentHTML('beforeend', html);
    else $('history-list').innerHTML = html;
    historyOffset = page.next_offset;
    $('more-history').hidden = historyOffset === null;
    $('history-status').textContent = $('history-list').children.length ? 'Select a session to view its saved questions, answers and references.' : 'No saved conversations yet.';
  } catch (error) {
    $('history-status').classList.remove('sr-only');
    $('history-status').textContent = error.message;
  } finally { historyLoading = false; }
}
$('new-chat').addEventListener('click', newChat);
$('continue-chat').addEventListener('click', () => {
  if (chatBusy) return;
  viewingHistory = false;
  $('continue-chat').hidden = true;
  $('question-form').hidden = false;
  document.querySelector('.suggestions').hidden = false;
  $('chat-status').textContent = 'Continuing this shared session · follow-up questions use its recent conversation.';
  $('question').value = '';
  resizeQuestion();
  $('question').focus();
});
$('refresh-history').addEventListener('click', () => loadHistory());
$('more-history').addEventListener('click', () => loadHistory(true));
$('history-panel').addEventListener('toggle', () => { if ($('history-panel').open) loadHistory(); });
$('history-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-history-id]');
  if (!button || chatBusy) return;
  setChatBusy(true);
  try {
    const session = await api(`/api/history/${button.dataset.historyId}`);
    conversations = session.conversations;
    latest = conversations.at(-1) || null;
    viewingHistory = true;
    chatSessionId = session.id;
    $('continue-chat').hidden = false;
    $('question-form').hidden = true;
    document.querySelector('.suggestions').hidden = true;
    $('chat-status').textContent = `Saved session: ${session.title} · Choose Continue this session for a follow-up, or New chat to start fresh. Answers reflect the evidence saved at the time.`;
    renderConversations();
  } catch (error) { $('history-status').classList.remove('sr-only'); $('history-status').textContent = error.message; }
  finally { setChatBusy(false); }
});
$('answer-panel').addEventListener('click', event => {
  const button = event.target.closest('[data-export-answer]');
  if (!button) return;
  const result = conversations[Number(button.closest('[data-exchange]').dataset.exchange)];
  download('spacelab-response.json', {...result, synthetic:!(result.web_sources?.length), dataset_synthetic:true, exported_at:new Date().toISOString()});
});
$('question-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (chatBusy || viewingHistory || !permissionsReady) return;
  const question = $('question').value.trim();
  if (question.length < 3) {$('question').setCustomValidity('Please enter at least 3 characters.'); $('question').reportValidity(); return;}
  setChatBusy(true);
  const useWeb = $('web-search').checked;
  $('ask-button').textContent = useWeb ? 'Searching…' : 'Retrieving…';
  $('answer-panel').setAttribute('aria-busy','true');
  renderConversations();
  $('answer-panel').insertAdjacentHTML('afterbegin', `<div class="loading">${useWeb ? 'Searching the web and retrieving dataset evidence…' : 'Retrieving source records and preparing your answer…'}</div>`);
  const requestVersion = dataVersion;
  try {
    latest = await api('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question, mode:$('engine').value, theme:$('topic').value, style:$('style').value, web_search:useWeb, ...(chatSessionId ? {session_id:chatSessionId} : {})})});
    chatSessionId = latest.session_id;
    conversations.push(latest);
    renderConversations();
    $('chat-status').textContent = `Current session · ${conversations.length} saved conversation${conversations.length === 1 ? '' : 's'}.${requestVersion !== dataVersion ? ' The dataset changed during this answer; ask again for current values.' : ''}`;
    $('question').value = '';
    resizeQuestion();
    if ($('history-panel').open) loadHistory();
  } catch (error) {
    renderConversations();
    $('answer-panel').insertAdjacentHTML('afterbegin', `<div class="response-primary"><h2>Could not complete this conversation</h2><p class="error">${escapeHtml(error.message)}</p>${noteTooltip('Submit your question again. Previously saved conversations remain in history.', 'Retry information')}</div>`);
  } finally {
    setChatBusy(false); $('ask-button').innerHTML = 'Find insights <span>↗</span>';
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
    return `<path d="${path}" fill="#25385b" stroke="#647aaa" stroke-width="0.8" fill-rule="evenodd" stroke-linejoin="round"/>`;
  }).join('');
}

function renderExplorer() {
  const query = $('data-search').value.toLowerCase();
  const theme = $('data-theme').value;
  const filtered = records.filter(r => (theme === 'all' || r.theme === theme) && JSON.stringify(r).toLowerCase().includes(query));
  $('record-summary').textContent = `${filtered.length} of ${records.length} observations · expand an application group, then a record`;
  const openGroups = new Set([...$('records-list').querySelectorAll('[data-record-group][open]')].map(group => group.dataset.recordGroup));
  const applications = {flood:'Flood monitoring', vegetation:'Vegetation', 'land-use':'Land-use change', coastal:'Coastal observations'};
  $('records-list').innerHTML = Object.entries(applications).map(([key, label]) => {
    const members = filtered.filter(record => record.theme === key);
    if (!members.length) return '';
    const open = openGroups.has(key) || editingRecord?.theme === key || theme !== 'all' || Boolean(query);
    return `<details class="record-group" data-record-group="${key}" ${open ? 'open' : ''}><summary>${label}<span class="reference-count">${members.length} observations</span></summary><div class="record-group-content">${members.map(record => sourceCard(record)).join('')}</div></details>`;
  }).join('') || '<div class="card">No records match. Try another search or application.</div>';
  const sites = [...new Map(filtered.map(r => [JSON.stringify([r.location, r.state, r.longitude, r.latitude]), r])).values()];
  const points = sites.map(r => {
    const [x, y] = projectLocation(r.longitude, r.latitude);
    const labelX = x > 390 ? x-9 : x+9;
    const label = escapeHtml(`${r.location}, ${r.state}`);
    return `<g class="map-point" tabindex="0" role="img" aria-label="${label}: ${r.latitude}, ${r.longitude}"><title>${label}: ${r.latitude}, ${r.longitude}</title><circle cx="${x}" cy="${y}" r="5" fill="#818cf8" stroke="white" stroke-width="2"/><text class="map-label" x="${labelX}" y="${y-10}" text-anchor="${x>390?'end':'start'}" fill="#e2e8f0" font-size="12" stroke="white" stroke-width="3" paint-order="stroke">${label}</text></g>`;
  }).join('');
  $('location-map').innerHTML = `<defs><pattern id="grid" width="50" height="50" patternUnits="userSpaceOnUse"><path d="M 50 0 L 0 0 0 50" fill="none" stroke="#ffffff1a" stroke-width="1"/></pattern></defs><rect width="500" height="480" fill="url(#grid)"/><text x="25" y="25" font-size="11" fill="#b3bfd4">N ↑</text><text x="25" y="50" font-size="12" fill="#e2e8f0">Peninsular Malaysia</text><text x="275" y="50" font-size="12" fill="#e2e8f0">East Malaysia</text><path d="M250 65V430" stroke="#ffffff1a" stroke-dasharray="4 4"/><text x="25" y="458" font-size="10" fill="#b3bfd4">99–105° E · 0.5–7.5° N</text><text x="275" y="458" font-size="10" fill="#b3bfd4">109–120° E · 0.5–7.5° N</text><g aria-hidden="true" pointer-events="none">${outlinePaths()}</g>${points}`;
}
function setEditorControls() {
  $('data-theme').disabled = Boolean(editingRecord) || importingCsv;
  $('data-search').disabled = Boolean(editingRecord) || importingCsv;
  $('csv-file').disabled = Boolean(editingRecord) || importingCsv || !datasetReady || !canUpdateRecords();
  $('csv-import-button').disabled = Boolean(editingRecord) || importingCsv || !datasetReady || !canUpdateRecords();
  $('records-list').querySelectorAll('[data-edit-record]').forEach(button => {button.disabled = Boolean(editingRecord) || importingCsv;});
}

$('records-list').addEventListener('input', event => {
  if (editingRecord && event.target.name) editDraft[event.target.name] = event.target.value;
});
$('records-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-edit-record], [data-cancel-edit]');
  if (!button || savingRecord || importingCsv) return;
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
  if (editingRecord || !canUpdateRecords()) return;
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
  if (savingRecord || !canUpdateRecords() || !form.reportValidity()) return;
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
    $('chat-status').textContent = 'The dataset was updated. Saved answers retain their original evidence; ask a new question to use the updated values.';
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
$('csv-import-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (editingRecord || importingCsv || !datasetReady || !canUpdateRecords()) return;
  const file = $('csv-file').files[0];
  if (!file) return;
  const status = $('csv-import-status');
  status.classList.remove('error');
  if (file.size > 2 * 1024 * 1024 || !file.size) {
    status.classList.add('error');
    status.textContent = 'Choose a non-empty CSV file up to 2 MB.';
    return;
  }
  importingCsv = true;
  setEditorControls();
  $('csv-import-form').setAttribute('aria-busy', 'true');
  status.textContent = 'Validating and saving CSV…';
  try {
    const result = await api('/api/records/import', {method:'POST', headers:{'Content-Type':'text/csv; charset=utf-8'}, body:await file.text()});
    records = result.records;
    dataVersion += 1;
    $('chat-status').textContent = 'The dataset was updated. Saved answers retain their original evidence; ask a new question to use the updated values.';
    document.querySelectorAll('.record-count').forEach(el => {el.textContent = records.length;});
    document.querySelectorAll('.location-count').forEach(el => {el.textContent = new Set(records.map(r => r.location)).size;});
    status.textContent = `CSV saved: ${result.updated} updated, ${result.added} added. Answers, map and downloads now use these records.`;
    $('csv-file').value = '';
    renderExplorer();
  } catch (error) {
    status.classList.add('error');
    status.textContent = error.message;
  } finally {
    importingCsv = false;
    $('csv-import-form').removeAttribute('aria-busy');
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
    await refreshPermissions();
    records = await api('/api/records');
    document.querySelectorAll('.record-count').forEach(el => {el.textContent=records.length;});
    document.querySelectorAll('.location-count').forEach(el => {el.textContent=new Set(records.map(r => r.location)).size;});
    datasetReady = true;
    setEditorControls();
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
function applyPermissions() {
  const locked = !permissionsReady || permissions.excerpt_only;
  $('engine').querySelector('[value="qwen"]').disabled = locked;
  $('engine').disabled = locked;
  $('web-search').disabled = locked;
  if (locked) { $('engine').value = 'offline'; $('web-search').checked = false; }
  updateWebSearchHint();
  $('admin-login-form').hidden = isAdmin;
  $('admin-controls').hidden = !isAdmin;
  $('excerpt-only').checked = permissions.excerpt_only;
  $('allow-record-updates').checked = permissions.allow_record_updates;
  document.querySelector('.csv-import-panel').hidden = !canUpdateRecords();
  if (datasetReady) {
    renderExplorer();
    if (editingRecord && !canUpdateRecords()) {
      $('edit-status').textContent = 'Record updates are now disabled. Your draft cannot be saved.';
      $('records-list').querySelectorAll('[data-record-editor] input, [data-record-editor] select, [data-record-editor] textarea, [data-record-editor] [type="submit"]').forEach(control => {control.disabled = true;});
    }
  }
  setEditorControls();
}
function clearAdminSession() {
  adminToken = '';
  isAdmin = false;
  try { localStorage.removeItem(ADMIN_STORAGE_KEY); } catch (error) { /* Storage may be unavailable. */ }
}
async function refreshPermissions() {
  const requestedToken = adminToken;
  const [settings, session] = await Promise.all([api('/api/settings'), api('/api/admin/session')]);
  if (requestedToken !== adminToken) return;
  const changed = !permissionsReady || isAdmin !== session.admin || JSON.stringify(permissions) !== JSON.stringify(settings);
  permissions = settings;
  permissionsReady = true;
  isAdmin = session.admin;
  if (!isAdmin) clearAdminSession();
  if (changed) applyPermissions();
}
$('admin-login-form').addEventListener('submit', async event => {
  event.preventDefault();
  $('admin-login-button').disabled = true;
  try {
    const result = await api('/api/admin/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:$('admin-password').value})});
    adminToken = result.token;
    let saved = true;
    try { localStorage.setItem(ADMIN_STORAGE_KEY, adminToken); } catch (error) { saved = false; }
    await refreshPermissions();
    $('admin-status').textContent = saved ? 'Signed in as admin in this browser.' : 'Signed in for this page. Browser storage is unavailable.';
  } catch (error) { $('admin-status').textContent = error.message; }
  finally { $('admin-password').value = ''; $('admin-login-button').disabled = false; }
});
$('admin-settings-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.target.querySelector('button');
  button.disabled = true;
  try {
    permissions = await api('/api/admin/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({excerpt_only:$('excerpt-only').checked, allow_record_updates:$('allow-record-updates').checked})});
    applyPermissions();
    $('admin-status').textContent = 'Settings saved for all users.';
  } catch (error) { $('admin-status').textContent = error.message; }
  finally { button.disabled = false; }
});
$('admin-signout').addEventListener('click', async () => {
  const token = adminToken;
  clearAdminSession();
  applyPermissions();
  try {
    await api('/api/admin/logout', {method:'POST', headers:{'Content-Type':'application/json', Authorization:`Bearer ${token}`}, body:'{}'});
    $('admin-status').textContent = 'Signed out. Admin access was removed from this browser.';
  } catch (error) { $('admin-status').textContent = 'Browser sign-in cleared. Could not revoke the server session; it will expire automatically.'; }
});
window.addEventListener('storage', event => {
  if (event.key === ADMIN_STORAGE_KEY || event.key === null) {
    try { adminToken = localStorage.getItem(ADMIN_STORAGE_KEY) || ''; } catch (error) { adminToken = ''; }
    isAdmin = false;
    applyPermissions();
    refreshPermissions().catch(() => {});
  }
});
// Enforce on the server immediately; refresh other browsers' controls regularly.
setInterval(() => {
  if (!document.hidden && !savingRecord && !importingCsv && document.activeElement?.closest('#admin-settings-form') === null) {
    refreshPermissions().catch(() => {});
  }
}, 15000);
applyPermissions();
loadHistory();
init();

/* The server owns the round clock, registration lock and scoring. */
(() => {
  const key = 'spacelab.quizPlayer';
  let token = '', state = null, offset = 0, busy = false, polling = false, version = 0;
  let stageKey = '', adminKey = '', adminState = null, initialHash = window.quizRequested ? '#quiz' : location.hash;
  try { token = localStorage.getItem(key) || ''; } catch (_) { /* In-memory session works too. */ }
  const escape = value => escapeHtml(String(value));
  const post = (path, body) => api(path, {method:'POST', headers:{'Content-Type':'application/json', 'X-Quiz-Token':token}, body:JSON.stringify(body)});
  const now = () => Date.now() / 1000 + offset;
  const formatTime = milliseconds => `${(milliseconds / 1000).toFixed(3)}s`;
  const correctTime = result => `${formatTime(result.correct_time_ms)}${result.timing_estimated ? ' (estimated)' : ''}`;
  function accept(next) {
    const phaseChanged = state?.phase !== next.phase;
    state = next;
    offset = next.server_time - Date.now() / 1000;
    window.quizEnabled = next.enabled;
    document.querySelector('[data-view="quiz"]').hidden = !next.enabled;
    if (!next.enabled && !$('view-quiz').hidden) showView('assistant');
    if ((initialHash === '#quiz' && next.enabled) || (phaseChanged && next.enabled && next.player && next.phase !== 'lobby')) showView('quiz');
    if (phaseChanged && next.result) $('quiz-message').textContent = `Quiz complete: ${next.result.score} out of ${next.result.total}. Your result is saved.`;
    initialHash = '';
    render();
  }
  function render() {
    if (!state) return;
    const signature = JSON.stringify(state.question ? [state.enabled, state.player, state.question] : [state.enabled, state.phase, state.player, state.registered, state.starts_at, state.result]);
    if (signature === stageKey) return;
    stageKey = signature;
    const stage = $('quiz-stage');
    const previousQuestion = stage.dataset.question;
    stage.dataset.question = state.question ? String(state.question.index) : '';
    stage.removeAttribute('aria-label');
    if (!state.enabled) {
      stage.innerHTML = '<h2>The quiz is currently disabled.</h2>';
    } else if (state.result) {
      const r = state.result;
      stage.innerHTML = `<span class="tag">ROUND COMPLETE</span><h2 id="quiz-complete" tabindex="-1">Well played, ${escape(r.name)}!</h2><div class="quiz-score">${r.score}<small> / ${r.total}</small></div><p>${r.percentage}% correct. <strong>Rank #${r.rank}</strong> · Correct-answer time: <strong>${correctTime(r)}</strong>. Your result is saved. Wait for the admin to reset the round before joining again.</p>${r.timing_estimated ? '<p>Older untimed correct answers use their full question allowance.</p>' : ''}<p>Rankings use correct-answer count first, then the lowest total time on correct answers.</p>${review(r)}`;
      stage.setAttribute('aria-label', `Quiz complete. ${r.name}, ${r.score} out of ${r.total}.`);
    } else if (state.question) {
      const q = state.question;
      const shapes = ['▲', '◆', '●', '■'];
      stage.innerHTML = `<div class="quiz-topline"><span class="tag">ROUND ${q.round} · QUESTION ${q.index+1} / ${state.total} · ${q.seconds}s</span><span>${escape(state.player.name)}</span><strong id="quiz-clock" role="timer" aria-label="Seconds remaining"></strong></div><div class="quiz-time-track"><div id="quiz-time-bar"></div></div><h2 tabindex="-1" id="quiz-question">${escape(q.question)}</h2><div class="quiz-options" role="group" aria-label="Answer choices">${q.options.map((text, i) => `<button type="button" class="quiz-option quiz-color-${i}" data-choice="${i}" aria-pressed="${q.selected === i}" ${q.selected != null ? 'disabled' : ''}><span aria-hidden="true">${shapes[i]}</span><span>${String.fromCharCode(65+i)}. ${escape(text)}</span><span class="quiz-chosen">${q.selected === i ? '✓' : ''}</span></button>`).join('')}</div><p class="quiz-save-note">${q.selected == null ? 'Choose carefully: your first answer is final. No answer = 0 points.' : 'Answer locked. Waiting for the next question.'}</p>`;
      stage.querySelectorAll('[data-choice]').forEach(button => button.addEventListener('click', () => choose(q.index, Number(button.dataset.choice))));
    } else if (state.player) {
      stage.innerHTML = `<div class="quiz-lobby-icon" aria-hidden="true">✦</div><span class="tag">${state.starts_at ? 'GET READY' : 'YOU’RE IN'}</span><h2>${escape(state.player.name)}, ${state.starts_at ? 'the quiz is starting!' : 'welcome to the lobby.'}</h2><p>${state.registered} player${state.registered === 1 ? '' : 's'} registered. ${state.starts_at ? '<strong id="quiz-countdown" role="timer"></strong>' : 'Waiting for the admin to start everyone together.'}</p><p>Your place is saved in this browser. Questions last 10–20 seconds depending on difficulty; unanswered questions score zero. Equal scores are ranked by the fastest total time on correct answers.</p>`;
    } else if (state.phase !== 'lobby') {
      stage.innerHTML = '<span class="tag">REGISTRATION CLOSED</span><h2>This round has already started.</h2><p>Only players who joined before the start can take part. The admin can reset the round to reopen registration.</p>';
    } else {
      stage.innerHTML = `<span class="tag">JOIN THE CHALLENGE</span><h2>Ready for launch?</h2><p>${state.registered} player${state.registered === 1 ? '' : 's'} in the lobby. Enter your name, then wait for the host.</p><form id="quiz-join"><label for="quiz-name">Your name</label><input id="quiz-name" name="name" maxlength="60" autocomplete="name" placeholder="Enter your name" required><button class="primary" type="submit">Join the showdown →</button></form><p>One entry per name and browser per round. Use a distinct name if another player shares yours. Stay on this page when the host starts.</p>`;
      $('quiz-join').addEventListener('submit', join);
    }
    if (!$('view-quiz').hidden) {
      if (state.result) $('quiz-complete').focus({preventScroll:true});
      else if (state.question && previousQuestion !== String(state.question.index)) $('quiz-question').focus({preventScroll:true});
    }
    tick();
  }
  function review(result) {
    return `<details class="quiz-review"><summary>Review all ${result.total} answers</summary>${result.review.map((r, i) => `<div class="quiz-review-item"><strong>${i+1}. ${escape(r.question)} · ${r.correct ? '✓ Correct' : '✕ Wrong'}</strong><p>Your answer: ${r.selected == null ? 'No answer' : escape(r.options[r.selected])}<br>Correct answer: ${escape(r.options[r.answer])}</p><p>Response time: ${r.response_time_ms != null ? formatTime(r.response_time_ms) : r.selected == null ? 'No answer' : 'Not recorded (older answer)'}</p><p>${escape(r.explanation)}</p></div>`).join('')}</details>`;
  }
  async function join(event) {
    event.preventDefault();
    if (busy) return;
    // Do not enroll a player if their identity cannot survive a refresh.
    try { localStorage.setItem(key, token); } catch (_) {
      $('quiz-message').textContent = 'Allow browser storage before joining so your entry can be restored after a refresh.';
      return;
    }
    busy = true; version++;
    const button = event.target.querySelector('button');
    button.disabled = true;
    try {
      const next = await post('/api/quiz/register', {name:$('quiz-name').value});
      token = next.token;
      localStorage.setItem(key, token);
      $('quiz-message').textContent = 'Registered. Keep this browser open for the host’s start.';
      accept(next);
    } catch (error) { $('quiz-message').textContent = error.message; }
    finally { busy = false; button.disabled = false; }
  }
  async function choose(index, selected) {
    if (busy || !state?.question || state.question.index !== index || state.question.selected != null || now() >= state.question.deadline) return;
    busy = true; version++;
    $('quiz-stage').querySelectorAll('[data-choice]').forEach(b => { b.disabled = true; });
    try {
      accept(await post('/api/quiz/answer', {index, selected}));
      $('quiz-message').textContent = 'Answer locked. You cannot change your choice.';
    } catch (error) { $('quiz-message').textContent = error.message; }
    finally {
      busy = false;
      $('quiz-stage').querySelectorAll('[data-choice]').forEach(b => { b.disabled = !state.question || state.question.selected != null || now() >= state.question.deadline; });
      poll();
    }
  }
  function tick() {
    if (state?.question && $('quiz-clock')) {
      const remaining = Math.max(0, state.question.deadline - now());
      $('quiz-clock').textContent = `${Math.ceil(remaining)}s`;
      $('quiz-time-bar').style.width = `${remaining / state.question.seconds * 100}%`;
      if (!remaining) $('quiz-stage').querySelectorAll('[data-choice]').forEach(b => { b.disabled = true; });
    }
    if (state?.starts_at && $('quiz-countdown')) $('quiz-countdown').textContent = `Starting in ${Math.max(0, Math.ceil(state.starts_at - now()))}…`;
  }
  function renderAdmin(next) {
    adminState = next;
    // Ignore server_time so expanded answer reviews stay open on refresh.
    const stable = JSON.stringify({...next, server_time:0});
    if (stable === adminKey) return;
    adminKey = stable;
    $('quiz-toggle').textContent = next.enabled ? 'Disable quiz' : 'Enable quiz';
    $('quiz-start').disabled = !next.enabled || next.phase !== 'lobby' || !next.registered || busy;
    $('quiz-admin-status').textContent = `${next.enabled ? 'Visible to everyone' : 'Disabled / hidden'} · ${next.phase} · ${next.registered} registered player${next.registered === 1 ? '' : 's'}`;
    $('quiz-admin-results').innerHTML = next.players.length ? `<p>Players with the most correct answers rank first. Equal scores use the lowest total time on correct answers; identical scores and times share a rank.</p><div class="quiz-table-wrap"><table class="quiz-results-table"><caption>${next.phase === 'finished' ? 'Final leaderboard' : 'Registered players · results appear when the round ends'}</caption><thead><tr><th scope="col">Rank</th><th scope="col">Player</th><th scope="col">Answered</th><th scope="col">Score</th><th scope="col">Correct-answer time</th></tr></thead><tbody>${next.players.map(p => `<tr><td>${p.result ? `#${p.result.rank}` : '—'}</td><td>${escape(p.name)}</td><td>${p.answered} / ${next.total}</td><td>${p.result ? `${p.result.score} / ${p.result.total} (${p.result.percentage}%)` : 'Pending'}</td><td>${p.result ? correctTime(p.result) : 'Pending'}</td></tr>`).join('')}</tbody></table></div>${next.players.some(p => p.result?.timing_estimated) ? '<p>Estimated times include the full question allowance for older untimed correct answers.</p>' : ''}${next.players.filter(p => p.result).map(p => `<details class="quiz-player-review"><summary>#${p.result.rank} · ${escape(p.name)} · ${p.result.score} / ${next.total} · ${correctTime(p.result)}</summary>${review(p.result)}</details>`).join('')}` : '<p>No players registered yet.</p>';
  }
  async function control(action, enabled) {
    if (busy) return;
    if (action === 'reset' && !confirm('Delete all quiz registrations, answers and results, then reopen the lobby? This cannot be undone.')) return;
    busy = true; version++;
    document.querySelectorAll('.quiz-actions button').forEach(b => { b.disabled = true; });
    try {
      renderAdmin(await post('/api/admin/quiz', {action, enabled}));
      stageKey = '';
      $('quiz-message').textContent = '';
    } catch (error) { $('quiz-admin-status').textContent = error.message; }
    finally {
      busy = false;
      document.querySelectorAll('.quiz-actions button').forEach(b => { b.disabled = false; });
      if (adminState) $('quiz-start').disabled = !adminState.enabled || adminState.phase !== 'lobby' || !adminState.registered;
      poll();
    }
  }
  async function poll() {
    if (polling || busy) return;
    polling = true;
    const requestVersion = version;
    try {
      const next = await api('/api/quiz', {headers:{'X-Quiz-Token':token}});
      if (requestVersion !== version) return;
      // Avoid replacing the registration form while someone is typing.
      if (!state || state.player || next.player || state.phase !== next.phase || state.enabled !== next.enabled || !$('quiz-name') || document.activeElement !== $('quiz-name')) accept(next);
      if (isAdmin && !$('view-admin').hidden) {
        const nextAdmin = await api('/api/admin/quiz');
        if (requestVersion === version && isAdmin) renderAdmin(nextAdmin);
      }
    } catch (error) {
      if (!$('view-quiz').hidden) $('quiz-message').textContent = `Connection interrupted: ${error.message} The quiz clock continues; reconnect before the deadline to save answers.`;
    } finally { polling = false; }
  }
  $('quiz-toggle').addEventListener('click', () => control('visibility', !adminState?.enabled));
  $('quiz-start').addEventListener('click', () => control('start'));
  $('quiz-reset').addEventListener('click', () => control('reset'));
  window.addEventListener('quiz-permissions', () => {
    if (!isAdmin) { adminState = null; adminKey = ''; $('quiz-admin-results').replaceChildren(); }
    poll();
  });
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) {
      try { token = localStorage.getItem(key) || ''; } catch (_) { token = ''; }
      version++; stageKey = ''; poll();
    }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  setInterval(tick, 100);
  setInterval(poll, 750);
  poll();
})();

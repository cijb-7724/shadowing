const jobsContainer = document.querySelector('#jobs');
const reviewPanel = document.querySelector('#review-panel');
const sentenceEditor = document.querySelector('#sentence-editor');
let activeDraft = null;
let pollTimer = null;

const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
})[char]);

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data?.error || data?.message || `Request failed (${response.status})`);
  return data;
}

function toast(message) {
  const element = document.querySelector('#toast');
  element.textContent = message;
  element.hidden = false;
  setTimeout(() => { element.hidden = true; }, 3600);
}

async function loadStatus() {
  const status = await api('../api/status');
  const items = [
    ['yt-dlp', status.ytDlp], ['FFmpeg', status.ffmpeg], ['Whisper', status.whisper],
    ['語彙辞書', status.wordfreq],
    [`Ollama (${status.ollamaModel})`, status.ollama]
  ];
  document.querySelector('#dependency-status').innerHTML = items.map(([name, ready]) =>
    `<span class="status-chip ${ready ? '' : 'missing'}">${ready ? '✓' : '!'} ${escapeHtml(name)}</span>`
  ).join('');
}

function renderJobs(jobs) {
  if (!jobs.length) {
    jobsContainer.innerHTML = '<p class="muted">ジョブはまだありません。</p>';
    return;
  }
  const statusLabels = {
    queued: '待機中', running: '生成中', review: '要確認・未公開',
    published: '公開済み', failed: '失敗'
  };
  jobsContainer.innerHTML = jobs.map((job) => `
    <article class="job ${escapeHtml(job.status)}">
      <div class="job-top"><span>${escapeHtml(job.videoId)}</span><span>${escapeHtml(statusLabels[job.status] || job.status)}</span></div>
      <p class="job-message">${escapeHtml(job.message)}</p>
      ${job.status === 'review' ? '<p class="job-hint">まだ動画一覧には表示されていません。</p>' : ''}
      <div class="progress"><span style="width:${Math.max(0, Math.min(100, Number(job.progress || 0)))}%"></span></div>
      ${job.status === 'review' ? `<button class="review-button" type="button" data-review="${escapeHtml(job.videoId)}">内容を確認して公開</button>` : ''}
      ${job.status === 'published' ? `<a class="public-button" href="../video.html?id=${encodeURIComponent(job.videoId)}">学習ページを開く</a>` : ''}
      ${job.status === 'failed' ? `<button class="retry-button" type="button" data-retry="${escapeHtml(job.id)}">再実行</button>` : ''}
    </article>
  `).join('');
}

async function loadJobs() {
  const jobs = await api('../api/jobs');
  renderJobs(jobs);
  const running = jobs.some((job) => ['queued', 'running'].includes(job.status));
  clearTimeout(pollTimer);
  if (running) pollTimer = setTimeout(loadJobs, 1800);
}

document.querySelector('#add-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    await api('../api/jobs', { method: 'POST', body: JSON.stringify({ url: event.target.url.value }) });
    event.target.reset();
    toast('処理を開始しました。');
    loadJobs();
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});

document.querySelector('#refresh-jobs').addEventListener('click', loadJobs);
jobsContainer.addEventListener('click', (event) => {
  const retry = event.target.closest('[data-retry]');
  if (retry) return retryJob(retry.dataset.retry, retry);
  const job = event.target.closest('[data-review]');
  if (job) openReview(job.dataset.review);
});

async function retryJob(jobId, button) {
  button.disabled = true;
  try {
    await api(`../api/retry/${encodeURIComponent(jobId)}`, { method: 'POST' });
    toast('同じURLで再実行しました。');
    loadJobs();
  } catch (error) {
    toast(error.message);
    button.disabled = false;
  }
}

const vocabToText = (vocab) => (vocab || []).map((item) =>
  [item.term, item.meaning, item.level, item.note].map((value) => String(value || '').replaceAll('|', '｜')).join(' | ')
).join('\n');

const textToVocab = (text) => text.split('\n').map((line) => {
  const [term = '', meaning = '', level = '', note = ''] = line.split('|').map((part) => part.trim().replaceAll('｜', '|'));
  return { term, meaning, level, note };
}).filter((item) => item.term);

function renderDraft() {
  document.querySelector('#review-title').textContent = activeDraft.title;
  const reviewCount = activeDraft.sentences.filter((item) => item.needsReview).length;
  document.querySelector('#review-summary').innerHTML = `
    <span class="summary-chip">${activeDraft.sentences.length} 文</span>
    <span class="summary-chip">${escapeHtml(activeDraft.transcriptSource)}</span>
    <span class="summary-chip">要確認 ${reviewCount} 文</span>
  `;
  sentenceEditor.innerHTML = activeDraft.sentences.map((item, index) => `
    <article class="editor-row ${item.needsReview ? 'needs-review' : ''}" data-index="${index}">
      <div>
        <div class="editor-number">#${index + 1}</div>
        <label class="editor-time">再生秒<input data-field="playFrom" type="number" min="0" step="0.1" value="${Number(item.playFrom || 0)}"></label>
      </div>
      <div class="editor-field en"><label>英文</label><textarea data-field="en">${escapeHtml(item.en)}</textarea></div>
      <div class="editor-field jp"><label>日本語</label><textarea data-field="jp">${escapeHtml(item.jp)}</textarea></div>
      <div class="editor-field vocab-editor"><label>語彙</label><textarea data-field="vocab">${escapeHtml(vocabToText(item.vocab))}</textarea></div>
    </article>
  `).join('');
  reviewPanel.hidden = false;
  reviewPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function openReview(videoId) {
  try {
    activeDraft = await api(`../api/drafts/${encodeURIComponent(videoId)}`);
    renderDraft();
  } catch (error) {
    toast(error.message);
  }
}

function collectDraft() {
  sentenceEditor.querySelectorAll('[data-index]').forEach((row) => {
    const item = activeDraft.sentences[Number(row.dataset.index)];
    item.playFrom = Number(row.querySelector('[data-field="playFrom"]').value);
    item.en = row.querySelector('[data-field="en"]').value.trim();
    item.jp = row.querySelector('[data-field="jp"]').value.trim();
    item.vocab = textToVocab(row.querySelector('[data-field="vocab"]').value);
    item.needsReview = !item.en || !item.jp;
  });
  return activeDraft;
}

async function saveDraft() {
  if (!activeDraft) return;
  collectDraft();
  await api(`../api/drafts/${encodeURIComponent(activeDraft.id)}`, { method: 'PUT', body: JSON.stringify(activeDraft) });
}

document.querySelector('#save-draft').addEventListener('click', async () => {
  try { await saveDraft(); toast('下書きを保存しました。'); } catch (error) { toast(error.message); }
});

document.querySelector('#publish').addEventListener('click', async () => {
  if (!activeDraft) return;
  try {
    await saveDraft();
    await api(`../api/publish/${encodeURIComponent(activeDraft.id)}`, { method: 'POST' });
    toast('動画一覧へ反映しました。GitHub Pagesにはgit push後に反映されます。');
    await loadJobs();
  } catch (error) {
    toast(error.message);
  }
});

Promise.all([loadStatus(), loadJobs()]).catch((error) => toast(error.message));

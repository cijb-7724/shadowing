const params = new URLSearchParams(location.search);
const videoId = params.get('id');
const container = document.querySelector('#sentences');
let player;

const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
})[char]);

const formatTime = (seconds) => {
  const whole = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  return hours
    ? `[${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}]`
    : `[${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}]`;
};

window.onYouTubeIframeAPIReady = () => {
  if (!videoId) return;
  player = new YT.Player('youtube-player', {
    videoId,
    playerVars: { modestbranding: 1, playsinline: 1 }
  });
};

function playAt(seconds) {
  if (player?.seekTo) {
    player.seekTo(Number(seconds), true);
    player.playVideo();
  }
}

function renderLesson(lesson) {
  document.title = `${lesson.title} — Shadowing`;
  document.querySelector('#title').textContent = lesson.title;
  document.querySelector('#sentence-count').textContent = `${lesson.sentences.length} sentences`;
  container.innerHTML = lesson.sentences.map((sentence, index) => {
    const vocab = (sentence.vocab || []).map((item) => `
      <li><span class="vocab-term">${escapeHtml(item.term)}</span>${item.level ? `<span class="vocab-level">${escapeHtml(item.level)}</span>` : ''} — ${escapeHtml(item.meaning)}${item.note ? `<br><small>${escapeHtml(item.note)}</small>` : ''}</li>
    `).join('');
    return `
      <article class="sentence-block" data-index="${index}">
        <p class="english-sentence">
          <button class="timestamp" type="button" data-play="${Number(sentence.playFrom ?? sentence.speechStart ?? 0)}">${formatTime(sentence.playFrom ?? sentence.speechStart)}</button>
          ${escapeHtml(sentence.en)}
        </p>
        <button class="translation-toggle" type="button" aria-expanded="false">日本語訳を見る</button>
        <div class="translation-content" hidden>
          <p>${escapeHtml(sentence.jp || '日本語訳はまだ生成されていません。')}</p>
          ${vocab ? `<ul class="vocab-list">${vocab}</ul>` : ''}
        </div>
      </article>
    `;
  }).join('');
}

container.addEventListener('click', (event) => {
  const playButton = event.target.closest('[data-play]');
  if (playButton) return playAt(playButton.dataset.play);
  const toggle = event.target.closest('.translation-toggle');
  if (!toggle) return;
  const content = toggle.nextElementSibling;
  content.hidden = !content.hidden;
  toggle.textContent = content.hidden ? '日本語訳を見る' : '日本語訳を隠す';
  toggle.setAttribute('aria-expanded', String(!content.hidden));
});

document.querySelector('#collapse-all').addEventListener('click', () => {
  document.querySelectorAll('.translation-content').forEach((element) => { element.hidden = true; });
  document.querySelectorAll('.translation-toggle').forEach((element) => {
    element.textContent = '日本語訳を見る';
    element.setAttribute('aria-expanded', 'false');
  });
});

if (!videoId || !/^[\w-]{6,20}$/.test(videoId)) {
  container.innerHTML = '<div class="error-box">動画IDが正しくありません。</div>';
} else {
  fetch(`./data/videos/${encodeURIComponent(videoId)}.json`, { cache: 'no-cache' })
    .then((response) => {
      if (!response.ok) throw new Error(`学習データを取得できませんでした (${response.status})`);
      return response.json();
    })
    .then(renderLesson)
    .catch((error) => { container.innerHTML = `<div class="error-box">${escapeHtml(error.message)}</div>`; });
}

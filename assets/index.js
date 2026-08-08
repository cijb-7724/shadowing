const grid = document.querySelector('#video-grid');
const emptyState = document.querySelector('#empty-state');
const adminLink = document.querySelector('#admin-link');

if (['localhost', '127.0.0.1'].includes(location.hostname)) {
  adminLink.hidden = false;
}

const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
})[char]);

fetch('./data/videos.json', { cache: 'no-cache' })
  .then((response) => {
    if (!response.ok) throw new Error(`動画一覧を取得できませんでした (${response.status})`);
    return response.json();
  })
  .then((videos) => {
    emptyState.hidden = videos.length !== 0;
    grid.innerHTML = videos.map((video) => `
      <a class="card" href="./video.html?id=${encodeURIComponent(video.id)}">
        <figure class="thumb">
          <img src="https://img.youtube.com/vi/${encodeURIComponent(video.id)}/hqdefault.jpg"
               alt="${escapeHtml(video.title)} thumbnail" loading="lazy">
        </figure>
        <div class="card-body">
          <h2>${escapeHtml(video.title)}</h2>
          <p class="card-meta">${Number(video.sentenceCount || 0)} sentences</p>
        </div>
      </a>
    `).join('');
  })
  .catch((error) => {
    emptyState.hidden = false;
    emptyState.textContent = error.message;
  });

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const videosDir = path.join(root, 'videos');
const outDir = path.join(root, 'data', 'videos');
fs.mkdirSync(outDir, { recursive: true });

const files = fs.readdirSync(videosDir).filter((name) => name.endsWith('.html')).sort();
const manifest = [];

for (const file of files) {
  const html = fs.readFileSync(path.join(videosDir, file), 'utf8');
  const dataMatch = html.match(/const\s+data\s*=\s*(\[[\s\S]*?\]);\s*\n\s*document\.addEventListener/);
  const idMatch = html.match(/const\s+videoId\s*=\s*['"]([^'"]+)['"]/);
  const titleMatch = html.match(/<p>動画:\s*([^<]+)<\/p>/i) || html.match(/<title>[^<]*?-\s*([^<]+)<\/title>/i);
  if (!dataMatch || !idMatch) {
    console.warn(`Skipping ${file}: data or video ID was not found`);
    continue;
  }

  const oldData = vm.runInNewContext(dataMatch[1], Object.create(null), { timeout: 1000 });
  const id = idMatch[1];
  const title = (titleMatch?.[1] || file.replace(/^shadowing_/, '').replace(/\.html$/, ''))
    .replace(/^\*\*|\*\*$/g, '')
    .trim();
  const toSeconds = (stamp) => String(stamp).replace(/[\[\]]/g, '').split(':').map(Number).reduce((sum, part) => sum * 60 + part, 0);
  const parseVocab = (raw) => {
    if (!raw) return [];
    return String(raw).split(/,\s*(?=[^()]*(?:\(|$))/).map((part) => {
      const match = part.trim().match(/^(.+?)\s*[（(](.+)[）)]$/);
      return match ? { term: match[1].trim(), meaning: match[2].trim(), level: '' } : { term: part.trim(), meaning: '', level: '' };
    }).filter((item) => item.term);
  };
  const sentences = oldData.map((item, index) => {
    const playFrom = toSeconds(item.time);
    return {
      id: index + 1,
      speechStart: playFrom + 1,
      playFrom,
      end: index + 1 < oldData.length ? toSeconds(oldData[index + 1].time) + 1 : playFrom + 8,
      en: item.en,
      jp: item.jp,
      vocab: parseVocab(item.vocab),
      confidence: null,
      needsReview: false
    };
  });
  const lesson = {
    schemaVersion: 1,
    id,
    title,
    sourceUrl: `https://www.youtube.com/watch?v=${id}`,
    generatedAt: null,
    transcriptSource: 'legacy-import',
    sentences
  };
  fs.writeFileSync(path.join(outDir, `${id}.json`), `${JSON.stringify(lesson, null, 2)}\n`);
  manifest.push({ id, title, sentenceCount: sentences.length, generatedAt: null });
}

fs.writeFileSync(path.join(root, 'data', 'videos.json'), `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`Imported ${manifest.length} videos`);

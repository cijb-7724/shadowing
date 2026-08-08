# Shadowing Library

YouTubeの英語動画から、文ごとの英文・再生位置・日本語訳・高校レベル以上の初出語彙を作り、GitHub Pagesへ公開するためのローカルツールです。生成処理はMac内、閲覧は静的なGitHub Pagesで動きます。外部の有料APIは使いません。

## 仕組み

1. ローカル管理画面にYouTube URLを入力します。
2. 利用可能ならYouTubeの英語字幕と単語時刻を取得します。
3. 字幕がなければ、音声を取得してローカルの `faster-whisper` で文字起こしします。
4. 文頭の実測時刻を切り捨て、1秒戻した位置を再生位置にします。
5. ローカル頻度辞書が難語候補を決め、Ollamaが日本語訳・語義・CEFR目安を生成します。
6. 管理画面で確認・修正し、公開用JSONへ反映します。
7. GitでpushするとGitHub Pagesへ公開されます。

既存の4動画は `data/videos/*.json` へ移行済みです。旧 `videos/*.html` も互換性のため残しています。

## 初回セットアップ

このMacには `ffmpeg` と `yt-dlp` がすでに入っています。日本語訳用にOllamaを準備します。

```bash
brew install ollama
ollama pull qwen3:4b
ollama serve
```

語彙頻度辞書と、字幕がない動画用のWhisperをPython仮想環境へ準備します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-optional.txt
```

`faster-whisper` のモデルは字幕のない動画を最初に処理するときにダウンロードされます。モデル名は `shadowing.config.json` で変更できます。

## 起動

Finderで `start.command` をダブルクリックします。ターミナルから起動する場合は次を実行します。

```bash
.venv/bin/python -m shadowing_app
```

ブラウザで `http://127.0.0.1:8000/admin/` が開きます。仮想環境を作っていない場合は `python3 -m shadowing_app` でも起動できます。停止するときはターミナルで `Ctrl+C` を押します。

ブラウザを自動で開きたくない場合は `.venv/bin/python -m shadowing_app --no-browser` を使えます。

## 公開

管理画面の「公開ファイルへ反映」は、次のファイルを更新します。

- `data/videos/<video-id>.json`
- `data/videos.json`

内容を確認してから通常どおりcommit、pushしてください。

```bash
git status
git add index.html video.html assets admin data shadowing_app shadowing.config.json README.md
git commit -m "add generated shadowing lesson"
git push
```

GitHub Pagesでは `index.html` が動画一覧を、`video.html?id=<video-id>` が共通の学習画面を表示します。ローカル管理画面やモデルは公開されません。
ルートの `.nojekyll` により、先頭が `_` のYouTube動画IDを含むJSONもそのまま配信されます。

## 設定

`shadowing.config.json` の主な項目です。

- `playbackBufferSeconds`: 文頭から戻す秒数（既定値1秒）
- `captionLanguages`: 取得する英語原文字幕（既定値 `en-orig,en,en-GB`）
- `preferYouTubeCaptions`: 字幕を優先するか
- `transcription.model`: 字幕がない場合のWhisperモデル
- `ollama.model`: 翻訳・語彙生成に使うローカルモデル
- `ollama.batchSize`: 一度に処理する文数

Ollamaなしで文字起こしだけ確認したい場合は `ollama.enabled` を `false` にできます。その場合、日本語訳は空欄となり、管理画面で要確認になります。

## テスト

```bash
python3 -m unittest discover -v
```

## 注意

YouTube URLからの取得はYouTube側の仕様変更により失敗することがあります。利用する動画について、YouTubeの利用規約、著作権、公開範囲を確認してください。公開ページはYouTube埋め込みを使用し、取得した音声自体はリポジトリへ保存しません。作業ファイルは `.shadowing-work/` に保存され、Gitの対象外です。

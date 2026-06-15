# blog

合同会社カタツムリワークスのブログ（Hugo・テーマなし・老人会風）。

- 本番: https://blog.katatsumuri.work（Firebase Hosting・予定）
- 記事 URL: `/:year/:month/:day/:slug/`（日付階層）

## 開発

```sh
hugo server -D          # http://localhost:1313（ドラフトも表示）
hugo --gc --minify      # public/ に本番ビルド（CI/デプロイ前チェック）
```

## 記事の追加

`content/posts/YYYY-MM-DD-{slug}.md` を作る。frontmatter:

```yaml
---
title: '記事タイトル'
slug: 'english-slug'            # URL に使う。/:year/:month/:day/:slug/
date: 2026-06-12T10:00:00+09:00 # 時刻+TZ まで（同日複数記事の並び順用）
categories: ['tech']           # 下記の2つから1つ
tags: ['rust', 'hugo']         # 言語/FW/ツール（下記方針）
draft: false
---
```

## 分類の規約

役割を分ける：**カテゴリ = 大きな箱、タグ = 具体的な技術**。

### カテゴリ（2つに限定）
| スラッグ | 表示名 | 用途 |
|---|---|---|
| `tech` | 技術 | 技術的な内容（実装・インフラ・人柱記録など） |
| `zatsudan` | 雑談 | それ以外のゆるい話・お知らせ含む |

- 定義は `content/categories/{tech,zatsudan}/_index.md`（`title` が日本語表示名）。
- 増やしたくなったら `_index.md` を1つ足すだけ。ただし基本はこの2つで運用。

### タグ（言語・フレームワーク・ツールに限定）
- ふわっとしたラベル（「お知らせ」等）は付けない。**技術スタックのインデックス**にする。
- **小文字の英語スラッグ**で統一。
- 例: `rust` / `typescript` / `go` / `astro` / `hugo` / `axum` / `terraform` / `firebase` / `cloud-run` / `gcp` …
- その記事で実際に扱った言語・FW・ツールだけ付ける（挨拶記事などトピックの無い記事はタグなしでよい）。

## ナビ / 一覧

- ナビ: ホーム / アーカイブ / カテゴリ / タグ
- `/archives/`: 年→月でグルーピング
- `/categories/`・`/tags/`: 件数表示（`技術（3）`）。記事のあるものだけ一覧に出る。
- ホームは 14 件/ページのページネーション。

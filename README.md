# blog

合同会社カタツムリワークスのブログ（Hugo・テーマなし・老人会風）。

- 本番: https://blog.katatsumuri.work（Firebase Hosting）
- 記事 URL: `/:year/:month/:day/:slug/`（日付階層）

## 開発

```sh
hugo server -D          # http://localhost:1313（ドラフトも表示）
hugo --gc --minify      # public/ に本番ビルド（CI/デプロイ前チェック）
```

## デプロイ（Firebase Hosting）

ホスティングは GCP プロジェクト `katatsumuri-work`（web / Cloud Run と同一）の Firebase を使う。
web は既定サイト（`katatsumuri.work`）、blog は `katatsumuri-blog` サイトに分けている。
どのサイトに出すかは `firebase.json` の `site` で固定しているので、デプロイ時の指定は不要。

初回のみ:

```sh
npx firebase-tools login                                        # 対話ログイン（katatsumuri アカウント）
npx firebase-tools hosting:sites:create katatsumuri-blog        # blog 用サイトを作成
```

デプロイは **main への push で自動実行**されます。ビルド定義は `cloudbuild.yaml`、
動かしているのは Cloud Build です。

### 自動デプロイ（Cloud Build）

3 つの契機で走ります。どれも同じトリガー（`blog-deploy`）を使います。

| 契機 | 目的 |
|---|---|
| `push`（main） | 記事をマージしたら即反映 |
| 日次（Cloud Scheduler・JST 09:05） | **未来日の記事を当日に公開するため** |
| 手動 | 即時デプロイ |

```sh
# 手動で出す
gcloud builds triggers run blog-deploy --branch=main --project=katatsumuri-work

# 実行状況
gcloud builds list --project=katatsumuri-work --limit=5
```

日次実行があるのは Hugo の挙動のためです。Hugo は既定で未来日の記事をビルドから
除外するので、`date` を先の日付にして書き溜めておけますが、**その日にビルドする人が
必要**になります。push 契機だけだと未来日の記事がいつまでも出ません。

認証は Cloud Build のサービスアカウント（ADC）で、**長期鍵はどこにも置いていません**。
設定の実体は infra repo の `gcp/cloud-build-blog-deploy` にあります。

### なぜ GitHub Actions をやめたか

もともと GitHub Actions の `schedule` で日次ビルドを回していましたが、**発火しませんでした**。

- 2026-09-09 に組んでから 09-11 まで 3 日連続で `schedule` の実行が 0 件
- 30 分ごとに回している別のワークフローでも、実行率は 1 日 48 回の想定に対して 6 回程度
- cron を「毎時 0 分帯」から外しても改善せず

公開は「その日に出ないと意味がない」ので、GitHub の混雑から切り離して GCP 内に寄せました。
詳しくは記事 [GitHub Actions の cron が、ある日から 1 日 48 回中 6 回しか動かなくなった](https://blog.katatsumuri.work/2026/09/19/scheduled-workflow-silently-stops/) に書いています。

### 手元から直接デプロイする（緊急時）

```sh
hugo --gc --minify                                              # public/ にビルド
npx firebase-tools deploy --only hosting --project katatsumuri-work
```

認証が切れた場合は `npx firebase-tools login --reauth` で入り直します。

### カスタムドメイン（サブドメイン / 外部 DNS）

`katatsumuri.work` の DNS はムームードメイン管理で Cloudflare に移せないため、apex ではなく
**サブドメイン**で運用する。Firebase コンソールの Hosting → カスタムドメインで
`blog.katatsumuri.work` を追加すると **CNAME**（と確認用 TXT）が提示されるので、
それをムームードメイン DNS に追加する。**apex の A / MX は触らない＝メール無傷**。SSL は Firebase が自動発行。

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

### カテゴリ（3つ）
| スラッグ | 表示名 | 用途 |
|---|---|---|
| `tech` | 技術 | 技術的な内容（実装・インフラ・人柱記録など） |
| `zatsudan` | 雑談 | 会社まわりのゆるい話・お知らせ |
| `yomoyamo` | よもやま | 仕事の本筋から外れた話。趣味や個人的な道具づくりなど |

- 定義は `content/categories/{tech,zatsudan,yomoyamo}/_index.md`（`title` が日本語表示名）。
- `zatsudan` と `yomoyamo` は近いが、**会社の話は `zatsudan`、会社と関係ない個人の話は `yomoyamo`** で分ける。
- 増やしたくなったら `_index.md` を1つ足すだけ。ただしむやみに増やさない。

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

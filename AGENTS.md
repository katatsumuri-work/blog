# AGENTS.md

合同会社カタツムリワークスのリポジトリで AI コーディングエージェント（Claude Code、Codex CLI、Gemini Code Assist、GitHub Copilot など）が作業する際のルール集です。

組織全体の構成は親 repo [katatsumuri-work/katatsumuri-work](https://github.com/katatsumuri-work/katatsumuri-work) を参照してください。

---

## 言語

ユーザーとのやりとり、レビューコメント、コミットメッセージ、PR タイトル・本文、Issue、ドキュメント、コード内コメントは **すべて日本語** で書くこと。英語で書くのはコード識別子・公式仕様の引用部分などに限る。

---

## コミュニケーション

### レビューコメントの文体

「カジュアルだけど丁寧」を基本とすること。

- 「〜です」「〜ます」の丁寧語を使う
- 断定しすぎず「〜しそうです」「〜かなと思います」「〜と安心です」のような柔らかい表現を混ぜる
- 技術的な説明は簡潔にして、理由や影響をわかりやすく添える
- ラベルは `[must]`（修正必須）／`[imo]`（個人意見）／`[nits]`（細かい指摘）／`[ask]`（質問）を使い分ける
- ファイル・行番号別に整理してインラインコメント向けに書く

良い例：
> パースエラーが握りつぶされています。DynamoDB のデータが壊れた場合に SerialNumber=0 になって、どんな serialNumber >= 1 でも順序チェックを通ってしまいます。ここで弾いたほうがデバッグしやすいかなと思います。

悪い例：
> エラー握りつぶしてる。（カジュアルすぎる）
> パースエラーが無視されており、データ整合性に関する正確性バグが存在します。（硬すぎる）

### 参考資料の提示

レビュー時に指摘の根拠として有用な場合は、各言語・ライブラリ・フレームワークの **公式ドキュメントの URL** を必ず併記すること。一次情報を優先し、ブログ記事や Stack Overflow は補助的にとどめる。

例：
> [imo] `Result::map_err` を使うと中間変数を挟まずに書けます。
> 参考: https://doc.rust-lang.org/std/result/enum.Result.html#method.map_err

### コミットメッセージ・PR タイトル

- 日本語で書く
- 概要は1〜2文、何をなぜ変えたかが本文から読み取れること
- Conventional Commits は強制しない（自由）

---

## アーキテクチャ・実装方針

### Clean Architecture（クリーンアーキテクチャ）

新規モジュールやディレクトリ構造を設計するときは、Clean Architecture の依存方向ルールを守ること。

- **依存方向は外側 → 内側のみ**：infrastructure 層は use case 層に依存し、use case 層は domain（entities）層に依存する。逆向きの依存は禁止
- **ドメイン層はフレームワーク・DB・HTTP に依存しない**：純粋なロジックとして表現する
- **UI / Web フレームワーク（axum、Astro など）は最も外側**：内側のロジックを薄く呼び出すだけ
- **境界はインターフェース（trait / interface）で切り、依存性逆転を使う**：DB 操作などはドメイン側で trait を定義し、infrastructure 側で実装する

### コード設計の規範：ミノ駆動本

仙塲大也『良いコード／悪いコードで学ぶ設計入門 ― 保守しやすい成長し続けるコードの書き方』（通称・ミノ駆動本）の思想を実装の指針とすること。

- **完全コンストラクタ**：オブジェクト生成時にすべての不変条件を保証する
- **値オブジェクト**：意味のある値はプリミティブのまま渡さず、専用の型でラップする
- **ファーストクラスコレクション**：コレクションを扱うロジックは専用クラスにまとめる
- **早期 return / ガード節** で `if` のネストを浅く保つ
- **マジックナンバーは定数化、文字列リテラルは enum 化**
- **データクラス + 操作関数の分離（=データクラスアンチパターン）を避ける**：振る舞いは値を持つ型に書く
- **コードの臭い（God class、長すぎるメソッド、重複コード）に気づいたら指摘またはリファクタリング**

### 実装プロセスの規範：TDD（t-wada 流）

和田卓人（t-wada）の思想を準拠した TDD で進めること。

- **RED → GREEN → REFACTOR のリズム**：まず失敗するテストを書き、最小実装で通し、最後にリファクタリングする
- **テストは仕様の表現**：テスト名は「何をしたら何になるべきか」を日本語で書いてもよい
- **テストファースト**：実装より先にテストを書く。後付けで「動作を確認しただけ」のテストは避ける
- **三角測量**：1 つのケースで実装した後、別ケースを追加して一般化する
- **TODO リストで段階的に進める**：思いつく仕様を先にリストアップし、1 件ずつ TDD で消化する
- 例外として、UI 表示の微調整やプロトタイプは TDD を強制しない

### UNIX 哲学

UNIX 哲学（"Do one thing and do it well"）をモジュール・関数・型・テストすべての粒度に適用すること。

- **1 関数 1 責任**：複数のことをする関数は分割する
- **1 モジュール 1 関心事**：モジュール名で要約できないなら分割を検討する
- **依存は最小限**：本当に必要な依存だけを引く。サードパーティライブラリの安易な追加は避ける
- **小さく作って組み合わせる**：大きな関数より小さな関数の合成を優先する

---

## コミット前の必須チェック

各プロジェクトで使う lint・typecheck・test は **必ず** コミット前に実行し、全件パスを確認すること。

- 変更ファイルだけでなく、影響を受ける他ファイルのエラーも全件確認する
- 型定義の変更（フィールド追加・required 化など）は影響範囲が広いため特に注意
- pre-commit hook の失敗を `--no-verify` で握りつぶすのは禁止（明示的な指示がない限り）

### 各 stack のチェックコマンド

| repo / stack | コマンド |
|---|---|
| `api` (Rust) | `cargo fmt --check && cargo clippy -- -D warnings && cargo test` |
| `blog` (Hugo) | `hugo --gc --minify` がエラーなく完走 |
| `web` (TypeScript) | `pnpm typecheck && pnpm lint && pnpm test` |
| `infra` (Terraform) | `terraform fmt -check && terraform validate` |

---

## やってはいけないこと

- **テストを勝手に削除・mock 化・skip しない**：失敗するテストは原因を直す。skip は明示指示がある場合のみ
- **`--no-verify`、`--no-gpg-sign`、`-c commit.gpgsign=false` などのバイパスをしない**：hook が落ちたら fix してから再コミット
- **destructive な git 操作（`push --force`、`reset --hard`、`branch -D`、`checkout -- .`、`clean -f`）を独断でしない**：必ずユーザーに確認する
- **secrets を public な repo に書かない**：環境変数 ／ `.env`（gitignore 済み）／ `infra` repo にしか入れない
- **`.env` や credentials ファイルを `git add -A` で巻き込まない**：個別ファイル指定で add する
- **prod に直 push しない**：必ず PR 経由
- **コミットを amend したり既に push 済みのコミットを書き換えたりしない**：新しいコミットを積む

---

## 判断に迷ったら：ユーザーに質問する

仕様として明確になっていない、判断材料が足りない、複数の妥当な選択肢がある、など **エージェントだけでは決められない場面では、推測で進めず必ずユーザーに質問すること**。

- Claude Code の場合は **`AskUserQuestion` ツール** を使う（選択肢を 2〜4 個提示して回答を待つ）
- 他エージェントの場合は対話プロンプトなど、利用可能な質問機構を使う
- 質問は具体的に：「A と B のどちらにしますか？」「この値は何にすべきですか？」のように回答しやすい形で投げる
- 抽象的な「どうしますか？」は避ける

---

## Secrets の取り扱い

- `.env` は各 repo の `.gitignore` に必ず含める
- 本番 secrets は `infra` repo（private）または外部 secret manager（Cloudflare Workers Secrets など）で管理する
- README やコード内のサンプルに本物の値を書かない（`xxx-replace-me` などのプレースホルダーを使う）

---

## Submodule 運用

この組織のリポジトリ群は親 [katatsumuri-work/katatsumuri-work](https://github.com/katatsumuri-work/katatsumuri-work) で 4 つの子 repo（`api`, `blog`, `web`, `infra`）を submodule として束ねています。

- 子 repo で変更・push した後、親 repo で `git submodule update --remote` してから submodule pointer を明示的にコミット
- 親 repo を clone する場合は `git clone --recurse-submodules` を推奨
- 子 repo を単独で開いて作業しても問題なし。その場合 submodule pointer の更新は別途親で対応

---

## AI エージェントへの追加方針

- AI が書いたコードもレビュー対象。自動承認はしない
- 大きな変更（新機能追加、リファクタ等）はまず小さく分けて PR を出す
- 既存の慣習（命名規則、ディレクトリ構造、テストの書き方）に揃える。理由なく逸脱しない

---

## 参考資料

- 親 repo: https://github.com/katatsumuri-work/katatsumuri-work
- org プロフィール: https://github.com/katatsumuri-work
- 仙塲大也『良いコード／悪いコードで学ぶ設計入門』（ミノ駆動本）
- 和田卓人（t-wada）の TDD 関連発表・記事
- Robert C. Martin『Clean Architecture』
- Mike Gancarz『The UNIX Philosophy』

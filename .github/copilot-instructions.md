# Copilot Instructions

このリポジトリのルールは [AGENTS.md](../AGENTS.md) を参照してください。すべての作業前に必ず読み込んでください。

主要ポイント（詳細は AGENTS.md）：

- すべてのやりとりは日本語で行う
- レビューは「カジュアルだけど丁寧」、`[must]/[imo]/[nits]/[ask]` ラベルを使う
- アーキテクチャは Clean Architecture、コード設計はミノ駆動本に準拠
- 実装は TDD（t-wada 流、RED → GREEN → REFACTOR）
- UNIX 哲学（単一責任・最小化）を全粒度で適用
- 公式ドキュメントの URL を参考資料として併記する
- 判断に迷ったらユーザーに具体的な選択肢を示して質問する
- コミット前に lint・typecheck・test を全件パスさせる
- secrets を public repo に書かない、`--no-verify` でバイパスしない、destructive な git 操作を独断でしない

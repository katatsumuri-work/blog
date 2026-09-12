---
title: '書き換えた直後に一度も通していなかった ― 配布ワークフローが 4 か月ぶんの成功ログを積んでいた話'
slug: 'sync-agent-rules-workflow'
date: 2026-09-21T09:00:00+09:00
categories: ['tech']
tags: ['github-actions']
draft: false
---

AI コーディングエージェント向けのルールを `AGENTS.md` に書いています。コミットメッセージは日本語で、とか、テストを勝手に skip するな、とか、そういう取り決めです。

リポジトリが 4 つあるので、このファイルも 4 つに置く必要がありました。コピペで配るとすぐズレるのは目に見えていたので、**親リポジトリを正として子へ自動配布する GitHub Actions** を書きました。

書いたのは 5 月です。そして一度はちゃんと配られました。ところが**同じ日の夜に実装を書き換えていて、その書き換えた部分だけが 4 か月間、一度も走っていませんでした**。

その間ワークフローは実行されていて、ログはすべて成功です。ただしどれも、本体に入る前に抜けていました。

2026 年 9 月時点の話です（GitHub CLI 2.93.0、GitHub.com）。

## 配布の仕組み

構成は [4 つのリポジトリを submodule で束ねた]({{< ref "2026-09-20-git-submodule-monorepo.md" >}}) に書いたとおりで、親 1 つと子 4 つ（api / blog / web / infra）です。

親の `AGENTS.md` などが更新されたら、各子に同じ内容を配ります。

```yaml
on:
  push:
    branches: [main]
    paths:
      - 'AGENTS.md'
      - 'CLAUDE.md'
      - 'GEMINI.md'
      - '.github/copilot-instructions.md'
```

配るのは 4 ファイル。`AGENTS.md` が本体で、残り 3 つは各エージェント向けの入口です（中身は「`AGENTS.md` を読め」とだけ書いてあります）。

子ごとに並列で走らせて、単純にコピーします。

```yaml
strategy:
  fail-fast: false
  matrix:
    repo: [api, blog, web, infra]
```

`fail-fast: false` にしているのは、1 つの子で失敗しても残りは配りたいからです。

## PR を立てて即マージする

子の `main` にも保護をかけているので、**直接 push はできません**。そこで、PR を作ってその場で squash merge する形にしました。

```yaml
env:
  GH_TOKEN: ${{ secrets.SYNC_PAT }}
  PARENT_SHA: ${{ github.sha }}
run: |
  git checkout -b "chore/sync-agent-rules-${SHORT_SHA}"
  git commit -m "親 repo の AI エージェントルールを sync (parent ${SHORT_SHA})"
  git push -u origin "$BRANCH"

  PR_URL=$(gh pr create --base main --head "$BRANCH" ...)
  gh pr merge "$PR_URL" --squash --delete-branch
```

`GH_TOKEN` に入れているのは後述する PAT です。**権限は Contents と Pull requests の両方が要ります。** Contents だけだと push は通って `gh pr create` で落ちるので、少し分かりにくい失敗の仕方をします（私はこれを README に書き忘れていて、あとで直しました）。

ブランチ名に親のコミット SHA を入れているので、**どの更新に対応する配布か**が後から分かります。

リポジトリ設定の auto-merge を使う手もあります。ただしあれは「PR ごとに auto-merge を有効化できるようにする」設定なので、結局ボット側から API を叩くことになります。だったら**作成と同時に明示的にマージするほうが、何が起きるか読みやすい**かなと思いました。

## `GITHUB_TOKEN` では PR を作れない

ここで 1 つ詰まりました。ワークフローに自動で渡される `GITHUB_TOKEN` を使うと、PR 作成が弾かれます。

```
GitHub Actions is not permitted to create or approve pull requests
```

組織やリポジトリの設定で「**Actions による PR 作成**」を禁止できるようになっていて、それが効いている状態でした。

参考: [GitHub Docs - リポジトリの GitHub Actions 設定を管理する](https://docs.github.com/ja/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#preventing-github-actions-from-creating-or-approving-pull-requests)

設定を緩める手もありますが、**全ワークフローに効いてしまう**ので、ここだけのために開けたくありませんでした。PAT を 1 つ作って、このワークフローに渡しています。

そもそも `GITHUB_TOKEN` は**自分のリポジトリにしか権限がない**ので、子へ push する時点でどのみち別のトークンが要ります。

同じところは submodule の pointer 追従でも踏んでいて、エラーの全文や `.gitmodules` の SSH URL を PAT 付き https に差し替える話は [submodule pointer の追従を GitHub Actions で自動化した話]({{< ref "2026-06-15-automate-submodule-pointer-bump.md" >}}) に書きました。ここでは繰り返しません。

## 差分がないときは何もしない

毎回 PR が立つと鬱陶しいので、コピーした結果が変わらなければ抜けるようにしています。

```sh
if [[ -z "$(git status --porcelain)" ]]; then
  echo "変更なし、PR スキップ"
  exit 0
fi
```

素直な実装です。そして**これが 4 か月の空振りの正体**でした。

## PR が 1 つも立っていない

9 月になって子リポジトリの PR 一覧を見たとき、**`chore/sync-agent-rules-*` という PR が 1 つも無い**ことに気づきました。

配布は動いていたはずなのに、なぜ PR が無いのか。履歴を追って分かりました。

| 5/3 の時刻 | できごと |
|---|---|
| 18:36 | 各子に手でコピー |
| 18:37 | **ワークフロー初版を追加**（このときは PR ではなく直 push 方式） |
| 22:31 / 22:40 | `AGENTS.md` を 2 回更新 |
| 22:42 | 初版が発火し、bot が子へ**直 push**（成功） |
| **22:58** | **PR ＋ 即 squash merge 方式に書き換え** |

つまり 5 月に配られたのは**書き換える前の実装**でした。子のログにもはっきり残っています。

```console
$ git -C api log --format='%h %ad %an %s' --date=short
1b7a4ca 2026-05-03 github-actions[bot] Sync agent rules from parent repo
0d63a94 2026-05-03 ymzkryo            Sync agent rules from parent repo
```

PR が無いのは当然で、**当時のワークフローは PR を作らない実装だった**からです。

## 書き換えた部分が 4 か月走らなかった

問題は 22:58 の書き換え以降です。

配布対象の 4 ファイルを、私は**その後 9 月 8 日まで一度も更新しませんでした**。`on.push.paths` はこの 4 ファイルを見ているので、**push 起因の発火は 0 回**です。

```console
$ git log --format='%ad %s' --date=short -- AGENTS.md CLAUDE.md GEMINI.md .github/copilot-instructions.md
2026-09-08 docs: agent rules にユーザーの裁量尊重とファイル名の命名規則を追加
2026-05-03 PR #1 のセルフレビュー指摘を反映
2026-05-03 AGENTS.md に作業前プランニングとブランチ戦略のセクションを追加
2026-05-03 Add agent rules (AGENTS.md) and sync workflow
```

その間に何度か手動実行（`workflow_dispatch`）はしていて、ログはすべて成功でした。ただしその成功は、**全部「変更なし」で早期 return したもの**です。

```sh
if [[ -z "$(git status --porcelain)" ]]; then
  echo "変更なし、PR スキップ"
  exit 0
fi
```

親と子が一致していれば、コピーしても差分が出ません。差分が出なければここで抜けます。

結果として、**書き換えた本体——PR を作って squash merge してブランチを削除する部分——が 4 か月間、一度も実行されていませんでした**。リファクタした直後に一度通しておかなかったせいで、次に条件が揃うまで誰も気づけない状態になっていたわけです。

## 実差分を作って通した

確かめるには、実際に差分を作るしかありません。ダミーの空行を入れるのは気が引けたので、**本当に入れたかったルールの追加で兼ねました**。

親の `AGENTS.md` に 2 つ足して push したところ、`on.push.paths` で自動発火し、今度は 4 つの子すべてに PR が立ちました。

```console
api   PR #6 chore/sync-agent-rules-37a9506  MERGED  ブランチ削除済み
blog  PR #8 同上                            MERGED  ブランチ削除済み
web   PR #4 同上                            MERGED  ブランチ削除済み
infra PR #5 同上                            MERGED  ブランチ削除済み
```

配布後、5 リポジトリの blob SHA を突き合わせました。

```console
AGENTS.md                       cea36eae   （親 / api / blog / web / infra すべて一致）
CLAUDE.md                       5011b049
GEMINI.md                       49ea64e8
.github/copilot-instructions.md fe51ee8d
```

**保護された `main` に対して、PR 作成 → squash merge → ブランチ削除まで通る**ことを、private な `infra` を含む全リポジトリで確認できました。これでようやく「動く」と言えます。

## 早期 return は、実装が正しいことを証明しない

このワークフローは 4 か月間、正しく動いていました。差分がないときに何もしないのは意図した挙動です。問題は、**その分岐しか通っていなかった**こと。書き換えた本体は一度も実行されていませんでした。

CI が緑でも、それは「実行されたコードが正しかった」ことしか意味しません。**実行されなかったコードについては何も言っていない**わけです。当たり前のことですが、ログに `success` が並んでいると、つい全体が検証されたような気になります。

思えば、`gh pr list` を一度でも叩いていれば 4 か月も気づかずにいることはありませんでした。**「動いているはず」を確かめるコストは、たいてい数十秒**です。

同じ月に、別の自動化が**エラーも出さずに止まっていた**のも見つけています（[GitHub Actions の cron が、ある日から 1 日 48 回中 6 回しか動かなくなった]({{< ref "2026-09-19-scheduled-workflow-silently-stops.md" >}})）。あちらは「走るはずのものが走らない」、こちらは「走っているのに何もしていない」。**どちらも失敗として現れない**のが共通点でした。

## まとめ

- 共通ファイルは**親を正として子へ配る**。コピペ運用はズレます
- 子の `main` が保護されていても、**PR を立てて即 squash merge**すれば通ります
- `GITHUB_TOKEN` では PR を作れないことがあります。設定で禁止でき、そのときは PAT が要ります
- **実装を書き換えたら、その場で一度通す。** 次に条件が揃うまで誰も気づけません
- 動いているつもりの自動化は、**出力側（PR が立っているか、ファイルが揃っているか）を一度見る**のが確実です

書いた仕組みが動いていることを確かめるところまでが実装だな、と反省しました。

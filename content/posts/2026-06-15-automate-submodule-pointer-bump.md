---
title: 'submodule pointer の追従を GitHub Actions で自動化した話'
slug: 'automate-submodule-pointer-bump'
date: 2026-06-15T18:00:00+09:00
categories: ['tech']
tags: ['github-actions', 'git']
draft: false
---

カタツムリワークスのリポジトリは、親リポジトリが `api` / `blog` / `web` / `infra` の 4 つを **Git submodule** で束ねる構成にしています。便利なのですが、運用していると地味に面倒なことが一つありました。**子リポジトリを更新するたびに、親の submodule pointer を手で追従させる必要がある**ことです。

今回はこれを GitHub Actions で自動化したので、その記録を残しておきます。同じように submodule で monorepo を組んでいる方の参考になれば嬉しいです。

## 何が面倒だったか

submodule は「親が、子の特定コミットを指している」状態を持ちます。なので子リポジトリの `main` を進めても、親はそれを自動では追いかけてくれません。毎回こういう作業が要ります。

```sh
git submodule update --remote
git add api blog web infra
git commit -m "submodule pointer を最新 main に追従"
```

そして親の `main` は保護していて直 push できないので、**この追従だけのためにいちいち PR を作る**ことになります。1 日に何度も子を更新すると、この「追従 PR」がどんどん積み上がって、本筋と関係ないノイズになっていきます。

参考: [Git のさまざまなツール - サブモジュール](https://git-scm.com/book/ja/v2/Git-%E3%81%AE%E3%81%95%E3%81%BE%E3%81%96%E3%81%BE%E3%81%AA%E3%83%84%E3%83%BC%E3%83%AB-%E3%82%B5%E3%83%96%E3%83%A2%E3%82%B8%E3%83%A5%E3%83%BC%E3%83%AB)

## やりたかったこと

- 子リポジトリの `main` が進んだら、親の submodule pointer を**自動で**追従させたい
- 親 `main` は保護したまま（直 push はしない）にしたいので、**PR を作って即マージ**する形にしたい

子側からイベントを飛ばす案（`repository_dispatch`）も考えましたが、子 4 つに同じ設定を配るのは DRY じゃないなと思い、**親の cron 一箇所に集約**することにしました。30 分ごとに全 submodule をまとめて確認し、変化があれば PR を作って squash merge する、という素朴な作りです。

## ハマったところ：GITHUB_TOKEN だと PR が作れない

最初は何も考えず、ワークフロー標準の `GITHUB_TOKEN` で `gh pr create` しようとしました。すると、こう言って弾かれます。

```
GitHub Actions is not permitted to create or approve pull requests
```

これは organization / リポジトリの設定で、**「GitHub Actions に PR の作成・承認を許可するか」** がデフォルトで無効になっているためでした。セキュリティ的にはまっとうな挙動です（Actions が勝手に PR を量産・自己承認できると怖いので）。

参考: [GitHub Actions が pull request を作成・承認できないようにする](https://docs.github.com/ja/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository#preventing-github-actions-from-creating-or-approving-pull-requests)

設定を緩める手もありましたが、組織のポリシーを下げるのは避けたかったので、**PR の作成・マージ用に PAT（Personal Access Token）を別途用意**して、そちらを使うことにしました。この記事では `SYNC_PAT` という名前の secret にしています（値そのものは当然どこにも書きません）。

ついでに submodule の `fetch` も、private な `infra` を含むので PAT 経由にしておきます。`.gitmodules` は SSH URL なので、`insteadOf` で PAT 付きの https に差し替えてあげると通ります。

```sh
git config --global \
  url."https://x-access-token:${SYNC_PAT}@github.com/".insteadOf "git@github.com:"
```

参考: [git config - url.&lt;base&gt;.insteadOf](https://git-scm.com/docs/git-config#Documentation/git-config.txt-urlltbasegtinsteadOf)

## 実際のワークフロー

要点だけ抜き出すとこんな感じです。

```yaml
on:
  schedule:
    - cron: '*/30 * * * *' # 30 分ごと（多少遅延することあり）
  workflow_dispatch: # 子をマージ直後にすぐ反映したいとき用の手動実行

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: bump-submodule-pointers
  cancel-in-progress: false

jobs:
  bump:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: false
          fetch-depth: 0

      - name: Configure git auth (SYNC_PAT)
        run: |
          git config --global \
            url."https://x-access-token:${SYNC_PAT}@github.com/".insteadOf "git@github.com:"
        env:
          SYNC_PAT: ${{ secrets.SYNC_PAT }}

      - name: Update submodules to remote main
        run: |
          git submodule sync --recursive
          git submodule update --init --remote --recursive

      - name: Open PR and squash merge if changed
        env:
          GH_TOKEN: ${{ secrets.SYNC_PAT }} # PR 作成/マージは PAT
        run: |
          set -euo pipefail
          if [[ -z "$(git status --porcelain)" ]]; then
            echo "変化なし。スキップ。"; exit 0
          fi
          STAMP="$(date -u +%Y%m%d-%H%M%S)"
          BRANCH="chore/auto-bump-submodule-pointers-${STAMP}"
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git checkout -b "$BRANCH"
          git add api blog web infra
          git commit -m "chore: submodule pointer を最新 main に自動追従 (${STAMP})"
          git push -u origin "$BRANCH"
          PR_URL=$(gh pr create --base main --head "$BRANCH" \
            --title "chore: submodule pointer を最新 main に自動追従 (${STAMP})" \
            --body "各子 repo の最新 main に追従する自動 PR です。")
          gh pr merge "$PR_URL" --squash --delete-branch
```

ポイントをいくつか。

- **`workflow_dispatch` も付けておく**と安心です。cron は最大で 30 分待ちますが、子をマージした直後に手動実行すればすぐ反映できます。
  参考: [workflow_dispatch](https://docs.github.com/ja/actions/using-workflows/events-that-trigger-workflows#workflow_dispatch)
- **`concurrency` で多重起動を防ぐ**。cron と手動実行が重なっても、追従 PR が二重に走らないようにしています。
  参考: [concurrency の使用](https://docs.github.com/ja/actions/using-jobs/using-concurrency)
- **変化がなければ即スキップ**。`git status --porcelain` が空なら何もしないので、空っぽの PR が乱立しません。
- **PR 作成と submodule fetch だけ PAT、それ以外は標準のまま**。権限は必要なところに最小限で渡すのが安心かなと思います。

## 結果

これで、子リポジトリの PR をマージしたあとは（最大 30 分後、急ぐときは手動実行で即座に）親の pointer が勝手に追従するようになりました。手で追従 PR を作る作業がまるごと消えて、本筋の変更だけに集中できるようになっています。

submodule での monorepo はこの「pointer 追従」が地味な摩擦になりがちなので、CI に肩代わりさせると一気に楽になりました。`GITHUB_TOKEN` の PR 作成制限にだけ気をつければ、仕組み自体はかなりシンプルです。

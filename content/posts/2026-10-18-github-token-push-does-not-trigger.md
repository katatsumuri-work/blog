---
title: 'GITHUB_TOKEN で push しても、次の workflow は動かない。[skip ci] は何も止めていなかった'
slug: 'github-token-push-does-not-trigger'
date: 2026-10-18T09:00:00+09:00
categories: ['tech']
tags: ['github-actions', 'python', 'obsidian']
draft: false
---

GitHub Actions で、ある workflow が push したら、それをきっかけに別の workflow が動く。そういう連鎖を組んでいるなら、一度確かめておくと安心です。**`GITHUB_TOKEN` で行った push では、別の workflow は起動しません**。GitHub の仕様で、ドキュメントにもそう書いてあります。

私はこれを、タスク管理に使っている Obsidian の vault（Markdown のリポジトリ）で踏みかけました。毎朝タスクの status を書き換える workflow を足して、ファイルの移動は push で起動する既存の workflow に任せるつもりでした。ループが怖かったので、コミットには `[skip ci]` を付けていました。ところが仕様を読むと、**`[skip ci]` は何も止めていませんでした**。付けても外しても、後続は起動しない構成だったわけです。

入れてから 21 分後、最初の cron が走る前に直したので、`[skip ci]` 付きの版は一度も動いていません。そのかわり、`[skip ci]` を外して直したあとの 1 か月の記録を数えました。昇格の workflow が push したコミット 19 件に対して、push で起動した run は 0 件です。この記事では、仕様の中身と数え方、それから連鎖をやめて同じ job で済ませた直し方を書きます。舞台は個人のプライベートリポジトリです（2026 年 9〜10 月、GitHub Actions の `ubuntu-latest` / `actions/checkout@v6` / Python 3.11）。

## 昇格は status を 1 行書き換えるだけにして、移動は既存の workflow に任せた

タスクは 1 件 1 ファイルの Markdown で、frontmatter の `status` で状態を表しています（例として作ったタスクです）。

```yaml
---
title: "型紙を作り直す"
status: scheduled
project: leather-pattern
review_date: 2026-10-20
---
```

`scheduled` は「自分がやるけれど、着手日はまだ先」という状態です。着手日は `review_date` に入れていて、その日が来たら `next`（いまやる）に上げる運用にしています（最初は 3 日前に上げる設定で、あとで当日に変えました）。ところが上げる処理が無く、手で書き換えるまで `scheduled` のまま残っていました。そこで、着手日が来たら `next` に上げる workflow を、毎朝 6:50（JST）に cron で走らせることにしました。

このリポジトリには、もともと「`status` を見てファイルを置き場所へ動かす」スクリプト（`organize_files.py`）があります。`next` なら `00100_NEXTACTION/` へ、`done` ならアーカイブへ、という対応表を設定ファイルに持っています。

```text
00800_プロジェクト/.../00818_leather-pattern/   scheduled のあいだはプロジェクトの棚で寝ている
                    ↓  status: next
00100_NEXTACTION/                               next になると出てくる
```

なので、昇格スクリプト（`promote_scheduled.py`）は `status` の行を書き換えるだけにしました。着手日が来たものを集めて、

```python
if today >= basis - timedelta(days=lead_days):
    candidates.append((path, frontmatter, basis, kind))
```

`status:` の行を 1 つ置き換えます。

```python
new_content, n = re.subn(
    r"^status:\s*[\"']?scheduled[\"']?\s*$",
    "status: next",
    content,
    count=1,
    flags=re.MULTILINE,
)
```

あとはタスクのログ欄に「自動昇格した」と 1 行足すだけで、どこへ動かすかは、このスクリプトは知りません。昇格のロジックと配置のロジックを混ぜないためです。

## 再帰が怖くて、コミットに [skip ci] を付けた

ファイルを動かす `organize_files.py` は、すでに `on: push` の workflow（Organize TODOs）から呼ばれていました。

```yaml
name: Organize TODOs

on:
  push:
    branches:
      - main
      - master
  workflow_dispatch:
```

昇格の workflow が push すれば、Organize TODOs が起動してファイルが動くはずです。ただ、workflow の push で workflow が起動し、それがまた push して……とループしそうで怖くなりました。そこで、昇格側のコミットには `[skip ci]` を付けました。

```sh
git commit -m "chore: promote scheduled todos for ${TODAY} [skip ci]"
```

Organize TODOs はこの push では走らないので、移動は「次に誰かが push したとき」まで遅れます。それでいいと考えていました。

## GITHUB_TOKEN の push では、次の workflow はそもそも起動しない

9 月 9 日の 20:46 にこれを入れた直後、移動まですぐ済ませたくなって `[skip ci]` を外そうとしました。そこで調べると、外しても同じでした。workflow の中で使う `GITHUB_TOKEN` には、こういう仕様があります。

> When you use the repository's `GITHUB_TOKEN` to perform tasks, events triggered by the `GITHUB_TOKEN` will not create a new workflow run, with the following exceptions:

例外は 2 系統です。`workflow_dispatch` と `repository_dispatch` は常に run を作ります。また、`GITHUB_TOKEN` で PR を作成・更新したときの `pull_request`（`opened` / `synchronize` / `reopened`）は、承認待ちの run を作ります。**push は例外に入っていません**。続く段落には、今回の状況そのものが例として書かれています。

> For all other events, this behavior prevents you from accidentally creating recursive workflow runs. For example, if a workflow run pushes code using the repository's `GITHUB_TOKEN`, a new workflow will not run even when the repository contains a workflow configured to run when `push` events occur.

参考: [GitHub Docs - Triggering a workflow from a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow#triggering-a-workflow-from-a-workflow)

心配していた再帰は、GitHub が最初から防いでいました。`actions/checkout` は既定でトークンを認証情報として残すので、job の中でそのまま `git push` すると、`GITHUB_TOKEN` による push になります。

参考: [actions/checkout - README](https://github.com/actions/checkout#readme)

`[skip ci]` は、`push` と `pull_request` で起動する run を飛ばすためのものです。そもそも run が作られない push に付けても、効く対象がありません。

参考: [GitHub Docs - Skipping workflow runs](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs)

仕様どおりなら、あのまま運用した場合、朝 6:50 に昇格したタスクは、手元の PC を開いて自動バックアップが push するか、毎晩 23:55（JST）に schedule で走る別の整理 workflow が動くまで、プロジェクトの棚に残っていたことになります。

なお、同じブログの [GitHub Actions の cron が、ある日から 1 日 48 回中 6 回しか動かなくなった]({{< ref "2026-09-19-scheduled-workflow-silently-stops.md" >}}) では、動かないと困る定期実行は schedule に依存しない（push 駆動か外部スケジューラ）と書きました。push 駆動を選ぶなら、push に使うのが人の認証情報か、PAT・GitHub App のトークンである必要があります。

`GITHUB_TOKEN` まわりでは、Actions の中で PR を作ろうとして弾かれたこともあります。あちらはリポジトリの設定で PR の作成が禁止されていたのが原因で、今回の起動の抑止とは別の制限です（[submodule pointer の追従を GitHub Actions で自動化した話]({{< ref "2026-06-15-automate-submodule-pointer-bump.md" >}})）。

## 自分のリポジトリで数えた: bot の push 19 件で、push 起動の run は 0 件

仕様は自分のリポジトリでも確かめました。9 月 9 日の流れはこうです。

- 20:40 Organize TODOs 自身が bot として push（Organize TODOs は `on: push` の workflow で、移動したファイルをコミットして push します）
- 20:46 昇格の workflow を `[skip ci]` 付きで入れる
- 20:50 手元の自動バックアップが push
- 21:07 同じ job で移動まで済ませる形に直す

`[skip ci]` を外そうとして run の一覧を見比べると、20:40 の bot のコミットには push で起動した run が付いておらず、20:50 のコミットには Organize TODOs の run が付いていました。これが直すきっかけです（下の件数は、10 月 15 日に `event=push` で数え直したものです）。

コミットの SHA を指定して、push で起動した run を数えます。

```sh
gh api "repos/OWNER/REPO/actions/runs?head_sha=$SHA&event=push" --jq '.total_count'
```

まとめて見るなら、対象のコミットに絞ってから回します。

```sh
git log --author='github-actions\[bot\]' --grep='promote scheduled' --format=%H |
while read -r SHA; do
  echo "$SHA $(gh api "repos/OWNER/REPO/actions/runs?head_sha=$SHA&event=push" --jq '.total_count')"
done
```

`head_sha` に入るのは、push したあとのブランチの先端（いちばん新しいコミット）です。1 回の push で複数のコミットを送ると、手前のコミットは仕様と関係なく 0 件になります。メッセージに `[skip ci]` が付いたコミットも同じく 0 件になるので、どちらも数える対象から外しておきます。

2026-10-15 に、直したあとの 1 か月分を数えました。直したときに `[skip ci]` も外しているので、この 19 件のメッセージには `[skip ci]` は付いていません。直したあとの構成は連鎖に頼っていませんが、Organize TODOs の `on: push` は残っていて、`paths` の絞り込みもありません。push で起動するなら、ここに run が付くはずです。Organize TODOs 自体は同じ期間に push で 400 回起動していて、止まっていたわけではありません。昇格の workflow が push したコミット（JST で 2026-09-11〜10-12 の 19 件）と、私の認証情報で push したコミットの比較です。

| push した主体 | 対象 | push で起動した run |
| --- | --- | --- |
| `github-actions[bot]`（`GITHUB_TOKEN`） | 昇格のコミット 19 件 | **0 件** |
| 手元の自動バックアップ（私の認証情報） | 2026-10-10〜10-14 のコミット 5 件 | 5 件とも 2 本（Organize TODOs と、プロジェクト一覧を作る別の push 起動の workflow） |

どちらも自動化が push しています。期間・件数・変更の中身は揃えていないので、これだけで証明にはなりませんが、仕様と矛盾しない観測でした。

### head_sha だけで引くと、schedule の run が混ざる

上のコマンドで `event=push` を付けているのには理由があります。最初は付けずに件数だけを見ていて、**bot のコミットにも run が 2 件付いているもの**がありました。

```text
Review Date Reminder | event=schedule | 2026-10-11T22:10:50Z
TODO Reminder        | event=schedule | 2026-10-11T22:05:36Z
```

中身は、朝 7:00（JST）に schedule で走るリマインダーです。schedule の run はデフォルトブランチの最新コミットで動くので、その時点の先端が bot のコミットなら、その SHA が `head_sha` に入ります。push で起動したわけではありません。

> Scheduled workflows run on the latest commit on the default branch.

参考: [GitHub Docs - Events that trigger workflows（schedule）](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

`head_sha` で引いた件数を「その push で起動した run」と読むと、仕様と逆の結論になります。**`event` で絞って数える**のが安全です。

## 後続の処理は、同じ job の中で直接呼ぶ

直し方の候補は 3 つあります。当時考えたのは 1 行目と 3 行目で、2 行目はこの記事を書きながら気づいたものです。

| 方法 | やること | 判断 |
| --- | --- | --- |
| PAT か GitHub App のトークンで push する | 起動を抑止されないトークンで push して、Organize TODOs を起動させる | トークンの発行と更新が要る。再帰の防止も自分で考えることになる |
| `GITHUB_TOKEN` で `workflow_dispatch` を呼ぶ | `gh workflow run` で Organize TODOs を起動する（例外なので起動する） | 起動はできるが、移動が別の run・別のコミットに分かれ、push 同士の競合も増えそう |
| 同じ job で `organize_files.py` を呼ぶ | 昇格と移動を 1 つの job で済ませ、1 コミットにする | 他の workflow の起動に頼らないので、トークンの制約を受けない |

公式も、workflow から workflow を起動したいなら、`GITHUB_TOKEN` のかわりに GitHub App のトークンか PAT を使うよう書いています（上の Triggering a workflow from a workflow の節）。ただ今回やりたかったのはファイルを動かすことで、別の workflow を起動する必要はありませんでした。なので**同じ job で呼ぶ**ほうを採りました。スクリプトは分けたまま、呼ぶ場所だけを同じ job にまとめています（抜粋）。

```yaml
      - name: Promote scheduled todos
        run: python3 .github/scripts/promote_scheduled.py --slack

      # 昇格で next になったものを 00100_NEXTACTION へ移す。
      # ここでやらないと、次に人が push するか Organize Files（23:55 JST）まで動かない。
      - name: Organize promoted todos
        run: python3 .github/scripts/organize_files.py --todo-only

      - name: Commit promotions
        run: |
          set -eu
          TODAY=$(TZ=Asia/Tokyo date '+%Y-%m-%d')
          if git diff --staged --quiet; then
            echo "No changes to commit"
          else
            git commit -m "chore: promote scheduled todos for ${TODAY}"
            git pull --rebase origin ${{ github.ref_name }}
            git push
          fi
```

どちらのスクリプトも、書き換えたファイルを自分で `git add`／`git mv` します。最後のステップは、ステージされたものをまとめてコミットするだけです。実際のコミットはこうなります（1 件に絞り、ファイル名は伏せています）。

```text
chore: promote scheduled todos for 2026-10-12

 .../00804_desk => 00100_NEXTACTION}/2026-09-13-xxx.md  | 3 ++-
```

`status` の差し替え（1 行）と、昇格したことを残すログの追記（1 行）で `3 ++-`、それに移動（`=>`）が、**1 コミットに入っています**。

`organize_files.py` は、Organize TODOs や毎晩の整理 workflow からも呼ばれます。何度呼ばれても余計な変更が出ないように、`status` と置き場所を見て、もう正しい場所にあれば何もしない作りにしてあります。**経路が重なっても結果が同じになる**ので、同じ job から呼び足しても困りませんでした。

`[skip ci]` は外しました。効果が無いうえに、付いていると「意図して CI を止めている」と読めてしまうからです。

## runner は UTC なので、date.today() が前日になっていた

初回の cron が走った 9 月 10 日（6:54 JST）の昼に、もう 1 つ直しました。昇格の判定に `date.today()` を使っていたのですが、これは実行環境のローカルの日付を返します。GitHub ホストの runner は UTC なので、JST 6:50 の cron（UTC では前日の 21:50）で呼ぶと、**JST の前日**が返っていました。

初回の run のログにも `基準日: 2026-09-09` と出ていました（JST では 9 月 10 日の朝です）。当時は「着手日の 3 日前に昇格」にしていたので、実際には 2 日前に昇格するのと同じ動きになっていました。他のスクリプトと同じく、設定のタイムゾーンで今日を取るように揃えました。

```python
def get_today() -> date:
    """Get today's date in JST.

    runner は UTC なので `date.today()` を使うと、JST 06:50 の cron では前日になる。
    """
    return datetime.now(TZ).date()
```

`TZ` は設定ファイルの `Asia/Tokyo` から作った `ZoneInfo` です。workflow 側のシェルで日付を取るところも、`TZ=Asia/Tokyo date` と明示しています。

2026 年 10 月時点のドキュメントでは、`schedule` にもタイムゾーンを指定できるようになっています（上の schedule の参考リンク）。ただ、変わるのは起動する時刻のほうで、runner の時計は UTC のままです。Python が使うローカルのタイムゾーンは変わらないので、今回は実行環境に依存しないよう、`datetime.now(TZ).date()` で明示しました（プロセスに `TZ=Asia/Tokyo` を渡す手もあります）。

参考: [Python Docs - zoneinfo](https://docs.python.org/3/library/zoneinfo.html)

ちなみに「3 日前」は、9 月 12 日に「当日」へ変えました。手元のタスク 17 件で締切（`due_date`）と着手日の差を数えると、1 日が 14 件、3 日が 1 件、10 日が 2 件とばらばらで、一律の日数では表せませんでした。一律に 3 日早めると、`review_date` に書いた着手日の意味が薄れてしまいそうです。早く始めたいタスクは、`review_date` を前に置けば済むかなと思います。

## まとめ

- `GITHUB_TOKEN` で行った push では、別の workflow は起動しない。再帰を防ぐための仕様で、`[skip ci]` を付けても外しても変わらない
- 私のリポジトリでは、昇格の workflow が push したコミット 19 件に対して、push で起動した run は 0 件だった。`head_sha` だけで引くと schedule の run が混ざるので、`event=push` で絞って数える
- 後続が「別の workflow の起動」ではなく「同じリポジトリの書き換え」なら、今回は同じ job で直接呼ぶのが素直だった。そのぶん、呼ぶスクリプトは何度走っても結果が変わらない作りにしておく
- GitHub ホストの runner は UTC で動く。JST の 9 時より前に走る cron で `date.today()` を使うと、JST の前日になる
- workflow の push で次の workflow を起動するつもりの連鎖があれば、一度 **`event=push` の run を数えてみる**と安心

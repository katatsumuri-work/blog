---
title: 'SKILL.md の行数を CI で縛ったら、ちゃんと落ちたのに赤のままマージしていた'
slug: 'skill-md-line-gate'
date: 2026-10-14T09:00:00+09:00
categories: ['tech']
tags: ['claude-code', 'github-actions']
draft: false
---

Claude Code のスキルを自作していると、`SKILL.md` は知らないうちに育っていきます。そこで、公式ガイドが勧める「本文 500 行未満」を目安に、**450 行（90%）で PR を落とす** CI を入れました。

1 か月後、ゲートは狙いどおりに落ちました。ところが私は、**赤いままの PR を 4 本マージしていました**。行数は 2 日後に、別の調べもので手元でスクリプトを流し直したときに違反に気づき、分割して 450 を下回らせました。ただ、赤のままマージしていたこと自体には、この記事を書くために CI の履歴を見返すまで気づいていませんでした。原因は、このゲートを required check にしていなかったことです。

ゲートの作り方と、落ちたのに止まらなかった顛末、そのあとの分割で分かったことを書きます。舞台は、日報やタスク管理を回している個人のプライベートリポジトリです（2026 年 9〜10 月、GitHub Actions の `ubuntu-latest` / Python 3.11）。

## SKILL.md の本文は、スキルを使うときに丸ごと載る

スキルの読み込みは 3 段階になっています。起動時に読まれるのは全スキルの `name` と `description` だけで、`SKILL.md` の本文はそのスキルが必要になったときに読まれます。`references/` などの別ファイルは、さらに必要になったときだけ読まれます。

> At startup, only the metadata (name and description) from all Skills is pre-loaded. Claude reads SKILL.md only when the Skill becomes relevant, and reads additional files only as needed.

参考: [Skill authoring best practices - Concise is key](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices#concise-is-key)

`references/` は読まれない回がありますが、`SKILL.md` の本文はスキルを使うなら必ず丸ごとコンテキストに載ります。Claude Code のドキュメントによると、**載った本文はそのあとのターンでもコンテキストに残ります**。

> Once a skill loads, its content stays in context across turns, so every line is a recurring token cost.

参考: [Claude Code Docs - Extend Claude with skills](https://code.claude.com/docs/en/skills)

本文の 1 行 1 行が、そのあとのやりとりでもコンテキストを使い続けるということです。公式ガイドには目安の行数も書かれています。

> * Keep SKILL.md body under 500 lines for optimal performance
> * Split content into separate files when approaching this limit

参考: [Skill authoring best practices - Progressive disclosure patterns](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices#progressive-disclosure-patterns)

Claude Code 側のドキュメントにも「Keep `SKILL.md` under 500 lines」とあります。どちらも性能のための推奨で、超えたら読み込めなくなるとは書かれていません。ただ数字の根拠としては十分なので、500 は自分で決めずにそのまま借りました。決めたのは「どこで落とすか」だけです。

## 推奨の 500 ではなく、450 で落とす

500 ちょうどで落とすと、気づいた時点で**もう分割が必要な状態**になっています。公式も「近づいたら分ける」と書いているので、手前で知らせたいと考えました。**90% という数字は公式のものではなく、私の判断です**。

```python
# 公式ガイドの上限と、こちらで落とすしきい値
HARD_LIMIT = 500
WARN_AT = int(HARD_LIMIT * 0.9)  # 450
```

数えるのは frontmatter を除いた本文の行数です。公式の目安が本文に対するものなので、そこに合わせています。手元で測るだけなら、これで足ります。

```sh
awk 'NR==1&&/^---$/{f=1;next} f&&/^---$/{f=0;next} !f' SKILL.md | wc -l
```

あわせて「何を縛らないか」も決めました。

| 対象 | 扱い | 理由 |
| --- | --- | --- |
| `SKILL.md` | 450 行で PR を落とす | スキルを使うなら必ず丸ごと読まれる |
| `references/*.md` | 落とさない。行数は参考表示 | 必要なときだけ読まれる。公式にあるのは「100 行を超えたら目次を付ける」だけで、行数の目安は無い |
| サブエージェント定義・`CLAUDE.md` | 対象外 | 導入時は根拠のある数字を持っていなかった |

参考: [Skill authoring best practices - Structure longer reference files with table of contents](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices#structure-longer-reference-files-with-table-of-contents)

気持ちだけでしきい値を決めると、あとで根拠を説明しにくそうです。**根拠が無いものは縛らない**、と決めておくと迷わずに済みます。

ただ、この記事を書くために見直したところ、いまの Claude Code のドキュメントには `CLAUDE.md` についても「target under 200 lines per CLAUDE.md file」という目安がありました。根拠ができたので、こちらも縛る対象に入れられそうです。

参考: [Claude Code Docs - How Claude remembers your project](https://code.claude.com/docs/en/memory)

### tee に通すと、検査の失敗が消える

ワークフローは `.claude/skills/**` に触った PR で走らせます。結果をジョブのサマリにも出したくて `tee` に通しているのですが、ここでひとつ注意が要ります。

```yaml
      - name: Check SKILL.md line counts
        # `tee` でサマリにも出すが、bash -e は pipefail を立てないので
        # 明示しないと tee の exit code 0 が返り、gate が絶対に落ちなくなる。
        run: |
          set -o pipefail
          python3 .github/scripts/check_skill_size.py | tee -a "$GITHUB_STEP_SUMMARY"
```

`shell` を指定しない `run` は、Linux の runner では `bash -e {0}` で動き、`pipefail` は付きません。パイプの終了コードは最後のコマンド（`tee`）のものになるので、スクリプトが 1 を返しても `tee` が成功すれば**ステップは成功**します。**検査を書いたのに一度も落ちない**、という気づきにくい壊れ方です。

ステップごとに `set -o pipefail` を書くかわりに、`shell: bash`（ワークフロー全体なら `defaults.run.shell: bash`）を明示しても、`-eo pipefail` 付きで動きます。

参考: [GitHub Docs - Workflow syntax（`defaults.run.shell`）](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#defaultsrunshell)

導入時には、449 行で通って 450 行で落ちることをフィクスチャで確かめています。

## 1 か月で 287 行から 492 行へ。増えたのは数回の大きな追加だった

導入した日（2026-09-12）の最大は、日々のふりかえりを回すスキルの 372 行（74%）でした。翌日、このスキルを日次・週次・月次などに分割したので、いちばん大きい日次ふりかえりは 287 行から再スタートしています。

そこからの推移です（日付は JST のコミット日）。

| 日付 | 本文の行数 | 増減 | 足したもの |
| --- | ---: | ---: | --- |
| 09-13 | 309 | +22 | 分割直後の小さい追加（3 回） |
| 09-14 | 354 | **+45** | その日に完了したタスクの拾い漏れ対策 |
| 09-17〜09-24 | 373 | +19 | 小さい追加（5 回） |
| 10-05 | 419 | **+46** | コミットが無かった日の案件も聞く |
| 10-10 | 424 | +5 | 小さい追加 |
| 10-10 | 480 | **+56** | 記録チェックの項目を 1 つ足す |
| 10-10 | 492 | +12 | 同じ項目の聞き方を直す |

増えた 205 行のうち 147 行（72%）が、太字にした 3 回の追加によるものです。最後の 2 行は同じ 1 本の PR で、**この PR だけで +68 行**。ここで 450 を越えました。

このスキルの場合は、じわじわではなく、数回の大きな追加でしきい値を越えていました。**上限ちょうどで落とす設計だったら、492 行のこの PR は素通りしていたはずです**。手前で落としたので、検出はできました。

ただ、1 本で 68 行入ることがあるなら、**50 行の余裕では足りない場面もありそうです**。90% は「根拠を説明できる最小限の余裕」くらいに考えています。

## ゲートは落ちた。そして赤のまま 4 本マージした

ゲートが落ちたあとの CI の履歴です（日時は UTC）。

| 日時 | PR | ゲート | その後 |
| --- | --- | --- | --- |
| 10-10 04:50 | 1 本目: 日次ふりかえりに項目を足す | **failure**（480 行） | |
| 10-10 04:58 | 同上（追加コミット） | **failure**（492 行） | 05:00 にマージ |
| 10-10 06:13 | 2 本目: 別スキルの修正 | **failure** | 06:20 にマージ |
| 10-10 06:14 | 3 本目: 別スキルの修正 | **failure** | 06:20 にマージ |
| 10-12 00:07 | 4 本目: 別スキルの修正 | **failure** | 00:14 にマージ |
| 10-12 07:14 | 日次ふりかえりを分割 | success | 07:16 にマージ |

1 本目は、赤くなってから 10 分後にマージしています。このときはマージまで Claude Code に任せていて、**CI の結果を誰も見ていませんでした**。

それでもマージできたのは、**このゲートを required check にしていなかった**からです。デフォルトブランチにブランチ保護もルールセットも設定していないので、赤くてもマージは通ります。**CI を「落ちる仕組み」として作り、「止める仕組み」にはしていなかった**わけです。

参考: [GitHub Docs - About protected branches（Require status checks before merging）](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging)

もう 1 つ効いていたのが、検査の範囲です。このスクリプトは**変更したスキルだけでなく、全スキルを数えます**。そのため、日次ふりかえりと関係の無いスキルを直した PR まで赤くなりました。

2 本目以降の 3 本は、1 本目で入った 492 行の違反を引き継いで赤くなっていた PR です。CI のログでも、3 本とも違反は日次ふりかえりの 492 行の 1 件だけでした。PR 自体の変更は、日次ふりかえりと関係がありません。仮に誰かが見ていたとしても、自分の変更と関係ない理由の赤が続けば、「いつものやつ」として流していたかもしれません。

### required にするなら、paths の絞り込みも見直す

差分だけを検査すれば、無関係な PR は赤くなりません。ただ、そうすると違反しているスキルに触らない限り、違反がずっと見えなくなります。私は全体を見るほうを残して、赤いままマージできないようにするつもりです。

ただし、いまのワークフローをそのまま required にすると、別の詰まり方をします。`paths` で `.claude/skills/**`（と検査スクリプト・ワークフロー自身）に絞っているので、**それ以外しか触らない PR ではワークフロー自体が走りません**。

> If a workflow is skipped due to path filtering, branch filtering, or a commit message, then checks associated with that workflow will remain in a "Pending" state. A pull request that requires those checks to be successful will be blocked from merging.

参考: [GitHub Docs - Workflow syntax（`on.pull_request.paths`）](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)

検査は数秒で終わるので、`paths` を外して全 PR で走らせるのが素直かなと思っています。

確認する場所は、リポジトリの Settings の Rules（または Branches）です。デフォルトブランチに「Require status checks to pass」があり、そこにジョブ名（ここでは `check-skill-size`）が入っているかを見ます。一人で管理するリポジトリでは、マージする自分や自動化が bypass の対象になっていないかもあわせて見ておくと安心です。

なお個人アカウントの private リポジトリでは、ブランチ保護もルールセットも GitHub Pro 以上でないと使えません。**Free のままだと、そもそも止める手段が無い**ことになります。

参考: [GitHub Docs - About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)

もう 1 つ、このリポジトリには自動バックアップが master へ直接 push する運用もあります。表の 09-14 の追加はその直 push で入っていて、**そもそもゲートを通っていません**。保護を掛けるならこちらとの兼ね合いも見ることになりそうです。

**このあたりはまだ手を付けていません。** 記事の時点で、required check は未設定のままです。

## 直し方は「書くな」ではなく「置き場所を変えろ」だった

分割の前に、何が膨らませていたのかを見ました。行数の大半はいくつかの大きな節に集まっていて、どの節にも同じ形の記述が並んでいました。

```text
2026-09-14 の実測で、その日 done になった 13 件のうち 6 件を落とした（抜粋・要約）
```

「なぜそうするのか」を、実際に起きた失敗と一緒に書いた段落です。同じ失敗を繰り返さないために残した記録なので、**内容は削りたくありません**。**問題は内容ではなく置き場所でした**。

そこで方針をこう決めました。

- `SKILL.md` には「何をするか」を残す
- `references/` には「なぜそうするか」と「どう操作するか」を移す

手順 1（材料の集め方）の実例と落とし穴、手順 4（記録の書き戻し）の操作を、`references/` の 2 本（113 行・91 行）に移しました。本体からは 96 行を削り、判断のルールと参照先を 50 行書き足したので、**差し引きでは −46 行**です。`references/` の 2 本は目次や背景を付けて書き起こしたので、削った行数より長くなっています。手順の見出しは 6 つとも本体に残しています。

```text
[NG]  492 行 ( 98%)  .claude/skills/retro/skills/daily/SKILL.md
          ↓
[ok]  446 行 ( 89%)  .claude/skills/retro/skills/daily/SKILL.md
違反なし
```

移した `references/` がどれくらいの頻度で、どれくらいの量読まれているかは、まだ測っていません。今回確認できたのは、本体を 446 行に減らしてゲートを通せたところまでです。

## 「単一の出所」として参照されている節は、分割の PR では動かさなかった

外に出したかったのに、今回は残した節もあります。タスクの起票ルールを書いた手順 5（102 行）です。

この節は、リポジトリの `CLAUDE.md` の索引と、別スキルの `SKILL.md` から「起票ルールの**単一の出所**」として参照されています。`references/` に移しても単一の出所のままにはできますが、参照元 2 箇所も同時に直す必要があり、分割の PR に混ぜるには範囲が広すぎました。

重複を避けるために参照を一箇所へ集めた結果、**その節を動かすコストが一段上がっていた**わけです。

446 行は 450 の手前で、**足せるのはあと 3 行です**（4 行足すと落ちます）。次に何か足すときは、この節を参照元ごと動かす PR を先に出すことになりそうです。

## まとめ

- `SKILL.md` の本文はスキルを使うなら必ず丸ごと読まれ、そのあとのターンでもコンテキストを使う。公式ガイドは本文 500 行未満を勧めていて、「近づいたら分ける」とも書いている
- 推奨ちょうどではなく 90%（450 行）で落とした。今回は 1 本の PR で 68 行増えて 450 を越え、500 で落とす設計なら素通りしていた 492 行を検出できた。ただし 50 行の余裕で足りるとは限らない
- `tee` に通すなら `set -o pipefail` か `shell: bash` を。無いと、検査が失敗してもステップは成功する
- **落ちるゲートを作っても、required にしなければ止まらない**。1 本目はマージを Claude Code に任せていて、赤を誰も見ていなかった。全スキルを検査する設計なので、2 本目以降は違反を引き継いで無関係な PR まで赤くなった。私は 10-10〜10-12 の 3 日間で計 4 本（うち無関係な PR が 3 本）、赤のままマージした
- required にするなら、`paths` の絞り込みで Pending のまま止まらないかも確認する。個人の private リポジトリなら、プランが Pro 以上かも
- 行数のゲートが求めていたのは「書くな」ではなく「置き場所を変えろ」。移した先がどれだけ読まれているかはまだ測っていない。また「単一の出所」として参照されている節は、参照元ごと動かす必要がある

ゲートを作ったところで満足して、マージを止める側の設定を見ていなかった、というのが今回いちばんの反省です。

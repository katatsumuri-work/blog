---
title: '4 つのリポジトリを submodule で束ねた ― 親のコミットの 62% は「子が進んだ」だけだった'
slug: 'git-submodule-monorepo'
date: 2026-09-20T09:00:00+09:00
categories: ['tech']
tags: ['git', 'github-actions']
draft: false
---

一人でやっている会社ですが、リポジトリは 4 つに分かれています。API、ブログ、コーポレートサイト、インフラ。それぞれ言語もデプロイ先も違うので、分けること自体に迷いはありませんでした。

迷ったのは、**その 4 つをどう見渡すか**です。結局、親リポジトリを 1 つ作って **git submodule** で束ねました。

4 か月ほど運用したので、良かったところと面倒だったところを書いておきます。先に結論を言うと、**面倒の大半は 1 つのことに集約されていて、それは自動化で消せました**。

## 構成

親が 4 つの子を submodule として持つ、それだけです。

```
katatsumuri-work/          親（アンブレラ）
├── api/     → katatsumuri-work/api      Rust + axum       public
├── blog/    → katatsumuri-work/blog     Hugo              public
├── web/     → katatsumuri-work/web      Astro             public
└── infra/   → katatsumuri-work/infra    Terraform         private
```

`.gitmodules` には `branch = main` を明示しています。`git submodule update --remote` が「どのブランチの最新を取るか」を決める値です。

省略しても既定は remote HEAD なので、子の HEAD が `main` である今の構成では結果は同じです（`gitmodules(5)`、Git 2.39.5 で確認）。それでも書いているのは、**将来 HEAD が変わったときに親の意図が残るように**という理由だけです。

参考: [gitmodules(5)](https://git-scm.com/docs/gitmodules)

```ini
[submodule "api"]
	path = api
	url = git@github.com:katatsumuri-work/api.git
	branch = main
```

クローンするときは再帰指定が要ります。

```sh
git clone --recurse-submodules git@github.com:katatsumuri-work/katatsumuri-work.git
```

## なぜ 1 つのリポジトリにまとめなかったか

**子が独立して動けることを優先しました。**

ブログには Hugo のビルドとデプロイがあり、API には Rust のテストがあり、インフラには Terraform があります。これらを 1 つのリポジトリに入れると、CI が「変更されたパスを見て走るジョブを切り替える」構造になります。書けないことはありませんが、一人でやる規模で払うコストとしては重い。

それに、**公開範囲が違います**。API・ブログ・サイトは public ですが、インフラは private です。1 つにまとめるなら全体を private にするしかなく、そうすると「コードを見せる」という目的が失われます。

## なぜバラバラのままにしなかったか

逆に、親を作らず 4 つ並べるだけでもよかったはずです。実際それでも動きます。

親を作った理由は **「その時点の全体」をひとまとまりで記録したかった**からです。API をこのバージョンにしたとき、インフラはこの状態で、サイトはこう出ていた——という組み合わせが親のコミットとして残ります。あとから「あの頃どうなっていたか」を辿るとき、これがあると楽です。

もう 1 つは**入口が 1 つになる**こと。README を親に置いておけば、そこから 4 つに散っていけます。自分のためというより、あとから見る人のためです。

## 運用ルールは 2 行で足りる

- 子リポジトリで作業して push する
- 親で pointer を追従させる

子は普通のリポジトリなので、**単独でクローンしてそのまま作業できます**。submodule であることを意識するのは親側だけです。ここは想像していたより快適でした。

追加するときはこれだけです。

```sh
git submodule add -b main git@github.com:katatsumuri-work/blog.git blog
git commit -m "blog を submodule として追加"
```

親で最新を取り込むときはこうです。

```sh
git submodule update --remote --merge   # 各子の main の最新を取る
git add blog && git commit -m "blog の pointer を追従"
```

参考: [git-submodule(1)](https://git-scm.com/docs/git-submodule)

## 面倒なのは pointer 追従、それだけ

submodule の面倒さは、ほぼこの 1 点に集約されます。

子で push しても、**親は勝手に追いつきません**。親が記録しているのは「子のどのコミットを指すか」という情報なので、これを手で更新してコミットする必要があります。

```console
$ git status
Changes not staged for commit:
	modified:   blog (new commits)
```

この `(new commits)` が出るたびに、親でコミットを作る。子を触るたびに発生するので、地味に効いてきます。

### 数えてみたら 3 分の 2 だった

実際どのくらいの比率になっているか数えてみました。

```console
$ git log --oneline | wc -l
45
$ git log --format=%s | grep -cE '^chore: submodule pointer'   # 自動で追従したぶん
19
```

手で追従していた時期のコミット（`… pointer を … に追従` という書き方をしていました）が別に 9 件あるので、**pointer 追従は合わせて 28 件**。親の 45 コミットのうち **62%** が「子が進んだことを記録するだけ」でした。

内容のあるコミットは 17 しかありません。

ただし、この数字の読み方には注意が要ります。**28 件のうち 19 件は自動化を入れたあとのもの**です。30 分ごとに定期実行が回って、子が進むたびに PR を立てるので、**自動化は比率を下げるどころか押し上げています**。

手間はゼロになりましたが、履歴のノイズはむしろ増えました。「面倒だったから自動化して解決」ではなく、**「面倒が目に見えない場所へ移った」**というのが正確なところです。

## 自動化したら気にならなくなった

そこで、pointer 追従を GitHub Actions に任せました。定期的に各子の main を見て、進んでいれば親に PR を作って即マージする、という仕組みです。

詳しくは [submodule pointer の追従を GitHub Actions で自動化した話]({{< ref "2026-06-15-automate-submodule-pointer-bump.md" >}}) に書きました。

これを入れてから、pointer のことは考えなくなりました。

……と、しばらくは思っていました。実際にはこの定期実行、あとで**エラーも出さずに止まっていた**ことが分かります。public リポジトリの scheduled workflow は、60 日間動きがないと GitHub が自動で無効化するためです。親のログを見ると、**2026 年 6 月 17 日から 9 月 8 日まで約 2 か月半、コミットがゼロ**でした。その間 pointer は追従していません。

顛末は [GitHub Actions の cron が、ある日から 1 日 48 回中 6 回しか動かなくなった]({{< ref "2026-09-19-scheduled-workflow-silently-stops.md" >}}) に書きました。

**自動化は「考えなくてよくなる」のではなく、「考える対象が pointer から workflow に移る」**というのが正直なところです。それでも手で追従するより楽なのは間違いないのですが、任せきりにできるわけではありませんでした。

### もう 1 つの面倒：private な子を CI から引くとき

`infra` だけ private なので、GitHub Actions から submodule を fetch しようとすると認証で止まります。`.gitmodules` は SSH URL なので、トークン付きの https に差し替える必要がありました。

```sh
git config --global \
  url."https://x-access-token:${SYNC_PAT}@github.com/".insteadOf "git@github.com:"
```

「公開範囲を混ぜられる」のは submodule の利点として挙げましたが、**その分だけ CI にトークンを渡す手間が増えます**。表と裏です。

参考: [git config - url.&lt;base&gt;.insteadOf](https://git-scm.com/docs/git-config#Documentation/git-config.txt-urlltbasegtinsteadOf)

## 共通ファイルも配れる

親を正にして、共通のファイルを子へ配る仕組みも作りました。AI エージェント向けのルールファイル（`AGENTS.md` など）を全リポジトリで揃えたかったからです。

コピペで配ると必ずズレます。親で更新したら各子に PR を立てて即マージする、という配布パイプラインにしました。これも submodule 構成だから素直に書けた部分です。

## 向いている場合とそうでない場合

4 か月やってみて、こう感じています。

**向いていそう**

- **子ごとに CI やデプロイ先が違う**。1 つにまとめるとパス分岐だらけになる場合
- **公開範囲が混在する**。public と private を同居させたい場合
- 子が**単独でも意味を持つ**。それだけクローンして動かせる場合

**向いていなさそう**

- **子をまたぐ変更が頻繁**。API と web を一緒に直すことが多いなら、pointer 追従が毎回ついて回る
- **チームが大きい**。submodule の作法を全員に周知するコストが、得られる見通しに見合わない
- 子が細かく分かれすぎている。数が増えるほど pointer 追従の回数も増える

今回のケースは「子ごとに技術が違う」「public と private が混在」「子が単独で完結する」が揃っていたので、素直に嵌まりました。逆にこれらが当てはまらないなら、**無理に submodule にする理由はない**と思います。

## まとめ

- 親 1 つ ＋ 子 4 つの submodule 構成。子は**単独のリポジトリとして普通に扱える**
- 親を作ったのは「**その時点の全体**」を記録したかったから。入口が 1 つになる副次効果もある
- 面倒は 2 つ。**pointer 追従**（親のコミットの 62% がそれだった）と、**private な子を CI から引く認証**
- どちらも機械的なので自動化できる。ただし**自動化は比率を下げるどころか押し上げる**（履歴のノイズは増える）
- そして**自動化したら忘れてよいわけではない**。その定期実行が 2 か月半、黙って止まっていた
- 向くのは「子ごとに技術・公開範囲が違い、子が単独で完結する」場合

submodule は評判があまり良くない機能ですが、**面倒の正体が分かっていれば付き合える**というのが、やってみての感想です。

---
title: '定期実行を GitHub Actions から Cloud Build に移した ― 判断を握っている場所を変える'
slug: 'cloud-build-migration'
date: 2026-09-22T09:00:00+09:00
categories: ['tech']
tags: ['gcp', 'cloud-build', 'github-actions']
draft: false
---

前に [GitHub Actions の cron が、ある日から 1 日 48 回中 6 回しか動かなくなった]({{< ref "2026-09-19-scheduled-workflow-silently-stops.md" >}}) という記事を書きました。定期実行が発火せず、このブログの記事が公開されないまま止まっていた話です。

あの記事の最後にこう書きました。

> 正直に書いておくと、**私はまだそこまで直していません**。やったのは時分をずらしたことと、次に書く監視を足したことだけです。

その宿題を片付けました。公開経路も、それを見張る監視も、**Cloud Build + Cloud Scheduler** に移して、GitHub Actions のワークフローは削除しています。2026 年 9 月中旬の記録です（Hugo 0.161.1 extended / Firebase CLI 15.30.0）。

## 前提：なぜ定期実行が要るのか

このブログは記事を先に書いて、`date` を未来の日付にして置いています。Hugo は既定で未来日の記事をビルドから除外するので（[`buildFuture`](https://gohugo.io/configuration/all/#buildfuture)）、そのままなら当日まで出ません。

つまり「**その日にビルドし直す仕組み**」が公開の生命線です。誰も push しない日でも、朝になったらビルドが走る必要があります。

これを GitHub Actions の `schedule` に任せていたのですが、組んでから **3 日連続で実行が 0 件**でした。毎朝 404 を手で直す羽目になりました。

ただ、日次は 1 日 1 回しか動かないので、3 日ぶんでは統計になりません。そこで、この blog を submodule として束ねている親リポジトリで 30 分ごとに回していた別のワークフローの実行ログを数えたら、**1 日 48 回動くはずが 6 回**でした。日次が飛んでいたのも偶然ではなさそうだ、と判断しました。

## 選択肢と、捨てたもの

移す前に 4 つ検討しました。ここで比べているのは「**どこの cron を使うか**」です。決めたあとにもう一段「**その cron から何を叩くか**」で迷うのですが、それは次の節で書きます。

**毎時ビルドにする。** 時分をずらして回数を増やす案です。「当たるまで撃つ」発想で筋が悪く、1 日 24 回のうち 23 回は無駄になります。しかも確実性が上がった保証はどこにもありません。却下しました。

**push 駆動に替える。** これは**そもそも成立しません**。未来日公開では、公開時刻が来ても誰も push しないからです。イベント駆動に寄せれば解決、という単純な話ではありませんでした。

**監視が異常を検知したら自動で復旧させる。** 未公開を検知したらビルドを叩き直す案です。既にある仕組みに数行足すだけで済みます。ただし**当時はその監視自体も GitHub Actions の `schedule`** で、しかも実際に予定より 5 時間近く遅れて動いていました。飛んだ日は翌日まで気づけません。「毎日 1 本ずつ出す」が譲れない条件だったので、これも却下です。

**別のプラットフォームの cron を使う。** Cloudflare Workers の Cron Triggers も候補でした。実際 Workers は別のサービスで動かしていて実装も小さいのですが、**会社のインフラは GCP に寄せています**。サイトも API も Firebase / Cloud Run です。公開経路のためだけに別プロバイダを持ち込むと、依存が増えるわりに得るものが「cron が動く」ことだけになります。

残ったのが Cloud Scheduler でした。

## Cloud Scheduler から何を叩くか

前回の記事では「外部のスケジューラから `workflow_dispatch` を叩く形にするのが筋」と書きました。実際に手を動かしてみたら、そこで止まりませんでした。

**`workflow_dispatch` を叩く**なら、既存のワークフローをそのまま使えます。実装としては一番小さくて済みます。ただし **GitHub 側の認証情報が必要**です。Workload Identity 連携は「GitHub Actions から GCP へ」の向きの仕組みで、**逆向き（GCP から GitHub API を叩く）には使えません**。GitHub 側が Google の OIDC トークンを受け付けないからです。

選択肢は PAT（Personal Access Token）・GitHub App のトークン・OAuth トークンあたりで、最小構成なら PAT です。GitHub App にしても、今度はアプリの秘密鍵を持つことになります。**どれを選んでも、長期的な秘密がひとつ増える**のは変わりません。せっかく鍵レスで済んでいたものを戻すのは惜しいなと思いました。

参考: [GitHub Docs - Create a workflow dispatch event](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event) ／ [Workload Identity 連携](https://cloud.google.com/iam/docs/workload-identity-federation)（外部 ID から **Google Cloud のリソース**にアクセスするための仕組みです）

それに、この案だと**結局 GitHub Actions の実行に依存します**。混雑の影響を完全には切れません。

そこで **Cloud Build でビルドからデプロイまでやる**ことにしました。日次の経路では GitHub Actions も GitHub API も使わず、GitHub は**ソースの取得先**として使うだけになります。デプロイの認証は Cloud Build のサービスアカウントで完結します。ビルド環境では ADC（Application Default Credentials）として自動で拾われるので、鍵ファイルを渡す必要がありません。

ただし GitHub と無縁になるわけではありません。push トリガーとソース取得のために、**Cloud Build GitHub App のインストールとリポジトリ接続**は要ります。ここは Terraform の管理外で、事前に一度だけ手作業が必要でした。

## 構成

ビルド定義はリポジトリに置いて、インフラ側は「いつ・どの権限で動かすか」だけを持ちます。

```yaml
# cloudbuild.yaml（抜粋）
substitutions:
  _HUGO_VERSION: '0.161.1'
  _FIREBASE_TOOLS_VERSION: '15.30.0'

steps:
  - id: build
    name: debian:12-slim
    entrypoint: bash
    args:
      - -c
      - |
        set -euo pipefail
        apt-get update -qq && apt-get install -y -qq --no-install-recommends curl ca-certificates
        base="https://github.com/gohugoio/hugo/releases/download/v${_HUGO_VERSION}"
        tarball="hugo_extended_${_HUGO_VERSION}_linux-amd64.tar.gz"
        workdir="$(mktemp -d)"
        curl -sSLo "$workdir/$tarball"       "$base/$tarball"
        curl -sSLo "$workdir/checksums.txt"  "$base/hugo_${_HUGO_VERSION}_checksums.txt"
        ( cd "$workdir" && sha256sum --check --ignore-missing checksums.txt )
        tar -xzf "$workdir/$tarball" -C /usr/local/bin hugo
        # 未来日の記事は既定で除外される。それが当日公開の仕組みなので
        # --buildFuture は付けない
        hugo --gc --minify

  - id: deploy
    name: node:22-slim
    entrypoint: bash
    args:
      - -c
      - |
        set -euo pipefail
        npx --yes "firebase-tools@${_FIREBASE_TOOLS_VERSION}" deploy \
          --only hosting --project "$PROJECT_ID" --non-interactive
```

この 2 つは**最初は書いていませんでした**。Hugo のアーカイブは無検証でそのまま実行していましたし、`firebase-tools` も `npx --yes firebase-tools` で毎回その時点の最新が降ってくる状態です。この記事を書きながら気づいて足しました。

とくに後者は間抜けで、**この移行で踏んだ 2 つ目の失敗がまさに「firebase-tools が Node v19 に対応していない」**でした。ランタイムのほうは固定したのに、CLI のほうは野放しのままだったわけです。ある朝いきなり壊れる余地を残していました。

`sha256sum --check --ignore-missing` は、改ざんされていても対象が無くても非ゼロで落ちます。`--ignore-missing` は「検証対象が 1 つも無ければ成功」にはならないので、そこは安心してよさそうです。

Cloud Build が展開するのは、`$PROJECT_ID` のような**組み込みの置換変数**と、`_` で始まる**ユーザー定義の置換変数**（ここでは `$_HUGO_VERSION`）だけです。`$url` はどちらにも当たらないので、そのまま bash に渡ってシェル変数として解決されます。逆にいうと、**大文字ならなんでも展開されるわけではありません**。ユーザー定義のほうは `_[A-Z0-9_]+`（アンダースコア始まりの大文字英数）が条件なので、そこだけ覚えておけばよさそうです。

トリガーは 1 つで、**push・日次・手動のすべてを受けます**。Terraform 側では、必要な API の有効化・IAM・サービスアカウント・トリガー・Cloud Scheduler のジョブを定義しています。

参考: [Cloud Build - 置換変数の値を代入する](https://cloud.google.com/build/docs/configuring-builds/substitute-variable-values) ／ [ビルドトリガーの作成と管理](https://cloud.google.com/build/docs/automating-builds/create-manage-triggers)

## 使った `cloud-builders` のイメージが古かった

移行で 2 回落ちました。症状は別々でしたが、根っこはどちらも **使った `gcr.io/cloud-builders/*` イメージの実行環境が古いこと**でした。

最初は Hugo の**実行**で止まりました。当時は取得と実行を別ステップに分けていたのですが、取得（`curl`）自体は通っていて、落ちたのはそのあとバイナリを起動したところです。

```text
/workspace/hugo: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.33' not found
/workspace/hugo: /lib/x86_64-linux-gnu/libstdc++.so.6: version `GLIBCXX_3.4.29' not found
```

`gcr.io/cloud-builders/curl` の glibc が古く、**Hugo の extended 版が動きません**。extended はネイティブライブラリに依存するので、新しめのディストロが要ります。`debian:12-slim`（glibc 2.36）に変えて解決しました。

ただ、白状すると**ここは順番を間違えています**。このブログのテーマは自前で、SCSS を 1 つも使っていません。つまり現時点では extended である必然性がなく、「将来 SCSS を使うかもしれないから」で選んでいるだけです。同じエラーを踏んだ方は、イメージを差し替える前に **そもそも extended が要るか**を確かめるほうが早いかもしれません。通常版なら glibc の要求はぐっと緩くなります。

直したら、次はデプロイで止まりました。

```text
Firebase CLI v15.30.0 is incompatible with Node.js v19.0.0
Please upgrade Node.js to version >=20.0.0 || >=22.0.0 || >=24.0.0
```

今度は `gcr.io/cloud-builders/npm` の **Node が v19** でした。`node:22-slim` に変えています。

言えるのは「**今回使った 2 つが古かった**」までで、`cloud-builders` 全体が放置されていると断じる材料は持っていません。公式ドキュメント上はいまも提供されているものです。ただ、Node v19 は **2023 年 6 月に EOL** を迎えた版で、2026 年 9 月時点でもそれが載ったままでした。新しめのランタイムが要るものは、最初から公式イメージを使うほうが早いと思います。

参考: [Cloud Build - Cloud ビルダー](https://cloud.google.com/build/docs/cloud-builders)

### 手元の Docker で先に確かめる

2 回目からは、直す前に手元で確認するようにしました。

```console
$ docker run --rm --platform linux/amd64 node:22-slim bash -c 'node --version; npx --yes firebase-tools --version'
v22.23.2
15.30.0
```

`--platform linux/amd64` の指定が要ります（手元が Apple Silicon なので、付けないと別のアーキテクチャで試すことになります）。**Cloud Build に投げて数分待つより、この 1 回のほうが速い**です。実際、このやり方に変えてからは修正が一発で通るようになりました。

## 日次は 1 本に絞った

```hcl
# infra/gcp/cloud-build-blog-deploy/（抜粋）
default   = ["5 9 * * *"]   # variables.tf
time_zone = "Asia/Tokyo"    # main.tf（google_cloud_scheduler_job）
```

最初は保険も兼ねて 2 本（09:23 と 13:23）にしていたのですが、どちらの時刻にも根拠がありませんでした。

**「23 分」は GitHub Actions 時代の名残**です。あちらは「毎時 0 分付近は混むから避けろ」と公式に書かれていたので分をずらしていました。**その作法を、移行先でも要るのか確かめないまま持ち込んでいました**。記事の `date` が 09:00 なので、素直に 09:05 にしました。

2 本目も、起動に失敗しても `retry_config` が初回失敗後に 3 回まで再試行するので、重複していました。ビルド自体が失敗した場合は監視が拾います。**自動で直す枠は置かず、気づく枠に寄せる**という整理です。

参考: [Cloud Scheduler - cron ジョブのスケジュールを構成する](https://cloud.google.com/scheduler/docs/configuring/cron-job-schedules)

## 監視も一緒に移した

前回の記事で自分に突きつけた宿題が、もう 1 つありました。

> 監視をプライベートリポジトリに置いたのは 60 日ルールを避けるためで、障害ドメインを分けたことにはなっていません。

そのとおりだったので、監視も Cloud Scheduler から叩く形にしました。**避けられていたのは 60 日ルールだけで、遅延のほうは避けられていなかった**からです。実際、監視を入れた翌日から 2 日続けて 5 時間近く遅れて動いていました。

日次ビルドが 09:05、監視が **09:35**。ビルドは数分で終わるので、30 分あけておけば十分です。GitHub Actions の頃は遅延を見込んで 1 時間以上あけていましたが、ここまで詰められました。

念のため書いておくと、**Cloud Scheduler も「指定時刻ちょうど」を保証してはいません**。公式には at-least-once、つまり「予定実行ごとに最低 1 回は動く」という設計です。多重起動も起こりえます。それでも GitHub の `schedule` とは前提が違って、あちらは公式に「高負荷時には遅延し、ひどいと drop される」と書かれている側でした。**保証の強さが違う**というだけの話で、だから絶対に大丈夫、ということではありません。

参考: [Cloud Scheduler の概要](https://cloud.google.com/scheduler/docs/overview)

ここを移していなかったら、前の節の「ビルドが失敗しても監視が拾う」は成立していませんでした。監視が 5 時間遅れて動くなら、それは当日のうちに気づく仕組みとしては機能しません。

ただ、**これで障害ドメインを分けたわけではありません**。むしろ逆で、公開も監視もいまは同じ Cloud Scheduler / Cloud Build に乗っています。GCP 側でまとめて転んだら、公開が止まったことに誰も気づけません。前回「障害ドメインを分けたことにはなっていません」と書いた状態から、**分離の度合いはむしろ下がっています**。

意識的にそうしました。今いちばん困っているのは「日次が遅延・未発火で記事が出ないこと」で、その頻度に比べれば GCP がまるごと落ちる確率は低いと踏んだからです。**遅延リスクを取り除く代わりに、共倒れのリスクを受け入れた**という交換です。本当に分離したいなら、監視はまた別の場所（外形監視のサービスや dead man's switch）に置くことになります。そこは宿題として残っています。

## 結果

経路を作ったのが 2026-09-11、GitHub Actions の workflow を消して移行を終えたのが 09-12 です。その **09-12 から 09-14 まで 3 日続けて、手を触れずに記事が公開されました**。3 日続いた「毎朝 404 を手で直す」と、ちょうど同じ日数です。

初日の 09-12 だけは少しややこしくて、朝の時点では両方の経路が生きていました。Cloud Build の日次が 09:05、GitHub Actions の cron が 09:23、workflow を消したのが 09:32 です。**先に走った Cloud Build が出した**格好ですが、そのあと GitHub Actions も動いた可能性は残ります。

この記事を書いているのがその 09-14 なので、証跡はここまでです。公開日には 1 週間ぶん積み増されているはずですが、それは書いている時点では確かめようがありません。

移行前と後で、変わったところと、変わらなかったところです。

| 観点 | 移行前 | 移行後 |
|---|---|---|
| 実行 | 3 日連続で発火せず | 予定どおり |
| 手作業 | 毎朝の手動デプロイ | なし |
| デプロイ認証の長期鍵 | なし（WIF） | なし（ADC） |
| GitHub Actions 側の設定 | WIF provider / SA の紐付け | なし |
| Cloud Build GitHub App | 不要 | 必要（手動で一度だけ接続） |

変わらなかったのが「デプロイ認証の長期鍵」の行です。移行前の GitHub Actions も Workload Identity 連携を使っていて、長期鍵は置いていませんでした。**ここは移行の成果ではなく、悪化させずに済んだだけ**です。`workflow_dispatch` 案を採っていたら、GitHub 側の認証情報が復活していました。なお、前の節で触れた監視のほうは Slack の webhook を Secret Manager に持っているので、システム全体が秘密ゼロというわけではありません。

ついでに気づいたこととして、**自分の認証が切れていても公開は回り続けます**。発火しなかった 3 日間は私が手で叩いて出していたので、`gcloud` や `npx firebase-tools` の認証切れがそのまま「今日は出ない」に直結していました。いまは自分の認証状態とブログの公開が無関係になっています。

もっとも、**前回も「時分をずらしたから直った」と思った翌日に転んでいます**。3 日動いたくらいで直ったと言い切るのは、同じ轍かなと。判断は保留にしておきます。

## 学んだこと

**定期実行の信頼性が要るなら、その判断を握っている場所を変えるしかない。**

言い換えると「**今日ビルドするかどうかを、誰が決めているか**」です。cron の時分をずらすのも、回数を増やすのも、決めている相手は変わりません。それが GitHub のキューである限り、こちらにできるのは祈ることだけでした。

移したことで、決める側が GCP に移りました。それが正しかったかは、これから数か月かけて分かることだと思います。少なくとも今のところは、毎朝きちんと出ています。

## まとめ

- 未来日で記事を仕込む運用は「**その日にビルドする仕組み**」への依存です。push 駆動では代替できません
- Cloud Build でビルドからデプロイまでやると、日次経路では GitHub Actions も `workflow_dispatch` も使わず、**デプロイ認証の長期鍵を増やさずに移せます**（`workflow_dispatch` を叩く案だと、GitHub 側の認証情報がひとつ要ります）
- **今回使った `curl` / `npm` のビルダーは実行環境が古かった**ので、新しいランタイムが要るなら最初から公式イメージのほうが早そうです。ただし Hugo の glibc エラーなら、その前に **extended が本当に要るか**を疑うほうが安上がりです
- 直す前に **手元の Docker で `--platform linux/amd64` を指定して確かめる**と、CI に投げて待つより速いです
- **前のプラットフォームの作法を、確かめずに移行先へ持ち込まない**。根拠のない時刻指定が残ります
- 公開経路と監視は**依存先を意識して選ぶ**。今回は両方 GCP に寄せて、GitHub Actions で実際に踏んだ遅延・drop を切り離した代わりに、共倒れのリスクを受け入れています

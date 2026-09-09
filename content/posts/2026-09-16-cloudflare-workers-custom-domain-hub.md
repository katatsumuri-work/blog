---
title: 'Cloudflare Workers のカスタムドメインは「ゾーンが CF 上にある」前提 ― NS を移さず .app を増やした話'
slug: 'cloudflare-workers-custom-domain-hub'
date: 2026-09-16T09:00:00+09:00
categories: ['tech']
tags: ['cloudflare', 'dns']
draft: false
---

祝日 API（Cloudflare Workers + Hono）を独自ドメインで公開しようとして、壁にぶつかりました。

**Cloudflare Workers のカスタムドメインは、そのドメインが Cloudflare のゾーンとして登録されていること（＝ネームサーバーが Cloudflare を向いていること）が前提**です。外部 DNS のまま `workers.dev` に CNAME を張っても動きません。

以前、[外部 DNS のまま GCP と Firebase にカスタムドメインを生やす]({{< ref "2026-09-11-external-dns-custom-domain-gcp-firebase.md" >}}) という記事を書きました。あちらは「レコードを足すだけで張れる」話でしたが、**Workers はここが違います**。ちょうど裏返しの教訓になったので、その意思決定を残しておきます。

## やりたかったこと

祝日 API を `katatsumuri.work` のサブドメインで公開する、それだけです。

`api.katatsumuri.work`（Cloud Run）が外部 DNS のまま CNAME 1 本で張れていたので、Workers も同じ感覚でいました。

## 落とし穴: 外部 CNAME では届かない

外部 DNS に `*.workers.dev` 宛の CNAME を張っても、Cloudflare 側でルートが解決されず **エラー 1014** になります。

エラー 1014 は "CNAME Cross-User Banned" で、**別のアカウントのゾーンから CNAME で乗り入れることを禁止する**ものです。つまり Workers のカスタムドメインは、DNS レコードを向けるだけでは成立せず、**そのゾーン自体を Cloudflare が持っている必要がある**わけです。

考えてみれば、Cloudflare は DNS とエッジ実行が一体になったプラットフォームなので、「ゾーンを預けてもらう」のが前提の設計なのは自然です。ただ GCP / Firebase の感覚で来ると面食らいます。

参考: [Cloudflare Workers - Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)
参考: [Cloudflare - Error 1014: CNAME Cross-User Banned](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/#error-1014-cname-cross-user-banned)

## なぜネームサーバーを移さなかったか

「じゃあ `katatsumuri.work` のネームサーバーを Cloudflare に移せばいい」となりますが、これは選べませんでした。

このドメインでは **Google Workspace のメールが本番稼働**していて、Firebase Hosting も動いています。ネームサーバーを移すと **MX を含む全レコードを移設先で作り直す**ことになります。設定漏れや移行タイミングのズレで、会社のメールが一通でも落ちるのは受け入れられません。

**サブドメインを 1 つ生やしたいだけなのに、ドメイン全体の DNS を引っ越す**のは、リスクとリターンが釣り合っていない。ここは Cloud Run を選んだときと同じ判断です。

## 着地: ドメインを増やす

結論として、**個人・雑多サービス用に `.app` ドメインを新しく取得**しました。

「NS を移す」か「ドメインを増やす」かの二択で、後者を選んだ形です。決め手はやはり**メールを止めないこと**でした。ドメイン 1 つの年額は、業務メールが落ちるリスクに比べればはるかに安い。

新しいゾーンは最初から Cloudflare にあるので、Workers のカスタムドメインがそのまま使えます。設定は `wrangler.jsonc` に数行書くだけでした。

```jsonc
// カスタムドメイン。katatsumuri.app ゾーンが Cloudflare アカウントに登録済みであれば、
// deploy 時に DNS レコード(CNAME/AAAA)と TLS 証明書を Cloudflare が自動作成する。
"routes": [
  { "pattern": "jp-holidays-api.katatsumuri.app", "custom_domain": true }
]
```

`custom_domain: true` を書いて `deploy` すると、**DNS レコードも TLS 証明書も Cloudflare が勝手に作ります**。手で DNS を触る作業がゼロになるのは、ゾーンを預けている側の利点だと感じました。前の記事で書いた「A レコードと TXT を手で足して、証明書の発行を待つ」手順と比べると、かなり楽です。

## 副産物: 雑多サービスのハブになった

意図せぬ収穫として、**「個人・雑多なサービスをぶら下げるハブ」**が 1 つできました。

業務ドメインは会社の顔なので、実験的なものを気軽に生やしたくありません。一方この `.app` は最初から雑多用なので、思いついた API をサブドメインで足していけます。Workers なら `wrangler.jsonc` に 1 行足すだけです。

結果的に、**「守るドメイン」と「遊ぶドメイン」が分かれた**のは健全だったと思います。最初からそう設計したわけではなく、制約に押し出されて辿り着いた形ですが。

## 判断軸

同じ状況の人向けに、判断の軸を整理しておきます。

| | ネームサーバーを移す | ドメインを増やす |
|---|---|---|
| コスト | 無料 | 年額（`.app` は安い部類） |
| リスク | **メール断のリスク**。全レコード作り直し | ほぼ無し。既存ゾーンに触れない |
| 手間 | 移設作業 + 検証 | 取得して Workers に向けるだけ |
| 向く場面 | そのドメインで他が動いていない | **業務ドメインで何かが本番稼働している** |

要は、**そのドメインで失うものがあるかどうか**です。何も動いていないドメインなら移してしまえばいいし、メールが動いているなら触らないほうがいい。

## まとめ

- **Workers のカスタムドメインはゾーンが Cloudflare にあることが前提**です。外部 CNAME はエラー 1014 で弾かれます
- GCP / Firebase は外部 DNS のまま張れるので、**同じ感覚でいると詰まります**
- ゾーンを預けていれば `custom_domain: true` の 1 行で **DNS も証明書も自動**。ここは素直に快適です
- 業務ドメインで何かが本番稼働しているなら、**NS を移すよりドメインを増やすほうが安全**です
- 「守るドメイン」と「遊ぶドメイン」を分けると、実験の心理的コストが下がります

---
title: 'Cloudflare をやめて Cloud Run にした話 ―「DNS を動かさない」という制約'
slug: 'cloud-run-over-cloudflare'
date: 2026-06-16T09:00:00+09:00
categories: ['tech']
tags: ['cloud-run', 'gcp', 'dns']
draft: false
---

自己紹介 API（Rust + axum で書いています）を `api.katatsumuri.work` で公開するとき、最初は Cloudflare Workers に載せるつもりでした。が、最終的に Google Cloud Run に切り替えています。

技術的な優劣の話ではなく、**「ドメインの DNS を動かせない」という制約**が決め手でした。同じような状況の人もいると思うので、判断の経緯を残しておきます。

## やりたかったこと

- `api.katatsumuri.work` で API を HTTPS 公開したい
- できれば運用が楽で、無料枠に収まる構成にしたい

これだけなら Cloudflare Workers は有力候補です。エッジで動いて速いし、無料枠も広い。最初に検討したのも自然な流れでした。

## 制約：DNS はムームー固定、メールは止められない

ところが、`katatsumuri.work` には外せない事情が 2 つありました。

1. **ドメインの DNS はムームードメインで管理している**
2. **そのドメインで Google Workspace のメールが本番稼働している**（MX レコードが Google を向いている）

特に 2 つめが重い制約です。会社のメールアドレスなので、設定ミスで一通でも落とすわけにはいきません。

参考: [Google Workspace の MX レコードを設定する](https://support.google.com/a/answer/140034)

## Cloudflare Workers を諦めた理由

ここで Cloudflare Workers の前提が引っかかりました。Workers をカスタムドメインで公開するには、**そのドメインを Cloudflare のゾーンとして登録する＝ネームサーバーを Cloudflare に向ける**必要があります。

参考: [Cloudflare Workers - Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/)

つまり `katatsumuri.work` のネームサーバーを「ムームー → Cloudflare」に移管することになります。すると、これまでムームーで持っていた **すべての DNS レコードを Cloudflare 側で作り直す**ことになり、その中には Google Workspace の **MX レコードも含まれます**。

移管のタイミングや設定ミスで MX が一瞬でも欠けると、メールが届かなくなります。「速いエッジ実行」と引き換えにこのリスクを負うのは、さすがに見合わないなと判断しました。`api.` という一つのサブドメインのために、ドメイン全体の DNS を引っ越すのは大げさすぎる、という感覚です。

## Cloud Run を選んだ理由：DNS を動かさなくていい

一方、Cloud Run の **ドメインマッピング**は、**外部 DNS をそのまま使えます**。マッピングを作成すると「この DNS レコードを追加してください」と提示されるので、それを**ムームー側に足すだけ**です。サブドメインなら CNAME（`ghs.googlehosted.com.` 宛て）を 1 本追加すれば終わりで、ネームサーバーの移管は要りません。

参考: [Cloud Run - カスタム ドメインのマッピング](https://cloud.google.com/run/docs/mapping-custom-domains)

これなら：

- ネームサーバーはムームーのまま → **MX レコードは一切触らない**ので、メールは無傷
- 足すのは `api.` の CNAME 1 本だけ → 既存の DNS への影響が局所的
- TLS 証明書は Google マネージドで自動発行・更新

API 本体も Rust のコンテナをそのまま動かせるので、Workers 用に書き換える必要もありません。要件にいちばん素直に収まりました。

## 実際の構成

Terraform で Cloud Run サービスとドメインマッピングを定義しています（抜粋）。

```hcl
# カスタムドメインのマッピング（api.katatsumuri.work）
# DNS（ムームー）側の CNAME 追加は Terraform 管理外（手動）。
resource "google_cloud_run_domain_mapping" "api" {
  location = var.region
  name     = var.domain # api.katatsumuri.work

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.api.name
  }
}
```

マッピングを作ると、登録すべき DNS レコードが `status` に返ってきます。これを `outputs.tf` で拾って、その値をムームーの DNS 設定に手で入れる、という運用にしています。

```hcl
output "domain_dns_records" {
  description = "ムームー DNS に登録すべきレコード（CNAME など）"
  value       = google_cloud_run_domain_mapping.api.status[0].resource_records
}
```

DNS レコードの登録だけは Terraform の管理外（ムームーは Terraform プロバイダを使っていないので手動）ですが、「何を登録すればいいか」は出力で分かるようにしてあります。

ちなみに会社サイト本体（apex の `katatsumuri.work`）は Firebase Hosting に載せていますが、これも「外部 DNS のまま A レコードを足すだけで済む」という同じ理由で選んでいます。

## まとめ

最初は「どのサービスが速いか・安いか」で比べていたのですが、実際に効いたのは **「DNS（特に MX）を動かさずに済むか」** という一点でした。

- Cloudflare Workers … カスタムドメインに NS 移管が必要 → メール移行リスクで見送り
- Cloud Run … 外部 DNS のまま CNAME 追加だけ → 採用

制約を先に洗い出すと、選択肢が自然に絞れてくるなと改めて思いました。もし Cloudflare をフルで使える（DNS ごと Cloudflare に寄せられる）状況なら、また違う結論だったはずです。あくまで「うちの場合は」の判断として残しておきます。

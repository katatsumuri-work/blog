---
title: '手で作った Cloud Run を後から Terraform に import する ― plan が「No changes」になるまで'
slug: 'terraform-import-cloud-run'
date: 2026-09-13T09:00:00+09:00
categories: ['tech']
tags: ['terraform', 'gcp', 'cloud-run']
draft: false
---

自己紹介 API を Cloud Run に載せたとき、最初は `gcloud` コマンドで手早く作りました。動くものを先に見たかったからです。

ただ手で作ったままだと、何をどう設定したかが手元のシェル履歴にしか残りません。あとから **Terraform に import して IaC に移しました**。この記事は、その「後追い IaC 化」の記録です。

やることは単純で、**既存のリソースを Terraform の state に取り込んで、`terraform plan` が「No changes」と言うまでコードを実体に寄せる**、それだけです。ただ 1 つだけ、素直に No changes にならないリソースがありました。

## なぜ最初から Terraform にしなかったか

「最初から IaC で書けばよかったのでは」と言われそうですが、私は後追いでよかったと思っています。

最初は**そもそも構成が固まっていません**。リージョンをどこにするか、Artifact Registry をどう切るか、公開範囲をどうするか。試行錯誤の段階で 1 回ごとに `terraform apply` を回すのは、正直まだるっこしい。

`gcloud` で数回叩いて形が見えてから Terraform に写すほうが、結果的に速く、書くコードも無駄がありませんでした。**IaC は「固まった構成を保全する道具」**として使うのが、少なくとも一人でやる規模では合っていました。

## 準備: state バケットと ADC

state は GCS に置きます。バケットだけは Terraform の外で一度作ります（state を置く場所を state で管理できないため）。

```toml
terraform {
  backend "gcs" {
    bucket = "katatsumuri-work-tfstate"
    prefix = "cloud-run-api"
  }
}
```

`prefix` を切っておくと、あとで別のモジュールを足すときに同じバケットを使い回せます。

認証でひとつ注意があります。Terraform が見るのは **ADC（Application Default Credentials）** で、`gcloud auth login` とは別管理です。CLI では通っているのに Terraform だけ認証エラー、ということが起きます。

```sh
gcloud auth application-default login
```

## import する

**いきなり `apply` してはいけません。** リソースは既に存在するので、重複作成で失敗します。先に import して state を実体に合わせます。

今回取り込んだのは 6 つです。

```sh
terraform import google_project_service.run \
  katatsumuri-work/run.googleapis.com
terraform import google_project_service.artifactregistry \
  katatsumuri-work/artifactregistry.googleapis.com
terraform import google_artifact_registry_repository.api \
  projects/katatsumuri-work/locations/asia-northeast1/repositories/api
terraform import google_cloud_run_v2_service.api \
  projects/katatsumuri-work/locations/asia-northeast1/services/api
terraform import google_cloud_run_v2_service_iam_member.public \
  "projects/katatsumuri-work/locations/asia-northeast1/services/api roles/run.invoker allUsers"
terraform import google_cloud_run_domain_mapping.api \
  locations/asia-northeast1/namespaces/katatsumuri-work/domainmappings/api.katatsumuri.work
```

ID の書式がリソースごとにバラバラなのが地味に厄介です。IAM だけスペース区切りの 3 要素だったりします。ここは覚えるものではないので、各リソースのドキュメントの「Import」節を都度見るのが早いです。

参考: [Terraform - Import](https://developer.hashicorp.com/terraform/cli/import)

import 自体は state に取り込むだけで、**コードは書いてくれません**（`terraform plan -generate-config-out` である程度は出せますが、今回は手で書きました）。なので import 後の `plan` は、たいてい大量の差分が出ます。そこからが本番です。

## ドリフトを潰す

`plan` の差分を見て、コード側を実体に合わせていきます。差分が出たら、原則として**実体が正しい**と考えて、コードを寄せます。ここで実体のほうを変えると、動いているものを壊しかねません。

ほとんどは「書いていない属性のデフォルト値が実体と違う」というだけなので、素直に埋めれば消えていきます。

## 人柱: ドメインマッピングだけ No changes にならない

1 つだけ、埋めても消えない差分がありました。**Cloud Run のドメインマッピング**です。

しかも症状が悪く、差分が「更新」ではなく **`# forces replacement`（再作成）** として出ます。マッピングを作り直すということは、**動いている `api.katatsumuri.work` が一度落ちる**うえ、Google マネージド証明書も発行し直しになります。これは踏みたくない。

原因は、ドメインマッピングが今も v1 API で、**`certificate_mode` と `force_override` を import 時に返さない**ことでした。state に値が入らない一方、コード側で未指定だと provider がデフォルト値を埋めるため、「実体（不明）とコード（デフォルト値）が違う」と判定されます。そしてこの 2 つは ForceNew 属性なので、再作成として出ます。

対処としては、この 2 属性だけ差分を無視するようにしました。

```hcl
resource "google_cloud_run_domain_mapping" "api" {
  location = var.region
  name     = var.domain

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.api.name
  }

  # certificate_mode / force_override は Cloud Run の v1 API が import 時に返さず、
  # 未指定だと provider がデフォルト値を入れて「再作成（ForceNew）」になってしまう。
  # 既存マッピング（Google マネージド証明書 = AUTOMATIC）を壊さないよう差分を無視する。
  lifecycle {
    ignore_changes = [spec[0].certificate_mode, spec[0].force_override]
  }
}
```

`ignore_changes` は本来あまり使いたくない道具です。**「Terraform が実体を管理していない部分」を作ってしまう**ので、多用すると IaC の意味が薄れます。ただ今回は、

- 対象が 2 属性に限定されている
- 実体（マネージド証明書）を変えるつもりが今後もない
- 代わりに払う代償が「本番ドメインの再作成」

なので、割に合うと判断しました。**なぜ無視するのかをコメントで残す**ことは自分に課しています。半年後の自分が「なんで無視してるんだ」と消してしまわないように。

参考: [Terraform - The `lifecycle` Meta-Argument](https://developer.hashicorp.com/terraform/language/meta-arguments/lifecycle)

## No changes になってから

ここまで来ると `terraform plan` が「No changes」と言います。地味ですが、**実体とコードが一致したことの証明**なので気持ちのいい瞬間です。

以降の運用はシンプルで、新しいイメージをビルド・push して、タグを変えて `apply` するだけです。

```sh
terraform plan
terraform apply
terraform output          # service_uri / domain_dns_records など
```

DNS レコードの登録だけは Terraform の管理外に残しています（ムームードメインに Terraform プロバイダが無いため手動）。ただ「何を登録すればいいか」は `output` で分かるようにしてあるので、手作業が宙に浮かないようにはしています。

## まとめ

- 構成が固まる前は手で作り、**固まってから Terraform に import** する進め方は現実的でした
- import は state を埋めるだけで**コードは書いてくれません**。No changes まで詰めるのが本番です
- 差分が出たら**実体が正しい**と考えてコードを寄せます。実体を変えると動いているものを壊します
- Cloud Run のドメインマッピングは v1 API の都合で **`certificate_mode` / `force_override` が再作成差分として出る**ので、`ignore_changes` で抑えます
- `ignore_changes` を使うときは**理由をコメントに残す**。後から消せなくなります

「手で作ってしまったから IaC 化は無理」ということはありません。import してしまえば、そこからは普通の Terraform です。

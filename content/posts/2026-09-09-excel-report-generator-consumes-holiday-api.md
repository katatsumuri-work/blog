---
title: '祝日 API を"消費"して稼働報告書を自動生成する ― Excel の数式を殺さずに祝日対応を差し込む'
slug: 'excel-report-generator-consumes-holiday-api'
date: 2026-09-09T09:00:00+09:00
categories: ['tech']
tags: ['python', 'openpyxl', 'excel', 'api']
draft: false
---

前回、「消費者が LLM や表計算である前提で祝日 API を設計する」という producer 側の話を書きました。今回はその**対になる consumer 側**、実際にその API を業務ツールから叩く実装記録です。

題材は、月次の稼働時間報告書（Excel）をクライアントごとに一括生成する社内ツールです。ここに前回作った `/calendar` を消費する処理を足して、**土日だけでなく祝日も除いた稼働日数**を出せるようにしました。ポイントは「**既存の Excel テンプレートの数式を殺さずに、外部データを差し込む**」ところです。

## きっかけ：予定稼働日数が祝日を数えていた

このツール、従来は「予定稼働日数」をテンプレートの数式で出していました。中身はこんな `COUNTIFS` です。

```
=COUNTIFS(C8:C38,"<>土",C8:C38,"<>日")
```

C 列に入っている曜日から**土日だけを除外**して数える、というものです。素朴で分かりやすいのですが、これだと**祝日が稼働日にカウントされてしまう**。月に祝日が 2 日あれば、予定稼働日数が実態より 2 日多く出てしまいます。

ここに祝日対応を入れたいわけですが、稼働日の判定ロジックはもう前回の API 側（`isBusinessDay`）に持っています。なので、このツールは「**API を叩いて、返ってきた稼働日フラグを Excel に流し込むだけ**」の薄い消費者に徹します。

## 従来構造の把握：ロジックは Python になかった

面白かったのは、着手する前に構造を確認したら、**稼働日判定のロジックが Python 側に一切なかった**ことです。土日除外は上の `COUNTIFS`、つまりテンプレートの数式に埋まっていて、Python は「テンプレをコピーして企業名や対象月を書くだけ」でした。

ということは、Python 側に祝日判定を書いて固定値で埋めるのは筋が悪い。集計ロジックが「Python の中」と「Excel の数式」に二重に散ってしまいます。**集計は Excel ネイティブの数式のまま**にしておきたい ── これが差し込み設計の出発点でした。

## 差し込み設計：非表示の作業列 + `SUM`

そこで、こういう形にしました。

1. `/calendar/:month` を叩いて、月の全日を `isBusinessDay` 付きで取得する
2. 非表示の作業列 **K 列**に、稼働日フラグ（土日祝を除く平日 = 1、それ以外 = 0）を書く
3. 予定稼働日数のセル `G40` を `=SUM(K8:K38)` に置き換える

稼働日数を Python で計算して**固定値で埋める"のではなく"**、フラグだけ書いて集計は Excel の `SUM` に任せる、というのが肝です。こうすると、ファイルを開いた人が `G40` をクリックすれば「K 列の合計なんだな」と中身を追えるし、あとから手で修正することもできます。**Python は判定結果を置くだけ、集計は Excel ネイティブのまま**です。

```python
def write_calendar(ws, calendar_days):
    ws["K7"] = "稼働日"
    ws.column_dimensions["K"].hidden = True  # 集計用の作業列なので隠す

    by_day = {d.day: d for d in calendar_days}
    for day in range(1, 32):
        row = 8 + day - 1  # 8行目 = 1日
        info = by_day.get(day)
        if info is None:
            # 月末を超える行（30日月の31日など）はクリア
            ws[f"B{row}"] = None
            ws[f"C{row}"] = None
            ws[f"I{row}"] = None
            ws[f"K{row}"] = None
        else:
            ws[f"B{row}"] = info.day
            ws[f"C{row}"] = info.weekday
            ws[f"I{row}"] = info.name if info.is_holiday else None  # 祝日名をメモ欄に
            ws[f"K{row}"] = 1 if info.is_business_day else 0

    ws["G40"] = "=SUM(K8:K38)"
```

祝日名は I 列（メモ欄）に出しているので、報告書を見た人が「あ、この日は海の日か」と分かるようにもなっています。

## 罠1：`Python-urllib/*` の User-Agent が 403 で弾かれる

ここで人柱ポイントです。ローカルで `curl` すると普通に返ってくる API が、**Python から叩くと 403 になる**という現象にハマりました。

原因は User-Agent でした。Python の `urllib` は既定で `Python-urllib/3.x` という UA を送るのですが、これが弾かれていました。カスタム UA を明示して解決です。

```python
req = urllib.request.Request(
    url,
    headers={
        "Accept": "application/json",
        "User-Agent": "working-uptime-generator/0.1",  # 既定 UA だと 403
    },
)
```

「ローカルの `curl` では動くのに、スクリプトからだと落ちる」系の地味な罠でした。同じところで詰まる人がいそうなので残しておきます。

参考: [MDN - User-Agent](https://developer.mozilla.org/ja/docs/Web/HTTP/Headers/User-Agent)

## 罠2：取得に失敗したら"黙って進めない"

もう一つ意識したのは、**API 取得に失敗したときにフォールバックで適当な稼働日数を作らない**ことです。稼働報告書は請求にも関わる書類なので、「祝日 API が落ちてたので土日だけ除いた数字で作りました」と黙って進むのがいちばん怖い。なので取得失敗時は、フォールバックせずに**明示的にエラー終了**させています。

```python
except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
    sys.stderr.write(
        f"Error: Failed to fetch holiday calendar from '{url}': {e}\n"
        "Check network connectivity or HOLIDAY_API_BASE in config.yml.\n"
    )
    sys.exit(1)
```

「誤った稼働日数の報告書を作る」より「作れませんでしたと止まる」ほうがずっと安全、という判断です。

## ついでの一元化：作業者名を config へ

作業のついでに、**作業者名の二重管理**も解消しました。もともと作業者名は「生成するファイル名」と「テンプレートの氏名セル」の両方に別々に埋まっていて、変えるときに直し忘れそうな状態でした。これを `config.yml` に `WORKER_NAME` として一元化し、起動時にセルもファイル名もそこから埋めるようにしています。

これは前回の「API をデータの単一情報源にする」話の、ごく小さな Excel 版とも言えます。値の出どころを 1 か所に決めておくと、テンプレ直書きに勝てます。

## まとめ

既存の Excel 資産（数式・書式）を活かしたまま、外部データ（祝日 API）を差し込むときの勘どころは、こんな感じでした。

- **集計は数式のまま**にして、Python は判定結果（フラグ）を置くだけにする
- **非表示の作業列 + `SUM`** で、開いた人が中身を追える形を保つ
- **UA を明示**して 403 を避ける
- **失敗時はフォールバックせず止める**（誤った数字を作らない）
- テンプレ本体は触らず、コピー後の各ファイルにだけ書く

前回の producer 記事で「`isBusinessDay` を供給側で確定させた」おかげで、消費側のこのツールは本当に「叩いて詰めるだけ」で済みました。次回は、同じ API を今度は**手元用の薄い Rust CLI** から消費する話を書きます。

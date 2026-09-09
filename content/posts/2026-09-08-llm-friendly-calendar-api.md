---
title: '消費者が LLM な API を設計する ― 稼働表のための /calendar と isBusinessDay'
slug: 'llm-friendly-calendar-api'
date: 2026-09-08T09:00:00+09:00
categories: ['tech']
tags: ['api', 'llm', 'cloudflare-workers', 'hono']
draft: false
---

業務委託の**稼働表**を Excel やスプレッドシートで作るとき、地味に面倒なのが「今月は何日が祝日か」を毎回調べることです。さらに最近は、**その稼働表を LLM に作らせたい**とも思うようになりました。となると、人が眺めるための祝日一覧ではなく、**叩いてそのまま渡せる API** が欲しくなります。

そこで、以前から動かしている祝日 API（Cloudflare Workers + Hono）に `GET /calendar` を足しました。この記事は「**消費者が LLM や表計算である前提**で API を設計すると、何がどう変わるか」という設計の話です。実装は 3 部作の 1 本目（producer 側）で、続きで実際にこの API を Excel ツールと CLI から消費していきます。

## 祝日"だけ"の一覧では稼働表は組めない

もともとこの API には「祝日の一覧を返す」エンドポイントがありました。ですが、稼働表を作るには**それだけだと足りない**のです。

稼働表に必要なのは「その月の**全部の日**が、それぞれ平日なのか・土日なのか・祝日なのか・**結局その日は稼働日なのか**」という情報です。祝日一覧はあくまで「祝日の集合」なので、消費する側が「月の全日を生成して、土日を判定して、祝日一覧と突き合わせて……」という**判定ロジックを自前で書く**必要が出てきます。

この「消費側にロジックを書かせる」構造が、消費者が LLM や表計算だと途端に事故のもとになります。人間なら「まあ土日は除くよね」で通じますが、LLM に丸投げすると振替休日を数え忘れたり、表計算の `COUNTIFS` に祝日条件を足し忘れたりします。

## /calendar：月の全日をフラグ付きで返す

なので、**月（または期間）の全日を 1 日ずつ列挙し、各日に判定フラグを付けて返す**エンドポイントにしました。

- `GET /calendar/:month` … `YYYY-MM` で月初〜月末
- `GET /calendar?from=&to=` … 期間指定（両端含む）

各日はこういう形です。

```json
{
  "date": "2026-07-06",
  "weekday": "月",
  "isHoliday": false,
  "isWeekend": false,
  "isBusinessDay": true,
  "name": null
}
```

生成ロジック自体はごく素直で、`from` から `to` まで 1 日ずつ進めながらフラグを詰めるだけです。

```ts
export interface CalendarDay {
  date: string;          // ISO 8601 (YYYY-MM-DD)
  weekday: string;       // 曜日（日本語1文字）
  isHoliday: boolean;    // 内閣府データ上の祝日（振替休日・国民の休日を含む）
  isWeekend: boolean;    // 土日か
  isBusinessDay: boolean; // 稼働日か（土日でも祝日でもない日）
  name: string | null;   // 祝日名。祝日でなければ null
}

export function buildCalendar(from: string, to: string): CalendarDay[] {
  const days: CalendarDay[] = [];
  for (let d = from; d <= to; d = addDays(d, 1)) {
    const holiday = isHoliday(d);
    const weekend = isWeekend(d);
    days.push({
      date: d,
      weekday: weekdayJa(d),
      isHoliday: holiday,
      isWeekend: weekend,
      isBusinessDay: !holiday && !weekend,
      name: holidayName(d) ?? null,
    });
  }
  return days;
}
```

## 肝：`isBusinessDay` を供給側で確定させる

このエンドポイントでいちばん言いたいのはここです。**「その日が稼働日か」の判定（`isBusinessDay`）を、消費側ではなく API 側で確定させている**点です。

`isBusinessDay: !holiday && !weekend` という一行は、消費側でも書けます。書けるのですが、**書けてしまうからこそ、消費者ごとにバラバラに実装されて事故る**のだと思います。土日判定、祝日判定、振替休日の扱い ── この境界を全部 API 側に閉じ込めて、消費者には「稼働日は `true`/`false` のどっちか」という**答えだけを渡す**。すると、人・表計算・LLM のどれが消費しても同じ答えになります。

「ロジックは供給側に寄せ、消費側には判定済みの結果を渡す」というのは、消費者が LLM のときに特に効きます。LLM は言われたことは器用にやりますが、**言われていない前提（振替休日とか）を勝手に補完してくれるとは限らない**ので、曖昧さを残さないほど安全です。

## 表計算・LLM に効く CSV 出力

もう一つ、`?format=csv` で CSV を返せるようにしました。

```csv
date,weekday,isHoliday,isWeekend,isBusinessDay,name
2026-07-06,月,false,false,true,
2026-07-07,火,false,false,true,
...
```

これが地味に強くて、

- **表計算**：セルにそのまま貼れる
- **LLM**：プロンプトにそのまま貼って「この CSV から稼働表を作って」と渡せる

JSON より CSV のほうが、表計算にも LLM にも"そのまま食わせられる"んですよね。用途を稼働表に絞ったので、対応フォーマットも `json` と `csv` の 2 つだけに割り切っています。

なお、期間指定 `from..to` には上限（約 5 年 = 1830 日）を設けています。うっかり広い範囲を投げてワーカーが無駄に回らないようにするガードです。

参考: [Cloudflare Workers - Limits](https://developers.cloudflare.com/workers/platform/limits/)

## 3 種類の消費者で検証する

実際に、この `/calendar` を 3 種類の消費者から叩いて確かめています。

1. **人**：Rust 製の CLI で月テーブルとして表示（3 本目で書きます）
2. **表計算**：CSV を稼働報告書の Excel に差し込む（2 本目で書きます）
3. **LLM**：CSV ごと渡して「稼働表作って」と頼む

同じ API を 3 つのフロントで共有できて、しかもどれも「稼働日はどれか」を自分で計算しなくていい ── この気持ちよさが、`isBusinessDay` を供給側に置いた狙いそのものです。

## まとめ：API を「人の画面」ではなく「LLM の入力」として設計する

祝日データを扱う API 自体は珍しくないですが、`/calendar` を足すときに意識したのは次の 3 点でした。

- **機械可読**：全日を 1 日ずつ、フラグ付きで列挙する（一覧の集合ではなく）
- **境界を明示する**：土日・祝日・稼働日の判定を曖昧にせず、`true`/`false` で返す
- **フラグは供給側で確定する**：消費側に判定ロジックを持たせない

「この API は誰が消費するのか？」を人間ではなく **LLM や表計算**に置き換えて考えると、要件がけっこう変わるなと感じました。次回は、この API を実際に業務ツール（Excel の稼働報告書ジェネレータ）から消費する側の話を書きます。

参考:
- [Hono 公式ドキュメント](https://hono.dev/)
- [内閣府「国民の祝日」について](https://www8.cao.go.jp/chosei/shukujitsu/gaiyou.html)（祝日データの一次情報）

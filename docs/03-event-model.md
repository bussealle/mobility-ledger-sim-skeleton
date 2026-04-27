# 03. イベントモデル

## イベント=制約付き状態遷移関数

イベントは「いつ・誰によって・どんな前提下で発火し・何を変えるか」を定義する。シートの128イベントが基本セット(`data/events.json`)。

## イベントの構造

各イベントは以下のスキーマを持つ(`data/events.json` 参照):

```typescript
interface EventDef {
  id: string;                          // 'EV001' など
  name: string;                        // '完成車製造' など
  phase_label: string;                 // '0〜0.5年' などの時間表現
  category: string;                    // '製造', '金融', '事故・違反' 等
  description: string;
  timing_hint: string;                 // 自然言語のタイミング示唆
  state_changes: {                     // 状態変化フラグ(7+1)
    所有: boolean;
    占有: boolean;
    状態: boolean;
    価値: boolean;
    規制: boolean;
    債務: boolean;
    データ: boolean;
    不可逆: boolean;
  };
  trigger_type: 'choice' | 'probabilistic' | 'time' | 'cascade';
  actionable: boolean;                 // プレイヤー選択肢として表示するか
  preconditions: {
    phase_in: PhaseId[];               // この相にいるときのみ発火可能
    min_age_days: number;              // 最低経過日数
    requires_state: Record<string, unknown>;  // 詳細条件
  };
  postconditions: {
    ownership_change?: boolean;
    possession_change?: boolean;
    condition_change?: boolean;
    value_revaluation?: boolean;
    regulatory_change?: boolean;
    financial_change?: boolean;
    data_emit?: boolean;
    irreversible?: boolean;
  };
  stakeholders: Array<{
    stakeholder_id: string;
    role: '起点' | '対象' | '実行' | '確認' | '受益' | '責任';
    layer: string;                     // L1〜L6
  }>;
  probability_per_year?: number;       // trigger_type='probabilistic' のとき
  period_days?: number;                // trigger_type='time' のとき
}
```

## トリガー型(trigger_type)の4分類

### choice(選択イベント)

プレイヤーが能動的に選んで発火させるイベント。事前条件を満たすイベントを選択肢リストに表示する。

例: EV007 ファイナンス申込, EV040 早期買換え, EV065 輸出業者買取

**Phase 2では `actionable: true` のイベント中、事前条件を満たすものだけを選択肢に出す**。

### probabilistic(確率発火イベント)

時間経過に従って確率的に発火する。年率(`probability_per_year`)を時間経過(days経過)に変換して判定。

例: EV025 軽微事故(年8%), EV026 重大事故(年1.5%), EV032 支払遅延(年4%)

**判定方法**: 経過日数 d に対し、当該期間中の発火確率 = 1 - (1 - p_year)^(d/365)。プレイヤーには「この期間に何が起きたか」として事後通知する。

### time(周期発火イベント)

一定の周期で必ず発火する強制イベント。

例: EV031 月次払い(30日周期), EV030 車検(730日周期), EV114 自動車税(365日周期)

**判定方法**: 前回発火時刻 + period_days ≤ 現在時刻のとき発火。プレイヤーは介入できない(タイマー型)。

### cascade(連鎖イベント)

他のイベントの postcondition から自動発火するイベント。

例:
- EV010 契約締結 → EV011 頭金決済 を自動誘発
- EV012 新規登録 → EV013 車両引渡し を自動誘発
- EV108 早期完済 → EV094 抵当権抹消 を自動誘発

**判定方法**: 親イベントの postcondition チェーンに従って即座に発火する。プレイヤー選択を経ない。

## 事前条件評価ロジック

イベント `e` が現在の状態 `s` で発火可能かは:

```typescript
function isApplicable(e: EventDef, s: VehicleState): boolean {
  // (1) 相のチェック
  if (!e.preconditions.phase_in.includes(s.phase)) return false;

  // (2) 経過日数チェック
  if (s.simulation_time < e.preconditions.min_age_days) return false;

  // (3) 詳細条件チェック (事前条件の追加要件)
  if (!checkRequiresState(e.preconditions.requires_state, s)) return false;

  // (4) 不可逆性チェック (EOLからは何も発火しない)
  if (s.phase === 'EOL') return false;

  return true;
}
```

`requires_state` の詳細条件は Phase 2 では基本パターン(契約有/無, 残債>0, 登録有効, 等)のみ実装する。複雑な条件は Phase 3 以降で追加する。

## 事後効果の適用

イベント発火時の状態更新は `postconditions` のフラグから具体的な変更を生成する。

```typescript
function applyEvent(e: EventDef, s: VehicleState, ctx: EventContext): VehicleState {
  let next = structuredClone(s);

  // 各 postcondition フラグを具体的な状態変更に展開
  if (e.postconditions.ownership_change) {
    next.ownership = applyOwnershipChange(s.ownership, e, ctx);
  }
  if (e.postconditions.financial_change) {
    next.financial = applyFinancialChange(s.financial, e, ctx);
  }
  // ...

  // 共通: イベントログを追記
  next.data.total_events_logged += 1;
  next.data.history_score = recomputeHistoryScore(next);

  return next;
}
```

ハンドラ関数(`applyOwnershipChange` 等)は `core/handlers/` 以下にイベントID別または状態属性別に分けて実装する。Phase 2では**イベントIDごとに専用ハンドラを書かず、属性別の汎用ハンドラ + イベントメタデータの組み合わせで処理する**。

## イベント発火の優先順位

複数のイベントが同時に発火可能な場合の順序:

1. cascade(連鎖)が最優先 — 他イベントの結果として即座に発火
2. probabilistic(確率) — その期間内に発火と判定されたもの
3. time(周期) — 期限到来したもの
4. choice(選択) — プレイヤーが選んだもの

cascade > probabilistic > time > choice の順で評価し、状態を順次更新する。

## イベント候補の提示

UIに提示する選択肢リストは以下の手順で生成する:

```typescript
function getActionableChoices(state: VehicleState, allEvents: EventDef[]): EventDef[] {
  return allEvents
    .filter(e => e.trigger_type === 'choice')
    .filter(e => e.actionable)
    .filter(e => isApplicable(e, state))
    .sort(byCategory_then_byId);
}
```

数が多すぎる場合(20件超)は、カテゴリ別にグルーピングするか、関連度の高いものを上位に出すなどの工夫が必要。Phase 2では単純にカテゴリ別にグルーピングするだけで良い。

## 行き止まり対策

何も発火可能なイベントがない状態(行き止まり)になった場合:

1. **時間進行の選択肢を出す**: 「3ヶ月待つ」「1年待つ」など
2. **強制終了オプション**: 「廃車にする(EV085 強制廃車・抹消登録)」を最後の手段として常時提示

行き止まりは設計バグの可能性もあるので、ログに warning として記録する。

## イベント間の依存関係(参考)

データには明示されていないが、設計上想定される連鎖の例:

| 親イベント | 自動発火する子イベント |
|-----------|-----------------------|
| EV007 ファイナンス申込 | EV008 与信審査 |
| EV010 契約締結 | EV011 頭金決済, EV094 抵当権設定 |
| EV012 新規登録 | EV013 車両引渡し |
| EV052 所有権移転登録 | EV094 抵当権抹消(該当する場合) |
| EV108 早期完済 | EV094 抵当権抹消 |
| EV062 全損宣言 | EV038 保険金支払, EV063 廃車オークション売却 |

これらはPhase 2では明示的に `cascade` ハンドラで実装する。完全な依存マップは `data/cascade_chains.json`(Phase 3 で追加)で外部化する。

## イベントの確率パラメータ調整

シナリオごとに確率倍率を `scenarios.json` の `probability_modifiers` で指定する。例えば:

```json
"probability_modifiers": {
  "EV025_minor_accident": 1.5,
  "EV065_export_buyer": 0.4
}
```

これは「軽微事故が標準より1.5倍起きやすく、輸出業者買取の確率が標準の0.4倍」を意味する。実効確率 = 基本確率 × 倍率。

## 実装上の注意

- **128イベント全てを Phase 2 で完璧に動かす必要はない**: コアの 50〜60 イベントが正しく動けば良い。残りは postcondition がフラグ的にしか反映されなくても許容
- **事前条件の組み合わせ爆発を避ける**: requires_state は10個程度の基本パターンに限定する。それ以上は Phase 3 以降の課題
- **decisionは記録する**: プレイヤーの選択は後で振り返れるように `Ledger` に記録する(05-architecture.md 参照)

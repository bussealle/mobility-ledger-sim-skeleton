# Phase 2: コアエンジン + 最小UI

## 目的

「プレイヤーが選択を進めて廃車まで到達でき、イベントログが残る」状態を作る。Phase 3 以降の体験設計の土台となる、**動くMVP**を完成させる。

## このPhaseに着手する前に必読

1. `README.md`
2. `docs/01-design-principles.md` ← 何を成功とするか
3. `docs/02-state-model.md` ← 状態の構造
4. `docs/03-event-model.md` ← イベントの構造と挙動
5. `docs/04-stakeholder-model.md` ← 6レイヤ・6役割
6. `docs/05-architecture.md` ← ロジック/UI分離(必須)
7. `docs/06-glossary.md` ← 用語

`data/*.json` も少なくとも一度は目を通すこと。

## スコープ

### コアエンジン(Phase 1相当を含む)

- TypeScript + Node実行可能な純粋関数群
- `data/events.json`(128件), `stakeholders.json`(50件), `phases.json`, `scenarios.json` の読み込み
- 状態モデル(VehicleState 7属性ベクトル+相)の実装
- 事前条件評価
- 事後効果適用
- イベント発火(choice / probabilistic / time / cascade)
- 時間進行(advanceTime)
- Ledger(ログ累積)
- シード可能な乱数源
- CLIテストハーネス(ランダムプレイで EOL まで走らせる)

### 最小UI

- React + Vite で起動できる
- 3ペイン構成:
  - 左: VehiclePanel(現在の車両状態 7属性ベクトル全表示)
  - 中: EventPicker(発火可能イベント選択肢、カテゴリ別グループ表示)
  - 右: Timeline(過去のイベントログ時系列)
- 下部: TransactionPanel(直近発火イベントの詳細 — 状態変化と関与ステークホルダ)
- 「N日進める」ボタンで時間を進めると確率/周期イベントが発火する
- 廃車(EOL相)に到達したら結果画面を出す

### 非ゴール(Phase 2では実装しない)

- ステークホルダ星座ビュー → Phase 3
- 車両オーラ・属性アニメーション → Phase 3
- トランザクション展開アニメーション → Phase 3
- シナリオ選択UI → Phase 4(Phase 2 では `default-japan-2026` 固定で良い)
- 複数台同時シミュレーション → Phase 4
- 統計出力ビュー → Phase 4
- 共有可能URL → Phase 4
- 美術的なグラフィック・凝ったCSS → 不要。素朴で良い

## 受入基準

以下を全て満たすこと:

### コアエンジン

1. `npm run typecheck` がエラーゼロで完走する(strict有効)
2. `npm test` で `core/` 配下のユニットテストが全て通る
3. 以下のテストケースが通る:
   - 「同じシードで同じ操作を行うと同じ結果になる」(決定性)
   - 「Production 相から Distribution → Inventory → Origination → In_Use → ... → EOL までランダム選択で到達できる」
   - 「不可逆イベント発火後は元の相に戻らない」
   - 「事前条件を満たさないイベントは applyEvent で例外を投げる」
4. `npm run sim:replay -- --seed=42 --scenario=default-japan-2026` がエラーなく EOL まで走り、JSON ログを stdout に出す

### 最小UI

5. `npm run dev` で起動し、ブラウザで開ける
6. 起動直後に Production 相からスタートできる
7. 各イベント発火時に、4つのペイン全てが正しく更新される
8. 「N日進める」ボタンで時間が進み、確率/周期イベントが裏で発火してログに残る
9. 廃車に到達すると結果画面が出る(プレイ統計: 総イベント数、関与STK数、所要日数 程度で良い)
10. 1セッションを最初から最後まで操作してもクラッシュしない

## 推奨実装順序

### Step 1: プロジェクトセットアップ

```bash
npm create vite@latest mobility-ledger-sim -- --template react-ts
cd mobility-ledger-sim
npm install
npm install -D vitest @vitest/ui
```

`tsconfig.json` で `strict: true`, `noUncheckedIndexedAccess: true`, `exactOptionalPropertyTypes: true` を有効化。

### Step 2: データのインポート

`data/*.json` を `src/data/` 配下に置き、`*.ts` ファイルで `import data from './events.json' with { type: 'json' }` 形式で型付きインポートする。型定義は `core/types.ts` に集約。

### Step 3: 型定義(core/types.ts)

`docs/02-state-model.md` の TypeScript 定義を全てここに書き写す。これが他全ファイルの基盤になる。

### Step 4: 乱数源(core/rng.ts)

mulberry32 など軽量な PRNG を実装。インターフェースは `docs/05-architecture.md` 参照。

### Step 5: 初期状態の構築(core/seed.ts)

シナリオIDとシードを受け取り、初期 VehicleState を返す純粋関数。

### Step 6: ハンドラ群(core/handlers/*.ts)

`ownership.ts`, `financial.ts` など属性別に。各ハンドラは `(state, event, context) → newPartialState` のシグネチャ。

最初は空っぽに近い実装で良い。例えば `ownership.ts`:

```typescript
export function applyOwnershipChange(
  current: OwnershipState,
  event: EventDef,
  ctx: EventContext,
): OwnershipState {
  // Phase 2では: 関与STKのうち主要役割「対象」のSTKを次の所有者として記録
  // (もっと精緻なロジックは Phase 3 以降で)
  const subject = event.stakeholders.find(s => s.role === '対象');
  if (!subject) return current;
  return {
    ...current,
    legal_owner_id: subject.stakeholder_id,
    prior_owners: [...current.prior_owners, current.legal_owner_id],
    acquired_at: ctx.simulation_time,
  };
}
```

### Step 7: ルール評価(core/rules.ts)

`isApplicable`, `computeProbabilisticFirings`, `computeTimeFirings` を実装。

### Step 8: エンジン本体(core/engine.ts)

`applyEvent`, `getActionableEvents`, `advanceTime`, `isTerminal` を実装。

### Step 9: Ledger(core/ledger.ts)

ログの追記と JSON 入出力。

### Step 10: CLI ハーネス(src/cli/replay.ts)

```typescript
// ランダム選択でEOLまで走らせる
const state = seed(scenarioId, seedNumber);
let current = state;
const ledger = new Ledger();
while (!isTerminal(current)) {
  const choices = getActionableEvents(current, allEvents);
  if (choices.length === 0) {
    // 時間を進める
    const result = advanceTime(current, 30, rng);
    current = result.newState;
    result.firedEvents.forEach(e => ledger.append(e));
    continue;
  }
  const chosen = rng.pick(choices);
  const result = applyEvent(current, chosen, buildContext(current, ledger));
  current = result.newState;
  ledger.append(result.logEntry);
}
console.log(JSON.stringify(ledger.toJSON(), null, 2));
```

### Step 11: ユニットテスト

`tests/core/` に。Step 4-9 をカバーする最小限のテスト。

### Step 12: UI: useSimulationフック

`src/ui/hooks/useSimulation.ts` を実装。core を呼ぶだけで、ロジックを書かない。

### Step 13: UI: 各 Component

VehiclePanel → EventPicker → Timeline → TransactionPanel の順で実装。レイアウトは flexbox か grid で素朴に。

### Step 14: 結合テストと修正

実際に最初から最後までプレイしてみて、行き止まり・矛盾・例外を潰す。

## 設計上の注意

### 「actionable=true」だけ選択肢に出す

128件のうち `actionable: true` は103件。Phase 2 ではこれを正で扱う。表示しすぎるなら、相に応じてさらに絞り込む(現在の相で発火可能な choice イベントだけ)。

### 事前条件は最小限から

`requires_state` は最初は空でも構わない(実装が間に合うまで)。すべてのイベントは「相だけチェック」で発火可能とする。整合性は段階的に上げる。**動くことを優先**。

### postcondition の手抜き許容

ハンドラは「state_changes フラグから機械的に生成された差分」程度で良い。例えば:

- ownership_change=true → STK の '対象' 役を新所有者にする
- financial_change=true → 適当な額の active_contract を作る/更新する
- value_revaluation=true → value_curve に基づいて current_market_value を再計算する

精緻なロジックは Phase 3 以降。Phase 2 では「フラグが Y なら何かしら更新が起きる」が見えれば良い。

### cascade の最小実装

主要な cascade だけ手で書く(`docs/03-event-model.md` の表を参照):

- EV010 → EV011 (頭金決済), EV094(抵当権設定)
- EV012 → EV013(車両引渡し)
- EV108 → EV094(抵当権抹消)
- EV062 → EV038, EV063

その他は cascade として宣言だけして実装はスキップしても良い。Phase 3 で `data/cascade_chains.json` として外部化する。

### UI は素朴で良い

色付け・配置は最低限で良い。Phase 3 で見栄えを上げる。Phase 2 では「機能が動く」ことが目的。

## 成果物

- 動く `mobility-ledger-sim/` ディレクトリ一式
- README.md(起動方法・テスト方法を記載)
- 全テストが通る状態
- `npm run sim:replay` が成功する状態

## 完了報告フォーマット

Phase 2 完了時は以下の項目で報告すること:

1. 受入基準10項目それぞれの達成状況
2. 実装した core/ ファイル一覧
3. 実装した ui/ コンポーネント一覧
4. テストカバレッジ概算
5. 既知の制約・未実装機能のリスト(Phase 3 への申し送り)
6. プレイ動画(または起動して操作した時のスクリーンショット数枚)

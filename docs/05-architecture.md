# 05. アーキテクチャ

## 設計の根幹: ロジックとUIの厳格な分離

本プロジェクトの最重要原則は **ロジック層とUI層の厳格な分離** である。これを守ることで以下が可能になる:

- ロジックを純粋関数で書けるためテスタブル
- UIを差し替え可能(React → 別フレームワーク or CLI)
- ワークショップ運用時に複数台同時シミュレーションを CLI バッチで走らせ、結果だけUIで表示する運用が可能
- AIによるリプレイ生成・統計分析で同じロジックを再利用できる

**逆にこの分離を破ると、後段Phaseで必ず詰む**。React Hooks の中に状態遷移ロジックを書くな。Componentの中に確率判定を書くな。

## ディレクトリ構造(目標形)

```
mobility-ledger-sim/
├── public/
├── src/
│   ├── core/                      ← ロジック層(React非依存)
│   │   ├── types.ts               ← 全ての型定義
│   │   ├── state.ts               ← VehicleState の構築・更新
│   │   ├── rules.ts               ← 制約評価エンジン
│   │   ├── scheduler.ts           ← 時間進行とイベントキュー
│   │   ├── ledger.ts              ← トランザクションログ
│   │   ├── handlers/              ← 状態属性別のハンドラ
│   │   │   ├── ownership.ts
│   │   │   ├── financial.ts
│   │   │   ├── condition.ts
│   │   │   ├── value.ts
│   │   │   ├── regulatory.ts
│   │   │   ├── possession.ts
│   │   │   └── data.ts
│   │   ├── engine.ts              ← 統合エンジン: applyEvent等の主要API
│   │   ├── seed.ts                ← 初期状態構築(scenario→state)
│   │   └── selectors.ts           ← 派生情報の計算(残債、年齢、稼働率等)
│   ├── data/                      ← データファイルのインポート(typed)
│   │   ├── events.ts              ← events.json の typed import
│   │   ├── stakeholders.ts
│   │   ├── phases.ts
│   │   └── scenarios.ts
│   ├── ui/                        ← UI層(Reactのみがここに居る)
│   │   ├── App.tsx
│   │   ├── hooks/
│   │   │   └── useSimulation.ts   ← coreエンジンを呼ぶカスタムフック
│   │   ├── components/
│   │   │   ├── VehiclePanel.tsx
│   │   │   ├── EventPicker.tsx
│   │   │   ├── TransactionPanel.tsx
│   │   │   ├── Timeline.tsx
│   │   │   ├── StakeholderConstellation.tsx  (Phase 3)
│   │   │   ├── VehicleAura.tsx               (Phase 3)
│   │   │   ├── ScenarioSelector.tsx          (Phase 4)
│   │   │   └── StatsView.tsx                 (Phase 4)
│   │   └── styles/
│   ├── cli/                       ← CLIテストハーネス
│   │   ├── replay.ts              ← 既存ログのリプレイ
│   │   └── batch.ts               ← 複数台ランダムプレイ
│   └── main.tsx                   ← エントリポイント
├── data/                          ← 生のJSONデータ(srcの外。ビルド時にコピー)
│   ├── events.json
│   ├── stakeholders.json
│   ├── phases.json
│   └── scenarios.json
├── tests/
│   ├── core/
│   │   ├── state.test.ts
│   │   ├── rules.test.ts
│   │   └── engine.test.ts
│   └── fixtures/
├── docs/
├── instructions/
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## レイヤ間の依存関係

```
ui/* ────┐
         ├──→ core/* ──→ data/*
cli/* ───┘
```

- `ui/*` は `core/*` と `data/*` のみに依存
- `cli/*` も同様
- `core/*` は `data/*` のみに依存
- `core/*` は React, DOM, ブラウザAPIに**一切**依存しない

`core/` のコードは Node.js 単独で動く必要がある。これを CI で型チェック+テストする。

## core/ の主要API

### `engine.ts`

```typescript
export function applyEvent(
  state: VehicleState,
  event: EventDef,
  context: EventContext,
): { newState: VehicleState; logEntry: LogEntry };

export function getActionableEvents(
  state: VehicleState,
  allEvents: EventDef[],
): EventDef[];

export function advanceTime(
  state: VehicleState,
  days: number,
  rng: RandomSource,
): { newState: VehicleState; firedEvents: LogEntry[] };

export function isTerminal(state: VehicleState): boolean;
```

これらが UI/CLI から呼ばれる入口。

### `rules.ts`

```typescript
export function isApplicable(event: EventDef, state: VehicleState): boolean;
export function computeProbabilisticFirings(
  events: EventDef[],
  state: VehicleState,
  elapsedDays: number,
  rng: RandomSource,
  modifiers: Record<string, number>,
): EventDef[];
export function computeTimeFirings(
  events: EventDef[],
  state: VehicleState,
  ledger: Ledger,
): EventDef[];
```

### `ledger.ts`

```typescript
export interface LogEntry {
  timestamp: number;            // simulation time (days)
  event_id: string;
  event_name: string;
  trigger_type: string;
  state_changes: Partial<Record<keyof VehicleState, unknown>>;
  stakeholders_involved: Array<{
    stakeholder_id: string;
    role: string;
  }>;
  monetary_flows: Array<{
    from: string;
    to: string;
    amount: number;
    currency: string;
  }>;
  decision_metadata?: {
    chosen_by: 'player' | 'system' | 'cascade' | 'rng';
    alternatives_offered?: string[];
  };
}

export class Ledger {
  entries: LogEntry[];
  append(entry: LogEntry): void;
  filter(predicate: (e: LogEntry) => boolean): LogEntry[];
  toJSON(): string;
  static fromJSON(json: string): Ledger;
}
```

### 型定義(`types.ts`)

`docs/02-state-model.md` で定義された全構造を TypeScript の型として記述する。**型はここに集約**し、他ファイルからは import する。

## RandomSource(乱数源)

確率発火イベントのために乱数源が必要。テスト容易性のため**シード可能な乱数生成器**を独自実装する:

```typescript
export interface RandomSource {
  next(): number;              // 0..1
  uniform(min: number, max: number): number;
  bernoulli(p: number): boolean;
  pick<T>(arr: T[]): T;
}

export function createSeeded(seed: number): RandomSource;
```

`Math.random()` は使わない。テスト時に再現性が出ないため。

## UI層の規律

### useSimulation フック

UI側で状態を持つのは `useSimulation` フックただひとつ。これがcoreエンジンを呼び出してReact stateとして公開する。

```typescript
export function useSimulation(scenarioId: string) {
  const [state, setState] = useState<VehicleState>(() => seed(scenarioId));
  const [ledger, setLedger] = useState<Ledger>(() => new Ledger());

  const fireEvent = useCallback((eventId: string) => {
    const event = findEvent(eventId);
    const result = applyEvent(state, event, buildContext(state, ledger));
    setState(result.newState);
    ledger.append(result.logEntry);
    setLedger(new Ledger(/* ... */));  // immutable update
  }, [state, ledger]);

  const advance = useCallback((days: number) => {
    /* coreのadvanceTimeを呼ぶ */
  }, [state]);

  const actionableEvents = useMemo(
    () => getActionableEvents(state, allEvents),
    [state]
  );

  return { state, ledger, actionableEvents, fireEvent, advance };
}
```

### Componentの責務

各 Component は受け取った props を表示するだけ。状態遷移ロジックを持たない。Component内で `useState` を使うのは UI 状態(モーダル開閉、ホバー状態等)に限定する。

## テスト戦略

### core/ のユニットテスト(必須)

- `state.test.ts`: 状態構築・更新の純粋関数
- `rules.test.ts`: 事前条件評価
- `engine.test.ts`: applyEvent の入出力 contract
- `scheduler.test.ts`: 時間進行・周期発火・確率発火

特に「同じシードで同じ操作をすると同じ結果になる」(決定性)はテストで担保する。

### CLI 統合テスト(Phase 2 末で導入)

```bash
npm run sim:replay -- --seed=42 --scenario=default-japan-2026 --steps=random
```

ランダム選択でEOLまで走らせ、ログを JSON 出力する。これが正常終了することがPhase 2の受入基準のひとつ。

## なぜこの分離が大事か(再強調)

ワークショップ運営時、**100台分のランダムプレイを事前に走らせて統計だけUIで見せる**といった運用が必要になる(Phase 4)。このとき core/ がブラウザに依存していたら Node.js で走らない。逆に core/ が純粋関数の集合なら、CLI でも、Web Worker でも、サーバサイドでも走る。

UIは交換可能なフロントエンドの1つに過ぎない、というスタンスを貫く。

## 命名規則

- 型: `PascalCase`(VehicleState, EventDef, LogEntry)
- 関数: `camelCase`(applyEvent, isApplicable)
- 定数: `SCREAMING_SNAKE_CASE`(DEFAULT_SCENARIO_ID)
- ファイル: `kebab-case.ts`(state-model.ts は ❌、state.ts は ⭕)
- データ参照: `STK01`, `EV007`, `L1` などのIDは大文字を保ち、コード内で文字列リテラルとして直接書く(マジックナンバーではない、安定識別子)

## TypeScriptの設定

`tsconfig.json` で以下を有効にする:

- `"strict": true`
- `"noUncheckedIndexedAccess": true`
- `"exactOptionalPropertyTypes": true`

これらを入れずに書き始めると後で型エラー地獄になる。

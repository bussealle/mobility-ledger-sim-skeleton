# 02. 状態モデル

## 車両は「相 × 7属性ベクトル」のステートマシン

車両の状態を単一変数で表現することはできない。3層の構造を持つ:

```
┌─────────────────────────────────────────┐
│  Phase (ライフサイクル相, 10値)          │
│  Production / Distribution / Inventory /│
│  Origination / In_Use / Post_Contract / │
│  Used_Market / Cross_Border / Late_Life │
│  / EOL                                   │
└─────────────────────────────────────────┘
       ↓ 包含
┌─────────────────────────────────────────┐
│  7属性ベクトル                           │
│  - Ownership   (所有)                    │
│  - Possession  (占有)                    │
│  - Condition   (物理状態)                │
│  - Value       (経済価値)                │
│  - Regulatory  (規制状態)                │
│  - Financial   (金融状態)                │
│  - Data        (履歴・データ)            │
└─────────────────────────────────────────┘
       ↓ 詳細
┌─────────────────────────────────────────┐
│  各属性の構造化された値                  │
│  Ownership: {legal_owner_id, ...}       │
│  Possession: {physical_holder_id, ...}  │
│  Condition: {mileage, soh, accidents...}│
│  ...                                     │
└─────────────────────────────────────────┘
```

## 7属性の詳細仕様

### 1. Ownership(所有)

```typescript
interface OwnershipState {
  legal_owner_id: string;          // 現在の法的所有者(STK ID)
  ownership_type: 'manufacturer' | 'dealer_inventory' | 'captive' | 'spv' | 'individual' | 'corporate' | 'lease_company' | 'exporter' | 'overseas' | 'scrapped';
  acquired_at: number;             // 取得日(simulation time, days)
  prior_owners: string[];          // 過去の所有者ID履歴
}
```

### 2. Possession(占有)

物理的に誰が持っているかは法的所有者と必ずしも一致しない(リース・サブスク等)。

```typescript
interface PossessionState {
  physical_holder_id: string;      // 物理的に保持している主体
  location_country: string;        // 'JP', 'SG', 'TH', 'KE', etc.
  location_type: 'factory' | 'logistics' | 'dealer_yard' | 'in_use' | 'storage' | 'auction' | 'port' | 'workshop' | 'scrap';
  since: number;                   // この占有状態の開始日
}
```

### 3. Condition(物理状態)

```typescript
interface ConditionState {
  mileage_km: number;              // 累積走行距離
  age_days: number;                // 製造からの経過日数
  battery_soh: number | null;      // BEVの場合のみ。0.0〜1.0
  accident_history: AccidentRecord[];
  service_history: ServiceRecord[];
  current_fault_codes: string[];
}

interface AccidentRecord {
  occurred_at: number;
  severity: 'minor' | 'major' | 'total_loss';
  repaired: boolean;
}

interface ServiceRecord {
  occurred_at: number;
  type: 'periodic' | 'major_repair' | 'recall' | 'inspection';
  parts_replaced: string[];
}
```

### 4. Value(経済価値)

```typescript
interface ValueState {
  current_market_value: number;    // 現在の市場価値(円またはシナリオ通貨)
  msrp: number;                    // 新車時メーカー希望小売価格
  residual_set_value: number | null;  // 残価設定額(契約時に決定)
  last_revaluation_at: number;     // 最後に価格再評価された日
  value_curve_id: string;          // 適用される価値減衰カーブのID(scenarioに依存)
}
```

### 5. Regulatory(規制状態)

```typescript
interface RegulatoryState {
  registration_status: 'unregistered' | 'active' | 'suspended' | 'cancelled' | 'permanently_cancelled';
  registered_country: string | null;
  registration_id: string | null;  // ナンバーや登録番号
  next_inspection_due: number | null;  // 次回車検期限
  emission_compliant: boolean;
  outstanding_violations: number;  // 未払い違反金件数
  liens: LienRecord[];
}

interface LienRecord {
  holder_id: string;               // STK ID
  amount: number;
  set_at: number;
  status: 'active' | 'released';
}
```

### 6. Financial(金融状態)

```typescript
interface FinancialState {
  active_contracts: Contract[];
  total_outstanding_debt: number;
  total_paid_to_date: number;
  delinquency_status: 'current' | 'days_30' | 'days_60' | 'days_90+' | 'default';
  insurance_active: boolean;
  warranty_active: boolean;
  has_residual_guarantee: boolean;
  is_securitized: boolean;
  abs_pool_id: string | null;
}

interface Contract {
  id: string;
  type: 'loan' | 'lease' | 'subscription' | 'balloon' | 'fleet_lease';
  counterparty_id: string;         // STK ID
  start_date: number;
  end_date: number;
  monthly_payment: number;
  remaining_balance: number;
  status: 'active' | 'paid_off' | 'defaulted' | 'matured';
}
```

### 7. Data(履歴・データ)

```typescript
interface DataState {
  vin: string;                     // 不変識別子
  total_events_logged: number;
  attestations: Attestation[];     // 認証読取・SoH宣言など
  telematics_active: boolean;
  data_artifacts: string[];        // EV023 OTA, EV112 SoH宣言など、生成されたデータ成果物
  history_score: number;           // データ充実度の代理指標(0〜1)
}

interface Attestation {
  id: string;
  type: 'odometer_reading' | 'soh_declaration' | 'inspection_pass' | 'condition_certificate';
  attestor_id: string;
  attested_at: number;
  payload: Record<string, unknown>;
}
```

## VehicleState 全体

7属性を統合したルート型:

```typescript
interface VehicleState {
  vehicle_id: string;              // このシミュレーション内での一意ID
  phase: PhaseId;                  // 現在の相
  simulation_time: number;         // シミュレーション内時刻(days from start)
  ownership: OwnershipState;
  possession: PossessionState;
  condition: ConditionState;
  value: ValueState;
  regulatory: RegulatoryState;
  financial: FinancialState;
  data: DataState;
  scenario_id: string;             // 適用中のシナリオID
}
```

## 状態遷移の原則

### 原則1: 純粋関数

すべての状態遷移は `(state, event, context) → newState` の形の純粋関数で実装する。副作用なし。

### 原則2: イミュータビリティ

状態は不変オブジェクトとして扱い、変更時は新しいインスタンスを生成する(`structuredClone` または spread構文)。

### 原則3: 部分更新

各イベントは7属性のうち変更される部分のみを返す。マージはエンジン側で実施する。

### 原則4: 履歴を消さない

prior_owners・accident_history・service_history・attestations 等の履歴系フィールドは追記のみ。削除しない。

### 原則5: 不可逆イベントは状態に痕跡を残す

廃車・永久抹消・解体は単に phase='EOL' にするだけでなく、`regulatory.registration_status='permanently_cancelled'`、`data.attestations` への記録、`condition` の凍結など、複数フィールドに痕跡を残す。

## Phase遷移マトリックス

各相からの遷移可能先は `data/phases.json` の `transitions_to` で定義されている。これに違反する遷移は許可しない。

```
Production → Distribution
Distribution → Inventory
Inventory → Origination
Origination → In_Use
In_Use → Post_Contract / Used_Market / Cross_Border / EOL
Post_Contract → Used_Market / In_Use / Cross_Border / EOL
Used_Market → In_Use / Cross_Border / EOL / Late_Life
Cross_Border → In_Use / Late_Life / EOL / Cross_Border
Late_Life → EOL / Used_Market / Cross_Border
EOL → (terminal, 遷移先なし)
```

## 初期状態

シナリオ開始時の状態は `scenarios.json` の `vehicle_template` と `user_template` から構築される。デフォルトは:

- phase: `Production`
- simulation_time: 0
- ownership.legal_owner_id: シナリオで指定された初期所有者(通常 OEM = STK01)
- 各属性の初期値はシナリオ依存

詳細な初期化ロジックは `core/seed.ts` で実装する。

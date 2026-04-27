"""
v4.xlsxからシミュレーション用 events.json / stakeholders.json を生成
- 状態変化フラグから postconditions の骨格を自動生成
- フェーズ列から preconditions.phase の推測値を生成
- イベント×ステークホルダ×役割を統合
- actionable フラグはルールベースで主要選択肢にマーク
"""
import pandas as pd
import json
from collections import defaultdict

src = '/home/claude/build/vehicle_lifecycle_workshop_v4.xlsx'

ev_df = pd.read_excel(src, sheet_name='Events')
stk_df = pd.read_excel(src, sheet_name='Stakeholders')
es_df = pd.read_excel(src, sheet_name='EventStakeholders')

# ---------- フェーズ文字列 → ライフサイクル相のマッピング ----------
# シートのフェーズは「0〜0.5年」「2〜5年」等の時間表現
# これとカテゴリを組み合わせて、デフォルトの phase 制約を決定
def infer_phases(category, phase_str):
    """ライフサイクル相を推測する(複数許容)"""
    if category in ['製造']:
        return ['Production']
    if category in ['流通']:
        return ['Distribution']
    if category in ['納車']:
        return ['Origination']
    if category in ['登録']:
        # 登録は新規(Origination)と中古移転(Used_Market, In_Use)で発火
        return ['Origination', 'In_Use', 'Used_Market', 'Cross_Border']
    if category in ['輸出', '輸入']:
        return ['In_Use', 'Used_Market', 'Late_Life', 'Cross_Border']
    if category in ['廃車・循環']:
        return ['EOL', 'Late_Life']
    if category in ['市場']:
        return ['In_Use', 'Used_Market', 'Late_Life', 'Cross_Border']
    if category in ['小売']:
        # 0〜1年初期は Inventory→Origination、それ以降は Used_Market 寄り
        if '0〜' in phase_str:
            return ['Inventory', 'Origination']
        return ['Inventory', 'Used_Market', 'In_Use']
    if category in ['金融']:
        # 金融は契約成立期(Origination)から契約期間(In_Use)、満了後まで
        if '0〜1年' in phase_str:
            return ['Origination']
        return ['Origination', 'In_Use', 'Post_Contract']
    if category in ['保険']:
        return ['Origination', 'In_Use', 'Post_Contract']
    if category in ['事故・違反']:
        return ['In_Use', 'Used_Market', 'Cross_Border', 'Late_Life']
    if category in ['整備']:
        return ['In_Use', 'Used_Market', 'Cross_Border', 'Late_Life']
    if category in ['運行']:
        return ['In_Use', 'Cross_Border', 'Late_Life']
    if category in ['データ']:
        return ['Origination', 'In_Use', 'Post_Contract', 'Used_Market', 'Cross_Border', 'Late_Life']
    if category in ['規制']:
        return ['Origination', 'In_Use', 'Post_Contract', 'Used_Market', 'Cross_Border', 'Late_Life', 'EOL']
    if category in ['使用']:
        return ['In_Use', 'Cross_Border']
    # フォールバック
    return ['In_Use']

# ---------- 状態変化フラグ → 事後効果の骨格 ----------
STATE_FLAGS = ['所有', '占有', '状態', '価値', '規制', '債務', 'データ']

def build_postconditions(row):
    """状態変化フラグから事後効果の骨格(具体値はランタイムで決定)を生成"""
    post = {}
    if row['所有'] == 'Y':
        post['ownership_change'] = True
    if row['占有'] == 'Y':
        post['possession_change'] = True
    if row['状態'] == 'Y':
        post['condition_change'] = True
    if row['価値'] == 'Y':
        post['value_revaluation'] = True
    if row['規制'] == 'Y':
        post['regulatory_change'] = True
    if row['債務'] == 'Y':
        post['financial_change'] = True
    if row['データ'] == 'Y':
        post['data_emit'] = True
    if row['不可逆'] == 'Y':
        post['irreversible'] = True
    return post

# ---------- 確率/時間/選択イベントの分類 ----------
# カテゴリ別にデフォルトのトリガー型を決め、個別にオーバーライド
def infer_trigger_type(eid, category, name):
    """trigger_type: choice (プレイヤー選択) / probabilistic (確率) / time (周期) / cascade (連鎖)"""
    # 周期発火
    if eid in ['EV031', 'EV097', 'EV114', 'EV019', 'EV030', 'EV037', 'EV107', 'EV126']:
        return 'time'
    # 確率発火
    if eid in ['EV025', 'EV026', 'EV027', 'EV032', 'EV038', 'EV062', 'EV111', 'EV093', 'EV021']:
        return 'probabilistic'
    # 連鎖(他のイベントの結果として発火)
    if eid in ['EV011', 'EV012', 'EV013', 'EV094', 'EV095', 'EV117', 'EV052', 'EV121']:
        return 'cascade'
    # 残りは選択
    return 'choice'

# ---------- actionable: プレイヤーが能動的に選べるイベント ----------
# 概ね 'choice' だが、機械的すぎる選択は除く
def is_actionable(eid, trigger_type, category):
    if trigger_type == 'cascade':
        return False
    if trigger_type == 'time':
        return False
    if trigger_type == 'probabilistic':
        return False
    return True

# ---------- 確率パラメータ(年率) ----------
PROBABILISTIC_RATES = {
    'EV025': 0.08,   # 軽微事故 年8%
    'EV026': 0.015,  # 重大事故 年1.5%
    'EV027': 0.005,  # 盗難 年0.5%
    'EV032': 0.04,   # 支払遅延 年4%
    'EV038': 0.05,   # 保険金支払
    'EV062': 0.01,   # 全損宣言
    'EV111': 0.012,  # 保険全損認定
    'EV093': 0.20,   # 違反 年20%
    'EV021': 0.05,   # リコール
}

# ---------- 周期発火パラメータ ----------
TIME_PERIODICITY = {
    'EV031': 30,      # 月次払い
    'EV097': 7,       # 週次相当の通行料
    'EV114': 365,     # 年次税
    'EV019': 365,     # 年次定期点検
    'EV030': 730,     # 2年に1回車検
    'EV037': 365,     # 年次保険更新
    'EV107': 90,      # 四半期 ABS償還
    'EV126': 7,       # 週次PF精算
}

# ---------- ステークホルダ集計 ----------
# 各イベントにステークホルダ×役割を集約
ev_stk_map = defaultdict(list)
for _, r in es_df.iterrows():
    ev_stk_map[r['Event ID']].append({
        'stakeholder_id': r['Stakeholder ID'],
        'role': r['主要役割'],
        'layer': r.get('レイヤ', ''),
    })

# ---------- events.json の構築 ----------
events_out = []
for _, row in ev_df.iterrows():
    eid = row['Event ID']
    category = row['カテゴリ']
    name = row['イベント名']
    trigger_type = infer_trigger_type(eid, category, name)

    obj = {
        'id': eid,
        'name': name,
        'name_en': '',  # 後で必要に応じて埋める
        'phase_label': row['フェーズ'],
        'category': category,
        'description': row['説明'],
        'timing_hint': row['標準的タイミング'],
        'state_changes': {f: row[f] == 'Y' for f in STATE_FLAGS + ['不可逆']},
        'trigger_type': trigger_type,
        'actionable': is_actionable(eid, trigger_type, category),
        'preconditions': {
            'phase_in': infer_phases(category, row['フェーズ']),
            'min_age_days': 0,
            'requires_state': {},
        },
        'postconditions': build_postconditions(row),
        'stakeholders': ev_stk_map.get(eid, []),
    }
    if trigger_type == 'probabilistic':
        obj['probability_per_year'] = PROBABILISTIC_RATES.get(eid, 0.02)
    if trigger_type == 'time':
        obj['period_days'] = TIME_PERIODICITY.get(eid, 365)

    events_out.append(obj)

# ---------- stakeholders.json の構築 ----------
stakeholders_out = []
for _, row in stk_df.iterrows():
    stakeholders_out.append({
        'id': row['Stakeholder ID'],
        'name': row['ステークホルダ名'],
        'description': row['説明'],
        'layer': row.get('レイヤ', ''),
    })

# ---------- 出力 ----------
with open('/home/claude/sim/data/events.json', 'w', encoding='utf-8') as f:
    json.dump(events_out, f, ensure_ascii=False, indent=2)
with open('/home/claude/sim/data/stakeholders.json', 'w', encoding='utf-8') as f:
    json.dump(stakeholders_out, f, ensure_ascii=False, indent=2)

print(f"events.json: {len(events_out)} events")
print(f"  actionable: {sum(1 for e in events_out if e['actionable'])}")
print(f"  probabilistic: {sum(1 for e in events_out if e['trigger_type']=='probabilistic')}")
print(f"  time: {sum(1 for e in events_out if e['trigger_type']=='time')}")
print(f"  cascade: {sum(1 for e in events_out if e['trigger_type']=='cascade')}")
print(f"stakeholders.json: {len(stakeholders_out)} stakeholders")

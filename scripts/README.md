# scripts/

このディレクトリには、開発時に使うユーティリティスクリプトを置きます。
通常の実装作業では使いません。

## regenerate-data-from-xlsx.py

`data/*.json` を元の Excel ワークブック (`vehicle_lifecycle_workshop_v4.xlsx`) から再生成するための Python スクリプト。

### いつ使うか

- 元の xlsx を更新した(イベント追加、ステークホルダ追加、状態変化軸の修正など)
- フェーズ推論ロジック・トリガー型分類・確率パラメータを変更したい

通常の実装作業(Phase 2/3/4)では **使いません**。生成済みの `data/*.json` を直接読んで実装してください。

### 使い方

```bash
# 依存パッケージ
pip install pandas openpyxl

# 実行(xlsx のパスは適宜変更)
python3 scripts/regenerate-data-from-xlsx.py
```

スクリプトの先頭付近の `src` 変数で xlsx のパスを指定しています。

### 編集するときの注意

このスクリプトは以下のロジックを含みます:

- `infer_phases(category, phase_str)`: イベントの発火可能フェーズを推測
- `infer_trigger_type(eid, category, name)`: choice/probabilistic/time/cascade を分類
- `is_actionable(...)`: プレイヤー選択肢として表示するか
- `PROBABILISTIC_RATES`: 確率発火イベントの年率
- `TIME_PERIODICITY`: 周期発火イベントの周期日数

これらはヒューリスティクスです。もし `data/events.json` を直接編集したい場合は、JSON を直接編集してこのスクリプトの再実行は避けてください(上書きされます)。

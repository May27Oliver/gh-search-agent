# logger — 導覽

這個資料夾負責把 agent 每一次的執行過程**寫成檔案**。你可以把它想像成飛機的黑盒子：執行完之後，就算現場已經結束了，還可以從檔案回推整個過程發生了什麼。

完整規格寫在 [`specs/main/LOGGING.md`](../../../specs/main/LOGGING.md)，這份導覽只講大原則。

## 先看哪個

只有一個類別要看，全部都在 [`session.py`](./session.py) 裡：`SessionLogger`。它有三個對外方法：

- `append_turn(turn_log)` — 每跑完 agent 的一輪，就往 `turns.jsonl` 這個檔案加一行。JSONL 格式（每行一個 JSON 物件）方便之後用 `jq`、`grep`、`tail` 一行一行看。
- `write_turn_artifact(turn_index, tool_name, payload)` — 把這一輪的詳細資料寫成一份獨立的 JSON 檔，放在 `artifacts/` 底下。檔名是 `turn_01_intention_judge.json` 這種格式。
- `finalize(run_log, final_state)` — agent 跑完之後叫一次，寫出 `run.json`（整次執行的總結）和 `final_state.json`（最後的 state 快照）。

## 寫出來的目錄長這樣

```text
<log_root>/sessions/<session_id>/
├── run.json            # 整次執行的 RunLog（輸入 / outcome / 用了哪個 model / 時間戳）
├── turns.jsonl         # 每輪一行的 TurnLog，一路累積
├── final_state.json    # 最後的 SharedAgentState 快照
└── artifacts/
    ├── turn_01_intention_judge.json
    ├── turn_02_parse_query.json
    └── ...
```

每一份 artifact 裡面會有四個欄位：

- `input_state`：這一輪開始前的 state。
- `raw_model_output`：這輪如果叫了 LLM，就有它吐出來的原始字串；沒叫就是 `None`。
- `output_state`：這一輪結束之後的 state。
- `state_diff`：只列出「前後差在哪」的欄位。除錯時看 diff 最快，不用人眼比對整份 state。

## 為什麼用檔案、不用資料庫或 stdout

- 這是 take-home 專案，不想引入 DB 跟遷移的複雜度。
- JSONL / JSON 檔可以直接用 `jq`、`grep`、`less` 觀察，寫 eval scorer 也方便——`eval/scorer.py` 就是直接讀 `run.json` 來判定 outcome 的。
- stdout 會被 CLI 的輸出蓋過、且不能留存，不適合當黑盒子。

## 想加一個新欄位到 log 的話

1. 去 `schemas/logs.py` 加欄位（這是 log 的唯一定義來源）。
2. 填資料的源頭通常是 `agent/loop.py::_turn_log()` 或 CLI 的 `_cmd_query()`，看你要記的東西屬於「每輪」還是「整次」。
3. **不要在 logger 本身加業務邏輯**。這個資料夾只負責把給它的東西序列化寫檔，不判斷該不該寫、不做統計。

## 相關測試

`tests/test_logger.py` 覆蓋了建立 session 目錄、append 一行、finalize 順序這些情況。改 logger 的時候先看這裡。

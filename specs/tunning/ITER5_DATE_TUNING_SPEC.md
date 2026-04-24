# Iteration 5 Date Tuning Spec

## 1. 目標

本輪 tuning 處理 **`prompts/core/parse-v1.md`** 的日期語意章節，
並把 `Today: YYYY-MM-DD` 錨點注入到 **`src/gh_search/tools/parse_query.py`**
的 user_message 前綴（方案 B，§7.1）。為了讓 eval 可重現，錨點從
`eval/runner.py` 顯式注入 dataset-anchored 日期常數（`2026-04-23`，依
dataset notes），透過 `agent/loop.py` 傳到 `parse_query`；production CLI
路徑不強制注入，fallback `date.today()`。

本輪共動 4 個檔案（§7）：

- `prompts/core/parse-v1.md`（規則擴充）
- `src/gh_search/tools/parse_query.py`（接收 today kwarg + 前綴注入）
- `src/gh_search/agent/loop.py`（`run_agent_loop` 加 optional today，往
  `_dispatch` 傳）
- `src/gh_search/eval/runner.py`（`run_smoke_eval` 從 dataset 常數注入 today）

這一層的責任是：

- 把使用者描述的「絕對年份 / 相對時間 / 年份區間 / 模糊時間」轉成
  `created_after` / `created_before` 的 ISO 日期
- 在模糊/無法安全推論時保留 `null`（保守原則）
- 允許 parser 取得當日日期，以便解析 `last year` / `this year` 類
  dataset-backed 相對時間（`recent` / `last N months` 等落入模糊保守
  或 out of scope，見 §3.3 / §6）

這一層 **不負責**：

- keyword phrase 正規化（iter4 已處理）
- intention gate（iter3 已處理）
- language over-inference（保留給 iter6）
- decoration token 清理（保留給 iter7）
- stars 邊界 / 矛盾判定（validator / 後續 iter）

## 2. 背景

Iter4 phrase policy 把三個模型推到 56.67% / 66.67% / 63.33%，剩餘
失分裡 **date 類別**是 scope 最純、最可預測的一桶。

Iter4 follow-up per-item 分析顯示 date-related 失分共 **11 個 pair**
（見 §5），跨 5 個 pattern：

| Pattern | Fail 數 | 題目 |
|---|---|---|
| A. 相對日期缺 today 錨點 | 6 | q013×3（`last year`）、q017×3（`this year`） |
| B. 年份區間閉合缺 `created_before` | 2 | q018 GPT / CLA（`from 2024`） |
| C. 中文「以后」邊界 | 2 | q028 CLA / DSK（`2023年以后`） |
| D. 英文 `after YEAR` 邊界 | 1 | q025 GPT（`aftr 2022`，跨 run pred 在 `2022-01-01` / `2022-12-31` 之間 flake，均未套用 `after YEAR → YEAR+1` 規則） |
| E. 模糊時間詞過度推論（FP） | 2 | q021 GPT / CLA（`not too old but not too new` → 塞日期） |

### 2.1 Dataset GT 的實際日期政策

對照 `datasets/eval_dataset_reviewed.json` 所有 date-constrained 題目：

| 使用者語言 | GT 對應 | 範例 |
|---|---|---|
| `after YEAR`（英文） | **exclusive**：`created_after=YEAR+1-01-01` | q011「after 2023」→ `2024-01-01`；q025「aftr 2022」→ `2023-01-01` |
| `before YEAR`（英文） | **exclusive**：`created_before=YEAR-1-12-31` | q012「before 2020」→ `2019-12-31` |
| `between Y1 and Y2` | **inclusive span**：`after=Y1-01-01, before=Y2-12-31` | q014「between 2019 and 2022」→ `2019-01-01 ~ 2022-12-31` |
| `from YEAR` / `in YEAR` | **full year**：`after=YEAR-01-01, before=YEAR-12-31` | q018「from 2024」→ `2024-01-01 ~ 2024-12-31` |
| `YEAR年以后`（中文） | **inclusive**：`created_after=YEAR-01-01` | q028「2023年以后」→ `2023-01-01`（**與英文 after 不同**） |
| `last year` | **上一年全年**：`after=(TODAY_YEAR-1)-01-01, before=(TODAY_YEAR-1)-12-31` | q013（today=2026-04-23）→ `2025-01-01 ~ 2025-12-31` |
| `this year` | **今年至今**：`after=TODAY_YEAR-01-01, before=null` | q017 → `2026-01-01 ~ null` |
| 模糊：`recent-ish` / `not too old` / `cool` | **全 null（保守）** | q021 → `null / null` |

關鍵非對稱：**英文 `after YEAR` 是 exclusive（year+1），中文 `YEAR年以后`
是 inclusive（year）**。這不是 bug 是 dataset 刻意設計的語言差異（q011
notes + q028 notes 都明示過），parser 必須照實學。

### 2.2 根因

現行 `prompts/core/parse-v1.md` 只有一行日期規則：

> `created_after / created_before: ISO dates YYYY-MM-DD, or null. 'after 2023' means created_after='2024-01-01'. 'before 2020' means created_before='2019-12-31'.`

覆蓋不到：

1. **相對時間**：完全沒有規則，也沒有 today 可參考
2. **`from YEAR`**：沒規則，模型自由發揮 → GPT/CLA 漏掉 `before=YEAR-12-31`
3. **中文時間詞**：沒說中文「以后」與英文 `after` 的邊界不同
4. **模糊詞保守原則**：沒明示「不能安全對應具體日期時保留 null」
5. **`aftr`（typo）**：沒明示「錯字仍照語意處理」（q025 GPT pred 在 iter4
   baseline 為 `2022-12-31`、follow-up 為 `2022-01-01` — 跨 run flake，
   但兩個值都代表沒套用 `after YEAR → YEAR+1` 規則）

## 3. 單一判定原則

Parser 對 date 輸出必須滿足：

### 3.1 Today 錨點可取得（且 eval 可重現）

Parser 在 system prompt 外會收到當日日期字串 `Today: YYYY-MM-DD`（§7.1
在 user_message 前綴注入）。所有相對時間規則以此為基準。

錨點來源規則：

- **Eval 路徑**（`run_smoke_eval` → `run_agent_loop` → `parse_query`）：
  必須由 runner 顯式注入 **dataset-anchored 常數**，目前為
  `DATASET_TODAY_ANCHOR = date(2026, 4, 23)`（依 `eval_dataset_reviewed.json`
  q013 / q017 notes 的「以 2026-04-23 為標註基準」）。跨年、跨日 rerun
  結果都穩定、不會讓 `last year` / `this year` 答案漂動。
- **Production 路徑**（`gh-search query` CLI）：不強制注入 today，
  `parse_query` 接收 `today=None` 時 fallback 到 `date.today()`。production
  使用者自然語境就是「今天」。

變更規格以後 dataset 要改標註基準時，只需動 `DATASET_TODAY_ANCHOR` 常數
（並重跑 smoke），不需動 prompt / tool / loop 任何一層。

### 3.2 邊界規則（絕對年份）

- **英文 `after YEAR`**：`created_after = (YEAR+1)-01-01`，`created_before = null`
- **英文 `before YEAR`**：`created_before = (YEAR-1)-12-31`，`created_after = null`
- **`between Y1 and Y2` / `from Y1 to Y2`**：`created_after=Y1-01-01, created_before=Y2-12-31`
- **`from YEAR` / `in YEAR`**：`created_after=YEAR-01-01, created_before=YEAR-12-31`
- **中文 `YEAR年以後` / `YEAR年以后` / `YEAR年之后` / `YEAR年以来`**：
  `created_after=YEAR-01-01`（inclusive，**不是 YEAR+1**）
- **中文 `YEAR年以前` / `YEAR年之前`**：`created_before=(YEAR-1)-12-31`（exclusive，
  與英文 `before YEAR` 對齊）

### 3.3 相對時間規則（以 today 為基準，dataset-backed only）

設 `TODAY_YEAR = year(Today)`。本輪只收 dataset 有實際支撐的相對時間
模式：

- **`this year` / 今年**：`created_after=TODAY_YEAR-01-01, created_before=null`
  （q017 支撐）
- **`last year` / 去年**：`created_after=(TODAY_YEAR-1)-01-01,
  created_before=(TODAY_YEAR-1)-12-31`（q013 支撐）
- **`recent` / 最近 / `recently` / 最近幾天**（無具體數量）：落入 §3.4
  保守原則，全 null

`last N months` / `last N days` / `past N weeks` 等有具體數量的相對時間
**不在本輪規則覆蓋範圍**。dataset 目前沒有此類題目，貿然加規則可能引入
新 FP（例如把 `3 months of development experience` 誤判成時間篩選），
延到有 dataset evidence 時再補。

### 3.4 模糊時間詞保守原則

下列表述**不得**推論具體日期，`created_after` 與 `created_before` 都留 `null`：

- `recent`（無具體時間區間）
- `recently updated`（語意是 `sort=updated` 而非日期）
- `not too old` / `not too new` / `cool` / `new-ish` / `relatively new`
- `modern` / `latest`（含義過寬）
- `a while back` / `some time ago`

規則 wording：*「When the user's temporal phrasing is vague or cannot
be mapped to a concrete calendar range, leave both `created_after`
and `created_before` as `null`. Do not guess.」*

### 3.5 Typo / 口語容忍

`aftr`、`b4`、`bfr` 等明顯 typo 仍依 §3.2 正常規則處理。規則 wording
會明示：*「Apply the same rule even if the keyword is misspelled
(e.g. `aftr 2022` → same as `after 2022`）」*。

### 3.6 一致性

新規則覆蓋後，原本 OK 的題目（q011 / q012 / q014 / q018 DSK）必須維持
OK。尤其 q011「after 2023 → 2024-01-01」必須保留 exclusive 行為，不能
因為加了中文 inclusive 規則而誤改。

## 4. 明確責任分界

以下情況 **不得**在 parse prompt 解決：

- parser 塞了裝飾詞到 keywords（q007 `implementations`、q019 DSK `repos`）→ iter7
- parser over-infer language（q001 JavaScript、q009 Vue）→ iter6
- 多語 topic 詞（q027 爬蟲、q029 サンプル）→ iter7
- stars 邊界（q015 CLA）→ 另開
- stars 矛盾（q030）→ validator / repair
- outcome contract（q020 max_turns）→ 另開

這些都保留到後續 iter，若本輪為了救某題而動上述範圍，視為 scope drift
並停下來另開一輪。

## 5. 本輪要救回的題目

### 5.1 Date-only blocker（修完預期變 CORRECT）

| qid | model | 輸入語意 | iter4 pred | GT | Pattern |
|---|---|---|---|---|---|
| q013 | GPT | `last year` | `2023-01-01 ~ 2023-12-31` | `2025-01-01 ~ 2025-12-31` | A（相對時間） |
| q013 | CLA | `last year` | `2024-01-01 ~ null` | `2025-01-01 ~ 2025-12-31` | A |
| q013 | DSK | `last year` | `2024-01-01 ~ 2024-12-31` | `2025-01-01 ~ 2025-12-31` | A |
| q017 | GPT | `this year` | `2024-01-01 ~ null` | `2026-01-01 ~ null` | A |
| q017 | CLA | `this year` | `2024-01-01 ~ null` | `2026-01-01 ~ null` | A |
| q017 | DSK | `this year` | `2025-01-01 ~ null` | `2026-01-01 ~ null` | A |
| q018 | GPT | `from 2024` | `2024-01-01 ~ null` | `2024-01-01 ~ 2024-12-31` | B（區間閉合） |
| q018 | CLA | `from 2024` | `2024-01-01 ~ null` | `2024-01-01 ~ 2024-12-31` | B |
| q028 | CLA | `2023年以后` | `2024-01-01 ~ null` | `2023-01-01 ~ null` | C（中文邊界） |
| q028 | DSK | `2023年以后` | `2024-01-01 ~ null` | `2023-01-01 ~ null` | C |
| q025 | GPT | `aftr 2022` | 錯值（`2022-12-31` 或 `2022-01-01`，跨 run flake） | `2023-01-01 ~ null` | D（typo + 邊界） |

**共 11 個 `(qid, model)` pair**。

### 5.2 Date false positive（修完預期變 CORRECT，當前是過度推論）

| qid | model | 輸入語意 | iter4 pred | GT | Pattern |
|---|---|---|---|---|---|
| q021 | GPT | `not too old but not too new` | `2019-01-01 ~ 2022-12-31` | `null ~ null` | E（模糊保守） |
| q021 | CLA | `not too old but not too new` | `2020-01-01 ~ 2023-12-31` | `null ~ null` | E |

**共 2 個 pair**。但 q021 只要 date FP 修掉，其餘欄位對齊，就會整題 CORRECT
（keywords=[]，language=Swift，其他欄位目前對）。

### 5.3 Date 修對但仍有其他 blocker（本輪 **不保證**回分）

目前三個模型的 `q013` / `q017` / `q018` / `q025` / `q028` / `q021` 依
iter4 follow-up per_item 觀察均 **只有 date 欄位 mismatch**，沒有其他
blocker。本輪預期 §5.1 + §5.2 共 13 個 pair 會轉 CORRECT。

但 parser stochasticity 可能讓某題在 rerun 時其他欄位（keywords / language /
stars）出現非 date 問題，擋住該 pair 翻正。此情形依 §10 實質判準處理：
- 若翻正數仍 ≥ 11/13，視為實質通過，在 §11.4 逐題歸因
- 若翻正數 < 11/13，視為規則覆蓋不足或 scope 外的 blocker 影響過大，
  走 iter5 follow-up 或在 §11.4 決定延後到下一輪

### 5.4 預期 accuracy 變化

iter4 follow-up baseline：

| 模型 | iter4 follow-up accuracy |
|---|---|
| `gpt-4.1-mini` | 56.67%（17/30） |
| `claude-sonnet-4` | 66.67%（20/30） |
| `deepseek-r1` | 63.33%（19/30） |

iter5 預期 Δ（§5.1 + §5.2 合計）：

| 模型 | §5.1 Δ | §5.2 Δ | iter5 預期 Δ | iter5 預期 accuracy |
|---|---|---|---|---|
| GPT | +4（q013 / q017 / q018 / q025） | +1（q021 GPT） | **+5** | **73.33%（22/30）** |
| CLA | +4（q013 / q017 / q018 / q028） | +1（q021 CLA） | **+5** | **83.33%（25/30）** |
| DSK | +3（q013 / q017 / q028） | 0（q021 DSK iter4 已 OK） | **+3** | **73.33%（22/30）** |

保守下界（若某 pair 被 parser stochasticity 擋住）：GPT +4 / CLA +4 /
DSK +2。若實測落到下界以下再 2 題以上才視為規則覆蓋失敗，進 follow-up。

## 6. 不在本輪範圍

- `src/gh_search/normalizers/keyword_rules.py`（iter4 scope）
- `prompts/core/intention-v1.md`（iter3 scope）
- `prompts/core/repair-v1.md`
- `prompts/appendix/parse-*-v1.md`（model-specific few-shot 留給 rerun 後
  視需要再補）
- `src/gh_search/validator.py`
- `src/gh_search/eval/scorer.py`
- `src/gh_search/cli.py` 的 `gh-search query` / `gh-search smoke` flag
  （today 不做 CLI 層覆寫）
- parser decoration-token 清理（q007 `implementations`、q018 DSK `projects`、
  q019 DSK `repos`）
- parser language over-inference（q001、q009、q029）
- 多語 topic alias（q027、q029）
- stars 邊界 / 矛盾（q015、q030）
- execution robustness（q020 max_turns contract）
- 有具體數量的相對時間（`last N months` / `last N days` / `past N weeks`，
  無 dataset evidence）

若本輪為救某題而開始動以上檔案或 prompt 段落，視為 scope drift，停下來
另開一輪。

## 7. 程式碼與 prompt 調整方向

### 7.1 Today 錨點注入（方案 B，threaded through eval path）

#### 7.1.1 `parse_query.py`：接收 today kwarg、前綴注入 user_message

目標檔案：

- [src/gh_search/tools/parse_query.py](../../src/gh_search/tools/parse_query.py)

```python
from datetime import date

def parse_query(
    state: SharedAgentState,
    llm: LLMJsonCall,
    *,
    today: date | None = None,
) -> SharedAgentState:
    system_prompt = compose_system_for(PROMPT_NAME, llm)
    today_iso = (today or date.today()).isoformat()
    user_message = f"Today: {today_iso}\n\n{state.user_query}"
    response = llm(system_prompt, user_message, RESPONSE_SCHEMA)
    ...
```

設計取捨：

- **注入位置**：放在 user_message 前綴而非 system_prompt，讓 prompt 檔案
  保持 pure static（方便 git diff 與 appendix 模型覆寫）。system_prompt
  由 core + appendix composed 而來，混進動態變數會擾亂 prompt caching
  與 cross-model 對照。
- **格式**：`Today: YYYY-MM-DD\n\n<user_query>` — 單行、ISO 8601、
  與 user_query 用空行隔開。
- **Fallback**：`today=None` 時用 `date.today()`（production CLI 走此路徑）。

#### 7.1.2 `agent/loop.py`：`run_agent_loop` 與 `_dispatch` 傳遞 today

目標檔案：

- [src/gh_search/agent/loop.py](../../src/gh_search/agent/loop.py)

```python
def run_agent_loop(
    user_query: str,
    run_id: str,
    llm: LLMJsonCall,
    github: GitHubClient,
    max_turns: int = 5,
    results_sink: list[Repository] | None = None,
    session_logger: SessionLogger | None = None,
    *,
    today: date | None = None,
) -> SharedAgentState:
    ...
    new_state = _dispatch(
        state, tool, llm=recording_llm, github=github,
        results_sink=results_sink, today=today,
    )


def _dispatch(
    state: SharedAgentState,
    tool: ToolName,
    *,
    llm: LLMJsonCall,
    github: GitHubClient,
    results_sink: list[Repository] | None,
    today: date | None = None,
) -> SharedAgentState:
    ...
    if tool is ToolName.PARSE_QUERY:
        return parse_query(state, llm=llm, today=today)
    ...
```

其他分支（`intention_judge` / `validate_query` / `compile_github_query`
等）完全不動 — today 只影響 parse_query。

#### 7.1.3 `eval/runner.py`：eval 路徑強制注入 dataset anchor

目標檔案：

- [src/gh_search/eval/runner.py](../../src/gh_search/eval/runner.py)

```python
from datetime import date

# dataset notes (q013 / q017) specify 2026-04-23 as the annotation anchor.
DATASET_TODAY_ANCHOR: date = date(2026, 4, 23)

def run_smoke_eval(
    ...,
    today_anchor: date = DATASET_TODAY_ANCHOR,
) -> SmokeSummary:
    ...
    final_state = run_agent_loop(
        user_query=item["input_query"],
        run_id=run_id,
        llm=llm,
        github=github,
        max_turns=max_turns,
        results_sink=results,
        session_logger=session_logger,
        today=today_anchor,
    )
```

`DATASET_TODAY_ANCHOR` 是模組常數，未來 dataset 改版時只動這一行。不
exposé 到 CLI flag — smoke 的 reproducibility 是 dataset-bound，不該讓
使用者在命令列覆寫。

#### 7.1.4 Production CLI 路徑不動

`src/gh_search/cli.py` 的 `gh-search query` 不傳 `today`，`run_agent_loop`
→ `parse_query` 會拿 `None` → fallback `date.today()`。符合「使用者在
production 的 today 就是系統日期」直覺。

### 7.2 `prompts/core/parse-v1.md`：擴充日期規則章節（dataset-backed only）

把現行單行日期規則擴充成結構化區塊。**只收錄 dataset 有實際 case 支撐
的模式**，完整替換段落如下（不動其他 keyword / language / stars / sort /
order / limit 章節）：

```
Date rules (use the `Today: YYYY-MM-DD` header in the user message as the anchor for relative expressions):

Absolute year boundaries:
- English "after YEAR": created_after = (YEAR+1)-01-01, created_before = null.
  Example: "after 2023" → created_after="2024-01-01".
- English "before YEAR": created_before = (YEAR-1)-12-31, created_after = null.
  Example: "before 2020" → created_before="2019-12-31".
- "between Y1 and Y2" or "from Y1 to Y2": created_after=Y1-01-01, created_before=Y2-12-31.
- "from YEAR" or "in YEAR" (bare-year full-year shorthand): created_after=YEAR-01-01, created_before=YEAR-12-31.

Chinese year boundaries (inclusive start, differs from English "after"):
- "YEAR年以後" / "YEAR年以后" / "YEAR年之後" / "YEAR年之后" / "YEAR年以來":
  created_after=YEAR-01-01 (include YEAR itself), created_before=null.
  Example: "2023年以后" → created_after="2023-01-01".
- "YEAR年以前" / "YEAR年之前": created_before=(YEAR-1)-12-31 (exclude YEAR), created_after=null.

Relative time (anchored on Today):
- "this year" / "今年": created_after=<TodayYear>-01-01, created_before=null.
- "last year" / "去年": created_after=<TodayYear-1>-01-01, created_before=<TodayYear-1>-12-31.

Vague or unmappable temporal phrasing — both dates MUST stay null:
- "recent", "recently", "modern", "latest", "new-ish", "relatively new".
- "not too old", "not too new", "cool", "some time ago", "a while back".
- "last few months", "recent months", any phrase without an explicit calendar anchor.
Do not guess concrete dates from vague wording.

Misspellings:
- Apply the same rule even if the keyword is misspelled ("aftr 2022" → same as "after 2022"; "b4 2020" → same as "before 2020").
```

刪除現行單行規則（`parse-v1.md:5`），整段改以上述區塊。

**刻意不收**的模式（避免 dataset-less 規則引入 FP）：

- `last N months` / `last N days` / `past N weeks` — dataset 沒有此類
  題目，規則化可能把 `3 months of experience` 類無關描述誤判為時間篩選
- `this month` / `this week` / `today` — 同上
- `YEAR projects` 當作 full year — 「YEAR」可能是版本代號或技術代號（例如
  `vue 3`、`python 2`），bare-year shorthand 只保留 `from YEAR` / `in YEAR`
  這種前置詞明確的形式

### 7.3 `parse-<model>-v1.md` appendix：不動

依 `PHASE2_PLAN.md §1.1` 原則，model-specific tuning 只能寫在 appendix。
本輪 core 規則改動屬跨模型統一規則，三個 appendix 保持不動。若 rerun
後某模型某 pattern 仍系統性 miss，才在該 appendix 補 few-shot（延後到
iter5 驗收階段才決定）。

## 8. 測試策略

### 8.1 Unit：`parse_query` today 注入契約

目標檔案：

- `tests/test_tool_parse_query.py`

新增測試確認 today 前綴格式正確、且可注入固定 today 做重現：

```python
from datetime import date

def test_parse_query_prefixes_today_iso_to_user_message():
    llm, captured = _stub_llm({...})
    state = _fresh_state("find python repos from last year")
    parse_query(state, llm=llm, today=date(2026, 4, 23))
    assert captured["user_message"].startswith("Today: 2026-04-23\n\n")
    assert "find python repos from last year" in captured["user_message"]


def test_parse_query_today_defaults_to_system_date_when_not_provided():
    # Production 路徑不傳 today 時仍注入當天
    import re
    llm, captured = _stub_llm({...})
    state = _fresh_state("whatever")
    parse_query(state, llm=llm)
    assert re.match(r"Today: \d{4}-\d{2}-\d{2}\n\n", captured["user_message"])
```

### 8.1.1 Unit：agent loop 傳遞 today 契約

目標檔案：

- `tests/test_agent_loop.py`

```python
def test_run_agent_loop_forwards_today_to_parse_query(monkeypatch):
    captured: dict = {}
    def fake_parse_query(state, *, llm, today=None):
        captured["today"] = today
        return state.model_copy(update={...})
    monkeypatch.setattr("gh_search.agent.loop.parse_query", fake_parse_query)
    run_agent_loop(
        user_query="irrelevant",
        run_id="r1",
        llm=stub_llm,
        github=stub_github,
        today=date(2026, 4, 23),
    )
    assert captured["today"] == date(2026, 4, 23)
```

### 8.1.2 Unit：eval runner 注入 `DATASET_TODAY_ANCHOR`

目標檔案：

- `tests/eval/test_runner.py`（或現有 runner 測試檔案）

```python
from gh_search.eval.runner import DATASET_TODAY_ANCHOR, run_smoke_eval

def test_dataset_today_anchor_matches_dataset_notes():
    # dataset notes q013/q017 明示 2026-04-23
    assert DATASET_TODAY_ANCHOR == date(2026, 4, 23)


def test_run_smoke_eval_passes_today_anchor_to_loop(monkeypatch):
    seen: dict = {}
    def fake_loop(*args, **kwargs):
        seen["today"] = kwargs.get("today")
        return minimal_final_state()
    monkeypatch.setattr("gh_search.eval.runner.run_agent_loop", fake_loop)
    run_smoke_eval(...)
    assert seen["today"] == DATASET_TODAY_ANCHOR
```

### 8.2 Unit：prompt 規則存在性（contract-level）

目標檔案：

- `tests/test_prompt_composer.py` 或新增 `tests/test_parser_prompt_date_rules.py`

確認 iter5 新 date 規則段落確實寫進 core prompt（避免未來誤刪）：

```python
DATE_PROMPT_CONTRACT_PHRASES = [
    "Today: YYYY-MM-DD",
    "after YEAR",
    "before YEAR",
    "between Y1 and Y2",
    "from YEAR",
    "YEAR年以后",  # Chinese inclusive
    "last year",
    "this year",
    "vague or unmappable",
    "aftr 2022",   # typo tolerance
]

@pytest.mark.parametrize("phrase", DATE_PROMPT_CONTRACT_PHRASES)
def test_parse_prompt_contains_iter5_date_rule(phrase):
    core = (PROJECT_ROOT / "prompts/core/parse-v1.md").read_text(encoding="utf-8")
    assert phrase in core, f"iter5 date rule '{phrase}' missing from parse-v1.md"
```

這組 case 是 **文件對照合約**，不替 LLM 判決負責，但避免 prompt 在後續
iter 被誤刪回 iter4 版本。

### 8.3 Unit：parser prompt date rule 不得動到其他章節

目標檔案：

- `tests/test_parser_prompt_date_rules.py`

對 parse prompt 做 regex 驗證，確認非 date 章節沒被順手改：

```python
def test_parse_prompt_preserves_iter4_keyword_policy():
    core = (PROJECT_ROOT / "prompts/core/parse-v1.md").read_text(encoding="utf-8")
    # iter4 phrase policy 仍存在
    for phrase in ["spring boot", "react native", "machine learning", "ui kit"]:
        assert phrase in core
    # Non-date rules intact
    assert "language: the programming language" in core
    assert "min_stars / max_stars" in core
    assert "sort: one of 'stars'" in core
```

### 8.4 E2E：cross-model smoke rerun（§9.2）

Pure prompt rule 本身無法用 unit test 驗證 LLM 會不會聽話 — 最終判決在
smoke rerun。Unit test 只保證：

- today 注入契約穩定（§8.1）
- prompt 新規則沒被誤刪（§8.2）
- prompt 其他章節沒被動到（§8.3）

實際判決依 §10 實質判準（target pair 翻正率 ≥ 11/13 + Δ 達保守下界）。

## 9. 驗證方式

### 9.1 Unit

```bash
pytest -q tests/test_tool_parse_query.py
pytest -q tests/test_parser_prompt_date_rules.py  # 新檔
pytest -q  # 全綠
```

### 9.2 Cross-model full smoke rerun

```bash
gh-search smoke --model gpt-4.1-mini    --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter5_20260424
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter5_20260424
gh-search smoke --model DeepSeek-R1     --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter5_20260424
```

### 9.3 Diff 分析

對照 iter4 follow-up / iter5 per-item，依 §10 實質判準驗收：

- §5.1 列的 11 個 pair + §5.2 列的 2 個 pair（共 13）在 iter5 對應模型
  **至少 11 個翻正**（`is_correct` 由 `false` → `true`）。剩餘 1–2 個
  未翻正 pair 必須於 §11.4 逐題歸因（parser stochasticity / 規則覆蓋
  不足 / 第三方因素），符合 §10.3。
- cross-model rerun 的 accuracy Δ 需 ≥ §11.1 保守下界
  （GPT +4 / CLA +4 / DSK +2）。
- iter4 已 CORRECT 的題目零 regression（outcome / score / predicted
  structured query 都不退）。
- 尤其 q011 / q012 / q014 / q018 DSK（iter4 已 CORRECT 的 date 題）要
  確認 exclusive 邊界規則沒被 iter5 新規則誤影響。

## 10. 通過標準

本輪採 **實質判準**（對齊 iter4 §11.4 做法），通過需同時滿足：

1. **Δ 達標（核心）**：cross-model rerun accuracy Δ ≥ §11.1 保守下界
   （GPT +4 / CLA +4 / DSK +2）。若 Δ 達到或超過表格中的預期值
   （GPT +5 / CLA +5 / DSK +3），則列為完整達標；若落在保守下界區間，
   視為實質通過但在 §11.3 / §11.4 明確記錄差距。
2. **零 regression**：iter4 follow-up 所有 CORRECT 題在 iter5 維持
   CORRECT（尤其已對的 date 題 q011 / q012 / q014 / q018 DSK），
   確認 exclusive 邊界規則沒被新規則誤影響。
3. **Target pair 翻正率**：§5.1 + §5.2 共 13 個 pair，至少 **11/13**
   在 iter5 rerun 翻正；剩下的 1–2 個 pair 必須在 §11.4 逐一歸因：
   - parser stochasticity（例如其他欄位這次 flake 出非 date 問題）
   - 規則覆蓋不足（prompt wording 對該模型不敏感）— 進 iter5 follow-up
   - 第三方因素（例如 LLM provider 側行為變動）
4. **Pytest 全綠**：
   - `tests/test_tool_parse_query.py` — today 注入契約（§8.1）
   - `tests/test_agent_loop.py` — loop 傳遞 today 契約（§8.1.1）
   - eval runner 測試 — `DATASET_TODAY_ANCHOR` + runner 注入契約（§8.1.2）
   - `tests/test_parser_prompt_date_rules.py` — 規則存在性（§8.2）與非
     date 章節保留性（§8.3）
5. **契約穩定**：`parse_query` 的 today 注入格式穩定（`Today: YYYY-MM-DD\n\n...`），
   且 eval 路徑永遠拿 `DATASET_TODAY_ANCHOR`、production CLI 拿系統日期。
6. **Scope 鎖死**：本輪 **只動** 4 個檔案（§1 列出）：
   - `prompts/core/parse-v1.md`
   - `src/gh_search/tools/parse_query.py`
   - `src/gh_search/agent/loop.py`（加 optional today 參數）
   - `src/gh_search/eval/runner.py`（加 `DATASET_TODAY_ANCHOR` 常數與
     `today_anchor` 參數）

   不得動 normalizer / validator / scorer / intention prompt / repair
   prompt / appendix prompt / CLI flag。

**嚴格判準（不採用）**：若採「13/13 全翻正」為 pass/fail line，則 iter4
的 q019 DSK 類 parser stochasticity 案例會反覆擋住每一輪 accept，violate
iter4 §11.4 的先例。因此本 spec 不採嚴格判準。

## 11. 預期影響與驗收欄位

### 11.1 預期 accuracy

| 模型 | iter4 follow-up | iter5 預期 | Δ |
|---|---|---|---|
| `gpt-4.1-mini` | 56.67%（17/30） | **73.33%（22/30）** | **+5** |
| `claude-sonnet-4` | 66.67%（20/30） | **83.33%（25/30）** | **+5** |
| `deepseek-r1` | 63.33%（19/30） | **73.33%（22/30）** | **+3** |

保守下界 Δ：GPT +4 / CLA +4 / DSK +2（若 §5.2 q021 某模型沒完全吃到
保守原則、或 §5.1 某 pair 被其他欄位 flake 擋住）。

若實測 Δ 低於下界以 2 題以上，代表 prompt 規則覆蓋不足或 LLM 對規則
表述不敏感，在 `ITER5_NOTES.md` 記錄差距並列入 iter5 follow-up。

### 11.2 實際 rerun 結果

（rerun 後填入，格式比照 iter4 §11.1）

| 模型 | iter4 follow-up | iter5 | 實際 Δ | 對照預期 |
|---|---|---|---|---|
| `gpt-4.1-mini` | 56.67%（17/30） | TBD | TBD | TBD |
| `claude-sonnet-4` | 66.67%（20/30） | TBD | TBD | TBD |
| `deepseek-r1` | 63.33%（19/30） | TBD | TBD | TBD |

### 11.3 §5.1 + §5.2 target pair 實際回收

（rerun 後填入，格式比照 iter4 §11.2）

### 11.4 Caveat 記錄位

（rerun 後填入，格式比照 iter4 §11.3）

## 12. 下一輪交接

本輪完成後，下一輪優先項按 iter5 per-item 剩餘 blocker 排序：

1. **iter6** — parser `language` over-inference
   - `q001`（react → JavaScript）
   - `q009`（vue → JavaScript / Vue）
   - `q029`（react → JavaScript）
2. **iter7** — parser decoration-token 清理
   - `q007 implementations`、`q018 projects`、`q019 DSK repos`
   - 可同時納入 `q020 stuff`
3. **iter8** — 多語 topic alias / drop policy
   - `q027 爬蟲 / 套件`
   - `q029 サンプルプロジェクト / japanese / project`
4. **後續** — validator / repair / outcome contract
   - `q030` 矛盾條件
   - `q020` max_turns contract
   - stars boundary off-by-one（q015）
   - execution robustness

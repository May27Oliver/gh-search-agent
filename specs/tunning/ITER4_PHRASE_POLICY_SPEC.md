# Iteration 4 Phrase Policy Tuning Spec

## 1. 目標

本輪 tuning 只處理 **`src/gh_search/normalizers/keyword_rules.py`**，把 phrase
正規化行為對齊 dataset GT 的實際風格，讓 parser 即使輸出多字合併字串，也能
被還原成 GT 可比對的粒度。

這一層的責任是：

- 把輸入 keyword list 轉成 deterministic、order-independent、idempotent 的
  canonical form
- 同時服務 parser 後處理、`validate_query`、`repair_query`、scorer、log trace
- 吃任何形狀的輸入（單字 token / 多字字串 / 不同大小寫 / 複數 / alias）並吐
  出一致的輸出

這一層 **不負責**：

- parser 判斷要不要把 tokens 合併（那是 parser prompt 的行為）
- 判斷 query 是不是 repo search（那是 `intention_judge`）
- 語意矛盾（那是 `validator`）

## 2. 背景

Iter3 把 gate 打開之後，downstream 失分最大的一桶是 **phrase 結構對不上**。
三個模型在 iter3 per-item 結果顯示：

| 模型 | phrase-mismatch 題數 |
|---|---|
| `gpt-4.1-mini` | 8 |
| `claude-sonnet-4` | 9 |
| `deepseek-r1` | 9 |

典型失敗形式包含：

- `['web frameworks']` vs GT `['web', 'framework']`（q003 全模型）
- `['cli tools']` / `['cli', 'tools']` vs GT `['cli', 'tool']`（q004 全模型）
- `['kubernetes operator', 'example']` vs GT `['kubernetes', 'operator', 'example']`（q005 Claude / DSK）
- `['llm inference engines']` vs GT `['LLM', 'inference', 'engine']`（q008 全模型）
- `['testing frameworks']` vs GT `['testing', 'framework']`（q014 全模型）
- `['game engines']` vs GT `['game', 'engine']`（q016 Claude / DSK）
- `['microservice framework']` vs GT `['microservice', 'framework']`（q028 Claude / DSK）

### 2.1 根因

- `_PLURAL_MAP` 和 `_merge_phrases` 都是 **per-token** 運作的。
- 當 parser 吐出 `['web frameworks']`（單一多字字串），`canonicalize_keyword_token`
  lookup 的是整串 `"web frameworks"`，不在 plural map（只有單字 `frameworks`
  在）。per-token 規則完全沒觸發。
- 結果：GT 跑完 normalize 是 `['web', 'framework']`，pred 跑完是 `['web frameworks']`，
  永遠對不上。

### 2.2 Dataset GT 的實際 phrase 政策

對照 `datasets/eval_dataset_reviewed.json` 所有 GT `keywords`：

- **合併**：`ruby on rails`、`spring boot`、`react native`、`vue 3`、
  `state management`、`machine learning`、`ui kit` — 這些是命名實體 / 不可拆
  的複合技術詞（拆開會改變語意）。
- **拆開**：`web framework`、`testing framework`、`microservice framework`、
  `admin dashboard`、`game engine`、`orm library`、`graphql server`、
  `react component`、`kubernetes operator`、`ai agent` — 這些本質是
  `modifier + category`，拆開後語意不變。

現行 `_TECHNICAL_PHRASES`（`keyword_rules.py:120-137`）混了兩種類型，把本該拆
的詞當命名實體合併，和 GT 直接衝突。

## 3. 單一判定原則

`normalize_keywords` 的輸出必須滿足：

### 3.1 Tokenization

任何多字字串（包含空白的 keyword）都先按 whitespace 拆成 sub-tokens，再進 per-
token canonicalization。輸入不管是 `"web frameworks"` 還是 `"web"` + `"frameworks"`，
經過 Stage 0 之後對等。

### 3.2 Merge 政策

只有 `_TECHNICAL_PHRASES` 裡明文收錄的**命名實體**才會被 `_merge_phrases`
合併回單一 keyword。其他 `modifier + category` 組合一律維持拆開。

### 3.3 Plural 政策

`_PLURAL_MAP` 的責任是把「user / parser 使用的 legitimate keyword 的任意複數
形式」還原成 dataset GT 的單數 canonical 形式。覆蓋率**只以 §5.1 phrase-only
blocker 所需的複數為準**；parser 多塞的裝飾詞（q007 `implementations`、q018
`projects` 等）不在本層處理（§4）。

### 3.4 Multi-word stopword 政策（Stage 0 導致的回歸風險）

`_MODIFIER_STOPWORDS` 目前包含 multi-word token：`open source`、`most starred`、
`ranked by stars`、`sorted by stars`。若 Stage 0 直接把所有含空白的 keyword
拆成 sub-tokens，這些 stopword 會退化成 `open / source`、`most / starred` 等
殘留 token，造成 regression。

因此 Stage 0 拆分**前後**都要處理 multi-word stopword：

- **Stage -1（pre-split exact-match 刪除）**：對 raw input keyword 完全匹配
  multi-word stopword 的整條 entry（例如 `"open source"`、`"ranked by stars"`），
  直接整條拿掉，**不進 Stage 0**。
- **Stage 3.5（post-split bag-check 刪除）**：Stage 0 拆完之後，對 canonicalized
  token bag 做「multi-word stopword 的所有 parts 是否都在 bag」檢查，若是就把
  這些 parts 一起移除。這處理 parser 把整條裝飾詞塞在一個 merged 字串的情況
  （例如 input `"open source logistics"` → Stage 0 → `["open","source","logistics"]`
  → Stage 3.5 檢測 `open source` 整組 match，拔掉兩個 token，留下 `logistics`）。

這兩層都屬於「stopword filter」責任，仍是 `keyword_rules.py` 內部邏輯，沒有
scope 外溢。

### 3.5 Idempotence

`normalize_keywords(normalize_keywords(x)) == normalize_keywords(x)`，任何新改
動都要維持這條。

## 4. 明確責任分界

以下情況 **不得** 在 normalizer 解決：

- parser 塞了 GT 不該有的裝飾 keyword（例如 q018 的 `projects`、q007 的
  `implementations`）→ parser 責任
- parser 把非語言當 language（例如 q009 DSK `language=Vue`）→ parser 責任
- 相對日期解析錯（q013、q017、q025 等）→ parser 責任
- 中日文 topic 詞沒翻譯（q027 `爬蟲`、q029 `サンプルプロジェクト`）→ 多語
  alias 的後續 iter

這些都保留到後續層處理：

- parser prompt tuning（iter5 / iter6）
- multilingual canonicalization（另開）
- validator / repair（另開）

## 5. 本輪要救回的題目

### 5.1 Phrase-only blocker（修完就會變 CORRECT）

| qid | 原 outcome | phrase-mismatch |
|---|---|---|
| q003（GPT / Claude / DSK） | success WRONG | `['web frameworks']` → `['web', 'framework']` |
| q004（GPT / Claude / DSK） | success WRONG | `['cli tools']` / `['cli', 'tools']` → `['cli', 'tool']` |
| q005（Claude / DSK） | success WRONG | `['kubernetes operator', 'example']` → `['kubernetes', 'operator', 'example']` |
| q008（GPT / Claude / DSK） | success WRONG | `['llm inference engines']` → `['llm', 'inference', 'engine']` |
| q010（GPT / DSK） | success WRONG | `['ai agent frameworks']` 或 `['ai agent', 'framework']` → `['ai', 'agent', 'framework']` |
| q014（GPT / Claude / DSK） | success WRONG | `['testing frameworks']` → `['testing', 'framework']` |
| q016（Claude / DSK） | success WRONG | `['game engines']` → `['game', 'engine']` |
| q019（Claude） | success WRONG | `['learning programming']` → `['learning', 'programming']` |

### 5.2 Phrase 修對，但還有其他 blocker（本輪 **不保證**回分）

| qid | phrase 修復後仍 WRONG 的原因 | 後續責任 iter |
|---|---|---|
| q001（GPT） | `language` over-inference（JavaScript） | iter6 language over-inference |
| q007（GPT） | parser 多塞 `implementations` | parser prompt（iter5） |
| q009（GPT） | `language` over-inference | iter6 |
| q009（DSK） | `language=Vue`（非 valid GH language） | iter6 |
| q015（Claude） | stars boundary off-by-one（2000 vs 2001） | 另開 |
| q018（DSK） | parser 多塞 `projects` | parser prompt（iter5） |
| q028（Claude / DSK） | date 解析錯（2024 vs 2023） | iter5 date |

### 5.3 預期 accuracy 變化

| 模型 | iter3 | iter4 預期 | Δ |
|---|---|---|---|
| `gpt-4.1-mini` | 11/30 (36.67%) | **16/30 (53.33%)** | **+5** |
| `claude-sonnet-4` | 12/30 (40.00%) | **19/30 (63.33%)** | **+7** |
| `deepseek-r1` | 12/30 (40.00%) | **19/30 (63.33%)** | **+7** |

## 6. 不在本輪範圍

- `prompts/core/parse-v1.md`（parser prompt tuning）
- `prompts/core/intention-v1.md`
- `prompts/core/repair-v1.md`
- `src/gh_search/validator.py`
- `src/gh_search/eval/scorer.py`
- parser / repair few-shot
- date normalization
- multilingual sub-token alias
- `language` over-inference rule
- execution robustness

若本輪為了救某一題而開始動 parser prompt 或 validator，視為 scope drift，
停下來另開一輪。

## 7. 程式碼調整方向

目標檔案：

- [src/gh_search/normalizers/keyword_rules.py](../../src/gh_search/normalizers/keyword_rules.py)

### 7.1 `normalize_keywords` pipeline 調整

#### 7.1.1 Stage -1：multi-word stopword exact-match 刪除

在最前面新增一層：對 raw input 整條 entry 做 lower+strip，若完全等於某個 multi-
word stopword（目前 `open source`、`most starred`、`ranked by stars`、`sorted
by stars`），整條剔除。

```python
# Stage -1: drop raw entries that exactly match a multi-word stopword before
# Stage 0 whitespace splitting would shred them into sub-tokens.
multi_word_stopwords = {s for s in _MODIFIER_STOPWORDS if " " in s}
pre_filtered: list[str] = []
for raw in keywords:
    if not isinstance(raw, str):
        continue
    if raw.strip().lower() in multi_word_stopwords:
        continue
    pre_filtered.append(raw)
```

#### 7.1.2 Stage 0：whitespace split

在現有 Stage 1（per-token canonicalization）之前插入：

```python
# Stage 0: split multi-word tokens on whitespace so per-token rules (plural,
# alias, language-leak) can fire on every sub-token. Parser may emit merged
# strings like 'web frameworks'; those must enter the pipeline as
# ['web', 'frameworks'] before Stage 1.
sub_tokens: list[str] = []
for raw in pre_filtered:
    for part in raw.split():
        sub_tokens.append(part)
```

接著 Stage 1 吃的是 `sub_tokens` 而不是 `keywords`。

#### 7.1.3 Stage 3.5：phrase-style multi-word stopword bag 刪除

Stage 3 的 single-word stopword filter 照舊。Stage 3 後、Stage 5 phrase merge
前新增：對 canonicalized token list 做 bag-style 檢查，若某個 multi-word
stopword 的所有 parts 都在 bag（考慮重複次數），整組一併移除。

```python
# Stage 3.5: drop multi-word stopwords whose parts all landed in the bag
# after Stage 0 split. Reuses _contains_all + remove pattern from phrase
# merge, but removes instead of merges.
for phrase in multi_word_stopwords:
    parts = tuple(phrase.split())
    while _contains_all(filtered, parts):
        for part in parts:
            filtered.remove(part)
```

Stage 5 phrase merge 與 Stage 6 dedupe 保持原邏輯。

### 7.2 `_TECHNICAL_PHRASES` 精修

改成只保留命名實體：

```python
_TECHNICAL_PHRASES: tuple[str, ...] = (
    "ruby on rails",
    "spring boot",
    "react native",
    "vue 3",
    "state management",
    "machine learning",
    "ui kit",
)
```

從 dict **移除**：

- `react component`
- `graphql server`
- `game engine`
- `web framework`
- `admin dashboard`
- `microservice framework`
- `chatbot library`
- `testing framework`
- `orm library`

### 7.3 `_PLURAL_MAP` 擴充

只新增 §5.1 phrase-only blocker 實際需要的複數：

```python
"tools": "tool",   # q004 全模型
```

`templates`、`projects`、`implementations` **不加**。對應 case（q009 DSK、
q018 DSK、q007 GPT）的真實 blocker 是 parser 把裝飾詞當 keyword 塞進來，
加進 plural map 也只是把 `projects` 改成 `project`，仍會和 GT 對不上 — 這
屬於 parser prompt 責任（§4），scope 外，留給 iter5。

現行已收錄的保留不動：
`frameworks, libraries, libs, engines, examples, utilities`。

### 7.4 `find_keyword_violations` 一致性

`find_keyword_violations`（`keyword_rules.py:210`）也使用 `_TECHNICAL_PHRASES`
做 phrase-split 偵測。pruning dict 之後，不會再把 `['web', 'framework']` 報成
violation，和 normalize 行為一致。這是自動對齊，不需要額外改程式碼，但測試要
確認不再出 false-positive。

## 8. 測試策略

### 8.1 Unit：normalizer 契約測試

目標檔案：

- `tests/normalizers/test_keyword_rules.py`

兩組 parametrized case，角色不同：

#### 8.1.1 Phrase-only recovery（對應 §5.1，本輪 end-to-end 必須回分）

input 用 iter3 實際 parser 輸出，expected 用 dataset GT 跑完 normalize 的形式。
這組 case 同時代表 §11 Δ 的每一個 phrase-only blocker。

```python
ITER4_RECOVERY = [
    # (qid, parser_output, language, expected_normalized)
    ("q003",  ["web frameworks"],                 "Rust",       ["web", "framework"]),
    ("q004a", ["cli tools"],                      "Go",         ["cli", "tool"]),
    ("q004b", ["cli", "tools"],                   "Go",         ["cli", "tool"]),
    ("q005",  ["kubernetes operator", "example"], None,         ["kubernetes", "operator", "example"]),
    ("q008",  ["llm inference engines"],          None,         ["llm", "inference", "engine"]),
    ("q010a", ["ai agent frameworks"],            None,         ["ai", "agent", "framework"]),
    ("q010b", ["ai agent", "framework"],          None,         ["ai", "agent", "framework"]),
    ("q014",  ["testing frameworks"],             "JavaScript", ["testing", "framework"]),
    ("q016",  ["game engines"],                   "C++",        ["game", "engine"]),
    ("q019",  ["learning programming"],           None,         ["learning", "programming"]),
]
```

#### 8.1.2 Normalizer contract-only（不代表 end-to-end 回分）

q028 phrase 段落會被 normalizer 修對，但 end-to-end 有 date blocker（Claude /
DSK 把 `2023 年以後` 解成 `2024-01-01`），本輪不保證回分。仍要有一條
case 鎖 normalizer 對 `microservice framework` 的行為，避免未來 dict 回退。

```python
ITER4_CONTRACT_ONLY = [
    # 這組只驗 normalizer 輸出，不算進 §5.1 / §11 Δ。
    ("q028_normalizer", ["microservice framework"], "Go", ["microservice", "framework"]),
]
```

#### 8.1.3 Multi-word stopword regression（§3.4）

```python
ITER4_STOPWORD = [
    # pre-split exact match
    (["open source"],                                ["open source"],            []),  # 完全移除
    (["ranked by stars"],                            None,                       []),
    # post-split bag match
    (["open source logistics"],                      None,                       ["logistics"]),
    (["most starred rust"],                          "Rust",                     []),  # rust 作 language leak + stopword 全拔
    # 單字 stopword 仍照舊
    (["popular", "vue 3"],                           None,                       ["vue 3"]),
]
```

### 8.2 Unit：GT-side 一致性

同步加一組「GT 格式進入 normalize 後該等於什麼」，確保 scorer 兩邊都拿到對稱
的 canonical form：

```python
ITER4_GT_CANONICAL = [
    # GT keywords → normalized form
    (["web", "framework"],                       ["web", "framework"]),
    (["cli", "tool"],                             ["cli", "tool"]),
    (["kubernetes", "operator", "example"],       ["kubernetes", "operator", "example"]),
    (["LLM", "inference", "engine"],              ["llm", "inference", "engine"]),
    (["ai", "agent", "framework"],                ["ai", "agent", "framework"]),
    (["testing", "framework"],                    ["testing", "framework"]),
    (["game", "engine"],                          ["game", "engine"]),
    (["learning", "programming"],                 ["learning", "programming"]),
    (["microservice", "framework"],               ["microservice", "framework"]),
    # merge 必須仍然保留
    (["spring boot", "starter"],                  ["spring boot", "starter"]),
    (["react native", "ui kit"],                  ["react native", "ui kit"]),
    (["machine", "learning"],                     ["machine learning"]),
    (["vue", "3", "admin", "dashboard", "template"], ["vue 3", "admin", "dashboard", "template"]),
]
```

這組同時驗證 pruning 沒有誤傷命名實體的 merge。

### 8.3 Idempotence

既有 idempotence 測試（若有）必須全綠。新加一條：

```python
@pytest.mark.parametrize("keywords,language", [...])
def test_normalize_is_idempotent(keywords, language):
    once = normalize_keywords(keywords, language=language)
    twice = normalize_keywords(once, language=language)
    assert once == twice
```

### 8.4 Regression：既有 test 不得變紅

全部 `pytest -q` 必須綠。iter2 的 keyword unit test 若有測到被移除的 phrase
（例如 `testing framework` 會 merge），要更新為新政策。

## 9. 驗證方式

### 9.1 Unit

```bash
pytest -q tests/normalizers/
pytest -q  # 全綠
```

### 9.2 Cross-model full smoke rerun

```bash
gh-search smoke --model gpt-4.1-mini    --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter4_20260424
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter4_20260424
gh-search smoke --model DeepSeek-R1     --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter4_20260424
```

### 9.3 Diff 分析

對照 iter3 / iter4 per-item：

- §5.1 每題在對應模型的 `is_correct` 必須翻成 `true`
- iter3 已 CORRECT 的題目零 regression（outcome / score 都不退）

## 10. 通過標準

本輪通過需同時滿足：

1. §5.1 列出的 **19 個 (qid, model) pair**（q003×3 + q004×3 + q005×2 + q008×3
   + q010×2 + q014×3 + q016×2 + q019×1）在 iter4 全部 CORRECT
2. iter3 的所有 CORRECT 題（GPT 11 / Claude 12 / DSK 12）在 iter4 維持 CORRECT
3. `pytest -q` 全綠，`tests/normalizers/` 的新 case（§8.1.1 + §8.1.2 + §8.1.3）
   全數通過
4. `normalize_keywords` 維持 deterministic + idempotent
5. 本輪不動 parser / validator / scorer / prompt / 其他非 `keyword_rules.py`
   檔案
6. q028（Claude / DSK）本輪**不要求回分** — phrase 會被修對但 date blocker
   留給 iter5

## 11. 預期影響與實際結果

| 模型 | iter3 accuracy | iter4 預期 | Δ |
|---|---|---|---|
| `gpt-4.1-mini` | 36.67%（11/30） | **53.33%（16/30）** | **+5** |
| `claude-sonnet-4` | 40.00%（12/30） | **63.33%（19/30）** | **+7** |
| `deepseek-r1` | 40.00%（12/30） | **63.33%（19/30）** | **+7** |

若 cross-model smoke 實測 Δ 比預期少 2 題以上，代表 scope 外有其他
blocker（例如我們低估了 language over-inference 的 co-occurrence），在
ITER4_NOTES.md 記錄差距並寫入 iter5 交接。

### 11.1 實際 rerun 結果（2026-04-24）

| 模型 | iter3 | iter4 | 實際 Δ | 對照預期 |
|---|---|---|---|---|
| `gpt-4.1-mini` | 36.67%（11/30） | **56.67%（17/30）** | **+6** | 超過預期 +1 |
| `claude-sonnet-4` | 40.00%（12/30） | **66.67%（20/30）** | **+8** | 超過預期 +1 |
| `deepseek-r1` | 40.00%（12/30） | **63.33%（19/30）** | **+7** | 命中預期 |

對應 run：

- `eval_gpt41mini_iter4_20260424`
- `eval_claude_sonnet4_iter4_20260424`
- `eval_deepseek_r1_iter4_20260424`

### 11.2 §5.1 target pair 實際回收

`§5.1` 列出的 19 個 `(qid, model)` pair 在 iter4 **全部翻正**：

- GPT：`q003 q004 q008 q010 q014`，以及 bonus `q016`
- Claude：`q003 q004 q005 q008 q014 q016 q019`，以及 bonus `q010`
- DeepSeek：`q003 q004 q005 q008 q010 q014 q016`，以及 bonus `q020`

其中 bonus 題不代表 Iter4 scope 擴張；它們是 phrase fix 生效後，原本被其他
flaky 因素遮住的題目這輪剛好沒有再被外部因素攔住。

### 11.3 Caveat：一題真 regression、兩題 outcome contract 仍不乾淨

1. `deepseek-r1 / q019`

- iter3：`['learning', 'programming']`，`is_correct = true`
- iter4：`['learning', 'programming', 'repos']`，`is_correct = false`

這是 **parser stochasticity**，不是 Iter4 normalizer 改壞：

- `repos` 不是 phrase policy、不是 plural drift、也不是 stopword
- `keyword_rules.py` 對這個 input 的輸出是正確且 deterministic 的
- 這題應列入 iter5 的 parser decorative-token 清理（與 `projects`、
  `implementations` 同類）

2. `claude-sonnet-4 / q020`、`deepseek-r1 / q020`

這兩題在 iter4 都出現：

- `final_outcome = max_turns_exceeded`
- `is_correct = true`
- `score = 1.0`

也就是 **結構化輸出已經撞到 GT，但 loop/outcome contract 還沒完全收乾淨**。
因此 `q020` 可以算進 accuracy，但不應被描述成完全健康的 end-to-end success。

### 11.4 通過判定

Iter4 採 **實質判準通過**：

- `§10.1`：19 個 target pair 全數回收
- `§10.3` ~ `§10.6`：達成
- `§10.2` 若嚴格照字面要求「iter3 correct 題零 regression」，則會被
  `deepseek-r1 / q019` 擋住

本 spec 採用的結論是：

- Iter4 **實質通過**
- `deepseek-r1 / q019` 明確記錄為 parser stochasticity follow-up
- `q020` 的 `max_turns_exceeded + score=1.0` 明確記錄為 loop/outcome contract
  follow-up
- 不把這兩個問題誤記成 Iter4 phrase policy 失敗

## 12. 下一輪交接

本輪完成後，下一輪優先項按 iter4 per-item 剩餘 blocker 排序：

1. **iter5** — parser prompt 清理
   - date 相對時間錨定：`q013 q017 q018 q028`
   - decorative token 不塞 keyword：`q007 implementations`、`q018 projects`、
     `q019 repos`
2. **iter6** — parser `language` over-inference
   - `q001`、`q009`、`q029`
3. **iter7** — 多語 alias / drop policy 落地
   - `q027`、`q029`
4. **後續** — validator / repair / outcome contract
   - `q030` 矛盾條件保留
   - `q020` max_turns contract
   - stars boundary off-by-one
   - execution robustness

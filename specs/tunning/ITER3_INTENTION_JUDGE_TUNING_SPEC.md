# Iteration 3 Intention Judge Tuning Spec

## 1. 目標

本輪 tuning 只處理 `intention_judge` 的 reject 門檻，將其收斂成 **dataset-aligned permissive gate**。

這一層的責任是：

- 判斷 query 是否屬於 GitHub repository search domain
- 判斷 query 是否至少包含一個可解析 signal
- 決定是否進入 `parse_query`

這一層 **不負責**：

- semantic contradiction 判斷
- parser output policy
- keyword normalization
- validator failure recovery

若 query 屬於 GitHub repo search，且至少含有一個可解析 signal，應判為 `supported`，交由後續 `parse_query -> validate_query` 處理。

## 2. 背景

Iter2 之後，`keywords` 相關 tuning 已明顯提升三模型分數，但 `intention_judge` 仍持續把 dataset GT 明確標為可 parse 的題目提前拒絕，直接造成 0 分。

目前已確認與 dataset GT 衝突的題目：

- `q004`
- `q009`
- `q019`
- `q020`
- `q021`
- `q022`
- `q030`

其中 `q030` 的 dataset note 已明確指定：

> 保留原始衝突條件，依規則不自動修正，交由 validator 或 failure analysis 處理。

這代表 dataset 的責任分工是：

- `intention_judge`：判斷是否屬於 repo search domain
- `parser`：保留可抽取的 signal
- `validator`：處理矛盾 / 無效結構

因此，本輪不採 product-style conservative gate，而採 **eval dataset 對齊** 的 permissive gate。

## 3. 單一判定原則

`intention_judge` 的判定原則統一為：

### 3.1 Supported

當 query 符合以下兩條件時，判為 `supported`：

1. 明確屬於 GitHub repository search
2. 至少能抽出任一可解析 signal

可解析 signal 包含：

- `keywords`
- `language`
- `min_stars`
- `max_stars`
- `created_after`
- `created_before`
- `sort`
- `order`
- `limit`

### 3.2 Ambiguous

僅在下列情況判為 `ambiguous`：

- 查的是 GitHub repo，但完全抽不出任何 signal
- 使用者要求本身過於空白，連空 `keywords` + 其他欄位都無法成立

例如：

- `find good repos`
- `help me search github`

### 3.3 Unsupported

僅在下列情況判為 `unsupported`：

- 不是 GitHub repository search
- 查的是其他物件而非 repository metadata

例如：

- issues
- pull requests
- users
- code snippets
- tweet / post / blog content
- bug filing / repo 外工作流操作

## 4. 明確責任分界

以下情況 **不得** 在 `intention_judge` 提前拒絕：

- `min_stars > max_stars`
- `created_after > created_before`
- query 條件彼此矛盾
- query 很模糊但仍有可解析 signal
- query 只有排序意圖、沒有 keyword
- query 只有 language、沒有 keyword

這些都應保留到後續層處理：

- parser
- validator
- failure analysis

## 5. 本輪要救回的題目

本輪 success set 直接對齊 dataset GT。

### 5.1 必須從 reject 轉為 supported

- `q004` any good golang cli tools out there?
- `q009` recommend some vue 3 admin dashboard templates
- `q019` good repos for learning programming
- `q020` popular stuff on github
- `q021` show me some cool swift repos not too old but not too new
- `q022` I want repos about apple
- `q030` star 超過 500 但少於 100 rust

### 5.2 各題 signal 解讀

- `q004`: `language=Go`, `keywords=['cli', 'tool']`
- `q009`: `keywords=['vue 3', 'admin', 'dashboard', 'template']`
- `q019`: `keywords=['learning', 'programming']`
- `q020`: `sort=stars`, `order=desc`, `keywords=[]`
- `q021`: `language=Swift`, `keywords=[]`
- `q022`: `keywords=['apple']`
- `q030`: `language=Rust`, `min_stars=501`, `max_stars=99`, `keywords=[]`

## 6. 不在本輪範圍

本輪只動 `intention_judge`。以下全部排除：

- parser prompt
- parser few-shot
- keyword rules
- multilingual alias
- date normalization
- scorer policy
- validator rule
- execution robustness

若本輪為了救 gate 而開始改 parser / validator，會造成 scope drift。

## 7. Prompt 調整方向

目標檔案：

- [prompts/core/intention-v1.md](../../prompts/core/intention-v1.md)

### 7.1 核心 wording 調整

目前 prompt 中這句需要移除或改寫：

- `too vague to constrain safely`

因為這會把 dataset 內有效題誤殺。

應改成：

- 只要屬於 GitHub repo search，且有任一可解析 signal，就判為 `supported`
- semantic contradictions 不在本層處理
- 排序意圖、language-only、topic-only 都可構成 supported

### 7.2 Few-shot 規劃

新增 `supported` few-shot：

- `q004` 類：language + topic phrase
- `q009` 類：framework phrase + dashboard/template topic
- `q020` 類：只有 popularity intent，無 keywords
- `q022` 類：只有單一 topic keyword
- `q030` 類：保留矛盾 stars 條件，仍判 supported

新增 `unsupported` few-shot：

- help me file a bug
- show me PRs in repo X
- find users named alice
- show me trending PRs this week
- find the user who maintains react

## 8. 測試策略

### 8.1 Unit / Tool-level

目標檔案：

- `tests/test_tool_intention_judge.py`

新增或更新測試，固定以下判定：

- `q004` -> `supported`
- `q009` -> `supported`
- `q019` -> `supported`
- `q020` -> `supported`
- `q021` -> `supported`
- `q022` -> `supported`
- `q030` -> `supported`

negative case：

- 非 repo search query -> `unsupported`

### 8.2 Integration-level

不可只靠 stub LLM 的 unit test。

至少補 2 題真 LLM integration 驗證，確認 prompt 改動後：

- judge 不再提前終止
- control 會繼續流向 `parse_query`

建議最小集合：

- `q020`
- `q030`

### 8.3 Negative Set

需固定一組 off-domain negative case，避免 gate 放寬後誤放行：

- `show me PRs in repo X`
- `find users named alice`
- `give me code snippets for redis retry logic`

## 9. 驗證方式

### 9.1 快速驗證

先用 `gpt-4.1-mini` 跑最小集合，確認 7 題不再 reject。

### 9.2 Cross-model falsification

至少驗證：

- `gpt-4.1-mini`
- `claude-sonnet-4`

這 7 題都不再被 `intention_judge` 提前拒絕。

但需明確區分：

- `gate opened`
- `score actually recovered`

### 9.3 Full eval rerun

最小 rerun 指令：

```bash
gh-search smoke --model gpt-4.1-mini --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_gpt41mini_iter3_20260424
gh-search smoke --model claude-sonnet-4 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_claude_sonnet4_iter3_20260424
gh-search smoke --model DeepSeek-R1 --dataset datasets/eval_dataset_reviewed.json --eval-run-id eval_deepseek_r1_iter3_20260424
```

## 10. 通過標準

本輪通過需同時滿足：

1. `q004 q009 q019 q020 q021 q022 q030` 在 `gpt-4.1-mini` 與 `claude-sonnet-4` 上皆不再 `rejected`
2. `q020` 與 `q030` 本輪只要求 gate 打開，不要求在本輪回分
3. `intention_judge` 的拒絕僅保留真正 off-domain case
4. `§8.3` 的 negative set 仍維持 `unsupported`
5. 本輪不改動 parser / validator / scorer

## 11. 預期影響

這輪若成功，會先回收一批目前被 gate 提前歸零的題目，但需區分：

### 11.1 本輪直接受益（gate 打開後即可望回分）

- GPT：`q004 q009 q019 q021 q022`
- Claude：`q004 q009 q019 q021`
- DeepSeek：`q019`

### 11.2 本輪只打開 gate，需後續 validator / repair tuning 才可能回分

- GPT：`q020 q030`
- Claude：`q020 q030`
- DeepSeek：`q020 q030`

原因：

- `q020` 目前會被 `validator` 的 `no_effective_condition` 擋下，再進 `repair_query`
- `q030` 目前會被 `validator` 的 `min_gt_max_stars` 擋下，再進 `repair_query`

因此 Iter3 是高槓桿、低耦合的 gate iteration，但不應誇大為本輪即可完整回收 7 題分數。

## 12. 實際結果（2026-04-24）

### 12.1 分數變化

| model | iter2 | iter3 | delta |
|---|---:|---:|---:|
| `gpt-4.1-mini` | `10/30 = 33.33%` | `11/30 = 36.67%` | `+1` |
| `claude-sonnet-4` | `11/30 = 36.67%` | `12/30 = 40.00%` | `+1` |
| `deepseek-r1` | `9/30 = 30.00%` | `12/30 = 40.00%` | `+3` |

### 12.2 Outcome 變化

本輪最大變化不是單題 parser 修正，而是 gate 不再提前拒絕。

- iter2 `rejected`
  - GPT: `7`
  - Claude: `6`
  - DeepSeek: `3`
- iter3 `rejected`
  - GPT: `0`
  - Claude: `0`
  - DeepSeek: `0`

同時，原本被 gate 擋住的下游問題開始浮現：

- GPT iter3: `execution_failed=3`, `max_turns_exceeded=1`
- Claude iter3: `execution_failed=2`, `max_turns_exceeded=2`
- DeepSeek iter3: `execution_failed=1`, `max_turns_exceeded=2`

這些不是本輪 scope drift，而是 gate 放寬後暴露出的 downstream bottlenecks。

### 12.3 7 題 gate 驗證結果

| qid | GPT | Claude | DeepSeek | gate opened |
|---|---|---|---|---|
| `q004` | `success / wrong` | `success / wrong` | `success / wrong` | `yes` |
| `q009` | `success / wrong` | `execution_failed` | `success / wrong` | `yes` |
| `q019` | `success / correct` | `success / wrong` | `success / correct` | `yes` |
| `q020` | `success / wrong` | `max_turns_exceeded / correct` | `max_turns_exceeded / wrong` | `yes` |
| `q021` | `success / wrong` | `success / wrong` | `success / correct` | `yes` |
| `q022` | `success / correct` | `success / correct` | `success / correct` | `yes` |
| `q030` | `max_turns_exceeded / wrong` | `max_turns_exceeded / wrong` | `max_turns_exceeded / wrong` | `yes` |

結論：

- `§10.1` 達成：7 題在三模型皆不再走 `rejected`
- `§10.2` 判讀正確：`q020` / `q030` 的主要效果是打開 gate，不是本輪穩定回分

### 12.4 實際回分 vs 原預期

#### 實際回分

- GPT：`q019`, `q022`
- Claude：`q020`, `q022`
- DeepSeek：`q019`, `q021`, `q022`

#### 實際沒有回分，但 gate 已打開

- `q004`
- `q009`
- `q021`（GPT / Claude）
- `q020`（GPT / DeepSeek）
- `q030`

這代表 gate 已不再是主瓶頸，新的主瓶頸已經轉移到 parser / validator / repair。

### 12.5 已知 follow-up

1. `q020`
   - Claude 出現 `final_outcome = max_turns_exceeded`
   - 但 `is_correct = True`、`score = 1.0`
   - 這代表 loop / outcome contract 有不一致，需後續單獨處理
2. `q030`
   - 三模型都不再 reject
   - 但都在 validator / repair 路徑上失分，符合本 spec 先前預期
3. `q004`, `q009`, `q021`
   - gate 已打開
   - parser 結構仍和 GT 對不上
   - 這是下一輪 tuning 的主戰場

### 12.6 通過判定

| 條款 | 結果 |
|---|---|
| `§10.1` 7 題不再 rejected | `pass` |
| `§10.2` `q020/q030` 本輪只要求 gate 打開 | `pass` |
| `§10.3` gate 已收斂成 permissive repo-domain filter | `pass` |
| `§10.4` negative set 維持 unsupported | `pass`（unit 層已鎖） |
| `§10.5` 不改 parser / validator / scorer | `pass` |

因此，**Iter3 通過**。

## 13. 下一輪交接

本輪完成後，下一優先應回到：

1. parser 的 phrase / language tuning
2. validator / repair 對 `q020` / `q030` 的 downstream contract
3. date / temporal parsing
4. multilingual canonicalization
5. execution robustness

也就是：

- Iter3 只處理 gate
- parser / validator / date 留到後續 iteration

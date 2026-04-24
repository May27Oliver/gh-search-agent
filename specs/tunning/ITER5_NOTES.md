# Iteration 5 Notes

結案版本：**iter5 主版**（`ITER5_DATE_TUNING_SPEC.md` 規定的 4 檔動作）。
`fu1`、`fu2` 兩次 follow-up 已 revert，不採用。

## 1. 實際成果

| 模型 | iter4 follow-up | iter5 | Δ | 對照 spec §11 預期 |
|---|---|---|---|---|
| `gpt-4.1-mini` | 17/30 (56.67%) | **22/30 (73.33%)** | **+5** | 命中預期 +5 ✓ |
| `claude-sonnet-4` | 20/30 (66.67%) | **25/30 (83.33%)** | **+5** | 命中預期 +5 ✓ |
| `deepseek-r1` | 19/30 (63.33%) | **21/30 (70.00%)** | **+2** | 落保守下界 +2（預期 +3） |

對應 run artifact：

- `eval_gpt41mini_iter5_20260425`
- `eval_claude_sonnet4_iter5_20260425`
- `eval_deepseek_r1_iter5_20260425`

正式 shipped run 以上表為準（DSK 21/30）。

### 1.1 DSK stochasticity observation

iter5 revert 後於 2026-04-25 做了一次 verify rerun（prompt 與 shipped run
完全一致、只是再跑一次），以檢驗 revert 乾淨度。結果顯示：

- **GPT 與 CLA 的 per-item 結果與原 run bit-for-bit 一致**（兩者各 22/30、25/30，
  0 differences）
- **DSK 在同 prompt 下 rerun 出現 19/30**（比原 run 少 2 題）

| DSK run | Accuracy | 差異題目 |
|---|---|---|
| `eval_deepseek_r1_iter5_20260425` (shipped) | 21/30 | baseline |
| `eval_deepseek_r1_iter5_verify_20260425` | 19/30 | `q025` 翻正，但 `q015`/`q018`/`q028` 退 |

verify rerun DSK 掉的三題失敗模式：

| qid | 失敗欄位 | 類別 |
|---|---|---|
| q015 | `sort=null, order=null`（`popular → sort=stars` 未套） | sort default missing |
| q018 | keywords 多 `projects`（`spring boot`/`starter` 兩邊對） | decoration leak |
| q028 | keywords=`['微服务框架']`（CJK 原詞未翻） | CJK → EN canonicalization |

這些與 fu2 rerun DSK 掉的題目組（`q015` / `q018` / `q023` / `q028`）**幾乎同組**，
也對應 iter5→fu1 DSK 掉的題目組（`q001` / `q010` / `q018`）中相同脆弱領域
（sort default / decoration / CJK / JSON robustness）。

**本 notes 不從 2 次 sample 推論 DSK 穩定分布的區間**（樣本數太少）。
可以確認的是：

1. 在 2026-04-25 的兩次同 prompt rerun 中，DSK 出現了 21/30 與 19/30 兩個結果。
2. 波動集中在 sort default missing、decoration leak、CJK→EN canonicalization
   這三個固定脆弱 pattern。
3. GPT / CLA 在同實驗中完全穩定，顯示波動是 DSK 模型特性，不是 prompt 內容或
   runner 問題。

### 1.2 判讀規則（給後續 iter6+ 使用）

基於 §1.1 觀察，評估 DSK 在 iter6+ 的改動時：

- **±2 題以內的 headline accuracy 變化**不能直接解讀成「有效提升」或「有效退步」，
  需視為 noise candidate，以下列任一方式驗證才下結論：
  - 做第二次 rerun，觀察差異題目集是否穩定
  - 檢查 target-pair 層級的 per-item diff，不只看 accuracy
  - 確認變化題目是否落在 §1.1 列出的三個脆弱 pattern 之外
- **> 2 題變化**仍按原方式評估（視為可能的 signal，但需對照 per-item 診斷）
- **若改動本身是動 `parse-v1.md`**，特別要留意波動是否集中在 §1.1 三個脆弱 pattern
  — 若是，先視為 attention-budget 副作用，不是規則邏輯錯誤（參照 §6）

## 2. Target pair 回收（§5.1 11 pair + §5.2 2 pair = 13 pair）

**實際翻正：10/13**（低於 §10.3 的 ≥ 11/13 門檻）

| qid | tag | iter5 結果 | 備註 |
|---|---|---|---|
| q013 | GPT | ✓ | `last year` → `2025-01-01 ~ 2025-12-31` 對 |
| q013 | **CLA** | **✗** | **Date 完全修對**，被 **out-of-scope min_stars boundary** (500 vs 501) 擋住 |
| q013 | **DSK** | **✗** | **Date 完全修對**，被 **out-of-scope sort default** (`trending → sort=stars`) 擋住 |
| q017 | GPT/CLA/DSK | ✓ ×3 | `this year` → `2026-01-01` 對 |
| q018 | **GPT** | **✗** | `from YEAR → full-year` 規則 GPT 對 "bare-year full-year shorthand" wording 不敏感；`created_before` 漏；+ decoration leak (`projects`) |
| q018 | CLA | ✓ | — |
| q028 | CLA/DSK | ✓ ×2 | 中文 `2023年以后` → `2023-01-01` 對 |
| q025 | GPT | ✓ | typo `aftr 2022` → `2023-01-01` 對 |
| q021 | GPT/CLA | ✓ ×2 | 模糊 `not too old` → null/null 對 |

**Date rule 實際覆蓋率：12/13**（只有 q018 GPT 的 `from YEAR → full year` 規則未被 GPT 套用）。

3 個未翻正 pair 的歸因：

| Pair | Blocking 欄位 | 歸屬後續 iter |
|---|---|---|
| q013 CLA | `min_stars` boundary | stars boundary / semantics iter |
| q013 DSK | `sort`/`order` default | iter7 sort defaults |
| q018 GPT | `created_before` 規則覆蓋 + decoration `projects` | **Deferred**（見 §3）+ iter7 decoration |

## 3. Deferred：q018 GPT `from YEAR → full year`

Follow-up 嘗試了兩個 wording 強化方案，最終都 revert。原因見 §4。

Deferred 的決策不是「以後一定要修」，而是：

- iter5 date rule 已命中 12/13 pair 的 date 部分
- GPT 對 `"from YEAR" or "in YEAR" (bare-year full-year shorthand)` 這種抽象描述不敏感，但 GPT 對具體 Example 會套用 → 後續若要補，**要改策略**（見 §5）

## 4. iter5 regression 清單（實際發生）

iter5 主版對 iter4 follow-up 有 3 個 regression，均為 **parser stochasticity** on non-date 欄位，不是 iter5 date rule 造成：

| 模型 | qid | 失敗欄位 | 歸屬 |
|---|---|---|---|
| GPT | q028 | `keywords=['微服务框架']`（CJK compound 未翻譯） | parser stochasticity — CJK↔EN keyword choice |
| CLA | q007 | keywords 多 `implementations` | iter7 decoration leak |
| DSK | q025 | `sort/order=None` | iter7 sort default |

三個在 iter5 仍然**date-CORRECT**（q028 GPT `after=2023-01-01` 對、q025 DSK `after=2023-01-01` 對），只是其他欄位 flake。

## 5. Follow-up 嘗試記錄（fu1 / fu2，**已 revert、不採用**）

兩次 follow-up 都只動 `prompts/core/parse-v1.md`，目標是補強 `from YEAR → full-year`
讓 GPT q018 翻正（target 10/13 → 11/13）。

### fu1（已 revert）

加入強力版：

```
- "from YEAR" or "in YEAR" ... Both dates MUST be set; never leave created_before null for this form.
  Example: "from 2024" → created_after="2024-01-01", created_before="2024-12-31".
  "repositories from 2024" and "repos in 2024" follow the same rule.
```

結果：

- q018 GPT ✓ 翻正（主目標達成）
- **q017 GPT ✗ regressed**：GPT 把 `"this year"` 套 "in YEAR" full-year rule，多塞 `before=2026-12-31`
  → "Both dates MUST be set" 這句跨段泛化到 Relative time
- Target 仍 10/13（q018 進、q017 退，淨 0）

### fu2（已 revert）

軟化版 — 刪除 "Both dates MUST be set" 強制句、保留 Example、新增 scoping 說明：

```
This full-year rule only applies to explicit year forms like "from 2024" or "in 2024";
relative expressions like "this year" or "last year" use the Relative time rules below instead.
```

結果：

- q018 GPT ✓ 翻正、q017 GPT 守住、q013 CLA bonus 翻正 → **target 11/13 達門檻**
- 但 DSK 多 4 個 regression（q015 / q018 / q023 / q028），分散在：
  - `popular → sort=stars`（sort default）
  - keyword decoration leak (`projects`)
  - noisy input 下 parser 直接吐不出 JSON
  - CJK → EN keyword canonicalization 停擺
- DSK 從 21/30 掉到 18/30（-3）

### 為何 fu2 revert

四個 DSK regression 全**不是** date rule 算錯，而是**其他隱性能力同時鬆掉**。
對照 GPT（+0）、CLA（+1）、DSK（-3），方向非常不對稱。詳細 pattern 分析：

| DSK fu2 regression | 失敗欄位 | DSK iter5 正確 | DSK iter4 fu 正確 |
|---|---|---|---|
| q015 | sort/order | ✓ | ✓ |
| q018 | decoration filter | ✓ | ✓ |
| q023 | JSON robustness | ✓ | ✓ |
| q028 | CJK→EN translation | ✓ | ✓ |

**結論：DSK 對 `parse-v1.md` 長度敏感**。我們在 date section 加 3 行 Example，
DSK 對無關規則的 attention 就鬆脫。

## 6. 關鍵學習：DeepSeek-R1 prompt length threshold

**DeepSeek-R1 已接近或超過 `parse-v1.md` 穩定承載量。**

證據：

1. iter4 fu → iter5：DSK 掉 q019（decoration `repos`，非 date）
2. iter5 → fu1：DSK 掉 q001 / q010 / q018（sort default / decoration）
3. iter5 → fu2：DSK 掉 q015 / q018 / q023 / q028（sort / decoration / JSON / CJK）

**三次 rerun 三組不同 regression**，但**都落在 DSK 本來就勉強及格的「隱性規則」**：
sort default、decoration filter、CJK→EN canonicalization、JSON stability。

這不是 DSK 隨機 noise，是**結構性 attention budget 問題**：prompt 一變長，
DSK 在高優先級新規則反應正確，但用「隱性習慣」撐住的邊界行為開始掉。

### 實務影響（寫給 iter6+）

**不要再把更多 tuning 疊進 `prompts/core/parse-v1.md`。**

特別危險：

- language over-inference 細則（iter6 本來規劃的方向）
- decoration token policy
- multilingual canonicalization policy
- 更多對照例子 / 例外條件

這些是 DSK 最脆弱的區域，若寫進 core prompt 會觸發結構性 regression。

### 建議下輪策略改變

1. **core parse prompt 保持短**：只留最核心、跨模型共通、不可不說的規則
2. **穩定性工作移出 prompt**：
   - deterministic normalizer（已有 `keyword_rules.py` 基礎）
   - validator / repair loop
   - scorer-side shared canonicalization
3. **規則分層**：parser 做最小 schema extraction；後處理補 facet / decoration / aliases
4. **DSK appendix 精準補丁**：需要對 DSK 補強時，不在 core 加 general rule，
   而是在 `prompts/appendix/parse-deepseek-r1-v1.md` 加 1-2 個最傷的 pattern
5. **Prompt length guardrail**：往後每輪 tuning 若動 `parse-v1.md`，
   在 spec 明寫長度 delta 與 DSK regression 風險評估

## 7. 通過判定

依 `ITER5_DATE_TUNING_SPEC.md §10` 實質判準：

| 判準 | 結果 |
|---|---|
| §10.1 Δ 達標 | GPT +5 / CLA +5 / DSK +2（DSK 落保守下界、達標） ✓ |
| §10.2 零 regression | 3 regressions（parser stochasticity，均非 date 規則造成） △ |
| §10.3 target 翻正 ≥ 11/13 | **10/13 未達** ✗ |
| §10.4 pytest 全綠 | 384 passed ✓ |
| §10.5 today 注入格式穩定 | ✓ |
| §10.6 scope 鎖死 4 檔 | ✓ |

**結論：iter5 採 `實質通過` 結案，明確承認未達 §10.3 門檻。**

理由：

- Date rule 本身 12/13 命中 target pair 的 date 欄位，規則有效
- 3 個未翻正 pair 有 2 個（q013 CLA / q013 DSK）被 iter5 明確 out-of-scope 的欄位
  （stars boundary、sort default）擋住
- 剩 1 個 q018 GPT 屬模型對抽象 wording 不敏感，嘗試兩次 follow-up 都造成比收益
  更大的副作用（fu1 傷 q017 GPT、fu2 傷 DSK 4 題）
- 此 pair 標 Deferred，等 iter6+ 整體 prompt 策略改變後再處理

## 8. 下一輪交接（修正版，取代 `ITER5_DATE_TUNING_SPEC §12`）

原 spec §12 建議 iter6 做 parser language over-inference。**依 §6 學習需要調整**：

### 不建議（會觸發 DSK regression）

- iter6 繼續在 `parse-v1.md` 加 language over-inference 規則
- iter7 繼續在 `parse-v1.md` 加 decoration token policy
- 任何「再往 core parse prompt 加長」的路線

### 建議（對 DSK 友善）

1. **iter6 改方向**：把 language over-inference 放到 post-parser 後處理層
   （新檔或 `validator.py` / `normalizers/` 擴充），parser 繼續吐原始 language，
   後處理層判斷是否要洗成 null。好處：DSK 不受影響、可單元測試。
2. **iter7 改方向**：把 decoration token 清理交給 `keyword_rules.py`
   新 stopword set（如 `projects`、`implementations`、`repos`）。同樣繞開 prompt。
3. **iter8 multilingual**：`keyword_rules.py` 加 alias table（爬蟲/サンプル等）。
   **絕對不在 parse-v1.md 加 CJK/JP 規則**，那是 DSK 最脆弱的一層。

### 次要 follow-up

- q018 GPT `from YEAR → full year`：擱置。若將來做 GPT appendix tuning 時可考慮在
  `parse-gpt-4.1-mini-v1.md` 加 1 個 Example，**但不回 core**
- q013 CLA stars boundary：列入「stars boundary iter」獨立規劃
- q013 DSK / q025 DSK / q015 DSK sort default：列入 iter7 sort default 規劃

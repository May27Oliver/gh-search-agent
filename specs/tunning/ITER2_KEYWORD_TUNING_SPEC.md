# Keyword Tuning Spec

## 1. 目的

這份文件定義 `structured_query.keywords` 的 tuning 與 normalization 規則。

目標不是為單一題目補 mapping，而是建立 **可跨模型重用** 的 keyword policy，降低以下共同失敗：

- technical phrase 被拆開
- 單複數漂移造成 exact match 失分
- `language` / `sort intent` / 修飾詞誤進 `keywords`
- typo / multilingual query 無法映射到 canonical keyword

本 spec 適用於：

- `gpt-4.1-mini`
- `claude-sonnet-4`
- `deepseek-r1`

## 2. 設計原則

### 2.1 Model-Agnostic First

優先投資：

- keyword policy
- deterministic normalization
- shared dictionary

不要先做：

- 針對單一題目的 prompt patch
- 針對單一模型的 case-by-case mapping

### 2.2 Policy Over Case List

禁止把 prompt 寫成題目對照表，例如：

- `golang cli tools -> language=Go, keywords=['cli','tool']`
- `spring boot starter -> keywords=['spring boot','starter']`

允許的是抽象規則，例如：

- 程式語言名詞優先映射到 `language`
- 常見技術短語優先保留為單一 phrase keyword
- popularity intent 映射到 `sort=stars, order=desc`

### 2.3 Parser + Normalizer 分工

- parser 負責理解語意與輸出初稿
- normalizer 負責有限、可解釋、可測試的 deterministic 收斂

不要把所有 keyword 修復都塞進 prompt。

## 3. Keyword Policy

### 3.1 什麼應該進 keywords

`keywords` 只保留搜尋主題、技術概念、實體名詞、技術短語。

例：

- `machine learning`
- `spring boot`
- `react native`
- `state management`
- `chatbot`
- `crawler`

### 3.2 什麼不應該進 keywords

以下資訊應優先進其他欄位，而不是 `keywords`：

- 程式語言：`python`, `golang`, `rust`, `typescript`, `java`, `javascript`
- 排序意圖：`popular`, `top`, `best`, `trending`, `most starred`
- 數值限制：`500+`, `under 100 stars`, `more than 2k`
- 數量限制：`top 10`, `20 repos`
- 模糊修飾詞：`cool`, `good`, `small`

以下詞預設視為 keyword stopwords，不應保留在 `keywords`：

- `popular`
- `top`
- `best`
- `trending`
- `recent`
- `newest`
- `cool`
- `good`
- `small`
- `open source`

註：
- `open source` 在 GitHub repo search domain 通常不提供額外過濾能力，預設不保留為 keyword。
- 若後續資料集證明某些修飾詞確實有檢索價值，再個別提升成 facet rule，而不是直接放回 `keywords`。

## 4. Technical Phrase Dictionary

### 4.1 目的

technical phrase dictionary 用來保護常見技術短語，避免 parser 或 normalizer 拆壞 phrase。

### 4.2 範圍

第一版只納入：

- 在資料集中反覆出現
- 三模型共同容易拆壞
- 具有明顯搜尋語意的 phrase

建議首批詞條：

- `machine learning`
- `state management`
- `spring boot`
- `react native`
- `ui kit`
- `vue 3`
- `graphql server`

### 4.2.1 Seed Dictionary v1

以下 seed dictionary 可直接作為第一版 technical phrase 保護名單。

#### 語言名稱與語言別名

這一組主要用於：

- `language` facet mapping
- keyword 中的語言詞移除
- typo / alias canonicalization

建議收錄：

- `python -> Python`
- `py -> Python`
- `javascript -> JavaScript`
- `js -> JavaScript`
- `typescript -> TypeScript`
- `ts -> TypeScript`
- `java -> Java`
- `kotlin -> Kotlin`
- `swift -> Swift`
- `go -> Go`
- `golang -> Go`
- `rust -> Rust`
- `ruby -> Ruby`
- `c++ -> C++`
- `cpp -> C++`
- `c# -> C#`

#### Framework / 技術短語

這一組預設保留在 `keywords`，除非未來 schema 新增更細 facet。

建議收錄：

- `ruby on rails`
- `spring boot`
- `react native`
- `react component`
- `vue 3`
- `state management`
- `machine learning`
- `graphql server`
- `game engine`
- `web framework`
- `admin dashboard`
- `ui kit`
- `microservice framework`
- `chatbot library`
- `testing framework`
- `orm library`

#### 資料庫 / 基礎設施 / 工具名稱

這一組預設保留在 `keywords`，因為目前 schema 沒有專門的 `database` / `infra_tool` facet。

建議收錄：

- `postgres`
- `postgresql`
- `ngrok`
- `cargo`
- `android`
- `ios`
- `kubernetes`
- `docker`
- `terraform`
- `redis`
- `mysql`
- `mongodb`

### 4.2.2 分類原則

不是所有技術名詞都該做同樣處理：

- 程式語言：優先映射到 `language`
- framework / library / stack phrase：保留為 `keywords`
- database / infra / tooling 名稱：目前保留為 `keywords`

例如：

- `ruby on rails`：保留為 phrase keyword
- `ruby`：優先映射到 `language='Ruby'`
- `spring boot`：保留為 phrase keyword
- `kotlin`：優先映射到 `language='Kotlin'`
- `android`：目前保留為 keyword
- `postgres` / `postgresql`：目前保留為 keyword
- `cargo`：目前保留為 keyword
- `ngrok`：目前保留為 keyword

### 4.3 規則

若 query 或 parser output 命中 technical phrase dictionary：

1. phrase 優先保留為單一 keyword
2. 不再拆成多個 token
3. scorer 比對時可接受 phrase-preserving normalization

### 4.4 不要把 dictionary 變成題目表

dictionary 應該只收：

- 通用技術短語
- facet aliases
- 常見 typo / multilingual canonical forms

不要收：

- 完整 query 句子
- 單題專用 mapping

## 5. Singular / Plural Tolerance

### 5.1 目的

單複數漂移是目前三模型共同最大宗失分來源之一：

- `framework` / `frameworks`
- `library` / `libraries`
- `engine` / `engines`
- `example` / `examples`
- `utility` / `utilities`

### 5.2 規則

在 keyword normalization 與 scorer canonicalization 中加入有限 lemmatization：

- `frameworks -> framework`
- `libraries -> library`
- `engines -> engine`
- `examples -> example`
- `utilities -> utility`
- `libs -> library`

### 5.3 限制

不要做通用 NLP stemming。

只允許：

- 小型白名單 lemmatization
- 可測試、可解釋、可回歸驗證的詞形還原

## 6. Facet Mapping Rules

### 6.1 Language Terms

若 query 含明確語言詞：

- `python`
- `golang`
- `go`
- `rust`
- `typescript`
- `javascript`
- `java`
- `kotlin`
- `swift`
- `ruby`
- `c#`
- `c++`

優先映射到 `language`。

若 `language` 已填，normalizer 比對前應移除重複語言詞：

- `keywords=['python','scraping']` 且 `language='Python'`
- canonicalized keyword set -> `['scraping']`

### 6.2 Popularity / Ranking Terms

以下詞不進 `keywords`，改映射到排序欄位：

- `popular`
- `top`
- `best`
- `most starred`
- `ranked by stars`
- `sorted by stars`

對應：

- `sort='stars'`
- `order='desc'`

### 6.3 Quantity Terms

以下資訊不進 `keywords`：

- `top 10`
- `20 repos`
- `list 15`

改映射到：

- `limit`

## 7. Multilingual / Noisy Canonicalization

### 7.1 原則

multilingual 與 typo 處理先走：

1. parser prompt policy
2. 小型 alias dictionary
3. 最後才考慮擴大 normalizer

### 7.2 第一版 alias dictionary

可接受的小型 canonical alias：

- `golang -> Go`
- `js -> JavaScript`
- `ts -> TypeScript`
- `rb -> Ruby`
- `rails -> ruby on rails`（僅當上下文明確指 framework，不直接映射到 `language`）
- `postgres -> postgresql`
- `pg -> postgresql`
- `starz -> stars`
- `strs -> stars`
- `libs -> library`
- `lib -> library`
- `repoz -> repos`
- `aftr -> after`
- `rect -> react`
- `frameework -> framework`
- `javscript -> javascript`
- `pythn -> python`
- `爬蟲 -> scraping`
- `套件 -> crawler` 或 `library`，依 dataset canonical 決定
- `微服务 -> microservice`
- `框架 -> framework`
- `熱門 -> popular`
- `排序 -> sorted`
- `star 數 -> stars`
- `サンプル -> sample`
- `プロジェクト -> project`
- `日本語 -> japanese`

註：
- multilingual alias 必須對齊 dataset ground truth，而不是自由翻譯。
- 若 alias 含歧義，寧可保守，不要一次擴太大。

## 8. Implementation Plan

Iteration 1 前先釘三條 single-source-of-truth invariants，用來避免 parser / validator / scorer 各自抄一套邏輯造成 drift：

1. **Keyword canonicalization 只有一個入口。**
   - 唯一入口為 `normalize_keywords(..., language=...)`（見 §8.0.3）
   - predicted structured query 與 ground truth structured query 皆須經此入口
   - scorer 不得自行 lowercase / sort / strip / merge / lemmatize；只可呼叫 shared canonicalization

2. **Validation issue 結構化，不吃字串。**
   - `Validation.errors` 由 `list[str]` 改為 `list[ValidationIssue]`（見 §8.0.5）
   - `repair_query` 直接消費 `ValidationIssue`，不保留字串 adapter
   - logs / artifacts 存同一份結構化資料，不得轉回字串

3. **Normalization / validation trace 走正式 schema 欄位，不靠 state_diff 偶然帶出。**
   - 新增 `KeywordNormalizationTrace`（見 §8.4）
   - `prompt_version` / `keyword_rules_version` 同時記在 run-level 與 turn-level
   - 不允許「有時候在 output_state、有時候只在 state_diff、有時候要人工反推」的路徑

這三條是後續 §8.0–§8.4 的前提。任何實作若與此衝突，視為 drift。

### 8.0 Agent Loop Integration

`keyword_rules.py` 不應直接把原始自然語言 query 逐字改寫。

正確角色是：

1. LLM 先把 `user_query` 轉成 `structured_query` 初稿
2. `keyword_rules.py` 再對 `structured_query.keywords` 做 deterministic normalization / validation
3. 若仍違反規則，再交給 `repair_query`

建議流程：

`user_query`
-> `parse_query`
-> `normalize_keywords`
-> `validate_query`
-> `repair_query`（若需要）
-> `compile_github_query`
-> `execute_github_search`

### 8.0.1 為什麼不用逐字 rewrite 原始 query

不建議做：

- 把原始 query 一個字一個字拆開
- 對每個 token 直接查 dictionary 後重寫整句

原因：

1. technical phrase 很容易被拆壞  
   例：`spring boot`、`react native`、`machine learning`

2. 同一個詞在不同上下文角色不同  
   例：`python` 可能是 `language`，不一定該留在 `keywords`

3. typo / multilingual query 不適合用逐字規則硬改

因此：

- 原始 query 保持不變
- parser 先做語意理解
- `keyword_rules.py` 再對 `structured_query` 做結構化修正

### 8.0.2 keyword_rules.py 的責任

`keyword_rules.py` 應該服務兩個目的：

1. **normalization**
   - phrase preserve / merge
   - alias normalization
   - singular / plural canonicalization
   - remove leaked language tokens
   - remove modifier stopwords

2. **validation**
   - 找出不應留在 `keywords` 的詞
   - 找出應保留卻被拆壞的 technical phrase
   - 找出和 `language` / `sort` / `limit` 衝突的 keyword

### 8.0.3 建議函式介面

建議在 `src/gh_search/normalizers/keyword_rules.py` 或等價模組提供：

```python
def normalize_keywords(
    keywords: list[str],
    *,
    language: str | None = None,
) -> list[str]:
    ...


def find_keyword_violations(
    keywords: list[str],
    *,
    language: str | None = None,
) -> list[ValidationIssue]:
    ...


def canonicalize_keyword_token(token: str) -> str:
    ...
```

其中：

- `normalize_keywords(...)`
  - 回傳 canonicalized keyword list
  - 為 keyword canonicalization **唯一入口**，runtime 與 scorer 共用（見 §8.3）
- `find_keyword_violations(...)`
  - 回傳結構化 `list[ValidationIssue]`（見 §8.0.5）
  - 直接供 `validate_query` / `repair_query` / logs 共用，不允許任一 caller 再做字串 adapter
- `canonicalize_keyword_token(...)`
  - 只處理單一 token / phrase 的 alias 與詞形還原

另外：

- `KEYWORD_RULES_VERSION` 常數（例：`"kw-rules-v1"`）與 dictionaries 一併定義於 `keyword_rules.py`
- 不分散到 `pyproject.toml` / JSON / README，多一份就多 drift 風險

### 8.0.4 Query 標注 vs Query 重寫

若後續需要在 parser 前增加輔助訊號，可做的是 **query annotation**，不是 query rewrite。

例如：

```json
{
  "detected_language_terms": ["golang"],
  "detected_modifier_terms": ["popular"],
  "detected_phrases": ["spring boot"]
}
```

這類標注可用於：

- prompt 提示
- validator debug
- error analysis

但不應直接拿來覆蓋原始 `user_query`。

### 8.0.5 Validation Issue Schema

所有 validation 輸出（不限 keyword）共用單一結構化模型，讓 validator / repair / logs / analysis 吃同一份資料：

```python
class ValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None
    token: str | None = None
    replacement: str | None = None
```

規範：

- `Validation.errors` 型別為 `list[ValidationIssue]`，不再是 `list[str]`
- `find_keyword_violations(...)` 直接回 `list[ValidationIssue]`，不另定 `KeywordViolation` 型別
- `repair_query` 以 JSON dump 的 `ValidationIssue` 列表餵給 LLM，**不做字串預處理、不保留字串 adapter**
- 所有 run / turn artifact 存同一份 `ValidationIssue`，不得轉回字串

建議 keyword 相關 `code` 命名（v1）：

- `language_leak`
- `modifier_stopword`
- `phrase_split`
- `plural_drift`
- `alias_applied`
- `quantity_leak`
- `sort_intent_leak`

`code` 清單未來可擴，但每次新增須同步登記於 spec 與 test fixture，不得只在程式碼內默默新增。

### 8.1 Prompt Policy

在 parser prompt 中新增明確規則：

- 保留 technical phrases
- 不要把 language 放進 `keywords`
- 不要把 popularity modifiers 放進 `keywords`
- 不要做不必要的單複數改寫
- 不要自行擴寫原句沒有的 keyword

### 8.2 Deterministic Normalizer

新增 `src/gh_search/normalizers/keyword_rules.py`（§8.0.3 定義的單一入口），第一版只做：

- lowercase
- technical phrase preserve / merge
- singular / plural whitelist lemmatization
- remove leaked language tokens
- remove modifier stopwords
- apply alias dictionary

### 8.3 Scorer Integration

scorer 必須與 runtime 共用同一份 canonicalization，且為唯一入口：

- scorer 比對 predicted 與 ground truth 前，**兩邊皆**呼叫同一個 `normalize_keywords(..., language=...)`
- scorer **不得**自己做 lowercase / sort / dedupe / phrase merge / lemmatization 等任何 keyword transform
- scorer 若發現 ground truth 在 normalize 後仍含應被移除的 token（例：language leak 未清乾淨），視為 dataset bug，修 dataset 而不是在 scorer 加特例
- 同一條規則不能只在 scorer 吃掉、parser / runtime 完全不知道

違反此條即為 drift — 例如 runtime 已把 `python` 從 keyword 移除、scorer 卻仍把它算 mismatch。

### 8.4 State / Logging Integration

tuning 可追蹤性靠正式 trace schema，**不靠 state_diff 偶然帶出**。

新增 normalization trace model：

```python
class KeywordNormalizationTrace(BaseModel):
    prompt_version: str | None
    keyword_rules_version: str | None
    raw_keywords: list[str]
    normalized_keywords: list[str]
    violations: list[ValidationIssue]
```

Placement（正式欄位，不靠 state_diff）：

- `prompt_version` 與 `keyword_rules_version` **同時**記在 run-level artifact 與 turn-level artifact
- `raw_keywords` / `normalized_keywords` 放 turn-level normalization trace
- `violations` 放 turn-level validation trace（與 `repair_query` input 為同一份 `ValidationIssue` 列表）
- 不允許同一個欄位「有時候在 output_state、有時候只在 state_diff、有時候要從原始 prompt 人工反推」

這樣才能分辨：

- 是 prompt policy 改動讓結果改善
- 還是 `keyword_rules.py` dictionary / rule 改動吸收了 mismatch
- 還是純粹是 LLM 隨機性

## 9. 驗證方式

### 9.1 必看指標

- keyword mismatch 題數
- per-field recall: `keywords`
- multilingual case accuracy
- typo / noisy case accuracy
- model matrix row-wise accuracy
- golden tests 是否回歸

### 9.2 驗證順序

1. 先跑單模型小規模驗證
2. 再跑至少 2 個 cross-provider 模型
3. 通過後才進 core prompt 或 shared normalizer

### 9.3 Regression Guard

至少固定檢查（golden tests 位置：`tests/golden/iter0_cases.json`）：

- `q012` — 乾淨的 `language` + `created_after/before` + `sort` + `limit`，代表「標準明確題」
- `q015` — keyword + `language` + `min_stars` + popularity intent，代表「典型複合限制題」
- `q025` — typo / noisy 但 baseline 已能通過，代表「tuning 不得把原本過的 noisy 題打壞」

若 keyword tuning 讓 golden tests 回歸，不得合併。

## 10. Iteration 1 建議通過標準

以三模型共同指標判定：

1. keyword mismatch 題數相對 baseline 明顯下降
2. `framework/frameworks`, `library/libraries`, `engine/engines`, `example/examples`, `utility/utilities` 這類漂移至少被吸收大半
3. `spring boot`, `react native`, `ui kit` 這類 phrase split 題至少部分轉正
4. 不得新增新的大宗誤判類型
5. golden tests 全 pass

## 11. 非目標

這份 spec 不打算在 Iteration 1 解決：

- 大型通用 synonym engine
- 全量詞幹分析
- 通用跨語言翻譯系統
- 每題專用 facet mapping prompt
- 只對單一模型有效的長 prompt 補丁

## 12. 本輪 Tuning 成果

本輪已完成：

- `keyword_rules.py` 作為 single source of truth
- parser / validator / scorer 共用同一套 `normalize_keywords(...)`
- `ValidationIssue` 結構化
- run / turn artifact 記錄 `keyword_rules_version` 與 normalization trace

### 12.1 Iteration 2 成績提升

相較於前一輪 baseline，本輪三模型 accuracy 明顯上升：

- `gpt-4.1-mini`: `4/30 -> 10/30`（`13.33% -> 33.33%`）
- `claude-sonnet-4`: `5/30 -> 11/30`（`16.67% -> 36.67%`）
- `deepseek-r1`: `3/30 -> 9/30`（`10.00% -> 30.00%`）

這代表：

- 純 keyword canonicalization 類問題已有明顯改善
- 問題主體仍在 parser / date / gate / multilingual，而不是 infra

### 12.2 本輪已被吸收的問題

本輪已有效吸收的主要類型：

- 單 token 的大小寫差異
- 部分單複數漂移
- 部分 technical phrase preserve / merge
- 部分 language leak
- 一部分 typo / noisy query 的 canonicalization

### 12.3 本輪新增觀察

在 keyword tuning 生效後，剩餘問題變得更清楚：

- phrase merge 邊界定義不清
- multilingual alias 仍停留在 single-token 層級
- relative date parsing 仍不穩
- intention gate 還是過度保守
- 少量 `execution_failed` 需要獨立調查，不應和 keyword tuning 混為一談

## 13. 尚待 Tuning 的項目

### 13.1 Phrase-level plural drift

目前最大宗 keyword 類失敗仍是：

- `web frameworks -> web framework`
- `testing frameworks -> testing framework`
- `game engines -> game engine`

根因：

- 現行 plural normalization 對 single token 有效
- 對包含空白的 token / phrase 尚未逐 sub-token canonicalize

### 13.2 Multilingual alias 尚未支援 sub-token

仍待解的例子：

- `微服务框架`
- `爬蟲套件`
- `サンプルプロジェクト`

根因：

- alias 規則多為 single-token
- 對整串 phrase 無法先拆再 canonicalize 再重組

### 13.3 Relative date parsing

以下仍非 keyword_rules 可解：

- `last year`
- `this year`
- `from 2024`
- `2023年以后`

這屬於 parser / date normalization 工項。

### 13.4 Intention gate 過度拒絕

仍需進一步區分：

- 應回收的 reject：如 `q004`, `q009`, 可能還有 `q022`
- 合理持續 reject：如 `q019`, `q020`, `q021`, `q030`

這塊應獨立於 keyword rules 調整。

### 13.5 少量 execution_failed

本輪出現少量：

- `execution_failed`

其 `response_status` 為 `None`，看起來更像 transport / execution robustness 問題，而不是純 keyword mismatch。

此項需另開小線追查，不應混入 keyword rule 設計。

## 14. 已拍板的下一輪方向

### 14.1 Phrase merge policy 正式拍板

dataset 實際隱含政策為：

- **只 merge 單一實體名稱 / 固定技術棧名稱**
- **不 merge `modifier + category` 結構**

應保留 merge 的 phrase：

- `machine learning`
- `state management`
- `vue 3`
- `spring boot`
- `react native`
- `ui kit`

`ruby on rails` 可視為未來擴充，不是本輪必要範圍。

不應 merge 的結構：

- `web framework`
- `testing framework`
- `microservice framework`
- `chatbot library`
- `orm library`
- `graphql server`
- `game engine`
- `admin dashboard`
- `react component`
- `kubernetes operator`
- `inference engine`
- `ai agent framework`

### 14.2 Sub-token normalization policy

下一輪 `normalize_keywords(...)` 應改為：

1. 若 token 含空白，先拆成 sub-token
2. 對每個 sub-token 套用 alias / plural normalization
3. 僅在命中 allowlist phrase 時重組 merge
4. 若未命中 allowlist，保持拆開狀態

這條規則是下一輪 keyword tuning 的核心。

### 14.3 Dataset / canonical policy 拍板

#### q005

- `kubernetes operator` **不 merge**

理由：

- 與 `web framework`、`game engine`、`inference engine` 等同屬 `modifier + category`

#### q027

目前判定為 dataset bug，建議修為：

- `爬蟲 -> crawler`
- `套件 -> library`
- `q027` ground truth -> `['crawler', 'library']`

理由：

- `套件 -> crawler` 不符合一般技術語意
- 原 query 更接近 `crawler library`

#### q029

建議：

- `日本語 -> drop`
- `プロジェクト -> drop`
- `サンプル -> sample`

理由：

- `日本語` 在此更像文件 / 說明語言，不是 GitHub Search API 的穩定 facet
- dataset 目前 canonical policy 只保留 `sample`

### 14.4 下一輪實作範圍

下一輪 keyword tuning 應只做：

1. phrase dict 裁剪
2. sub-token normalization
3. multilingual alias 擴充到 sub-token
4. noise / drop token 明確化
5. 修 dataset `q027` ground truth

下一輪 **不**混入：

- intention gate 大改
- relative date parsing
- language over-inference
- execution_failed transport fix

這些應分成獨立工項，避免再度把 keyword tuning 與其他 failure family 混在一起。

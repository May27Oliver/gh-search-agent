# tests — 導覽

這個資料夾放所有的自動化測試，用 pytest 跑。命名慣例很簡單：`src/gh_search/` 底下每一個實作模組，都會有一支對應的 `test_<模組>.py`。要找「這段程式碼怎麼被測的」就按名字找過來就對了。

## 怎麼跑測試

```bash
pytest -q                                     # 跑全部，輸出精簡
pytest -q tests/test_agent_loop.py            # 只跑某一支
pytest --cov=src --cov-report=term-missing    # 含覆蓋率報告，會標出哪幾行沒測到
pytest -k intention                           # 跑名稱含 "intention" 的測試（關鍵字過濾）
```

Phase 1 的收尾條件是：`pytest -q` 全綠，而且總覆蓋率 ≥ 80 %（domain 的純函數要求更高，至少 90 %）。

## 哪個測試對應哪個實作

| 測試檔 | 對應的實作 |
|---|---|
| `test_schemas_*.py` | `src/gh_search/schemas/` 底下的 pydantic model |
| `test_compiler.py` / `test_validator.py` | domain 純函數（`compiler.py` / `validator.py`） |
| `test_tool_*.py` | `src/gh_search/tools/` 底下的每支 tool（一支 tool 一個測試檔） |
| `test_agent_loop.py` | `src/gh_search/agent/loop.py` |
| `test_github_client.py` | `src/gh_search/github/client.py`（用 `responses` 套件把 HTTP 假掉） |
| `test_openai_client.py` | `src/gh_search/llm/openai_client.py` |
| `test_logger.py` | `src/gh_search/logger/session.py` |
| `test_scorer.py` / `test_smoke_runner.py` | `src/gh_search/eval/` |
| `test_cli_scaffold.py` / `test_cli_query.py` | `src/gh_search/cli.py` |

## 寫新測試的幾個慣例

1. **先寫會失敗的測試**。新功能、新 bugfix，一律先在這裡寫一支應該會紅的測試再去動實作。PR 的 diff 要看得出「RED 先、GREEN 後」的順序。
2. **Mock 邊界、不 mock domain**。LLM 跟 GitHub HTTP 可以假掉（它們是外部邊界），但 `compiler.py`、`validator.py`、`schemas/` 這些 domain 物件**不要 mock**。mock 掉 domain 等於測試沒在驗真的邏輯。
3. **不用真的金鑰**。CLI 測試的標準寫法是 `monkeypatch.setenv("OPENAI_API_KEY", "sk-test")` 加 `@patch("gh_search.cli.make_openai_llm")`。想控制 LLM 回什麼，用現有的 `_scripted_llm(*responses)` helper 就好，不要自己再發明一套。
4. **小心 cwd 的 `.env` 污染**。測試常常 `monkeypatch.chdir(tmp_path)`，這是好習慣；不過因為 `config.py` 曾經會往上層找 `.env`（現在已經改掉），還是留意一下測試有沒有不小心讀到 repo 根的 `.env`。
5. **每題測試都用獨立的 `tmp_path`**。不要為了省事就共用 log 目錄，測試之間互相污染 debug 起來很麻煩。

## 為什麼一律用 `responses` 而不是 `requests-mock`

純粹是「同一件事只用一種工具」的原則。避免有些測試用這個、有些測試用那個，風格不一致。要換就整批換，不要混用。

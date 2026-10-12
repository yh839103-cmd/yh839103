# AGENTS.md — 給 AI 寫程式助手（OpenCode 等）的專案說明

這是一個 LINE 聊天機器人「安鎧Ai」：使用者在手機 LINE 傳訊息，伺服器呼叫 Google Gemini 免費 API 產生回答。
程式部署在 Render（免費方案），**每次 push 到 main 都會自動上線**，所以只能推送測試全部通過的程式。

## 檔案地圖

| 檔案 | 做什麼 | 改這裡的時機 |
|---|---|---|
| `app/main.py` | Flask 伺服器、接收 LINE webhook、回覆／推播訊息 | 新增要處理的 LINE 事件類型 |
| `app/core.py` | 對話記憶、指令、長訊息切段、**所有給使用者看的文字**、快速回覆按鈕 `QUICK_REPLIES` | 改說明文字、按鈕、指令 |
| `app/line_messages.py` | 把文字包成 LINE 訊息並加上快速回覆按鈕 | 改訊息格式 |
| `app/llm.py` | 呼叫 Gemini：重試、換備用模型、整體時間上限、工具呼叫 | 改 AI 行為、系統提示詞 |
| `app/tools.py` | AI 可呼叫的免費查詢工具（維基百科、天氣） | 新增查詢工具 |
| `tests/` | 單元測試＋端對端 webhook 測試（用簽章送假的 LINE 訊息） | 每個新功能都要加測試 |
| `docs/index.html` | 開發紀錄網頁（GitHub Pages） | 每個新版本都要加一段紀錄 |
| `docs/PROPOSAL.md` | 專題計畫書 | 功能大改時更新 |

## 開發指令

```bash
pip install -r requirements-dev.txt   # 安裝套件（第一次）
pytest -q                             # 跑全部測試，必須全部通過
```

本機實際執行需要 `.env`（照 `.env.example` 填三組金鑰），一般改程式只要跑 `pytest` 就夠了。

## 必須遵守的規則

1. **絕對不要把金鑰寫進任何檔案或 commit**（LINE secret、LINE token、Gemini key）。金鑰只放在 Render 的環境變數和本機的 `.env`（已在 `.gitignore`）。
2. **改完程式一定要跑 `pytest -q`，全部通過才能 commit／push。** 測試失敗時先修好，不要刪測試。
3. 每個新功能或修正都要**新增測試**。LINE 事件的寫法可參考 `tests/test_webhook.py` 的 `_event()` 和 `_post()`。
4. 給使用者看的文字用**繁體中文、台灣用語**，集中放在 `app/core.py`。
5. 不要動 `v1-first-version` 分支（那是第一版的作業紀錄）。
6. 改動要小而集中：一次只做一件事，commit 訊息用中文寫清楚「改了什麼、為什麼」。
7. 不要新增需要付費或需要額外金鑰的服務；這個專案全部使用免費方案。
8. 更新 `docs/index.html` 時，**新增**一段新版本紀錄（原本的問題、修改內容、前後差異、重新測試結果），不要刪掉舊版本的紀錄。

## 已知限制（改程式時要考慮）

- Render 免費方案：記憶體約 512MB、閒置會休眠；對話記憶存在記憶體，重啟會清空。
- Gemini 免費方案有每分鐘／每天的次數上限，忙線時會回 503／429（`llm.py` 已處理重試）。
- LINE 的 reply token 有使用期限：AI 回答整體不能太久（`AI_TIME_BUDGET`，預設 60 秒；Gemini 思考程度預設 low），逾時改用推播。
- LINE 快速回覆按鈕：最多 13 個、按鈕文字最多 20 字，只顯示在最後一則訊息。

## 已完成任務：讓 Bot 可以上網搜尋（Tavily）（保留規格供參考）

Gemini 免費方案不能用 Google 搜尋，所以接 Tavily 搜尋 API（每月 1,000 次免費、不用信用卡）。
照下面的規格做，**不要新增任何 pip 套件**，HTTP 請求一律用內建的 `urllib`（跟 `tools.py` 現有寫法一樣）。

**API 規格**
- `POST https://api.tavily.com/search`
- Header：`Authorization: Bearer <金鑰>`、`Content-Type: application/json`
- Body：`{"query": "...", "search_depth": "basic", "max_results": 5, "include_answer": "basic", "topic": "general"}`
- 回應：`answer`（字串）、`results`（陣列，每筆有 `title`、`url`、`content`）
- 金鑰從環境變數 `TAVILY_API_KEY` 讀取（去掉前後空白）

**要改的檔案**
1. `app/tools.py`
   - 在 `DECLARATIONS` 新增一個工具 `search_web`，參數只有 `query`（字串，必填），說明寫：「上網搜尋最新資訊，例如新聞、近期事件、價格、營業時間、活動日期。維基百科查不到或需要最新資料時使用。」
   - 新增函式 `search_web(query: str) -> dict`：
     - 沒有設定 `TAVILY_API_KEY` 時，回傳 `{"error": "搜尋功能尚未設定金鑰"}`，不要丟出例外
     - 有金鑰時呼叫 Tavily，回傳 `{"source": "網路搜尋（Tavily）", "answer": ..., "results": [{"title", "url", "content"（最多 300 字）}]}`
   - 在 `FUNCTIONS` 註冊 `"search_web": search_web`
2. `app/llm.py` 的 `DEFAULT_SYSTEM_PROMPT`
   - 第 3 點改成有三個工具（search_wikipedia、get_weather、search_web）
   - 第 4 點改成：新聞、近期事件、價格、營業時間等即時資訊先用 search_web 查；回答最後附上 1～2 個來源網址
3. `tests/test_llm.py` 新增測試（用 `mock.patch("urllib.request.urlopen", ...)` 假造回應，不要真的連網）：
   - 沒有金鑰時回傳 error
   - 有金鑰時，送出的請求網址是 Tavily、Header 有 `Bearer`，回傳的 results 有 title／url／content
   - `search_web` 有出現在 `DECLARATIONS` 和 `FUNCTIONS`
   - 注意：`test_tools_declared_when_enabled` 目前檢查工具名稱清單，要一起更新
4. `render.yaml` 的 `envVars` 新增 `- key: TAVILY_API_KEY` 加 `sync: false`；`.env.example` 新增 `TAVILY_API_KEY=`；`README.md` 的環境變數表格新增一列
5. 完成後跑 `pytest -q`，全部通過（原本 32 項＋新增的）

## 可以做的改善（待辦）

- [x] 讓 Bot 可以上網搜尋（2026-10-12 完成：OpenCode + Big Pickle 實作）
- [ ] 群組中只在被 @ 提及時才回覆（目前群組每則都回）
- [ ] 看得懂照片：把使用者傳的圖片交給 Gemini（Gemini 支援圖片輸入）
- [ ] 傳「位置」時直接回覆該地點的天氣（`tools.get_weather` 已有查詢功能）
- [ ] 圖文選單（Rich Menu）：聊天室下方固定的選單
- [ ] 對話記憶改存在免費資料庫，重啟也不會忘記

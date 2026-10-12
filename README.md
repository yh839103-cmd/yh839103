# LINE AI 聊天助理 🤖

用 Python + Flask 打造、串接 Google Gemini（免費方案）的 LINE 聊天機器人。支援多輪對話記憶、指令、長訊息自動切段。

📄 計畫書：[docs/PROPOSAL.md](docs/PROPOSAL.md)　｜　📒 開發紀錄網頁：https://yh839103-cmd.github.io/yh839103/

## 版本紀錄

| 版本 | 日期 | 內容 |
|---|---|---|
| v2 改善版 | 2026-10-11 | 改善輸入提示：快速回覆按鈕、非文字訊息提示、中文指令說明 |
| v1 第一版 | 2026-10-05 | AI 對話、對話記憶、查維基百科與天氣；保留於 [`v1-first-version`](https://github.com/yh839103-cmd/yh839103/tree/v1-first-version) 分支 |

## 用 AI 寫程式助手開發

- `AGENTS.md`：給 OpenCode 等 AI 助手看的專案說明（檔案地圖、測試指令、必須遵守的規則、待辦清單）
- `opencode.json`：OpenCode 的本地模型（Ollama）設定

## 功能

- 💬 AI 對話：傳任何文字訊息，Gemini 會回覆
- 🧠 對話記憶：記得最近 10 輪對話（閒置 1 小時自動清除）
- ⌨️ 指令：「說明」、「重新開始」（也支援 `/help`、`/reset`）
- 🔘 **快速回覆按鈕**（v2）：每則回覆下方都有按鈕，不用打字也能操作
- 🖼️ **非文字訊息提示**（v2）：傳貼圖、圖片、語音等會提示「目前只看得懂文字」，不再沒反應
- 👋 加好友時自動送出歡迎說明
- ✂️ 超過 LINE 5000 字上限時自動切段
- ⏳ AI 思考時顯示「輸入中」動畫
- 🔎 會自己查資料：中文維基百科（知識）、Open-Meteo（天氣），免費且不需金鑰
- 🔁 Google 忙線時自動重試，並依序改用其他免費模型

## 專案結構

```
app/
  main.py   # Flask Webhook 伺服器、LINE 事件處理
  core.py   # 對話記憶、指令、訊息切段、提示文字與按鈕設定（純 Python，可單元測試）
  line_messages.py  # 把文字包成 LINE 訊息並加上快速回覆按鈕
  llm.py    # Gemini API 串接（只用內建 urllib），含重試與工具呼叫
  tools.py  # AI 可呼叫的免費查詢工具：維基百科、天氣
tests/      # 單元測試＋端對端 webhook 測試
docs/       # 計畫書
```

## 快速開始

### 1. 準備金鑰

1. 到 [LINE Developers Console](https://developers.line.biz/console/) 建立 **Messaging API** Channel，取得：
   - `Channel secret`（Basic settings 頁）
   - `Channel access token`（Messaging API 頁，按 Issue）
2. 到 [Google AI Studio](https://aistudio.google.com/apikey) 建立免費的 Gemini API Key（不用綁信用卡）。

### 2. 本機執行

```bash
git clone <你的 repo 網址>
cd line-ai-bot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env    # 填入金鑰
set -a && source .env && set +a
python -m app.main
```

### 3. 讓 LINE 連到你的電腦

```bash
ngrok http 8000
```

把 ngrok 給的 `https://xxxx.ngrok-free.app/callback` 填到 LINE Console → Messaging API → **Webhook URL**，按 Verify，並開啟 **Use webhook**。
建議同時關閉「自動回應訊息」，以免和 Bot 重複回覆。

### 4. 部署到雲端（Render）

1. 在 [Render](https://render.com/) 選 **New → Blueprint**，連結這個 GitHub repo（會讀取 `render.yaml`）。
2. 填入 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`、`GEMINI_API_KEY`。
3. 部署完成後，把 `https://<你的服務>.onrender.com/callback` 填回 LINE Webhook URL。

也可以用 Docker：

```bash
docker build -t line-ai-bot .
docker run --env-file .env -p 8000:8000 line-ai-bot
```

## 環境變數

| 變數 | 必填 | 說明 |
|---|---|---|
| `LINE_CHANNEL_SECRET` | ✅ | LINE Channel secret |
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE Channel access token |
| `GEMINI_API_KEY` | ✅ | Google AI Studio 的 API Key |
| `GEMINI_MODEL` | | 預設 `gemini-flash-latest`（自動使用最新 Flash 模型） |
| `GEMINI_FALLBACK_MODEL` | | 主模型忙線時依序改用（逗號分隔），預設 `gemini-3.7-flash,gemini-3.5-flash-lite` |
| `TAVILY_API_KEY` | | Tavily 搜尋 API 金鑰（每月 1,000 次免費），設定後 AI 才能上網查最新資訊 |
| `ENABLE_TOOLS` | | 設成 `false` 可關閉查資料功能，預設開啟 |
| `SYSTEM_PROMPT` | | 自訂 AI 角色設定 |
| `GEMINI_TEMPERATURE` | | 0～2，越低回答越穩定，預設 0.4 |
| `AI_TIME_BUDGET` | | AI 回答整體時間上限（秒），預設 60 |
| `GEMINI_THINKING_LEVEL` | | Gemini 思考程度，預設 `low`（回答較快）；設成空白則用模型預設 |
| `MAX_TURNS` | | 記憶輪數，預設 10 |
| `SESSION_TTL` | | 記憶保留秒數，預設 3600 |

## 測試

```bash
pytest -q
```

每次 push 都會由 GitHub Actions 自動執行測試。

## 注意事項

- 對話記憶存在伺服器記憶體中，重啟後會清空；因此 gunicorn 只用 1 個 worker（多執行緒）。
- 請勿把 `.env` 上傳到 GitHub。
- Gemini 免費方案有每分鐘／每天的次數限制，超過時 Bot 會回「請稍後再試」；實際額度可在 Google AI Studio 查看。

## 常見問題

| 狀況 | 原因與解法 |
|---|---|
| 訊息「已讀」但 Bot 沒回 | LINE 官方帳號後台 → 設定 → 回應設定：**聊天關閉**、**Webhook 開啟**。聊天開著時訊息會進真人客服收件匣 |
| 收到「本帳號無法個別回覆用戶的訊息」 | 同一頁把 **自動回應訊息** 關閉 |
| Verify 出現 400 Bad Request | `LINE_CHANNEL_SECRET` 填錯（貼反、多了字）。到 LINE Basic settings 重新複製，貼到 Render → Environment |
| Bot 回「請稍後再試」 | 到 Render → Logs 搜尋「Gemini」：503 是 Google 忙線（程式會自動重試並改用備用模型）、400/403 是金鑰錯誤、429 是超過免費額度 |
| 回答不正確或像在亂掰 | Gemini 免費方案無法上網查詢，即時資訊（新聞、天氣、價格）可能過時；可調低 `GEMINI_TEMPERATURE` 或在 `SYSTEM_PROMPT` 寫清楚 Bot 的專長範圍 |
| 很久沒用後第一則訊息很慢或沒回 | Render 免費方案閒置會休眠；`.github/workflows/keep-awake.yml` 每 10 分鐘叫醒一次，也可在 LINE Developers 開啟 Webhook redelivery |
| 出現「輸入中」後沒有回覆 | v2 起已修正：AI 整體時間上限 60 秒、動畫 60 秒、回覆期限過了改用推播 |

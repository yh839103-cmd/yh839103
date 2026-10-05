# LINE AI 聊天助理 🤖

用 Python + Flask 打造、串接 Google Gemini（免費方案）的 LINE 聊天機器人。支援多輪對話記憶、指令、長訊息自動切段。

📄 計畫書：[docs/PROPOSAL.md](docs/PROPOSAL.md)

## 功能

- 💬 AI 對話：傳任何文字訊息，Gemini 會回覆
- 🧠 對話記憶：記得最近 10 輪對話（閒置 1 小時自動清除）
- ⌨️ 指令：`/help` 說明、`/reset` 清除記憶
- 👋 加好友時自動送出歡迎說明
- ✂️ 超過 LINE 5000 字上限時自動切段
- ⏳ AI 思考時顯示「輸入中」動畫

## 專案結構

```
app/
  main.py   # Flask Webhook 伺服器、LINE 事件處理
  core.py   # 對話記憶、指令、訊息切段（純 Python，可單元測試）
  llm.py    # Gemini API 串接（只用內建 urllib）
tests/      # 單元測試
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
| `SYSTEM_PROMPT` | | 自訂 AI 角色設定 |
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
| Bot 回「請稍後再試」 | Gemini 金鑰錯誤或超過免費額度；到 Render → Logs 搜尋「呼叫 AI 失敗」看原因 |
| 很久沒用後第一則訊息很慢 | Render 免費方案閒置會休眠，第一則約需 1 分鐘喚醒 |

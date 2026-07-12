# backend

```
Development is done in the `main` branch. The `release` branch is the latest stable release.
```

---

## 安裝依賴

本專案使用 `uv` 進行套件管理：
```bash
uv sync --no-dev
```
或需要開發環境的套件：
```bash
uv sync
```

---

## 資料庫初始化 (Alembic Migrations)

第一次啟動專案前，必須建立資料庫結構：

```bash
# 執行升級，將 models 同步到資料庫中
uv run alembic upgrade head
```
(備註：開發過程中若有修改 `models.py`，請執行 `uv run alembic revision --autogenerate -m "描述"` 來產生新的遷移檔，再執行 `upgrade head`)

---

## 啟動伺服器

```bash
fastapi run
```
伺服器將運行於 http://127.0.0.1:8000
可前往 http://127.0.0.1:8000/docs 查看 API Swagger

---

## 全域速率限制 (API Rate Limiting)

本專案使用 `slowapi` 實作防禦性限速機制。當客戶端觸發限速時，API 將回傳 `429 Too Many Requests` 狀態碼

* **限速基準**：預設以客戶端的 IP 位址為識別基準
* **前端處理建議**：若收到 429 錯誤，應實作指數退避（Exponential Backoff）或延遲重試

---

## API Overview

| Method | Endpoint | Description | Required Permissions | Rate Limit |
|--------|----------|-------------|----------------------|------------|
| `GET` | `/status` | 健康檢查端點 (DB & Redis) | None | 10/minute, 300/hour |
| `GET` | `/api/v1/auth/discord/login` | 回傳 Discord OAuth2 授權網址並 307 重新導向 | None | 5/hour, 20/day |
| `GET` | `/api/v1/auth/discord/callback` | 從 Discord 回來的 code 去跟 Discord 換取資料，確認身分後 setCookie | None | 5/hour, 20/day |
| `POST` | `/api/v1/auth/logout` | 登出並清除 session cookie | None | 5/hour, 20/day |
| `GET`  | `/api/v1/users/me` | 回傳使用者資訊 | None | 60/minute, 1000/hour |
| `GET`  | `/api/v1/nodes` | 回傳當前使用者身份可見的節點列表 | None | 60/minute, 1000/hour |
| `GET`  | `/api/v1/nodes/{node_id}` | 回傳當前使用者身份可見的單一 節點資訊 | None | 60/minute, 1000/hour |
| `POST` | `/api/v1/nodes` | 新增節點 | `node.create` | 3/hour, 5/day |
| `PATCH` | `/api/v1/nodes/{node_id}` | 更新節點| `node.update.own` | 5/hour, 20/day |
| `DELETE` | `/api/v1/nodes/{node_id}` | 刪除節點 | `node.delete.own` | 3/hour, 5/day |

---

Note: 帳號啟用帳號接口尚未實做
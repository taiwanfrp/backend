# backend

```
Development is done in the `main` branch. The `release` branch is the latest stable release.
```

---

## 安裝依賴

本專案使用 `uv` 進行套件管理：
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
uv run uvicorn app.main:app --reload
```
伺服器將運行於 http://127.0.0.1:8000
可前往 http://127.0.0.1:8000/docs 查看 API Swagger

---

## API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/auth/discord/login` | 回傳 Discord OAuth2 授權網址並 307 重新導向 |
| `POST` | `/api/v1/auth/discord/callback` | 從 Discord 回來的 code 去跟 Discord 換取資料，確認身分後 setCookie |
| `POST` | `/api/v1/auth/logout` | 登出並清除 session cookie |
| `GET`  | `/api/v1/auth/me` | 回傳使用者資訊 |

---

Note: 登入的使用者帳號狀態檢查與啟用帳號接口尚未實做
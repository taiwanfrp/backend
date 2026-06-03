# backend

```
Development is done in the `main` branch. The `release` branch is the latest stable release.
```

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
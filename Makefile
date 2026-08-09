.PHONY: help dev db-upgrade db-rev db-seed admin
.DEFAULT_GOAL := help

help:
	@echo "可用的命令:"
	@echo "  dev         - 啟動 FastAPI 開發伺服器"
	@echo "  db-upgrade  - 執行資料庫遷移"
	@echo "  db-rev      - 產生新的資料庫遷移檔案"
	@echo "  db-seed     - 寫入預設權限與身份組資料"
	@echo "  admin       - 建立管理帳號"

dev:
	fastapi dev --host=::

db-upgrade:
	alembic upgrade head

db-rev:
	@if [ -z "$(m)" ]; then \
		echo "請提供 migration 訊息, 例如: make db-rev m=\"你的描述文字\""; \
		exit 1; \
	fi
	uv run alembic revision --autogenerate -m "$(m)"

db-seed:
	uv run python scripts/seed_db.py

admin:
	uv run python scripts/make_admin.py
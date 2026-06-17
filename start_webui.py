"""JobMatch Web UI — точка входа для локального запуска."""
import uvicorn
from src.db import init_db
from src.web.app import app

if __name__ == "__main__":
    init_db()
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="info")

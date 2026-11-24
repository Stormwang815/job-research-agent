import os
import tempfile
from pathlib import Path

# Configure before application import; never touch developer credentials or history.
_runtime = tempfile.TemporaryDirectory(prefix="job-agent-tests-")
_root = Path(_runtime.name)
os.environ.update(LOAD_DOTENV="false", APP_ACCESS_TOKEN="", RATE_LIMIT_PER_MINUTE="10000",
                  DATABASE_PATH=str(_root / "test.db"), REPORT_DIR=str(_root / "reports"), DATA_DIR=str(_root / "data"))

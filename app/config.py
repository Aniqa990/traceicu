from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "mimic-iv-clinical-database-demo-2.2"
HOSP_DIR = DATA_DIR / "hosp"
ICU_DIR = DATA_DIR / "icu"

CLUSTER_WINDOW_MINUTES = 15

MAX_ICU_OBSERVATIONS = 5000
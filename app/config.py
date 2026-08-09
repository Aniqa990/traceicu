from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "mimic-iv-clinical-database-demo-2.2"
HOSP_DIR = DATA_DIR / "hosp"
ICU_DIR = DATA_DIR / "icu"

CLUSTER_WINDOW_MINUTES = 15

MAX_ICU_OBSERVATIONS = 5000

HF_TOKEN = os.getenv("HF_TOKEN")
 

LLM_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

 
# Max number of patients' reconstructed timelines to keep in memory at once.
TIMELINE_CACHE_SIZE = 64
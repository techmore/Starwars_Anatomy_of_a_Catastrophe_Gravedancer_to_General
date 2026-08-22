import os, sys, logging
os.environ["GRAVEDANCER_SECTION_MIN_WORD_RATIO"] = "0.15"
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO)
from pathlib import Path
from scripts.run_oxalpha_pipeline import main
sys.exit(main(7, Path(".oxalpha-run-s7")))

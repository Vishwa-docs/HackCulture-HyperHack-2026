"""Run full pipeline stages 1-7."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__) + "/..")
os.chdir(os.path.dirname(__file__) + "/..")

from dotenv import load_dotenv
load_dotenv()

from src.pipelines.run_all import Pipeline

p = Pipeline(team_id="hackculture")
p.run_all(from_stage=1, to_stage=7)

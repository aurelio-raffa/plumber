"""Orchestrator for the analysis pipeline. All the workflow is included in a single Python program that looks at the
results of each step and decides what to submit next using custom code.
"""
import os
import sys

sys.path.append(os.getcwd())

from src import root_path
# === imports go below this line ===

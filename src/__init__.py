import os
import sys

# we add to PATH the root folder
root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # path to directory containing the script
sys.path.append(root_path)

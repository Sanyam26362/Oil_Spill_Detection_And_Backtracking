import os
import subprocess

scripts = [
    "scripts/run_scenario_001.py",
    "scripts/run_scenario_002.py",
    "scripts/run_scenario_003.py",
    "scripts/run_scenario_004.py",
    "scripts/run_scenario_005.py",
]

for script in scripts:
    print(f"Running {script}...")
    try:
        subprocess.run([".venv\\Scripts\\python.exe", script], check=True)
        print(f"Successfully finished {script}.")
    except subprocess.CalledProcessError as e:
        print(f"Error running {script}: {e}")
        break

print("All scenarios generated!")

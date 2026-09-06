import csv
from collections import defaultdict
from datetime import datetime

REPORT_FILE = "detection_diagnostic_report.csv"

with open(REPORT_FILE, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

monthly_spills = defaultdict(int)
monthly_5k = defaultdict(int)
monthly_10k = defaultdict(int)
monthly_25k = defaultdict(int)

for r in rows:
    dt = datetime.fromisoformat(r["obs_time"])
    m = dt.strftime("%Y-%m")
    monthly_spills[m] += 1
    if int(r["vessels_5km"]) > 0:
        monthly_5k[m] += 1
    if int(r["vessels_10km"]) > 0:
        monthly_10k[m] += 1
    if int(r["vessels_25km"]) > 0:
        monthly_25k[m] += 1

print(f"{'Month':<10} | {'Spills':<8} | {'Matches @5km':<13} | {'Matches @10km':<14} | {'Matches @25km':<14}")
print("-" * 75)
for m in sorted(monthly_spills.keys()):
    print(f"{m:<10} | {monthly_spills[m]:<8} | {monthly_5k[m]:<13} | {monthly_10k[m]:<14} | {monthly_25k[m]:<14}")
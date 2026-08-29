import re
from datetime import datetime

log_file = r"C:\Users\agarw\.gemini\antigravity-ide\brain\8d9009a5-2e87-4245-a172-3c22d81cc5e9\.system_generated\tasks\task-267.log"

gen_time = 0.0
ingest_time = 0.0
attr_time = 0.0
total_time = 0.0

with open(log_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

for line in lines:
    if "time=" in line:
        # e.g. Attribution: 12 candidates, top=SYNTH-S001-SRC, time=1.008s
        match = re.search(r"time=([\d\.]+)s", line)
        if match:
            attr_time += float(match.group(1))

# Let's approximate the others based on timestamps.
# This might be tricky because the log doesn't output time directly for generation and ingestion.
# But it does log timestamps at each line.
# Format: 2026-08-29 11:17:23,711
def parse_time(line):
    try:
        ts = line[:23]
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")
    except:
        return None

for i in range(len(lines)):
    line = lines[i]
    if "SCENARIO BM" in line:
        t0 = parse_time(line)
        # next line is Generated
        t1 = parse_time(lines[i+1])
        if t1 and t0:
            gen_time += (t1 - t0).total_seconds()
    if "Cleaned scenario" in line:
        t0 = parse_time(line)
        t1 = parse_time(lines[i+1]) # Ingested
        if t0 and t1 and "Ingested" in lines[i+1]:
            ingest_time += (t1 - t0).total_seconds()

if lines:
    t_start = parse_time(lines[0])
    t_end = parse_time(lines[-1])
    if t_start and t_end:
        total_time = (t_end - t_start).total_seconds()

print(f"Total time: {total_time}s")
print(f"Total generation time: {gen_time}s")
print(f"Total ingestion time: {ingest_time}s")
print(f"Total attribution time: {attr_time}s")
print(f"Total evaluation time: {total_time - gen_time - ingest_time - attr_time}s")

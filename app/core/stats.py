import json
import os

STATS_FILE = "data/stats.json"

def increment_stat(key: str):
    os.makedirs("data", exist_ok=True)
    stats = {}
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            try:
                stats = json.load(f)
            except:
                stats = {}
    
    stats[key] = stats.get(key, 0) + 1
    
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

def get_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    return {}

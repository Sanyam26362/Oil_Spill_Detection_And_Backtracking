import sys
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from app.services.weather_service import WeatherService
from app.services.drift_engine import DriftEngine

weather_yearly_dir = PROJECT_ROOT / "data" / "weather" / "raw" / "yearly"
ocean_yearly_dir = PROJECT_ROOT / "data" / "ocean" / "raw" / "yearly"

ws = WeatherService(weather_yearly_dir=weather_yearly_dir, ocean_yearly_dir=ocean_yearly_dir)

lat = 35.05
lon = 24.04
time = datetime(2019, 7, 15, 12, 0, 0, tzinfo=timezone.utc)

try:
    env = ws.get_velocity(lat, lon, time)
    print(env)
    
    de = DriftEngine(ws)
    traj = de.forward_drift(lat, lon, time, 6.0, 15)
    print("Trajectory states:", len(traj.states))
except Exception as e:
    print("Error:", e)

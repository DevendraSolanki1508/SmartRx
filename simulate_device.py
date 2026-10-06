"""Pretends to be the ESP32 shelf node, so you can demo without hardware.
    python simulate_device.py            normal readings every 2 s
    python simulate_device.py --breach   cold-store temperature climbs above 8 C
"""
import json, math, sys, time, urllib.request

URL = "http://localhost:8000/readings"
breach = "--breach" in sys.argv


def send(**body):
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


i = 0
while True:
    t = 4.8 + math.sin(i / 4) * 0.8 + (min(i, 12) * 0.45 if breach else 0)
    r = send(shelf_id="C1", weight_g=1240, temp_c=round(t, 1), humidity=52, door_open=False)
    print(f"C1 temp {t:.1f} C -> units {r['estimated_units']}, excursion={r['excursion']}")
    i += 1
    time.sleep(2)

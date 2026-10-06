# SmartRx

Windows quick start: double-click run_demo.bat (needs Python 3.10+).
Live demo without hardware: python simulate_device.py [--breach]

Run:
    pip install -r requirements.txt
    rm -f smartrx.db && python seed.py      # demo data + 2 drafted purchase orders
    uvicorn app.main:app --reload
Open http://localhost:8000 (dashboard) or /docs (API). Test: `pytest -q`.

Dashboard: reads the API when served by FastAPI; falls back to built-in demo data when the
backend is unreachable. Use `?api=http://host:8000` if the page is hosted elsewhere.

Evaluation: python simulate.py  (writes results.json; the dashboard comparison panel reads it)

Implemented: FEFO dispensing, alerts, sensor ingest, purchase-order generation
(forecast = recent mean x weekday factor), approve/reject, audit log.
Not yet: real forecasting model (Prophet/LightGBM), sending POs to suppliers (approve only
marks them approved), MQTT, auth.

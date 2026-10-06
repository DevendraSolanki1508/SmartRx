"""90-day evaluation: SmartRx forecast-based reordering vs a fixed threshold rule.
    python simulate.py            (30 random runs, writes results.json)
Both policies see identical demand, lead times and supplier shelf life in every run.
"""
import json, math, random, statistics, sys
from datetime import date

DAYS, EVAL_START, RUNS = 120, 30, 30           # metrics are counted over days 30..119 (90 days)
# name, base daily demand, shelf life (days), supplier lead time (days), supplier case size (minimum order multiple)
PROFILES = [("Paracetamol 650", 15, 365, 2, 50), ("Amoxicillin 500", 12, 180, 2, 40), ("Metformin 500", 10, 365, 3, 50),
            ("Cetirizine 10", 9, 240, 2, 30), ("Pantoprazole 40", 8, 270, 3, 30), ("Insulin glargine", 4, 90, 3, 10),
            ("Hepatitis B vaccine", 1.5, 60, 3, 10), ("Azithromycin 500", 6, 150, 2, 20),
            ("Antifungal cream", 0.8, 90, 3, 24), ("Vitamin D3 60K", 1.2, 120, 3, 24)]


def to_case(x, c):
    return -(-int(math.ceil(x)) // c) * c


def poisson(rng, lam):
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def make_med(rng, name, d, life, lead, case):
    amp, per, ph, wph = rng.uniform(0.15, 0.45), rng.uniform(50, 90), rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    surge = (rng.randint(30, 90), 14, rng.uniform(1.5, 2.0)) if rng.random() < 0.4 else None  # outbreak
    drop = (rng.randint(40, 80), 0.3) if rng.random() < 0.3 else None   # demand collapse (substitution, season end)
    dem = []
    for t in range(DAYS):
        lam = d * (1 + amp * math.sin(2 * math.pi * t / per + ph)) * (1 + 0.25 * math.sin((t % 7) * 0.9 + wph))
        if surge and surge[0] <= t < surge[0] + surge[1]:
            lam *= surge[2]
        if drop and t >= drop[0]:
            lam *= drop[1]
        dem.append(poisson(rng, lam))
    return {"name": name, "d": d, "life": life, "lead": lead, "case": case, "dem": dem,
            "lead_t": [max(1, lead + rng.choice([-1, 0, 0, 1])) for _ in range(DAYS)],
            "rem_t": [int(life * rng.uniform(0.35, 1.0)) for _ in range(DAYS)]}


def threshold_order(m, pos):
    R, Q = math.ceil(m["d"] * (m["lead"] + 2)), math.ceil(m["d"] * 14)   # tuned on the true long-run mean
    return to_case(Q, m["case"]) if pos <= R else 0


def smart_order(m, t, sales, pos):
    if t < 14:
        return threshold_order(m, pos)
    L = m["lead"]
    recent = sum(sales[-14:]) / 14
    last = sales[-28:]
    mean28 = sum(last) / len(last)
    off = len(sales) - len(last)
    wf = [1.0] * 7
    if mean28 > 0:
        for w in range(7):
            v = [s for i, s in enumerate(last) if (off + i) % 7 == w]
            wf[w] = (sum(v) / len(v)) / mean28 if v else 1.0
    f = lambda a, b: sum(recent * wf[(t + k) % 7] for k in range(a, b + 1))
    need = f(1, L + 7)
    safety = math.ceil(0.25 * need)
    if pos - f(1, L) >= safety:
        return 0
    qty = need + safety - pos
    cap = f(1, L + min(30, m["life"] // 3)) - pos          # never order more than can sell before it expires
    q = min(qty, cap)
    if q <= 0:
        return 0
    q = to_case(q, m["case"])
    # expiry guard: skip a case that cannot be sold within the guaranteed shelf life, unless a stockout is imminent
    if pos + q > f(1, L + int(0.6 * m["life"])) and pos - f(1, L) >= 0:
        return 0
    return q


def run(policy, m):
    inv, pipe, sales = [[int(m["life"] * 0.8), to_case(m["d"] * (m["lead"] + 7), m["case"])]], [], []
    expired = received = unmet = short_days = dem_total = inv_sum = 0
    opening = 0
    for t in range(DAYS):
        ev = t >= EVAL_START
        if t == EVAL_START:
            opening = sum(b[1] for b in inv)
        for p in [p for p in pipe if p[0] == t]:
            inv.append([t + p[2], p[1]]); pipe.remove(p)
            received += p[1] if ev else 0
        for b in [b for b in inv if b[0] <= t]:
            expired += b[1] if ev else 0; inv.remove(b)
        inv.sort()
        need = m["dem"][t]; got = 0
        for b in inv:
            take = min(b[1], need - got); b[1] -= take; got += take
        inv = [b for b in inv if b[1] > 0]
        sales.append(got)
        if ev:
            dem_total += need; unmet += need - got; short_days += need > got; inv_sum += sum(b[1] for b in inv)
        pos = sum(b[1] for b in inv) + sum(p[1] for p in pipe)
        q = threshold_order(m, pos) if policy == "threshold" else smart_order(m, t, sales, pos)
        if q > 0:
            pipe.append([t + m["lead_t"][t], q, m["rem_t"][t]])
    return {"expired": expired, "avail": opening + received, "short_days": short_days, "unmet": unmet,
            "dem": dem_total, "inv": inv_sum / (DAYS - EVAL_START)}


def main(runs=RUNS):
    res = {"threshold": [], "smartrx": []}
    for seed in range(runs):
        rng = random.Random(seed)
        meds = [make_med(rng, *p) for p in PROFILES]
        for pol, key in (("threshold", "threshold"), ("smart", "smartrx")):
            r = [run(pol, m) for m in meds]
            res[key].append({"wastage_pct": 100 * sum(x["expired"] for x in r) / sum(x["avail"] for x in r),
                             "stockout_day_pct": 100 * sum(x["short_days"] for x in r) / (len(r) * (DAYS - EVAL_START)),
                             "fill_rate_pct": 100 * (1 - sum(x["unmet"] for x in r) / sum(x["dem"] for x in r)),
                             "avg_inventory_units": sum(x["inv"] for x in r)})
    out = {"generated": date.today().isoformat(), "runs": runs, "days_evaluated": DAYS - EVAL_START, "medicines": len(PROFILES)}
    for key, rows in res.items():
        out[key] = {k: {"mean": round(statistics.mean(r[k] for r in rows), 2), "std": round(statistics.pstdev(r[k] for r in rows), 2)}
                    for k in rows[0]}
    out["smartrx_better_in_runs_pct"] = {k: round(100 * sum((a[k] < b[k]) if k != "fill_rate_pct" else (a[k] > b[k])
                                         for a, b in zip(res["smartrx"], res["threshold"])) / runs) for k in res["smartrx"][0]}
    return out


if __name__ == "__main__":
    out = main()
    json.dump(out, open("results.json", "w"), indent=2)
    for k in out["threshold"]:
        print(f"{k:22s} threshold {out['threshold'][k]['mean']:8.2f} +/- {out['threshold'][k]['std']:.2f}   "
              f"smartrx {out['smartrx'][k]['mean']:8.2f} +/- {out['smartrx'][k]['std']:.2f}   better in {out['smartrx_better_in_runs_pct'][k]}% of runs")

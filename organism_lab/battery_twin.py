"""Offline synthetic battery-line monitoring experiment. NOT a physical process controller."""
from random import Random
from statistics import mean

def synthetic_line(*, seed=7, samples=200):
    if not isinstance(samples, int) or samples < 2 or samples > 100000:
        raise ValueError("samples must be between 2 and 100000")
    rng = Random(seed)
    rows = []
    for i in range(samples):
        temperature = round(22 + rng.uniform(-5, 8), 2)
        humidity = round(45 + rng.uniform(-20, 20), 2)
        speed = round(10 + rng.uniform(-3, 4), 2)
        # Deliberately synthetic target with transparent causal assumptions.
        defect = temperature > 27 or humidity > 60 or speed > 12
        energy = round(2.0 + 0.08 * speed + 0.03 * abs(temperature - 22), 3)
        rows.append({"sample": i, "temperature_c": temperature,
                     "humidity_pct": humidity, "speed": speed,
                     "defect": defect, "energy_kwh": energy})
    return rows

def evaluate(rows, *, temperature_limit=26, humidity_limit=58, speed_limit=12):
    if not rows:
        raise ValueError("Need observations")
    tp = fp = fn = tn = 0
    for row in rows:
        alert = (row["temperature_c"] > temperature_limit or
                 row["humidity_pct"] > humidity_limit or row["speed"] > speed_limit)
        defect = row["defect"]
        if alert and defect: tp += 1
        elif alert: fp += 1
        elif defect: fn += 1
        else: tn += 1
    return {"samples": len(rows), "true_positive": tp, "false_positive": fp,
            "false_negative": fn, "true_negative": tn,
            "recall": tp / (tp + fn) if tp + fn else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "mean_energy_kwh": mean(row["energy_kwh"] for row in rows),
            "warning": "Synthetic illustrative data; not a validated industrial model."}

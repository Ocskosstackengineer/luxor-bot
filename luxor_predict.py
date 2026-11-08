"""
luxor_predict.py - Luxor tippgenerátor és backtest (75 szám, oszloponként 4 = 20 szám)

Használat (Python 3.9+, numpy):
    python luxor_predict.py adat.csv                     # tipp a következő hétre (kerules módszer)
    python luxor_predict.py adat.csv -m forro52          # más módszer
    python luxor_predict.py adat.csv --backtest          # minden módszer mérése a véletlenhez képest

Bemenet: a szerencsejatek.hu luxor.csv formátuma, soronként:
    év;hét;dátum;határszám;első kép;első keret;kihúzott db;szám1;szám2;... (húzási sorrendben)
A sorrend mindegy (év+hét szerint rendez).

Módszerek (a 1311 hetes backtestben EGYIK SEM tért el mérhetően a véletlentől):
    kerules    - az előző hét első 36 húzásában szereplő számok kerülése (a legjobb mért, z = +2,2,
                 ami ennyi stratégia mellett a véletlen ingadozáson belül van)
    forroN     - leggyakoribb számok az utolsó N hét első 36 húzásában (pl. forro52)
    hidegN     - legritkább számok az utolsó N hétben
    esedekes   - régóta nem húzott (első 36-ban) számok
    veletlen   - egyenletes véletlen

Az első 36 húzást használja, mert annyi minden héten van; a sorsolás vége (a 37+. szám)
attól függ, mikor lesz valakinek telitalálata.
"""
import argparse
import math
import sys

import numpy as np

COLS = ["L", "U", "X", "O", "R"]
K36 = 36


def parse_line(line):
    p = line.rstrip("\r\n").rstrip(";").split(";")
    if len(p) < 10 or not p[0].strip().isdigit():
        return None
    nums = [int(x) for x in p[7:] if x.strip()]
    if len(set(nums)) != len(nums) or not all(1 <= n <= 75 for n in nums) or len(nums) < K36:
        return None
    return {"year": int(p[0]), "week": int(p[1]), "date": p[2].strip(),
            "counters": [int(x or 0) for x in p[3:7]], "nums": nums}


def load_rows(path):
    with open(path, encoding="utf-8-sig") as f:
        rows = [r for r in (parse_line(l) for l in f) if r]
    return sorted(rows, key=lambda r: (r["year"], r["week"]))


def first36(rows):
    X = np.zeros((len(rows), 75), dtype=np.int32)
    for t, r in enumerate(rows):
        X[t, np.array(r["nums"][:K36]) - 1] = 1
    return X


def score(method, X, rng):
    """Pontszám mind a 75 számra a múltbeli első-36 mátrixból (X: hetek x 75)."""
    n = len(X)
    if method == "veletlen" or n == 0:
        return rng.random(75)
    if method == "kerules":
        return -X[-1] + rng.random(75) * 1e-3
    if method.startswith("forro"):
        return X[-int(method[5:] or 52):].sum(0).astype(float)
    if method.startswith("hideg"):
        return -X[-int(method[5:] or 52):].sum(0).astype(float)
    if method == "esedekes":
        seen = X[::-1].argmax(0).astype(float)
        seen[X.sum(0) == 0] = n
        return seen
    sys.exit(f"Ismeretlen módszer: {method}")


def pick(method, X, rng):
    """{'L': [4 szám], ...} és a kép javasolt 6 száma (U, X, O oszlop 2-2 legjobbja)."""
    s = score(method, X, rng) + rng.random(75) * 1e-9
    cols, kep = {}, []
    for c, name in enumerate(COLS):
        idx = np.arange(15 * c, 15 * c + 15)
        best = idx[np.argsort(-s[idx])[:4]]
        cols[name] = sorted((best + 1).tolist())
        if name in ("U", "X", "O"):
            kep += sorted((best[:2] + 1).tolist())
    return cols, kep


def all_numbers(cols):
    return sorted(n for c in COLS for n in cols[c])


def hyper(k_drawn, picks=20, N=75):
    p = k_drawn / N
    mean = picks * p
    var = picks * p * (1 - p) * (N - picks) / (N - 1)
    return mean, var


def backtest(rows, methods, start, rng):
    X = first36(rows)
    ts = range(start, len(rows))
    mean0, var0 = hyper(K36)
    se = math.sqrt(var0 / len(ts))
    print(f"\nBacktest: {len(ts)} hét, 20 szám (4/oszlop), találat az első 36 húzásban")
    print(f"Véletlen várható: {mean0:.3f}  (95%-os sáv: ±{1.96 * se:.3f})\n")
    print(f"{'módszer':12s} {'átlag':>7s} {'eltérés':>8s} {'z':>6s}")
    for m in methods:
        h = []
        for t in ts:
            cols, _ = pick(m, X[:t], rng)
            h.append(sum(X[t, n - 1] for n in all_numbers(cols)))
        h = np.array(h, float)
        z = (h.mean() - mean0) / se
        print(f"{m:12s} {h.mean():7.3f} {h.mean() - mean0:+8.3f} {z:+6.2f}")
    print("\n|z| < 2: nem különböztethető meg a véletlentől; sok módszernél egy-két |z|≈2 "
          "a véletlenből is várható.")


def main():
    ap = argparse.ArgumentParser(description="Luxor tippgenerátor és backtest")
    ap.add_argument("csv")
    ap.add_argument("-m", "--method", default="kerules")
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--start", type=int, default=300)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    rows = load_rows(a.csv)
    print(f"Beolvasva: {len(rows)} hét ({rows[0]['year']}/{rows[0]['week']} - "
          f"{rows[-1]['year']}/{rows[-1]['week']})")
    if a.backtest:
        backtest(rows, ["veletlen", "kerules", "esedekes", "forro26", "forro52", "forro260",
                        "hideg26", "hideg52", "hideg260"], a.start, rng)
        return
    cols, kep = pick(a.method, first36(rows), rng)
    for c in COLS:
        print(f"{c}: {' '.join(f'{n:>2}' for n in cols[c])}")
    print(f"Kép (középre): {' '.join(map(str, kep))}")


if __name__ == "__main__":
    main()

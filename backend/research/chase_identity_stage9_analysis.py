"""Stage IX Chase Identity - boundary method comparison on real cross-era data."""
import math

# top-30 prices per set (from pokemon_canonical_card_market_prices_latest, 2026-08-31)
TOP30 = {
"Base":[868.56,225.89,181.68,76.86,76.52,69.59,62.57,56.69,48.74,48.66,40.07,35.19,33.93,33.87,28.71,19.83,16.82,16.54,11.10,10.96,10.51,9.31,9.00,8.74,8.62,7.68,6.64,6.36,6.23,5.78],
"Jungle":[155.70,150.86,128.45,97.18,97.09,87.24,81.52,78.38,61.35,56.95,50.46,43.93,43.48,43.01,38.22,37.86,37.50,37.45,30.61,27.42,20.82,18.69,17.32,16.26,15.62,14.93,13.18,12.10,11.32,10.95],
"Fossil":[601.49,188.98,151.08,117.42,117.29,80.06,79.54,65.68,58.05,52.29,50.21,45.87,42.85,41.00,40.40,34.85,26.22,25.78,24.16,23.92,22.79,18.52,14.13,13.96,13.44,11.22,10.73,10.32,10.19,7.04],
"Neo Destiny":[4249.99,3998.99,3000.00,1051.50,595.00,474.97,471.66,435.00,399.99,380.39,374.99,299.99,295.28,295.00,290.00,200.00,192.89,168.16,152.97,148.53,140.14,114.32,89.50,87.66,86.62,84.87,69.00,65.77,61.47,57.05],
"Black & White":[155.71,118.51,98.27,7.90,7.86,7.65,7.40,4.98,4.55,4.46,4.11,3.91,3.76,3.26,2.98,2.95,2.89,2.85,2.79,2.74,2.63,2.45,2.40,2.34,2.18,1.59,1.25,1.13,1.03,1.01],
"Champion's Path":[268.24,228.70,18.89,7.02,6.83,4.75,4.59,3.97,3.93,2.82,2.55,2.43,2.25,2.23,1.88,1.75,1.71,1.67,1.49,1.47,1.44,1.19,0.98,0.97,0.84,0.70,0.36,0.32,0.29,0.29],
"Team Up":[3783.92,1764.71,843.13,465.88,379.76,353.46,291.37,244.01,241.21,192.57,174.79,160.75,141.74,139.66,135.98,126.72,113.31,91.20,83.61,76.31,69.72,62.67,61.92,57.46,57.35,52.11,51.44,51.32,44.19,43.04],
"Cosmic Eclipse":[568.04,494.20,418.85,320.63,271.65,268.38,247.88,234.68,225.09,207.32,183.42,138.07,134.38,129.82,126.49,121.80,106.18,102.85,98.75,94.31,93.16,92.95,88.41,80.59,79.64,71.86,68.95,67.03,65.94,65.06],
"Evolving Skies":[2310.74,1249.13,538.69,484.62,412.53,390.25,390.07,310.98,239.44,204.96,160.56,152.92,125.19,84.43,81.73,74.37,60.47,59.61,49.13,43.68,39.64,39.54,37.16,36.66,28.71,27.32,25.03,24.60,24.40,22.08],
"Crown Zenith":[49.36,16.24,13.96,13.54,12.83,11.84,9.98,8.44,7.79,7.36,6.41,6.36,4.38,4.06,3.97,3.81,3.70,3.68,3.23,3.10,3.02,2.91,2.81,2.76,2.56,2.45,2.33,2.19,2.12,2.03],
"Paldean Fates":[929.82,280.79,172.99,78.28,51.19,50.73,46.89,39.35,37.17,30.70,29.14,25.95,25.04,24.93,24.78,19.26,18.59,17.96,17.30,15.76,15.51,15.41,14.83,13.54,13.21,13.12,12.36,12.12,12.01,11.99],
"Paradox Rift":[118.92,55.13,54.96,48.50,45.60,40.84,39.50,36.43,34.11,31.46,30.84,29.31,27.02,26.93,25.93,24.14,23.33,21.81,20.69,19.17,17.51,16.97,16.53,15.83,15.56,15.50,15.42,13.76,12.83,11.62],
"Phantasmal Flames":[701.95,273.86,26.90,21.67,20.42,19.37,18.30,15.02,14.50,6.91,5.94,5.71,5.66,5.37,4.80,4.66,4.20,3.04,2.89,2.55,2.49,2.41,2.33,2.13,2.01,1.95,1.90,1.57,1.51,1.43],
"Prismatic Evolutions":[1456.79,541.74,340.87,320.12,295.02,289.46,206.50,194.89,183.16,167.14,106.83,102.40,68.07,63.95,60.49,50.52,47.43,42.64,35.69,32.30,30.01,29.50,28.64,26.04,25.42,25.27,20.18,18.85,17.95,17.44],
"Shrouded Fable":[75.33,59.77,58.30,53.52,50.03,42.58,39.16,33.60,32.44,31.53,31.24,29.11,27.08,26.82,23.76,23.09,21.46,21.38,19.51,18.99,17.01,16.91,16.67,13.12,13.05,11.91,7.96,7.93,7.59,7.23],
"Ascended Heroes":[1033.08,975.64,645.80,387.31,341.22,305.62,234.90,154.89,149.95,128.90,86.46,84.27,78.16,71.64,65.44,60.24,59.98,58.17,55.99,55.99,55.07,49.76,40.47,38.98,38.21,32.09,20.70,19.16,17.74,12.84],
}

# set-level context: (n_cards, set_value, hhi, n_eff, median_price)
CTX = {
"Base":(102,2175,0.185019,5.40,2.57),
"Jungle":(64,1638,0.047876,20.89,9.25),
"Fossil":(62,2075,0.113071,8.84,6.58),
"Neo Destiny":(113,19354,0.123345,8.11,14.88),
"Black & White":(115,504,0.190828,5.24,0.47),
"Champion's Path":(81,585,0.364215,2.75,0.21),
"Team Up":(196,10818,0.162974,6.14,0.51),
"Cosmic Eclipse":(271,6432,0.035159,28.44,0.42),
"Evolving Skies":(237,8260,0.120289,8.31,0.32),
"Crown Zenith":(161,260,0.058571,17.07,0.20),
"Paldean Fates":(247,2645,0.143038,6.99,2.63),
"Paradox Rift":(266,1221,0.028145,35.53,0.19),
"Phantasmal Flames":(132,1209,0.390547,2.56,0.18),
"Prismatic Evolutions":(181,5008,0.119531,8.37,0.28),
"Shrouded Fable":(107,878,0.041828,23.91,0.30),
"Ascended Heroes":(305,5673,0.092439,10.82,0.24),
}

ERA = {
"Base":"vintage","Jungle":"vintage","Fossil":"vintage","Neo Destiny":"vintage",
"Black & White":"mid","Champion's Path":"swsh","Team Up":"sm","Cosmic Eclipse":"sm",
"Evolving Skies":"swsh","Crown Zenith":"swsh","Paldean Fates":"sv","Paradox Rift":"sv",
"Phantasmal Flames":"sv","Prismatic Evolutions":"sv","Shrouded Fable":"sv","Ascended Heroes":"sv",
}


def log_gaps(prices):
    return [math.log(prices[i]) - math.log(prices[i + 1]) for i in range(len(prices) - 1)]


def method_b_cliff(prices, max_k=15, min_gap=0.35):
    """Largest log gap in the upper tail = Core boundary."""
    g = log_gaps(prices)[:max_k]
    best = max(range(len(g)), key=lambda i: g[i])
    return (best + 1, g[best]) if g[best] >= min_gap else (None, g[best])


def method_e_outlier(prices, all_median, k_mult=None):
    """Robust log-scale separation above the set's ordinary population."""
    logs = [math.log(p) for p in prices]
    med = math.log(all_median)
    devs = sorted(abs(x - med) for x in logs)
    mad = devs[len(devs) // 2] or 1e-9
    return [(x - med) / (1.4826 * mad) for x in logs]


def main():
    print("%-22s %-7s %6s %6s | %-14s | %-10s | %s" % (
        "set", "era", "n_eff", "top1%", "cliff(Core,gap)", "cum@cliff", "shape"))
    print("-" * 108)
    for name, prices in sorted(TOP30.items(), key=lambda kv: -CTX[kv[0]][3]):
        n, sv, hhi, neff, med = CTX[name]
        k, gap = method_b_cliff(prices)
        shares = [p / sv for p in prices]
        cum = sum(shares[:k]) * 100 if k else None
        shape = ("flat/deep" if neff >= 15 else "deep" if neff >= 8 else
                 "concentrated" if neff >= 4 else "hero")
        print("%-22s %-7s %6.2f %6.2f | %-14s | %-10s | %s" % (
            name, ERA[name], neff, shares[0] * 100,
            ("%d, %.2f" % (k, gap)) if k else ("none, %.2f" % gap),
            ("%.1f%%" % cum) if cum else "-", shape))

    print("\n\nN_eff as literal K -- does 1/HHI equal the cliff-implied Core?")
    print("%-22s %8s %8s %8s" % ("set", "n_eff", "cliff K", "verdict"))
    print("-" * 52)
    agree = 0
    for name, prices in TOP30.items():
        neff = CTX[name][3]
        k, _ = method_b_cliff(prices)
        ok = k is not None and abs(neff - k) <= 1.0
        agree += ok
        print("%-22s %8.2f %8s %8s" % (name, neff, k if k else "-", "OK" if ok else "NO"))
    print("\n1/HHI within +/-1 of the cliff Core in %d of %d sets" % (agree, len(TOP30)))

    print("\n\nSCALE INVARIANCE (Phase 12): multiply every price by 0.5x / 2x / 10x")
    bad = 0
    for name, prices in TOP30.items():
        base_k, _ = method_b_cliff(prices)
        for mult in (0.5, 2.0, 10.0):
            k2, _ = method_b_cliff([p * mult for p in prices])
            if k2 != base_k:
                bad += 1
                print("  CHANGED %-22s %sx  %s -> %s" % (name, mult, base_k, k2))
    print("  tier changes under uniform scaling: %d  %s" % (bad, "PASS" if bad == 0 else "FAIL"))

    print("\n\nRELATIVE SIGNIFICANCE (Phase 6): top card share vs ordinary card share")
    print("%-22s %10s %10s %12s %10s" % ("set", "top1 share", "med share", "ratio", "top1 $"))
    print("-" * 68)
    for name, prices in sorted(TOP30.items(), key=lambda kv: -CTX[kv[0]][3]):
        n, sv, hhi, neff, med = CTX[name]
        print("%-22s %9.3f%% %9.4f%% %11.0fx %10.2f" % (
            name, prices[0] / sv * 100, med / sv * 100, (prices[0] / med), prices[0]))


main()


# log-scale population statistics over the FULL set (not just top 30)
LOGSTAT = {  # name: (log_median, log_mad, n)
"Ascended Heroes":(-1.4271,0.7802,305), "Base":(0.9433,0.9670,102),
"Black & White":(-0.7550,0.5543,115), "Champion's Path":(-1.5606,0.3365,81),
"Cosmic Eclipse":(-0.8675,0.8473,271), "Crown Zenith":(-1.6094,0.9163,161),
"Evolving Skies":(-1.1394,1.6740,237), "Fossil":(1.8833,1.5515,62),
"Jungle":(2.2234,1.5541,64), "Neo Destiny":(2.7000,1.4185,113),
"Paldean Fates":(0.9670,1.3863,247), "Paradox Rift":(-1.6607,0.9985,266),
"Phantasmal Flames":(-1.7148,0.9445,132), "Prismatic Evolutions":(-1.2730,1.1451,181),
"Shrouded Fable":(-1.2040,1.0986,107), "Team Up":(-0.6832,0.8309,196),
}


def robust_z(price, name):
    med, mad, _ = LOGSTAT[name]
    return (math.log(price) - med) / (1.4826 * mad)


def method_e(name, prices, core_z=3.5, ext_z=2.0):
    core = sum(1 for p in prices if robust_z(p, name) >= core_z)
    ext = sum(1 for p in prices if robust_z(p, name) >= ext_z)
    return core, ext


print("\n\n" + "=" * 96)
print("METHOD E - robust log z above the set's own ordinary population")
print("=" * 96)
print("%-22s %-7s %6s | %5s %5s | %6s | %s" % (
    "set", "era", "n_eff", "Core", "Ext", "top1 z", "Core prices"))
print("-" * 96)
for nm, pr in sorted(TOP30.items(), key=lambda kv: -CTX[kv[0]][3]):
    neff = CTX[nm][3]
    c, e = method_e(nm, pr)
    print("%-22s %-7s %6.2f | %5d %5d | %6.2f | %s" % (
        nm, ERA[nm], neff, c, e, robust_z(pr[0], nm),
        ", ".join("%.0f" % p for p in pr[:c][:6]) + (" ..." if c > 6 else "")))

print("\n\nMETHOD E SCALE INVARIANCE (log-median shifts with the multiplier, so z is invariant)")
bad = 0
for nm, pr in TOP30.items():
    med, mad, n = LOGSTAT[nm]
    base = method_e(nm, pr)
    for mult in (0.5, 2.0, 10.0):
        LOGSTAT[nm] = (med + math.log(mult), mad, n)
        if method_e(nm, [p * mult for p in pr]) != base:
            bad += 1
            print("  CHANGED", nm, mult)
    LOGSTAT[nm] = (med, mad, n)
print("  tier changes under uniform scaling: %d  %s" % (bad, "PASS" if bad == 0 else "FAIL"))

print("\n\nz-THRESHOLD SENSITIVITY (Core count at several z cutoffs)")
print("%-22s %5s %5s %5s %5s %5s" % ("set", "z2.5", "z3.0", "z3.5", "z4.0", "z5.0"))
print("-" * 52)
for nm, pr in sorted(TOP30.items(), key=lambda kv: -CTX[kv[0]][3]):
    row = [sum(1 for p in pr if robust_z(p, nm) >= z) for z in (2.5, 3.0, 3.5, 4.0, 5.0)]
    print("%-22s %5d %5d %5d %5d %5d" % (nm, *row))

"""Family-wise arithmetic from the per-reading null rates measured in sim1..sim4 (percent).  'any' = any non-null verdict word,
'pos' = the word that favours a change.  Rates marked UB are upper bounds (only the t / halves part of a multi-condition rule was simulated).
Independence across readings is ASSUMED for P(at least one); the readings share one year of one market, so the true figure is lower,
while the expected count (the plain sum) does not depend on independence."""
import math
R = [  # (reading, any %, pos %, note)
 ("live swing KR", 5.3, 5.3, "UB t>=2.24 & IC>=0.02 & halves, sim1 fixed"), ("live swing US", 5.3, 5.3, "UB"),
 ("live long KR", 5.83, 5.83, "UB t>=2.24, sim2 B"), ("live long US", 5.83, 5.83, "UB"),
 ("kr avoid marks", 5.2, 5.2, "UB t<=-2.24 lag 20"),
 ("score split KR", 14.46, 7.21, "two-sided 2.0 lag 20"), ("score split US", 14.46, 7.21, ""),
 ("fund period KR", 3.88, 1.84, "two-sided 3.0; pos = TRAILING_BETTER, applies itself"), ("fund period US", 3.88, 1.84, ""),
 ("regime weights KR", 0, 0, "figures only"), ("regime weights US", 0, 0, "figures only"),
 ("us challenger swing", 5.11, 5.11, "UB t>=2.24 n48 step5 lag4"), ("us challenger long", 5.34, 5.34, "UB n151 lag13"),
 ("kr forward price", 5.11, 5.11, "UB"), ("kr forward fund", 5.11, 5.11, "UB"), ("kr forward events", 5.11, 5.11, "UB"),
 ("kr cap universe", 7.21, 7.21, "UB t>=2.0 lag 20 & halves"), ("kr traded universe", 14.46, 7.21, "two-sided 2.0"),
 ("kr swing challenger", 3.52, 3.52, "12 samples plain t>=2.0"), ("kr swing prior", 7.18, 3.52, "12 samples two-sided"),
 ("kr challenger swing", 13.73, 7.0, "UB two-sided n48"), ("kr challenger long", 14.54, 7.22, "UB two-sided n151"),
 ("kr method 120", 0, 0, "NO_PRIMARY: figures only"), ("kr method 240", 0, 0, "figures only"),
 ("committee KR (6 portfolios)", 6 * 0.43, 6 * 0.19, "Bonferroni UB over 6"), ("committee US (6 portfolios)", 6 * 0.43, 6 * 0.19, ""),
]
def fw(ps): return 100 * (1 - math.prod(1 - p / 100 for p in ps))
print("registry readings:", len(R))
print("expected count of chance non-null verdicts: %.2f ; of chance 'positive' verdicts: %.2f" % (sum(r[1] for r in R) / 100, sum(r[2] for r in R) / 100))
print("P(at least one non-null) if independent: %.1f%% ; P(at least one positive): %.1f%%" % (fw([r[1] for r in R]), fw([r[2] for r in R])))
print("self-applying:")
print("  fund period x2  TRAILING_BETTER by chance: %.2f%% (each 1.84)" % fw([1.84, 1.84]))
print("  rank book x2    ADOPT by chance: %.2f%% (each 3.79)" % fw([3.79, 3.79]))
print("  turnover x2     ADOPT by chance given cheaper: %.2f%% (each 49.43)" % fw([49.43, 49.43]))
print("  any of the six self-applying readings changes a rule by chance: %.1f%%" % fw([1.84, 1.84, 3.79, 3.79, 49.43, 49.43]))
print("  same without turnover: %.1f%%" % fw([1.84, 1.84, 3.79, 3.79]))
print("historical primary tests at nominal one-sided 1.25%% (t>=2.24): 2 (QSF1.2) + 2 (PIT) + 2 (open) + 1 (OOS) ... see report; at the measured 5.5%% for h252 n142: family of the 3 US long reruns is one sample, not three")

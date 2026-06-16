"""
Unit tests for the keyword rule engine.
Run directly: python watcher/test_rules.py
All tests must pass before committing.
"""
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from watcher.rules import evaluate, evaluate_for_users, RuleResult


def test(name: str, condition: bool, detail: str = ""):
    status = "✓" if condition else "✗ FAIL"
    print(f"  {status}  {name}")
    if not condition:
        print(f"         Detail: {detail}")
    return condition


def run_all_tests() -> bool:
    all_passed = True
    print()

    # ── High signal tests ─────────────────────────────────────────────────────
    print("High-signal keywords:")

    r = evaluate("Pogacar attacks on the final climb. Gap is opening.")
    all_passed &= test("attack → passes",       r.passes,                   str(r))
    all_passed &= test("signal level = high",   r.signal_level == "high",   r.signal_level)
    all_passed &= test("keyword captured",      "attack" in r.matched_keywords or "attacks" in r.matched_keywords, r.matched_keywords)

    r = evaluate("Crash in the peloton at km 45. Several riders down.")
    all_passed &= test("crash → passes",        r.passes, str(r))
    all_passed &= test("signal = high",         r.signal_level == "high", r.signal_level)

    r = evaluate("Vingegaard abandons. DNS confirmed.")
    all_passed &= test("abandon → passes",      r.passes, str(r))

    r = evaluate("Breakaway of 5 riders established. Gap 2 minutes.")
    all_passed &= test("breakaway → passes",    r.passes, str(r))

    r = evaluate("Van Eetvelt dropped from the lead group on the climb.")
    all_passed &= test("dropped → passes",      r.passes, str(r))

    print()

    # ── Low signal tests ──────────────────────────────────────────────────────
    print("Low-signal filters:")

    r = evaluate("100 km done. Average speed 42.3 km/h.")
    all_passed &= test("km done → blocked",     not r.passes, str(r))

    r = evaluate("Statistics update: most riders per team active today.")
    all_passed &= test("statistics → blocked",  not r.passes, str(r))

    r = evaluate("Weather update: temperature 28 degrees, wind from north.")
    all_passed &= test("weather → blocked",     not r.passes, str(r))

    r = evaluate("Family active in different races today.")
    all_passed &= test("family widget → blocked", not r.passes, str(r))

    print()

    # ── Medium signal tests ───────────────────────────────────────────────────
    print("Medium-signal keywords:")

    r = evaluate("Peloton reaches the summit. Sprint for the KOM points.")
    all_passed &= test("summit + sprint → passes",     r.passes, str(r))
    all_passed &= test("signal = medium",              r.signal_level == "medium", r.signal_level)

    r = evaluate("Peloton chasing the break. GC riders look nervous.")
    all_passed &= test("peloton + gc → passes",        r.passes, str(r))

    r = evaluate("Summit of the climb.")
    all_passed &= test("single medium only → blocked", not r.passes, str(r))

    print()

    # ── Rider match tests ─────────────────────────────────────────────────────
    print("Rider matching:")

    profile = {"riders_mentioned": ["tadej-pogacar", "remco-evenepoel"]}

    r = evaluate("Pogacar reaches the summit first.", profile)
    all_passed &= test("last name match → passes",        r.passes,       str(r))
    all_passed &= test("rider_match = True",              r.rider_match,  str(r))

    r = evaluate("Evenepoel is in the chasing group.", profile)
    all_passed &= test("medium + rider → passes",         r.passes,       str(r))
    all_passed &= test("rider_match = True",              r.rider_match,  str(r))

    r = evaluate("Vingegaard is in the chasing group.", profile)
    all_passed &= test("medium + no rider match → blocked", not r.passes, str(r))
    all_passed &= test("rider_match = False",             not r.rider_match, str(r))

    r = evaluate("Remco Evenepoel accelerates on the climb.", profile)
    all_passed &= test("full name match → passes",        r.passes, str(r))

    print()

    # ── Edge cases ────────────────────────────────────────────────────────────
    print("Edge cases:")

    r = evaluate("")
    all_passed &= test("empty diff → blocked",            not r.passes, str(r))

    r = evaluate("ok")
    all_passed &= test("too short → blocked",             not r.passes, str(r))

    r = evaluate("100 km done. Average speed 42 km/h. Crash in peloton!")
    all_passed &= test("low + high → high wins",          r.passes,              str(r))
    all_passed &= test("signal = high",                   r.signal_level == "high", r.signal_level)

    r = evaluate(None)
    all_passed &= test("None diff → blocked",             not r.passes, "returned: " + str(r.passes))

    print()

    # ── Multi-user tests ──────────────────────────────────────────────────────
    print("Multi-user evaluation:")

    profiles = {
        11111: {"riders_mentioned": ["tadej-pogacar"]},
        22222: {"riders_mentioned": ["jonas-vingegaard"]},
        33333: {"riders_mentioned": []},
    }

    # High signal — all users should get it
    results = evaluate_for_users("Crash in the peloton!", profiles)
    all_passed &= test("high signal → all users",         len(results) == 3,     str(results.keys()))

    # Medium signal + rider — only matching user gets it
    results = evaluate_for_users("Pogacar at the summit.", profiles)
    all_passed &= test("medium + pogacar → user 11111",   11111 in results,      str(results.keys()))
    all_passed &= test("user 22222 not notified",         22222 not in results,  str(results.keys()))

    # Low signal — nobody gets it
    results = evaluate_for_users("100 km done. Average speed 42 km/h.", profiles)
    all_passed &= test("low signal → nobody",             len(results) == 0,     str(results.keys()))

    print()
    return all_passed


if __name__ == "__main__":
    print("Running rule engine tests...")
    passed = run_all_tests()
    print()
    if passed:
        print("All tests passed ✓")
        sys.exit(0)
    else:
        print("Some tests failed ✗ — fix before committing")
        sys.exit(1)

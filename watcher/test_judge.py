"""
Judge tests — requires GROQ_API_KEY in .env.
Run: python watcher/test_judge.py
"""
import sys
import os
import io
import time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from watcher.judge import judge_event, JudgeResult


def test(name: str, condition: bool, detail: str = ""):
    status = "✓" if condition else "✗ FAIL"
    print(f"  {status}  {name}")
    if not condition:
        print(f"         Detail: {detail}")
    return condition


def run_tests() -> bool:
    all_passed = True
    profile = {
        "riders_mentioned": ["tadej-pogacar", "jonas-vingegaard"],
        "races_followed":   ["giro-d-italia"],
        "language":         "en",
    }

    print()
    print("High-signal events (should notify):")

    # Attack
    r = judge_event(
        diff="Pogacar attacks on the Colle di Guaitarola. "
             "Gap opening to 15 seconds already. Vingegaard struggling.",
        race_slug="giro-d-italia", year=2026, stage=11,
        user_profile=profile, chat_id=11111,
    )
    all_passed &= test("attack → notify",          r.should_notify,          str(r))
    all_passed &= test("message not empty",        len(r.message) > 10,      r.message)
    all_passed &= test("message has rider name",
        "pogacar" in r.message.lower() or "vingegaard" in r.message.lower(),
        r.message
    )
    print(f"         Message: {r.message}")
    time.sleep(1)

    print()

    # Crash
    r = judge_event(
        diff="Crash in the peloton at km 45. "
             "Several riders down including Vingegaard.",
        race_slug="giro-d-italia", year=2026, stage=11,
        user_profile=profile, chat_id=11111,
    )
    all_passed &= test("crash → notify",           r.should_notify,          str(r))
    all_passed &= test("message mentions crash",
        "crash" in r.message.lower() or "down" in r.message.lower() or
        "vingegaard" in r.message.lower(),
        r.message
    )
    print(f"         Message: {r.message}")
    time.sleep(1)

    print()
    print("Low-signal events (should NOT notify):")

    # Routine update
    r = judge_event(
        diff="Peloton at 120km. Average speed 42.3 km/h. "
             "No significant changes in the race situation.",
        race_slug="giro-d-italia", year=2026, stage=11,
        user_profile=profile, chat_id=11111,
    )
    all_passed &= test("routine update → no notify", not r.should_notify,    str(r))
    print(f"         Reason: {r.reason}")
    time.sleep(1)

    # Mid-race classification
    r = judge_event(
        diff="Virtual GC standings updated. "
             "No changes to the top 10 classification.",
        race_slug="giro-d-italia", year=2026, stage=11,
        user_profile=profile, chat_id=11111,
    )
    all_passed &= test("classification update → no notify", not r.should_notify, str(r))
    print(f"         Reason: {r.reason}")
    time.sleep(1)

    print()
    print("Error handling:")

    original_key = os.environ.get("GROQ_API_KEY", "")
    os.environ["GROQ_API_KEY"] = "bad_key"

    r = judge_event(
        diff="Pogacar attacks!",
        race_slug="giro-d-italia", year=2026, stage=11,
        chat_id=99999,
    )
    all_passed &= test("bad API key → no notify",  not r.should_notify,      str(r))
    all_passed &= test("no exception raised",       True)

    os.environ["GROQ_API_KEY"] = original_key

    print()
    return all_passed


if __name__ == "__main__":
    print("Running judge tests...")
    print("(Requires GROQ_API_KEY — makes ~5 real API calls)")
    passed = run_tests()
    print()
    if passed:
        print("All tests passed ✓")
        sys.exit(0)
    else:
        print("Some tests failed ✗")
        sys.exit(1)

"""
Standalone poller test — run this directly to verify polling works.
Usage: python watcher/test_poller.py
Polls every 10 seconds for 3 minutes and prints all results.
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from watcher.poller import RaceWatch, PollResult, run_watcher, poll_once

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)


async def on_change(result: PollResult):
    print()
    print("=" * 60)
    print(f"CHANGE DETECTED — {result.race_watch.race_slug} stage {result.race_watch.stage}")
    print(f"Time: {result.timestamp:%H:%M:%S}")
    print(f"Diff preview: {result.diff[:300]}")
    print("=" * 60)
    print()


async def main():
    # Test single poll first
    print("Testing single poll...")
    race = RaceWatch(race_slug="giro-d-italia", year=2026, stage=11)
    result = await poll_once(race)

    if result.error:
        print(f"ERROR: {result.error}")
        print()
        print("If you see 403, httpx is being blocked.")
        print("The Playwright fallback in Step 11 will handle this.")
        print("For now the poller architecture is correct.")
    else:
        print(f"OK — content extracted: {len(result.raw_content)} chars")
        print(f"Preview: {result.raw_content[:200]}")
        print()

    # Run continuous polling for 3 minutes at 10s interval (faster than prod for testing)
    print("Starting continuous poll — 10s interval for 3 minutes...")
    print("Ctrl+C to stop early")
    print()

    races = [RaceWatch(race_slug="giro-d-italia", year=2026, stage=11)]

    try:
        await asyncio.wait_for(
            run_watcher(races, on_change, interval=10),
            timeout=180,
        )
    except asyncio.TimeoutError:
        print("3 minute test complete.")
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    asyncio.run(main())

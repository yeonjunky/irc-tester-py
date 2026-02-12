#!/usr/bin/env python3
"""IRC Server Tester - entry point.

Usage
-----
    python main.py [--host HOST] [--port PORT] [--password PASSWORD]

Runs the full test suite against the specified IRC server and prints
a coloured pass/fail report.
"""

import argparse
import sys

from irc_tester.single_user_suite import SingleUserSuite
from irc_tester.multi_user_suite import MultiUserSuite


def main():
    parser = argparse.ArgumentParser(
        description="Test an IRC server for RFC 1459 / 2810-2813 compliance",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Server hostname or IP (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=6667,
        help="Server port (default: 6667)",
    )
    parser.add_argument(
        "--password", default="test",
        help="Server password (default: test)",
    )
    parser.add_argument(
        "--case", default="all",
        help="specify the case to test (default: all, format: case1*(','case2))"
    )
    args = parser.parse_args()

    config = {
        "host": args.host,
        "port": args.port,
        "password": args.password,
        "case": args.case,
    }

    bold = "\033[1m"
    reset = "\033[0m"
    green = "\033[92m"
    red = "\033[91m"
    reset = "\033[0m"

    print(f"\n{bold}IRC Server Tester{reset}")
    print(f"Target: {config['host']}:{config['port']}")
    print("=" * 60)

    all_results = []

    if (config["case"] == "all"):
        # ── Single-user tests ──────────────────────────────────────── #
        print(f"\n{bold}[ Single User Tests ]{reset}")
        suite_single = SingleUserSuite(config)
        all_results.extend(suite_single.run_all())

        # ── Multi-user tests ───────────────────────────────────────── #
        print(f"\n{bold}[ Multi User Tests ]{reset}")
        suite_multi = MultiUserSuite(config)
        all_results.extend(suite_multi.run_all())
    
    else:
        cases = config["case"].split(",")

        for c in cases:
            suite_single = SingleUserSuite(config)
            suite_multi = MultiUserSuite(config)

            single_tests = suite_single.get_tests()
            multi_tests = suite_multi.get_tests()

            tested = False
            for name, func in single_tests:
                if name == c:
                    result = func()
                    all_results.append(result)
                    if result.passed:
                        sym = f"{green}✓{reset}"
                    else:
                        sym = f"{red}✗{reset}"
                    detail = result.details if result.details else ""
                    print(f"  {sym} {bold}{result.name}{reset}  {detail}")
                    tested = True
                    break

            if tested:
                continue

            for name, func in multi_tests:
                if name == c:
                    result = func()
                    all_results.append(result)
                    if result.passed:
                        sym = f"{green}✓{reset}"
                    else:
                        sym = f"{red}✗{reset}"
                    detail = result.details if result.details else ""
                    print(f"  {sym} {bold}{result.name}{reset}  {detail}")
                    break

    # ── Summary ────────────────────────────────────────────────── #
    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    total = len(all_results)

    print("\n" + "=" * 60)
    colour = green if failed == 0 else red
    print(
        f"{bold}Results: {colour}{passed}/{total} passed, "
        f"{failed}/{total} failed{reset}"
    )
    print("=" * 60)

    if failed:
        print(f"\n{red}Failed tests:{reset}")
        for r in all_results:
            if not r.passed:
                print(f"  • {r.name}: {r.details}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

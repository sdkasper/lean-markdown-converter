#!/usr/bin/env python3
"""
Weekly dependency update checker.

Checks PyPI for package updates and tests markitdown API compatibility.
Generates a markdown report and sets GitHub Actions output variable.

Usage:
  python scripts/dependency_check.py --output report.md

Output:
  - Writes markdown report to --output path (if updates found)
  - Sets GITHUB_OUTPUT env var with has_updates=true|false
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from importlib.metadata import version


def get_installed_version(package: str) -> str:
    """Get installed version of a package."""
    return version(package)


def get_latest_pypi_version(package: str) -> str:
    """Fetch latest version from PyPI JSON API."""
    try:
        url = f"https://pypi.org/pypi/{package}/json"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["info"]["version"]
    except Exception as e:
        print(f"Error fetching PyPI data for {package}: {e}")
        return None


def test_markitdown_compatibility(version_str: str) -> dict:
    """
    Test if a markitdown version passes compatibility tests.

    Returns:
        {
            "passed": bool,
            "total": int,
            "output": str (pytest output),
            "exit_code": int
        }
    """
    try:
        # Install the target version
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", f"markitdown[all]=={version_str}", "-q"],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            return {"passed": False, "total": 0, "output": result.stderr, "exit_code": result.returncode}

        # Run compatibility tests
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_markitdown_compat.py", "-v"],
            capture_output=True,
            text=True,
            timeout=60
        )

        # Parse output to count passed tests
        output = result.stdout + result.stderr
        passed = result.returncode == 0

        # Count test cases from output
        total = output.count(" PASSED") + output.count(" FAILED")
        if total == 0:
            total = 3  # Fallback: we know there are 3 tests

        return {
            "passed": passed,
            "total": total,
            "output": output,
            "exit_code": result.returncode
        }
    except Exception as e:
        return {"passed": False, "total": 0, "output": str(e), "exit_code": 1}


def get_outdated_packages() -> list:
    """
    Get list of outdated packages (excluding markitdown).

    Returns:
        [
            {"name": "package", "version": "1.0", "latest": "1.1"},
            ...
        ]
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return []

        packages = json.loads(result.stdout)
        # Exclude markitdown (already handled separately)
        return [p for p in packages if p["name"].lower() != "markitdown"]
    except Exception as e:
        print(f"Error getting outdated packages: {e}")
        return []


def generate_report(markitdown_info: dict, outdated: list) -> str:
    """Generate markdown report."""
    lines = []

    # markitdown section
    current = markitdown_info.get("current", "unknown")
    latest = markitdown_info.get("latest", "unknown")
    newer_available = markitdown_info.get("newer_available", False)
    compat_passed = markitdown_info.get("compat_passed", False)
    compat_total = markitdown_info.get("compat_total", 0)

    lines.append("## markitdown")
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| Current | {current} |")
    lines.append(f"| Latest | {latest} |")

    if newer_available:
        if compat_passed:
            status = f"✅ PASS ({compat_total}/{compat_total} tests)"
            lines.append(f"| Compatibility | {status} |")
            lines.append("")
            lines.append(f"→ Safe to upgrade. Run: `pip install markitdown[all]=={latest}` then regenerate requirements.txt")
        else:
            status = f"❌ FAIL (tests failing)"
            lines.append(f"| Compatibility | {status} |")
            lines.append("")
            lines.append(f"→ Upgrade blocked by failing tests. Do NOT upgrade markitdown.")
    else:
        lines.append("| Compatibility | ✅ No update available |")
        lines.append("")
        lines.append("→ Using latest compatible version.")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Outdated packages section
    if outdated:
        lines.append(f"## Outdated packages ({len(outdated)})")
        lines.append("| Package | Current | Latest |")
        lines.append("|---------|---------|--------|")
        for pkg in outdated:
            name = pkg.get("name", "unknown")
            current_ver = pkg.get("version", "unknown")
            latest_ver = pkg.get("latest_version", "unknown")
            lines.append(f"| {name} | {current_ver} | {latest_ver} |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Actions section
    lines.append("## Actions")
    if markitdown_info.get("newer_available") and compat_passed:
        lines.append(f"- [ ] Upgrade markitdown to {latest} (tests pass)")
    if outdated:
        count = len(outdated)
        lines.append(f"- [ ] Review {count} outdated {'package' if count == 1 else 'packages'} and update requirements.txt")

    return "\n".join(lines)


def set_github_output(has_updates: bool):
    """Set GITHUB_OUTPUT environment variable for GitHub Actions."""
    output_file = os.getenv("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            f.write(f"has_updates={'true' if has_updates else 'false'}\n")
    else:
        # Fallback: print to stdout for local testing
        print(f"has_updates={'true' if has_updates else 'false'}")


def main():
    parser = argparse.ArgumentParser(description="Check for dependency updates")
    parser.add_argument("--output", required=False, help="Output report file path")
    args = parser.parse_args()

    # Check markitdown
    current_version = get_installed_version("markitdown")
    latest_version = get_latest_pypi_version("markitdown")

    markitdown_info = {
        "current": current_version,
        "latest": latest_version,
        "newer_available": False,
        "compat_passed": False,
        "compat_total": 0,
    }

    has_updates = False

    if latest_version and latest_version != current_version:
        # Check if there's actually a newer version
        try:
            if tuple(map(int, latest_version.split("."))) > tuple(map(int, current_version.split("."))):
                markitdown_info["newer_available"] = True
                has_updates = True

                # Test compatibility with latest version
                print(f"Testing markitdown {latest_version} compatibility...")
                compat_result = test_markitdown_compatibility(latest_version)

                # Restore original version
                print(f"Restoring markitdown {current_version}...")
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", f"markitdown[all]=={current_version}", "-q"],
                    capture_output=True,
                    timeout=60
                )

                markitdown_info["compat_passed"] = compat_result["passed"]
                markitdown_info["compat_total"] = compat_result["total"]

                if not compat_result["passed"]:
                    print(f"⚠️  markitdown {latest_version} fails compatibility tests:")
                    print(compat_result["output"])
        except Exception as e:
            print(f"Error comparing versions: {e}")

    # Check other outdated packages
    outdated = get_outdated_packages()
    if outdated:
        has_updates = True

    # Generate and write report if there are updates
    if has_updates and args.output:
        report = generate_report(markitdown_info, outdated)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report written to {args.output}")

    # Set GitHub Actions output
    set_github_output(has_updates)

    if has_updates:
        print(f"Updates found: markitdown={latest_version}, {len(outdated)} outdated packages")
        return 0
    else:
        print("No updates found")
        return 0


if __name__ == "__main__":
    sys.exit(main())

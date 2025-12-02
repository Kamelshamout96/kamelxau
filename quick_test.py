"""
Quick Analysis Test
===================
Tests the analyzer with current data (even if limited)
"""

print("🚀 Running quick analysis test...")
print("=" * 70)

import subprocess
result = subprocess.run(["py", "pure_analyzer.py"], capture_output=True, text=True)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

print("\nReturn code:", result.returncode)

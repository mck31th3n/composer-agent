import sys
import json
import subprocess
from pathlib import Path

def run(cmd):
    print(f"CMD: {cmd}")
    subprocess.check_call(cmd, shell=True)

try:
    import jsonschema
except ImportError:
    run("pip install jsonschema")
    import jsonschema

print("\n--- P1: Schema Validation ---")
# Generate Plan
run(".venv/bin/python -m musicdiff.repair --diff diff_1.json --xml audit_sample.xml --out patch_1.json --dry-run")

# Validate
with open('contracts/patchplan.schema.json') as f:
    schema = json.load(f)
with open('patch_1.json') as f:
    plan = json.load(f)

jsonschema.validate(instance=plan, schema=schema)
print("✅ P1 PASS: Schema Valid")
print(f"Plan contains {len(plan['operations'])} operations.")

print("\n--- P3 (Pre): Parse Check ---")
from music21 import converter
converter.parse('audit_sample.xml')
print("✅ P3 (Pre) PASS")

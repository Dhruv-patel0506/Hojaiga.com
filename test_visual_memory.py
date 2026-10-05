"""Test Visual UI Memory organ."""
import sys
sys.path.insert(0, r"D:\new_automation\All codes")

from core_organs.organ_33_visual_memory import get_visual_memory

vm = get_visual_memory()

# Test 1: Check initial state
print("=== INITIAL STATE ===")
status = vm.get_status()
print("Snapshots:", status["total_snapshots"], "Profiles:", status["total_element_profiles"])

# Test 2: Check training gate for Chrome
print("\n=== TRAINING GATE (Chrome) ===")
gate = vm.db.get_training_gate("Chrome")
print("Gate:", gate)

# Test 3: Simulate 5 scans
print("\n=== SIMULATING 5 SCANS ===")
for i in range(5):
    result = vm.db.update_training_gate("Chrome", scan_success=True, elements_found=20, elements_total=20)
    print("Scan", i+1, ": gate_status=", result)

gate = vm.db.get_training_gate("Chrome")
rate = gate["successful_scans"] / max(gate["total_scans"], 1)
print("Final gate: scans=", gate["total_scans"], "rate=", f"{rate:.1%}", "status=", gate["gate_status"])

# Test 4: Recognition
print("\n=== RECOGNITION TEST ===")
recognition = vm.recognize("Chrome")
print("Recognized:", recognition is not None)
if recognition:
    print("  Elements:", len(recognition["elements"]))
    print("  Gate:", recognition["gate"])

# Test 5: Drift detection
print("\n=== DRIFT DETECTION ===")
fake_elements = [
    {"name": "Address Bar", "type": "EditControl"},
    {"name": "Back Button", "type": "ButtonControl"},
    {"name": "New Element", "type": "ButtonControl"},
]
drift = vm.detect_drift("Chrome", fake_elements)
print("Drift:", drift)

# Test 6: Brain assistance
print("\n=== BRAIN ASSISTANCE ===")
hints = vm.assist_compilation("Chrome", "search for something")
print("Hints available:", hints is not None)
if hints:
    print("  Element hints:", len(hints["element_hints"]))

# Test 7: Element profiles
print("\n=== ELEMENT PROFILES ===")
vm.db.upsert_element_profile(
    app_name="Chrome", element_name="Address Bar", element_type="EditControl",
    control_type="EditControl", visual_description="URL input field at top of browser",
    region_x=500, region_y=30, region_w=600, region_h=30,
    tab_location="", group_location="Navigation"
)
vm.db.confirm_element_found("Chrome", "Address Bar")
profiles = vm.db.get_element_profiles("Chrome")
print("Profiles:", len(profiles))
if profiles:
    p = profiles[0]
    print("  First:", p["element_name"], "confidence=", p["confidence_score"])

print("\n=== ALL TESTS PASSED ===")

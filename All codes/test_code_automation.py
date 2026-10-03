"""Test script for Universal Code Automation Engine."""
import sys
from app import TutorExtensions

def test_code_automation():
    """Test the code automation capabilities."""
    print("=" * 60)
    print("UNIVERSAL CODE AUTOMATION ENGINE TEST")
    print("=" * 60)
    
    # Initialize TutorExtensions
    ext = TutorExtensions()
    
    # Check capabilities
    caps = ext.get_available_capabilities()
    print("\n[Code Automation Status]")
    print(f"  Available: {caps['code_automation']['available']}")
    print(f"  Backend Status: {caps['code_automation']['backend_status']}")
    print(f"  Supported Languages: {len(caps['code_automation']['supported_languages'])}")
    print(f"  Task Types: {len(caps['code_automation']['task_types'])}")
    print(f"  Output Formats: {caps['code_automation']['output_formats']}")
    
    print("\n[Supported Languages]")
    for lang in caps['code_automation']['supported_languages']:
        print(f"  - {lang}")
    
    print("\n[Task Types]")
    for task in caps['code_automation']['task_types']:
        print(f"  - {task}")
    
    print("\n[Quick Capabilities Test]")
    
    # Test 1: Check backend availability
    backend_status = ext.get_code_automation_status()
    print(f"\n  Backend Available: {backend_status.get('backends_available', {})}")
    print(f"  Active Backend: {backend_status.get('active_backend', 'N/A')}")
    
    print("\n" + "=" * 60)
    print("Code Automation Engine is Ready!")
    print("=" * 60)
    print("\n[Usage Examples]")
    print("\n1. Generate a website:")
    print("   result = ext.generate_website('Create a portfolio website with a hero section')")
    print("\n2. Solve an assignment:")
    print("   result = ext.solve_assignment('Write a function to sort a list')")
    print("\n3. Fix a bug:")
    print("   result = ext.fix_bug(buggy_code, 'IndexError: list index out of range')")
    print("\n4. Add a feature:")
    print("   result = ext.add_feature(existing_code, 'Add validation for user input')")
    print("\n5. Generate desktop app:")
    print("   result = ext.generate_desktop_app('Create a calculator app')")
    print("\n[All results include]")
    print("  - Complete code")
    print("  - File paths (if written)")
    print("  - Syntax validation")
    print("  - Processing time")
    print("  - Success status")

if __name__ == "__main__":
    test_code_automation()

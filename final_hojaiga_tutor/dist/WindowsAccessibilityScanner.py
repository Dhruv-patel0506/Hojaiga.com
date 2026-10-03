"""
Windows Accessibility API Scanner
Uses Windows UI Automation to extract semantic UI tree with real button names,
control types, and hierarchy. No GPU load - pure API calls.
"""

import win32gui
import win32con
import win32process
import psutil
import json
from typing import List, Dict, Any, Optional

try:
    from uiautomation import Control, GetRootControl, FindControl, TreeScope, PropertyCondition
    UIA_AVAILABLE = True
except ImportError:
    UIA_AVAILABLE = False
    print("WARNING: uiautomation not installed. Install with: pip install uiautomation")


class WindowsAccessibilityScanner:
    """Scanner for Windows UI Automation tree"""
    
    def __init__(self):
        self.available = UIA_AVAILABLE
        if not self.available:
            print("[AccessibilityScanner] UI Automation not available - install uiautomation package")
    
    def get_active_window_with_process(self) -> Dict[str, Any]:
        """Get active window with process information"""
        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            
            # Get process info
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(pid)
                process_name = process.name()
                process_path = process.exe()
            except:
                process_name = "Unknown"
                process_path = ""
            
            return {
                "hwnd": hwnd,
                "title": title,
                "rect": rect,
                "pid": pid,
                "process_name": process_name,
                "process_path": process_path
            }
        except Exception as e:
            print(f"[AccessibilityScanner] Error getting window info: {e}")
            return {}
    
    def scan_ui_tree(self, hwnd: int) -> List[Dict[str, Any]]:
        """
        Scan UI tree using Windows UI Automation
        Returns hierarchical structure with real control names and types
        """
        if not self.available:
            print("[AccessibilityScanner] UI Automation not available")
            return []
        
        try:
            print(f"[AccessibilityScanner] Scanning UI tree for window {hwnd}")
            
            # Get the root control for the window
            root = Control.FromHandle(hwnd)
            if not root:
                print("[AccessibilityScanner] Could not get root control")
                return []
            
            # Build UI tree
            ui_elements = []
            self._traverse_ui_tree(root, ui_elements, level=0)
            
            print(f"[AccessibilityScanner] Found {len(ui_elements)} UI elements via Accessibility API")
            return ui_elements
            
        except Exception as e:
            print(f"[AccessibilityScanner] Error scanning UI tree: {e}")
            return []
    
    def _traverse_ui_tree(self, control: Control, elements: List[Dict[str, Any]], level: int = 0, parent_id: str = ""):
        """Recursively traverse UI Automation tree"""
        try:
            # Get control properties
            control_id = f"ctrl_{len(elements)}"
            control_name = control.Name or ""
            control_type = control.ControlTypeName or "Unknown"
            automation_id = control.AutomationId or ""
            class_name = control.ClassName or ""
            
            # Get bounding rectangle
            rect = control.BoundingRectangle
            bounding_box = {
                "x": rect.left,
                "y": rect.top,
                "width": rect.width(),
                "height": rect.height()
            }
            
            # Get control patterns (check if clickable, enabled, etc.)
            is_enabled = control.IsEnabled
            is_offscreen = control.IsOffscreen
            
            # Build element info
            element = {
                "id": control_id,
                "name": control_name or f"{control_type}",
                "role": control_type.lower(),
                "className": class_name,
                "automationId": automation_id,
                "boundingBox": bounding_box,
                "isClickable": self._is_clickable(control),
                "isEnabled": is_enabled,
                "text": control_name or "",
                "level": level,
                "parentId": parent_id,
                "children": []
            }
            
            elements.append(element)
            
            # Recursively traverse children
            children = control.GetChildren()
            for child in children:
                self._traverse_ui_tree(child, elements, level + 1, control_id)
                
        except Exception as e:
            # Skip controls that cause errors
            pass
    
    def _is_clickable(self, control: Control) -> bool:
        """Check if control is clickable (has Invoke or Toggle pattern)"""
        try:
            # Check for common clickable control types
            clickable_types = ["Button", "CheckBox", "RadioButton", "Hyperlink", "ListItem", "TabItem", "MenuItem"]
            if control.ControlTypeName in clickable_types:
                return True
            
            # Check for Invoke pattern (button-like behavior)
            try:
                control.GetInvokePattern()
                return True
            except:
                pass
            
            # Check for Toggle pattern
            try:
                control.GetTogglePattern()
                return True
            except:
                pass
            
            return False
        except:
            return False
    
    def get_ui_hierarchy_as_dict(self, hwnd: int) -> Dict[str, Any]:
        """
        Get UI hierarchy as nested dictionary (for JSON export)
        Format: {name: {children: [...]}}
        """
        if not self.available:
            return {}
        
        try:
            flat_elements = self.scan_ui_tree(hwnd)
            if not flat_elements:
                return {}
            
            # Build nested hierarchy
            element_map = {el["id"]: el for el in flat_elements}
            root_elements = []
            
            for el in flat_elements:
                if el["parentId"]:
                    parent = element_map.get(el["parentId"])
                    if parent:
                        parent["children"].append(el)
                else:
                    root_elements.append(el)
            
            # Build hierarchical dict
            hierarchy = {}
            for root in root_elements:
                hierarchy[root["name"]] = self._build_hierarchy_dict(root, element_map)
            
            return hierarchy
            
        except Exception as e:
            print(f"[AccessibilityScanner] Error building hierarchy: {e}")
            return {}
    
    def _build_hierarchy_dict(self, element: Dict[str, Any], element_map: Dict[str, Dict]) -> Dict[str, Any]:
        """Build nested hierarchy dictionary"""
        children_dict = {}
        for child in element["children"]:
            children_dict[child["name"]] = self._build_hierarchy_dict(child, element_map)
        
        return {
            "type": element["role"],
            "automationId": element["automationId"],
            "children": children_dict
        }


def test_scanner():
    """Test the accessibility scanner"""
    scanner = WindowsAccessibilityScanner()
    
    if not scanner.available:
        print("UI Automation not available - install uiautomation")
        return
    
    # Get active window
    window_info = scanner.get_active_window_with_process()
    print(f"Active window: {window_info.get('title')}")
    print(f"Process: {window_info.get('process_name')}")
    
    # Scan UI tree
    ui_elements = scanner.scan_ui_tree(window_info["hwnd"])
    
    # Print first 20 elements
    print("\nUI Elements (first 20):")
    for i, el in enumerate(ui_elements[:20]):
        indent = "  " * el["level"]
        print(f"{indent}[{i}] {el['name']} ({el['role']}) at ({el['boundingBox']['x']}, {el['boundingBox']['y']})")
    
    # Get hierarchy
    hierarchy = scanner.get_ui_hierarchy_as_dict(window_info["hwnd"])
    print("\nUI Hierarchy (JSON):")
    print(json.dumps(hierarchy, indent=2)[:500])


if __name__ == "__main__":
    test_scanner()

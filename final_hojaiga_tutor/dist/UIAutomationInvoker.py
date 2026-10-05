"""
UI Automation Pattern Invoker
Executes actions programmatically via Windows UI Automation patterns
without moving the physical mouse. Uses InvokePattern, ExpandCollapsePattern, etc.
"""

import sys
import json

try:
    from uiautomation import Control, GetRootControl, FindControl, TreeScope, PropertyCondition, By
    UIA_AVAILABLE = True
except ImportError:
    UIA_AVAILABLE = False
    print("ERROR: uiautomation not installed")


class UIAutomationInvoker:
    """Invoker for UI Automation patterns"""
    
    def __init__(self):
        self.available = UIA_AVAILABLE
    
    def find_element_by_coords(self, x: int, y: int) -> dict:
        """Find UI element at screen coordinates"""
        if not self.available:
            return {"success": False, "error": "UI Automation not available"}
        
        try:
            # Get element at point
            element = Control.FromPoint(x, y)
            if not element:
                return {"success": False, "error": "No element at coordinates"}
            
            return {
                "success": True,
                "name": element.Name,
                "controlType": element.ControlTypeName,
                "automationId": element.AutomationId,
                "className": element.ClassName,
                "boundingBox": {
                    "left": element.BoundingRectangle.left,
                    "top": element.BoundingRectangle.top,
                    "right": element.BoundingRectangle.right,
                    "bottom": element.BoundingRectangle.bottom
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def find_element_by_automation_id(self, automation_id: str, window_hwnd: int = None) -> dict:
        """Find UI element by AutomationId"""
        if not self.available:
            return {"success": False, "error": "UI Automation not available"}
        
        try:
            # Get root (either specific window or desktop)
            if window_hwnd:
                root = Control.FromHandle(window_hwnd)
            else:
                root = GetRootControl()
            
            if not root:
                return {"success": False, "error": "Could not get root control"}
            
            # Find element by AutomationId
            element = root.GetFirstChildControl()
            while element:
                if element.AutomationId == automation_id:
                    return {
                        "success": True,
                        "name": element.Name,
                        "controlType": element.ControlTypeName,
                        "automationId": element.AutomationId,
                        "found": True
                    }
                # Check children recursively
                child_result = self._find_recursive(element, automation_id)
                if child_result["success"]:
                    return child_result
                element = element.GetNextSiblingControl()
            
            return {"success": False, "error": f"Element with AutomationId '{automation_id}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _find_recursive(self, control, automation_id: str) -> dict:
        """Recursively search for element by AutomationId"""
        try:
            if control.AutomationId == automation_id:
                return {
                    "success": True,
                    "name": control.Name,
                    "controlType": control.ControlTypeName,
                    "automationId": control.AutomationId,
                    "found": True
                }
            
            for child in control.GetChildren():
                result = self._find_recursive(child, automation_id)
                if result["success"]:
                    return result
            
            return {"success": False, "error": "Not found in subtree"}
        except:
            return {"success": False, "error": "Search failed"}
    
    def invoke_element(self, x: int, y: int) -> dict:
        """Invoke element at coordinates using InvokePattern (button click)"""
        if not self.available:
            return {"success": False, "error": "UI Automation not available"}
        
        try:
            element = Control.FromPoint(x, y)
            if not element:
                return {"success": False, "error": "No element at coordinates"}
            
            # Try InvokePattern (for buttons)
            try:
                invoke_pattern = element.GetInvokePattern()
                if invoke_pattern:
                    invoke_pattern.Invoke()
                    return {
                        "success": True,
                        "method": "InvokePattern",
                        "element": element.Name,
                        "action": "clicked"
                    }
            except:
                pass
            
            # Try TogglePattern (for checkboxes, radio buttons)
            try:
                toggle_pattern = element.GetTogglePattern()
                if toggle_pattern:
                    toggle_pattern.Toggle()
                    return {
                        "success": True,
                        "method": "TogglePattern",
                        "element": element.Name,
                        "action": "toggled"
                    }
            except:
                pass
            
            # Try ExpandCollapsePattern (for menus, tree items)
            try:
                expand_pattern = element.GetExpandCollapsePattern()
                if expand_pattern:
                    expand_pattern.Expand()
                    return {
                        "success": True,
                        "method": "ExpandCollapsePattern",
                        "element": element.Name,
                        "action": "expanded"
                    }
            except:
                pass
            
            return {"success": False, "error": "No suitable pattern found for element"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def set_value(self, x: int, y: int, text: str) -> dict:
        """Set text value in edit box using ValuePattern"""
        if not self.available:
            return {"success": False, "error": "UI Automation not available"}
        
        try:
            element = Control.FromPoint(x, y)
            if not element:
                return {"success": False, "error": "No element at coordinates"}
            
            # Try ValuePattern (for text inputs)
            try:
                value_pattern = element.GetValuePattern()
                if value_pattern:
                    value_pattern.SetValue(text)
                    return {
                        "success": True,
                        "method": "ValuePattern",
                        "element": element.Name,
                        "action": "text_set",
                        "text": text
                    }
            except:
                pass
            
            # Fallback: Click and type
            try:
                element.Click()
                import pyautogui
                pyautogui.typewrite(text)
                return {
                    "success": True,
                    "method": "ClickAndType",
                    "element": element.Name,
                    "action": "text_typed",
                    "text": text
                }
            except:
                pass
            
            return {"success": False, "error": "Could not set value"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def expand_menu(self, x: int, y: int) -> dict:
        """Expand menu item using ExpandCollapsePattern"""
        if not self.available:
            return {"success": False, "error": "UI Automation not available"}
        
        try:
            element = Control.FromPoint(x, y)
            if not element:
                return {"success": False, "error": "No element at coordinates"}
            
            # Try ExpandCollapsePattern
            try:
                expand_pattern = element.GetExpandCollapsePattern()
                if expand_pattern:
                    expand_pattern.Expand()
                    return {
                        "success": True,
                        "method": "ExpandCollapsePattern",
                        "element": element.Name,
                        "action": "expanded"
                    }
            except:
                pass
            
            # Fallback: Click
            element.Click()
            return {
                "success": True,
                "method": "Click",
                "element": element.Name,
                "action": "clicked"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


def test_invoker():
    """Test the invoker"""
    invoker = UIAutomationInvoker()
    
    if not invoker.available:
        print("UI Automation not available")
        return
    
    # Test finding element at mouse position
    import pyautogui
    x, y = pyautogui.position()
    
    print(f"Mouse at: ({x}, {y})")
    result = invoker.find_element_by_coords(x, y)
    print(f"Element: {result}")
    
    # Test invoke
    if result["success"]:
        invoke_result = invoker.invoke_element(x, y)
        print(f"Invoke result: {invoke_result}")


if __name__ == "__main__":
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python UIAutomationInvoker.py <action> [args...]")
        print("Actions: invoke, set_value, expand, find")
        sys.exit(1)
    
    action = sys.argv[1]
    invoker = UIAutomationInvoker()
    
    if not invoker.available:
        print(json.dumps({"success": False, "error": "UI Automation not available"}))
        sys.exit(1)
    
    result = {}
    
    if action == "invoke":
        if len(sys.argv) < 4:
            result = {"success": False, "error": "Usage: invoke <x> <y>"}
        else:
            x = int(sys.argv[2])
            y = int(sys.argv[3])
            result = invoker.invoke_element(x, y)
    
    elif action == "set_value":
        if len(sys.argv) < 5:
            result = {"success": False, "error": "Usage: set_value <x> <y> <text>"}
        else:
            x = int(sys.argv[2])
            y = int(sys.argv[3])
            text = sys.argv[4]
            result = invoker.set_value(x, y, text)
    
    elif action == "expand":
        if len(sys.argv) < 4:
            result = {"success": False, "error": "Usage: expand <x> <y>"}
        else:
            x = int(sys.argv[2])
            y = int(sys.argv[3])
            result = invoker.expand_menu(x, y)
    
    elif action == "find":
        if len(sys.argv) < 4:
            result = {"success": False, "error": "Usage: find <x> <y>"}
        else:
            x = int(sys.argv[2])
            y = int(sys.argv[3])
            result = invoker.find_element_by_coords(x, y)
    
    else:
        result = {"success": False, "error": f"Unknown action: {action}"}
    
    print(json.dumps(result))

"""
Hybrid Teaching Drawing Engine for Hojaiga Lightboard
Combines simple teacher-style drawings with complex AI images
Features color-coded visual organization and clean lightboard-style presentations
Progressive animation system for drawing step-by-step explanations
"""
import math
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtGui import QColor, QPen, QPainter, QPainterPath

class DrawingMode(Enum):
    """Different drawing approaches for teaching."""
    SIMPLE_TEACHER = "simple_teacher"  # Hand-drawn style like teacher on lightboard
    COMPLEX_AI = "complex_ai"  # Professional AI-generated images
    CHART_FLOW = "chart_flow"  # Charts and flow diagrams
    HYBRID = "hybrid"  # Combination of approaches
    USER_ANNOTATION_RESPONSE = "annotation_response"  # Respond to user drawings
    PROGRESSIVE_ANIMATION = "progressive_animation"  # Step-by-step animated drawing

class LightboardColor(Enum):
    """Color scheme for lightboard-style visual organization (RGBYOV + more)."""
    # Primary colors for main elements
    RED = "#ef4444"          # Main topics, important concepts
    GREEN = "#22c55e"        # Examples, positive elements
    BLUE = "#3b82f6"         # Explanations, definitions
    YELLOW = "#eab308"       # Highlights, key points
    ORANGE = "#f97316"       # Subtopics, related concepts
    VIOLET = "#8b5cf6"       # Advanced concepts, connections
    
    # Additional colors for visual organization
    CYAN = "#06b6d4"         # Technical elements, formulas
    MAGENTA = "#ec4899"      # Emphasis, special cases
    WHITE = "#ffffff"         # General text, labels
    GRAY = "#94a3b8"         # Secondary text, supporting elements
    LIGHT_BLUE = "#38bdf8"   # Standard drawing color (existing)
    
    # Background/highlight colors
    HIGHLIGHT_RED = "rgba(239, 68, 68, 0.2)"
    HIGHLIGHT_GREEN = "rgba(34, 197, 94, 0.2)"
    HIGHLIGHT_BLUE = "rgba(59, 130, 246, 0.2)"
    HIGHLIGHT_YELLOW = "rgba(234, 179, 8, 0.2)"

class ElementType(Enum):
    """Types of elements for color coding."""
    MAIN_TOPIC = "main_topic"           # Red
    SUBTOPIC = "subtopic"               # Orange
    DEFINITION = "definition"           # Blue
    EXAMPLE = "example"                 # Green
    KEY_POINT = "key_point"             # Yellow
    FORMULA = "formula"                 # Cyan
    EMPHASIS = "emphasis"               # Magenta
    GENERAL_TEXT = "general_text"       # White
    SECONDARY_TEXT = "secondary_text"   # Gray
    DRAWING_ELEMENT = "drawing_element" # Light Blue
    ADVANCED_CONCEPT = "advanced_concept" # Violet

class DrawingCategory(Enum):
    """Categories of drawings for intelligent selection."""
    PHYSICS_CONCEPTS = "physics_concepts"  # Free body diagrams, waves, forces
    MATHEMATICS = "mathematics"  # Graphs, geometric proofs
    BIOLOGY_MEDICAL = "biology_medical"  # Heart, nervous system (use complex AI)
    NATURAL_PHENOMENA = "natural_phenomena"  # Tree, gravitation, magnetism (use complex AI)
    ENGINEERING = "engineering"  # Technical diagrams
    BRAINSTORMING = "brainstorming"  # Mind maps, flow charts
    GENERAL_EXPLANATION = "general_explanation"  # Simple explanatory drawings

@dataclass
class DrawingIntent:
    """AI's decision on how to draw something."""
    mode: DrawingMode
    category: DrawingCategory
    description: str
    use_complex_ai: bool
    drawing_commands: List[Dict[str, Any]]
    annotation_response: Optional[str] = None

class SimpleDrawingGenerator:
    """Generates simple teacher-style drawings for the lightboard with color coding and progressive animation."""
    
    @staticmethod
    def generate_progressive_derivation(center: QPointF, steps: List[Dict[str, Any]], 
                                     title: str = "Derivation") -> List[Dict[str, Any]]:
        """Generate progressive formula derivation with step-by-step animation."""
        commands = []
        
        # Step 1: Title
        title_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        commands.append({
            "type": "text",
            "text": title,
            "x": center.x() - 80,
            "y": center.y() - 120,
            "color": title_color,
            "font_size": 16,
            "bold": True,
            "animation_step": 1,
            "animation_delay": 0
        })
        
        # Process each derivation step with progressive animation
        current_y = center.y() - 80
        step_delay = 500  # milliseconds between steps
        
        for i, step in enumerate(steps):
            step_type = step.get("type", "explanation")
            content = step.get("content", "")
            
            if step_type == "heading":
                color = SimpleDrawingGenerator.get_color_for_element(ElementType.SUBTOPIC)
                commands.append({
                    "type": "text",
                    "text": content,
                    "x": center.x() - 70,
                    "y": current_y,
                    "color": color,
                    "font_size": 14,
                    "bold": True,
                    "animation_step": i + 2,
                    "animation_delay": step_delay * i
                })
                current_y += 40
                
            elif step_type == "formula":
                color = SimpleDrawingGenerator.get_color_for_element(ElementType.FORMULA)
                commands.append({
                    "type": "text",
                    "text": content,
                    "x": center.x() - 60,
                    "y": current_y,
                    "color": color,
                    "font_size": 13,
                    "animation_step": i + 2,
                    "animation_delay": step_delay * i
                })
                # Add formula underline
                text_width = len(content) * 8  # rough estimate
                commands.append({
                    "type": "line",
                    "start": [center.x() - 60, current_y + 18],
                    "end": [center.x() - 60 + text_width, current_y + 18],
                    "color": color,
                    "line_width": 2,
                    "animation_step": i + 2,
                    "animation_delay": step_delay * i + 100
                })
                current_y += 35
                
            elif step_type == "explanation":
                color = SimpleDrawingGenerator.get_color_for_element(ElementType.DEFINITION)
                commands.append({
                    "type": "text",
                    "text": content,
                    "x": center.x() - 60,
                    "y": current_y,
                    "color": color,
                    "font_size": 11,
                    "animation_step": i + 2,
                    "animation_delay": step_delay * i
                })
                current_y += 30
                
            elif step_type == "key_point":
                color = SimpleDrawingGenerator.get_color_for_element(ElementType.KEY_POINT)
                commands.append({
                    "type": "text",
                    "text": f"• {content}",
                    "x": center.x() - 60,
                    "y": current_y,
                    "color": color,
                    "font_size": 11,
                    "bold": True,
                    "animation_step": i + 2,
                    "animation_delay": step_delay * i
                })
                current_y += 30
                
            elif step_type == "drawing":
                # Handle different drawing types
                drawing_type = step.get("drawing_type", "arrow")
                if drawing_type == "arrow":
                    start = step.get("start", [center.x() - 50, current_y])
                    end = step.get("end", [center.x() + 50, current_y])
                    color = SimpleDrawingGenerator.get_color_for_element(ElementType.DRAWING_ELEMENT)
                    commands.append({
                        "type": "arrow",
                        "start": start,
                        "end": end,
                        "color": color,
                        "line_width": 3,
                        "animation_step": i + 2,
                        "animation_delay": step_delay * i
                    })
                elif drawing_type == "circle":
                    radius = step.get("radius", 30)
                    color = step.get("color", "#38bdf8")
                    commands.append({
                        "type": "shape",
                        "shape": "circle",
                        "x": center.x(),
                        "y": current_y,
                        "radius": radius,
                        "color": color,
                        "fill": step.get("fill", False),
                        "line_width": 3,
                        "animation_step": i + 2,
                        "animation_delay": step_delay * i
                    })
                current_y += 50
        
        return commands
    
    @staticmethod
    def generate_progressive_diagram(center: QPointF, diagram_parts: List[Dict[str, Any]],
                                      title: str = "Diagram") -> List[Dict[str, Any]]:
        """Generate progressive diagram with multiple related components."""
        commands = []
        
        # Title
        title_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        commands.append({
            "type": "text",
            "text": title,
            "x": center.x() - 100,
            "y": center.y() - 150,
            "color": title_color,
            "font_size": 16,
            "bold": True,
            "animation_step": 1,
            "animation_delay": 0
        })
        
        # Process each diagram part progressively
        step_delay = 600  # milliseconds between parts
        colors = [
            LightboardColor.RED.value,
            LightboardColor.GREEN.value,
            LightboardColor.BLUE.value,
            LightboardColor.YELLOW.value,
            LightboardColor.ORANGE.value,
            LightboardColor.VIOLET.value
        ]
        
        for i, part in enumerate(diagram_parts):
            part_type = part.get("type", "label")
            content = part.get("content", "")
            position = part.get("position", [center.x(), center.y()])
            color = colors[i % len(colors)]
            
            if part_type == "label":
                commands.append({
                    "type": "text",
                    "text": content,
                    "x": position[0],
                    "y": position[1],
                    "color": color,
                    "font_size": 12,
                    "bold": True,
                    "animation_step": i + 2,
                    "animation_delay": step_delay * i
                })
                
            elif part_type == "connection":
                start = part.get("start", [center.x(), center.y()])
                end = part.get("end", [center.x() + 100, center.y()])
                commands.append({
                    "type": "arrow",
                    "start": start,
                    "end": end,
                    "color": color,
                    "line_width": 2,
                    "animation_step": i + 2,
                    "animation_delay": step_delay * i
                })
                
            elif part_type == "shape":
                shape_type = part.get("shape", "circle")
                if shape_type == "circle":
                    radius = part.get("radius", 25)
                    commands.append({
                        "type": "shape",
                        "shape": "circle",
                        "x": position[0],
                        "y": position[1],
                        "radius": radius,
                        "color": color,
                        "fill": part.get("fill", False),
                        "line_width": 2,
                        "animation_step": i + 2,
                        "animation_delay": step_delay * i
                    })
                elif shape_type == "rectangle":
                    width = part.get("width", 80)
                    height = part.get("height", 40)
                    commands.append({
                        "type": "shape",
                        "shape": "rectangle",
                        "x": position[0] - width//2,
                        "y": position[1] - height//2,
                        "width": width,
                        "height": height,
                        "color": color,
                        "fill": part.get("fill", False),
                        "line_width": 2,
                        "animation_step": i + 2,
                        "animation_delay": step_delay * i
                    })
        
        return commands
    
    @staticmethod
    def get_color_for_element(element_type: ElementType) -> str:
        """Get the appropriate color for a given element type."""
        color_map = {
            ElementType.MAIN_TOPIC: LightboardColor.RED.value,
            ElementType.SUBTOPIC: LightboardColor.ORANGE.value,
            ElementType.DEFINITION: LightboardColor.BLUE.value,
            ElementType.EXAMPLE: LightboardColor.GREEN.value,
            ElementType.KEY_POINT: LightboardColor.YELLOW.value,
            ElementType.FORMULA: LightboardColor.CYAN.value,
            ElementType.EMPHASIS: LightboardColor.MAGENTA.value,
            ElementType.GENERAL_TEXT: LightboardColor.WHITE.value,
            ElementType.SECONDARY_TEXT: LightboardColor.GRAY.value,
            ElementType.DRAWING_ELEMENT: LightboardColor.LIGHT_BLUE.value,
            ElementType.ADVANCED_CONCEPT: LightboardColor.VIOLET.value
        }
        return color_map.get(element_type, LightboardColor.WHITE.value)
    
    @staticmethod
    def get_highlight_color(base_color: str) -> str:
        """Get the highlight version of a color."""
        color_map = {
            LightboardColor.RED.value: LightboardColor.HIGHLIGHT_RED.value,
            LightboardColor.GREEN.value: LightboardColor.HIGHLIGHT_GREEN.value,
            LightboardColor.BLUE.value: LightboardColor.HIGHLIGHT_BLUE.value,
            LightboardColor.YELLOW.value: LightboardColor.HIGHLIGHT_YELLOW.value,
        }
        return color_map.get(base_color, LightboardColor.HIGHLIGHT_BLUE.value)
    
    @staticmethod
    def generate_free_body_diagram(forces: List[Dict[str, Any]], center: QPointF, 
                                   title: str = "Free Body Diagram") -> List[Dict[str, Any]]:
        """Generate a structured free body diagram with color-coded elements."""
        commands = []
        
        # Draw title with main topic color
        title_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        commands.append({
            "type": "text",
            "text": title,
            "x": center.x() - 60,
            "y": center.y() - 80,
            "color": title_color,
            "font_size": 16,
            "bold": True
        })
        
        # Draw the object (clean, structured box)
        object_color = SimpleDrawingGenerator.get_color_for_element(ElementType.DRAWING_ELEMENT)
        commands.append({
            "type": "shape",
            "shape": "rectangle",
            "x": center.x() - 50,
            "y": center.y() - 35,
            "width": 100,
            "height": 70,
            "color": object_color,
            "fill": False,
            "line_width": 3
        })
        
        # Add object label
        label_color = SimpleDrawingGenerator.get_color_for_element(ElementType.DEFINITION)
        commands.append({
            "type": "text",
            "text": "Object",
            "x": center.x() - 15,
            "y": center.y() + 5,
            "color": label_color,
            "font_size": 12
        })
        
        # Draw force vectors with color coding
        force_colors = [
            LightboardColor.RED.value,
            LightboardColor.GREEN.value, 
            LightboardColor.BLUE.value,
            LightboardColor.YELLOW.value,
            LightboardColor.ORANGE.value
        ]
        
        for i, force in enumerate(forces):
            angle = force.get("angle", 0)
            magnitude = force.get("magnitude", 60)
            label = force.get("label", f"F{i+1}")
            
            end_x = center.x() + magnitude * math.cos(angle)
            end_y = center.y() + magnitude * math.sin(angle)
            
            # Use different colors for different forces
            force_color = force_colors[i % len(force_colors)]
            
            # Draw arrow line with proper thickness
            commands.append({
                "type": "arrow",
                "start": [center.x(), center.y()],
                "end": [end_x, end_y],
                "color": force_color,
                "line_width": 3
            })
            
            # Draw force label with clear positioning
            label_color = SimpleDrawingGenerator.get_color_for_element(ElementType.KEY_POINT)
            commands.append({
                "type": "text",
                "text": label,
                "x": end_x + 15 if end_x > center.x() else end_x - 40,
                "y": end_y - 10,
                "color": label_color,
                "font_size": 14,
                "bold": True
            })
        
        # Add coordinate system reference (clean, structured)
        axes_color = SimpleDrawingGenerator.get_color_for_element(ElementType.SECONDARY_TEXT)
        commands.append({
            "type": "text",
            "text": "→ x",
            "x": center.x() + 70,
            "y": center.y() + 50,
            "color": axes_color,
            "font_size": 11
        })
        commands.append({
            "type": "text", 
            "text": "↓ y",
            "x": center.x() - 70,
            "y": center.y() + 50,
            "color": axes_color,
            "font_size": 11
        })
        
        return commands
    
    @staticmethod
    def generate_sine_cosine_waves(center: QPointF, cycles: int = 2, 
                                   title: str = "Circular Motion → Waves") -> List[Dict[str, Any]]:
        """Generate structured sine and cosine wave demonstration with color coding."""
        commands = []
        width = 350
        height = 120
        start_x = center.x() - width // 2
        start_y = center.y()
        
        # Draw title with main topic color
        title_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        commands.append({
            "type": "text",
            "text": title,
            "x": center.x() - 80,
            "y": center.y() - 90,
            "color": title_color,
            "font_size": 16,
            "bold": True
        })
        
        # Draw clean coordinate axes with secondary color
        axes_color = SimpleDrawingGenerator.get_color_for_element(ElementType.SECONDARY_TEXT)
        commands.append({
            "type": "line",
            "start": [start_x, start_y],
            "end": [start_x + width, start_y],
            "color": axes_color,
            "line_width": 2
        })
        commands.append({
            "type": "line",
            "start": [start_x, start_y - height//2],
            "end": [start_x, start_y + height//2],
            "color": axes_color,
            "line_width": 2
        })
        
        # Add axis labels
        commands.append({
            "type": "text",
            "text": "θ (angle)",
            "x": start_x + width + 5,
            "y": start_y + 15,
            "color": axes_color,
            "font_size": 11
        })
        commands.append({
            "type": "text",
            "text": "amplitude",
            "x": start_x - 35,
            "y": start_y - height//2 - 10,
            "color": axes_color,
            "font_size": 11
        })
        
        # Draw sine wave (blue, clean curve)
        sine_color = LightboardColor.BLUE.value
        sine_points = []
        for i in range(width):
            x = start_x + i
            angle = (i / width) * cycles * 2 * math.pi
            y = start_y - math.sin(angle) * (height // 3)
            sine_points.append([x, y])
        
        commands.append({
            "type": "freehand",
            "points": sine_points,
            "color": sine_color,
            "line_width": 3
        })
        
        # Draw cosine wave (green, clearly distinguishable)
        cosine_color = LightboardColor.GREEN.value
        cosine_points = []
        for i in range(width):
            x = start_x + i
            angle = (i / width) * cycles * 2 * math.pi
            y = start_y - math.cos(angle) * (height // 3)
            cosine_points.append([x, y])
        
        commands.append({
            "type": "freehand",
            "points": cosine_points,
            "color": cosine_color,
            "line_width": 3
        })
        
        # Add clear, color-coded labels with legend box
        legend_x = start_x + width + 20
        legend_y = start_y - 40
        
        # Sine label
        commands.append({
            "type": "text",
            "text": "sin(θ)",
            "x": legend_x,
            "y": legend_y,
            "color": sine_color,
            "font_size": 14,
            "bold": True
        })
        
        # Cosine label
        commands.append({
            "type": "text",
            "text": "cos(θ)",
            "x": legend_x,
            "y": legend_y + 25,
            "color": cosine_color,
            "font_size": 14,
            "bold": True
        })
        
        # Add key point explanation
        key_point_color = SimpleDrawingGenerator.get_color_for_element(ElementType.KEY_POINT)
        commands.append({
            "type": "text",
            "text": "Key: Moving along circle",
            "x": center.x() - 70,
            "y": center.y() + 70,
            "color": key_point_color,
            "font_size": 12,
            "bold": True
        })
        commands.append({
            "type": "text",
            "text": "creates these waves",
            "x": center.x() - 70,
            "y": center.y() + 85,
            "color": key_point_color,
            "font_size": 12
        })
        
        return commands
    
    @staticmethod
    def generate_circle_with_radii(center: QPointF, num_radii: int = 8, 
                                   label: str = "Project X",
                                   subtopics: List[str] = None) -> List[Dict[str, Any]]:
        """Generate structured circle with radii for brainstorming with color coding."""
        commands = []
        radius = 90
        
        # Draw title with main topic color
        title_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        commands.append({
            "type": "text",
            "text": "Brainstorming Map",
            "x": center.x() - 60,
            "y": center.y() - radius - 30,
            "color": title_color,
            "font_size": 16,
            "bold": True
        })
        
        # Draw main circle with drawing element color
        circle_color = SimpleDrawingGenerator.get_color_for_element(ElementType.DRAWING_ELEMENT)
        commands.append({
            "type": "shape",
            "shape": "circle",
            "x": center.x(),
            "y": center.y(),
            "radius": radius,
            "color": circle_color,
            "fill": False,
            "line_width": 3
        })
        
        # Draw center label with main topic color
        center_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        commands.append({
            "type": "text",
            "text": label,
            "x": center.x() - 35,
            "y": center.y() - 8,
            "color": center_color,
            "font_size": 14,
            "bold": True
        })
        
        # Color palette for radii (RGBYOV + more)
        radius_colors = [
            LightboardColor.RED.value,
            LightboardColor.GREEN.value,
            LightboardColor.BLUE.value,
            LightboardColor.YELLOW.value,
            LightboardColor.ORANGE.value,
            LightboardColor.VIOLET.value,
            LightboardColor.CYAN.value,
            LightboardColor.MAGENTA.value
        ]
        
        # Draw radii with color coding
        for i in range(num_radii):
            angle = (2 * math.pi * i) / num_radii
            end_x = center.x() + radius * math.cos(angle)
            end_y = center.y() + radius * math.sin(angle)
            
            # Use different colors for each radius
            radius_color = radius_colors[i % len(radius_colors)]
            
            # Draw radius line
            commands.append({
                "type": "line",
                "start": [center.x(), center.y()],
                "end": [end_x, end_y],
                "color": radius_color,
                "line_width": 2
            })
            
            # Draw larger endpoint circle for better visibility
            commands.append({
                "type": "shape",
                "shape": "circle",
                "x": end_x,
                "y": end_y,
                "radius": 10,
                "color": radius_color,
                "fill": True,
                "line_width": 0
            })
            
            # Add subtopic labels if provided
            if subtopics and i < len(subtopics):
                subtopic_color = SimpleDrawingGenerator.get_color_for_element(ElementType.SUBTOPIC)
                label_x = end_x + (15 if end_x > center.x() else -50)
                label_y = end_y + (5 if end_y > center.y() else -15)
                commands.append({
                    "type": "text",
                    "text": subtopics[i][:15],  # Limit length
                    "x": label_x,
                    "y": label_y,
                    "color": subtopic_color,
                    "font_size": 11
                })
        
        # Add legend or key if many radii
        if num_radii > 4:
            legend_color = SimpleDrawingGenerator.get_color_for_element(ElementType.SECONDARY_TEXT)
            commands.append({
                "type": "text",
                "text": f"{num_radii} categories",
                "x": center.x() - 30,
                "y": center.y() + radius + 25,
                "color": legend_color,
                "font_size": 11
            })
        
        return commands
    
    @staticmethod
    def generate_flow_chart(center: QPointF, steps: List[str], 
                           title: str = "Process Flow") -> List[Dict[str, Any]]:
        """Generate structured flow chart with color-coded steps."""
        commands = []
        box_width = 140
        box_height = 45
        vertical_spacing = 70
        start_y = center.y() - (len(steps) * vertical_spacing) // 2
        
        # Draw title with main topic color
        title_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        commands.append({
            "type": "text",
            "text": title,
            "x": center.x() - 50,
            "y": start_y - 40,
            "color": title_color,
            "font_size": 16,
            "bold": True
        })
        
        # Color palette for steps (gradient from start to finish)
        step_colors = [
            LightboardColor.GREEN.value,    # Start
            LightboardColor.BLUE.value,     # Process
            LightboardColor.YELLOW.value,    # Important
            LightboardColor.ORANGE.value,    # Review
            LightboardColor.RED.value       # Final
        ]
        
        for i, step in enumerate(steps):
            y = start_y + i * vertical_spacing
            x = center.x() - box_width // 2
            
            # Use color based on step position
            step_color = step_colors[min(i, len(step_colors) - 1)]
            
            # Draw box with appropriate color
            commands.append({
                "type": "shape",
                "shape": "rectangle",
                "x": x,
                "y": y,
                "width": box_width,
                "height": box_height,
                "color": step_color,
                "fill": False,
                "line_width": 3
            })
            
            # Add step number
            number_color = SimpleDrawingGenerator.get_color_for_element(ElementType.KEY_POINT)
            commands.append({
                "type": "text",
                "text": f"{i+1}.",
                "x": x + 8,
                "y": y + box_height // 2 + 5,
                "color": number_color,
                "font_size": 12,
                "bold": True
            })
            
            # Draw step text
            text_color = SimpleDrawingGenerator.get_color_for_element(ElementType.GENERAL_TEXT)
            commands.append({
                "type": "text",
                "text": step[:18],  # Limit length for clarity
                "x": x + 35,
                "y": y + box_height // 2 + 5,
                "color": text_color,
                "font_size": 12
            })
            
            # Draw arrow to next step with consistent color
            if i < len(steps) - 1:
                next_y = y + box_height + vertical_spacing - box_height
                arrow_color = SimpleDrawingGenerator.get_color_for_element(ElementType.DRAWING_ELEMENT)
                commands.append({
                    "type": "arrow",
                    "start": [center.x(), y + box_height],
                    "end": [center.x(), next_y],
                    "color": arrow_color,
                    "line_width": 3
                })
        
        # Add start/end indicators
        start_indicator = SimpleDrawingGenerator.get_color_for_element(ElementType.EXAMPLE)
        commands.append({
            "type": "text",
            "text": "START",
            "x": center.x() + box_width // 2 + 10,
            "y": start_y + box_height // 2 + 5,
            "color": start_indicator,
            "font_size": 10,
            "bold": True
        })
        
        if len(steps) > 1:
            end_indicator = SimpleDrawingGenerator.get_color_for_element(ElementType.EMPHASIS)
            end_y = start_y + (len(steps) - 1) * vertical_spacing
            commands.append({
                "type": "text",
                "text": "END",
                "x": center.x() + box_width // 2 + 10,
                "y": end_y + box_height // 2 + 5,
                "color": end_indicator,
                "font_size": 10,
                "bold": True
            })
        
        return commands
    
    @staticmethod
    def generate_geometric_proof(center: QPointF, elements: List[Dict[str, Any]],
                                title: str = "Geometric Proof") -> List[Dict[str, Any]]:
        """Generate structured geometric proof diagrams with color coding."""
        commands = []
        
        # Draw title with main topic color
        title_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        commands.append({
            "type": "text",
            "text": title,
            "x": center.x() - 50,
            "y": center.y() - 100,
            "color": title_color,
            "font_size": 16,
            "bold": True
        })
        
        # Color palette for geometric elements
        geom_colors = {
            "primary": LightboardColor.BLUE.value,
            "secondary": LightboardColor.GREEN.value,
            "auxiliary": LightboardColor.YELLOW.value,
            "construction": LightboardColor.GRAY.value,
            "highlight": LightboardColor.RED.value
        }
        
        for element in elements:
            elem_type = element.get("type", "line")
            elem_color = element.get("color", geom_colors["primary"])
            
            if elem_type == "line":
                commands.append({
                    "type": "line",
                    "start": element["start"],
                    "end": element["end"],
                    "color": elem_color,
                    "line_width": element.get("line_width", 3)
                })
            elif elem_type == "triangle":
                points = element["points"]
                commands.append({
                    "type": "shape",
                    "shape": "polygon",
                    "points": points,
                    "color": elem_color,
                    "fill": False,
                    "line_width": element.get("line_width", 3)
                })
            elif elem_type == "circle":
                commands.append({
                    "type": "shape",
                    "shape": "circle",
                    "x": element["x"],
                    "y": element["y"],
                    "radius": element["radius"],
                    "color": elem_color,
                    "fill": element.get("fill", False),
                    "line_width": element.get("line_width", 3)
                })
            elif elem_type == "angle_mark":
                # Draw angle arc with highlight color
                commands.append({
                    "type": "angle_arc",
                    "center": element["center"],
                    "start_angle": element["start_angle"],
                    "end_angle": element["end_angle"],
                    "radius": element.get("radius", 25),
                    "color": element.get("color", geom_colors["highlight"]),
                    "line_width": 3
                })
            elif elem_type == "label":
                # Add geometric labels with definition color
                label_color = SimpleDrawingGenerator.get_color_for_element(ElementType.DEFINITION)
                commands.append({
                    "type": "text",
                    "text": element.get("text", ""),
                    "x": element["x"],
                    "y": element["y"],
                    "color": label_color,
                    "font_size": element.get("font_size", 12)
                })
        
        return commands

class HybridDrawingEngine:
    """Main engine that decides how to draw based on context."""
    
    def __init__(self):
        self.simple_generator = SimpleDrawingGenerator()
        self.complex_ai_topics = {
            "tree", "heart", "nervous system", "gravitation", 
            "magnetism", "shelter", "anatomy", "biological structure",
            "organic structure", "medical", "detailed biological"
        }
        self.simple_drawing_topics = {
            "forces", "free body", "diagram", "wave", "sine", "cosine",
            "graph", "function", "equation", "proof", "geometry",
            "flow", "chart", "brainstorm", "project", "categorize"
        }
    
    def analyze_drawing_intent(self, topic: str, context: str = "") -> DrawingIntent:
        """Analyze the topic and decide the best drawing approach."""
        topic_lower = topic.lower()
        
        # Check if this should use complex AI
        for complex_topic in self.complex_ai_topics:
            if complex_topic in topic_lower:
                return DrawingIntent(
                    mode=DrawingMode.COMPLEX_AI,
                    category=DrawingCategory.BIOLOGY_MEDICAL if "heart" in topic_lower or "nervous" in topic_lower else DrawingCategory.NATURAL_PHENOMENA,
                    description=f"Generate complex AI image for: {topic}",
                    use_complex_ai=True,
                    drawing_commands=[]
                )
        
        # Check if this is a brainstorming/chart topic
        if any(word in topic_lower for word in ["brainstorm", "flow", "chart", "project", "categorize", "organize"]):
            return DrawingIntent(
                mode=DrawingMode.CHART_FLOW,
                category=DrawingCategory.BRAINSTORMING,
                description=f"Create flow chart for: {topic}",
                use_complex_ai=False,
                drawing_commands=[]
            )
        
        # Check if this is a physics/math topic (simple drawings)
        if any(word in topic_lower for word in ["force", "wave", "sine", "cosine", "graph", "function", "proof", "geometry"]):
            return DrawingIntent(
                mode=DrawingMode.SIMPLE_TEACHER,
                category=DrawingCategory.PHYSICS_CONCEPTS if "force" in topic_lower else DrawingCategory.MATHEMATICS,
                description=f"Create teacher-style drawing for: {topic}",
                use_complex_ai=False,
                drawing_commands=[]
            )
        
        # Default to simple teacher style
        return DrawingIntent(
            mode=DrawingMode.SIMPLE_TEACHER,
            category=DrawingCategory.GENERAL_EXPLANATION,
            description=f"Create explanatory drawing for: {topic}",
            use_complex_ai=False,
            drawing_commands=[]
        )
    
    def generate_drawing(self, intent: DrawingIntent, center: QPointF, 
                         parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Generate drawing commands based on intent."""
        if parameters is None:
            parameters = {}
        
        if intent.mode == DrawingMode.SIMPLE_TEACHER:
            return self._generate_simple_drawing(intent, center, parameters)
        elif intent.mode == DrawingMode.CHART_FLOW:
            return self._generate_chart_flow(intent, center, parameters)
        elif intent.mode == DrawingMode.COMPLEX_AI:
            # This would call the professional drawing engine
            return [{"type": "complex_ai", "prompt": intent.description}]
        else:
            return self._generate_simple_drawing(intent, center, parameters)
    
    def _generate_simple_drawing(self, intent: DrawingIntent, center: QPointF, 
                                parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate simple teacher-style drawings with color coding."""
        desc = intent.description.lower()
        
        if "free body" in desc or "force" in desc:
            forces = parameters.get("forces", [
                {"angle": 0, "magnitude": 60, "label": "F1"},
                {"angle": math.pi/2, "magnitude": 40, "label": "F2"},
                {"angle": math.pi, "magnitude": 50, "label": "F3"}
            ])
            title = parameters.get("title", "Free Body Diagram")
            return self.simple_generator.generate_free_body_diagram(forces, center, title)
        
        elif "sine" in desc or "cosine" in desc or "wave" in desc:
            cycles = parameters.get("cycles", 2)
            title = parameters.get("title", "Circular Motion → Waves")
            return self.simple_generator.generate_sine_cosine_waves(center, cycles, title)
        
        elif "circle" in desc or "project" in desc or "brainstorm" in desc:
            num_radii = parameters.get("num_radii", 8)
            label = parameters.get("label", "Project X")
            subtopics = parameters.get("subtopics", None)
            return self.simple_generator.generate_circle_with_radii(center, num_radii, label, subtopics)
        
        elif "geometry" in desc or "proof" in desc:
            elements = parameters.get("elements", [])
            title = parameters.get("title", "Geometric Proof")
            return self.simple_generator.generate_geometric_proof(center, elements, title)
        
        else:
            # Default simple explanatory drawing with color coding
            return self._generate_default_explanatory(center, desc, parameters)
    
    def _generate_chart_flow(self, intent: DrawingIntent, center: QPointF,
                           parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate chart/flow diagrams."""
        steps = parameters.get("steps", [
            "Step 1: Identify",
            "Step 2: Analyze", 
            "Step 3: Solve",
            "Step 4: Verify"
        ])
        return self.simple_generator.generate_flow_chart(center, steps)
    
    def _generate_default_explanatory(self, center: QPointF, description: str, 
                                     parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate a default explanatory drawing with color coding."""
        commands = []
        
        # Draw title with main topic color
        title_color = SimpleDrawingGenerator.get_color_for_element(ElementType.MAIN_TOPIC)
        title = parameters.get("title", "Concept Overview")
        commands.append({
            "type": "text",
            "text": title,
            "x": center.x() - 50,
            "y": center.y() - 70,
            "color": title_color,
            "font_size": 16,
            "bold": True
        })
        
        # Draw a structured box with drawing element color
        box_color = SimpleDrawingGenerator.get_color_for_element(ElementType.DRAWING_ELEMENT)
        commands.append({
            "type": "shape",
            "shape": "rectangle",
            "x": center.x() - 70,
            "y": center.y() - 50,
            "width": 140,
            "height": 100,
            "color": box_color,
            "fill": False,
            "line_width": 3
        })
        
        # Add key point with key point color
        key_point_color = SimpleDrawingGenerator.get_color_for_element(ElementType.KEY_POINT)
        short_desc = description[:35] + "..." if len(description) > 35 else description
        commands.append({
            "type": "text",
            "text": short_desc,
            "x": center.x() - 60,
            "y": center.y() - 10,
            "color": key_point_color,
            "font_size": 13,
            "bold": True
        })
        
        # Add explanation with definition color
        explanation_color = SimpleDrawingGenerator.get_color_for_element(ElementType.DEFINITION)
        explanation = parameters.get("explanation", "Key concept explanation")
        commands.append({
            "type": "text",
            "text": explanation[:40] + "..." if len(explanation) > 40 else explanation,
            "x": center.x() - 60,
            "y": center.y() + 20,
            "color": explanation_color,
            "font_size": 11
        })
        
        # Add visual indicator (simple structured element)
        indicator_color = SimpleDrawingGenerator.get_color_for_element(ElementType.EXAMPLE)
        commands.append({
            "type": "shape",
            "shape": "circle",
            "x": center.x(),
            "y": center.y() + 50,
            "radius": 8,
            "color": indicator_color,
            "fill": True,
            "line_width": 0
        })
        
        return commands

class UserAnnotationDetector:
    """Detects and interprets user annotations on the whiteboard."""
    
    def __init__(self):
        self.annotation_history = []
    
    def analyze_annotation(self, strokes: List[List[QPointF]], context: str = "") -> Dict[str, Any]:
        """Analyze user annotation and determine intent."""
        if not strokes:
            return {"detected": False, "intent": "none"}
        
        # Calculate basic properties
        all_points = [point for stroke in strokes for point in stroke]
        if not all_points:
            return {"detected": False, "intent": "none"}
        
        # Calculate bounding box
        xs = [p.x() for p in all_points]
        ys = [p.y() for p in all_points]
        bounds = {
            "min_x": min(xs),
            "max_x": max(xs),
            "min_y": min(ys),
            "max_y": max(ys),
            "width": max(xs) - min(xs),
            "height": max(ys) - min(ys)
        }
        
        # Analyze stroke patterns
        stroke_count = len(strokes)
        avg_points_per_stroke = len(all_points) / stroke_count if stroke_count > 0 else 0
        
        # Detect annotation type
        annotation_type = self._classify_annotation(strokes, bounds, context)
        
        analysis = {
            "detected": True,
            "intent": annotation_type,
            "bounds": bounds,
            "stroke_count": stroke_count,
            "complexity": avg_points_per_stroke,
            "context": context
        }
        
        self.annotation_history.append(analysis)
        return analysis
    
    def _classify_annotation(self, strokes: List[List[QPointF]], bounds: Dict[str, Any], 
                           context: str) -> str:
        """Classify the type of annotation."""
        # Simple heuristics for classification
        if bounds["width"] < 50 and bounds["height"] < 50:
            return "point_mark"  # User marked a specific point
        elif bounds["width"] > 200 or bounds["height"] > 200:
            return "area_highlight"  # User highlighted an area
        elif len(strokes) == 1:
            return "single_stroke_question"  # Single stroke, likely a question mark
        elif len(strokes) > 3:
            return "complex_annotation"  # Complex drawing or writing
        else:
            return "general_annotation"  # General annotation
    
    def generate_annotation_response(self, analysis: Dict[str, Any], 
                                    lesson_context: str) -> str:
        """Generate AI response to user annotation."""
        if not analysis.get("detected"):
            return ""
        
        intent = analysis["intent"]
        context = analysis.get("context", "")
        
        if intent == "point_mark":
            return f"I see you've marked a specific point. Let me explain this area in more detail: {context}"
        elif intent == "area_highlight":
            return f"You've highlighted this area. This is important because..."
        elif intent == "single_stroke_question":
            return "I notice you have a question about this. Let me clarify..."
        elif intent == "complex_annotation":
            return "I see you've drawn something here. Let me address what you're showing..."
        else:
            return f"I see your annotation. Let me incorporate this into our discussion."

# Initialize global instance
_hybrid_drawing_engine = None
_user_annotation_detector = None

def get_hybrid_drawing_engine() -> HybridDrawingEngine:
    """Get or create hybrid drawing engine instance."""
    global _hybrid_drawing_engine
    if _hybrid_drawing_engine is None:
        _hybrid_drawing_engine = HybridDrawingEngine()
    return _hybrid_drawing_engine

def get_user_annotation_detector() -> UserAnnotationDetector:
    """Get or create user annotation detector instance."""
    global _user_annotation_detector
    if _user_annotation_detector is None:
        _user_annotation_detector = UserAnnotationDetector()
    return _user_annotation_detector
#!/usr/bin/env python3
"""
Specialized Diagram Generators
Uses the right tool for each type of visualization
"""

import matplotlib.pyplot as plt
import matplotlib
import numpy as np
import base64
import io
import re
from typing import Optional, List, Dict

# Set matplotlib to use dark background for lightboard aesthetic
matplotlib.use('Agg')
plt.style.use('dark_background')


class DiagramGenerator:
    """Generates diagrams using specialized tools"""

    @staticmethod
    def generate_graph(function: str, x_range: tuple = (-10, 10), points: int = 100) -> Optional[str]:
        """
        Generate a mathematical graph using Matplotlib

        Args:
            function: Mathematical function (e.g., "sin(x)", "x^2", "e^x")
            x_range: Range for x values (min, max)
            points: Number of points to plot

        Returns:
            Base64 encoded image string
        """
        try:
            x = np.linspace(x_range[0], x_range[1], points)
            y = DiagramGenerator._evaluate_function(function, x)

            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(x, y, color='#00ffff', linewidth=2, label=function)
            ax.set_xlabel('x', color='white')
            ax.set_ylabel('y', color='white')
            ax.set_title(f'Graph of {function}', color='white')
            ax.grid(True, alpha=0.3)
            ax.legend()
            ax.tick_params(colors='white')

            # Convert to base64
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight', facecolor='black')
            img_buffer.seek(0)
            img_str = base64.b64encode(img_buffer.read()).decode()
            plt.close()

            return img_str
        except Exception as e:
            print(f"[Graph Generation] Error: {e}")
            return None

    @staticmethod
    def _evaluate_function(function: str, x: np.ndarray) -> np.ndarray:
        """Evaluate mathematical function string"""
        # Replace common mathematical notation
        func_map = {
            'sin': 'np.sin',
            'cos': 'np.cos',
            'tan': 'np.tan',
            'exp': 'np.exp',
            'log': 'np.log',
            'sqrt': 'np.sqrt',
            'pi': 'np.pi',
            'e': 'np.e',
            '^': '**'
        }

        func_str = function
        for old, new in func_map.items():
            func_str = func_str.replace(old, new)

        # Evaluate safely
        return eval(func_str, {'np': np, 'x': x})

    @staticmethod
    def generate_trigonometric_graph(title: str = "Trigonometric Functions") -> Optional[str]:
        """Generate sine and cosine waves"""
        try:
            x = np.linspace(0, 4 * np.pi, 200)
            sin_y = np.sin(x)
            cos_y = np.cos(x)

            fig, ax = plt.subplots(figsize=(12, 6))
            ax.plot(x, sin_y, color='#00ffff', linewidth=2, label='sin(x)')
            ax.plot(x, cos_y, color='#ff00ff', linewidth=2, label='cos(x)')
            ax.set_xlabel('x (radians)', color='white')
            ax.set_ylabel('y', color='white')
            ax.set_title(title, color='white')
            ax.grid(True, alpha=0.3)
            ax.legend()
            ax.axhline(y=0, color='white', alpha=0.3)
            ax.axvline(x=0, color='white', alpha=0.3)
            ax.tick_params(colors='white')

            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight', facecolor='black')
            img_buffer.seek(0)
            img_str = base64.b64encode(img_buffer.read()).decode()
            plt.close()

            return img_str
        except Exception as e:
            print(f"[Trig Graph] Error: {e}")
            return None

    @staticmethod
    def generate_circle_animation(title: str = "Circular Motion", frames: int = 60) -> List[str]:
        """Generate animated frames of circular motion"""
        frames_list = []
        try:
            for i in range(frames):
                angle = (2 * np.pi * i) / frames
                x = np.cos(angle)
                y = np.sin(angle)

                fig, ax = plt.subplots(figsize=(8, 8))
                ax.set_xlim(-1.5, 1.5)
                ax.set_ylim(-1.5, 1.5)
                ax.set_aspect('equal')

                # Draw circle
                circle = plt.Circle((0, 0), 1, fill=False, color='#00ffff', linewidth=2)
                ax.add_patch(circle)

                # Draw point
                ax.plot(x, y, 'o', color='#ff00ff', markersize=15)

                # Draw lines to axes
                ax.plot([0, x], [0, y], '--', color='#00ff00', alpha=0.5)
                ax.plot([x, x], [0, y], '--', color='#ffff00', alpha=0.5)
                ax.plot([0, x], [y, y], '--', color='#ffff00', alpha=0.5)

                # Labels
                ax.text(x, y + 0.1, f'θ={angle:.2f}', color='white', ha='center')
                ax.text(x + 0.1, 0, f'x={x:.2f}', color='#ffff00', va='center')
                ax.text(0, y + 0.1, f'y={y:.2f}', color='#ffff00', ha='center')

                ax.set_title(f'{title} - Frame {i+1}/{frames}', color='white')
                ax.grid(True, alpha=0.3)
                ax.tick_params(colors='white')

                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format='png', dpi=80, bbox_inches='tight', facecolor='black')
                img_buffer.seek(0)
                img_str = base64.b64encode(img_buffer.read()).decode()
                frames_list.append(img_str)
                plt.close()

            return frames_list
        except Exception as e:
            print(f"[Circle Animation] Error: {e}")
            return []

    @staticmethod
    def generate_pythagorean_triangle() -> Optional[str]:
        """Generate Pythagorean theorem diagram"""
        try:
            fig, ax = plt.subplots(figsize=(8, 6))

            # Right triangle (3-4-5)
            triangle_x = [0, 3, 0, 0]
            triangle_y = [0, 0, 4, 0]
            ax.plot(triangle_x, triangle_y, color='#00ffff', linewidth=3)

            # Right angle marker
            ax.plot([0, 0.5], [0, 0], color='#ffffff', linewidth=2)
            ax.plot([0, 0], [0, 0.5], color='#ffffff', linewidth=2)

            # Labels
            ax.text(1.5, -0.3, 'a = 3', color='#ffff00', ha='center', fontsize=12)
            ax.text(-0.3, 2, 'b = 4', color='#ffff00', va='center', fontsize=12)
            ax.text(1.5, 2, 'c = 5', color='#ff00ff', ha='center', fontsize=12)

            # Right angle symbol
            ax.text(0.2, 0.2, '90°', color='#ffffff', fontsize=10)

            ax.set_xlim(-1, 4)
            ax.set_ylim(-1, 5)
            ax.set_aspect('equal')
            ax.set_title('Pythagorean Theorem: a² + b² = c²', color='white')
            ax.grid(True, alpha=0.3)
            ax.tick_params(colors='white')

            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight', facecolor='black')
            img_buffer.seek(0)
            img_str = base64.b64encode(img_buffer.read()).decode()
            plt.close()

            return img_str
        except Exception as e:
            print(f"[Pythagorean] Error: {e}")
            return None

    @staticmethod
    def generate_force_diagram(force_type: str = "gravity") -> Optional[str]:
        """Generate physics force diagram"""
        try:
            fig, ax = plt.subplots(figsize=(8, 6))

            if force_type == "gravity":
                # Two masses with gravitational force
                ax.plot([0, 5], [0, 0], 'o', color='#00ffff', markersize=30)
                ax.text(0, 0.3, 'm1', color='#00ffff', ha='center', fontsize=14)
                ax.text(5, 0.3, 'm2', color='#ff00ff', ha='center', fontsize=14)

                # Force arrows
                ax.arrow(0, 0, 2, 1, head_width=0.2, head_length=0.2, fc='#00ff00', ec='#00ff00', linewidth=2)
                ax.arrow(5, 0, -2, 1, head_width=0.2, head_length=0.2, fc='#00ff00', ec='#00ff00', linewidth=2)

                ax.text(1, 1.2, 'F', color='#00ff00', ha='center', fontsize=14)
                ax.text(4, 1.2, 'F', color='#00ff00', ha='center', fontsize=14)

                # Distance label
                ax.text(2.5, -0.3, 'r', color='#ffffff', ha='center', fontsize=14)

                ax.set_xlim(-1, 6)
                ax.set_ylim(-1, 2)
                ax.set_title('Gravitational Force: F = G(m₁m₂)/r²', color='white')
                ax.axis('off')

                img_buffer = io.BytesIO()
                plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight', facecolor='black')
                img_buffer.seek(0)
                img_str = base64.b64encode(img_buffer.read()).decode()
                plt.close()

                return img_str
        except Exception as e:
            print(f"[Force Diagram] Error: {e}")
            return None


class TopicClassifier:
    """Classify topics to determine the best visualization tool"""

    @staticmethod
    def classify(topic: str) -> str:
        """
        Classify topic type

        Returns:
            'graph' - Mathematical graph
            'trig' - Trigonometric function
            'circle' - Circular motion
            'geometry' - Geometric diagram
            'physics' - Physics force diagram
            'text' - Text/math only (no diagram)
        """
        topic_lower = topic.lower()

        # Graph-related
        if any(kw in topic_lower for kw in ['graph', 'plot', 'function', 'curve', 'wave']):
            if any(kw in topic_lower for kw in ['sin', 'cos', 'tan', 'trig']):
                return 'trig'
            if any(kw in topic_lower for kw in ['circle', 'circular']):
                return 'circle'
            return 'graph'

        # Geometry
        if any(kw in topic_lower for kw in ['pythagorean', 'triangle', 'right angle']):
            return 'geometry'

        # Physics
        if any(kw in topic_lower for kw in ['force', 'gravity', 'newton', 'momentum']):
            return 'physics'

        # Default to text/math only
        return 'text'


if __name__ == "__main__":
    # Test diagram generators
    print("[Test] Testing diagram generators...")

    # Test trigonometric graph
    print("[Test] Generating trigonometric graph...")
    trig_img = DiagramGenerator.generate_trigonometric_graph()
    if trig_img:
        print(f"[Test] Trig graph: {len(trig_img)} chars")

    # Test Pythagorean triangle
    print("[Test] Generating Pythagorean triangle...")
    pythag_img = DiagramGenerator.generate_pythagorean_triangle()
    if pythag_img:
        print(f"[Test] Pythagorean: {len(pythag_img)} chars")

    # Test force diagram
    print("[Test] Generating force diagram...")
    force_img = DiagramGenerator.generate_force_diagram()
    if force_img:
        print(f"[Test] Force diagram: {len(force_img)} chars")

    print("[Test] All tests complete!")

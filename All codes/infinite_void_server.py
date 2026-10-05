"""
Infinite Void Lightboard Server with LLaVA-v1.6-34B Integration
Connects to llama.cpp running LLaVA-v1.6-34B (Yi-34B based)
"""
import websockets
import json
import asyncio
import re
import time
import requests
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.animation as animation
import io
import base64

class LLaVADrawingGenerator:
    """Generates JSON drawing commands using LLaVA-v1.6-34B model"""

    def __init__(self, model_port=8081):
        self.model_port = model_port
        self.base_url = f"http://localhost:{model_port}"
        print(f"[LLaVA] Connecting to llama.cpp on port {model_port}")

    def generate_circular_motion_animation(self):
        """Generate animated frames showing circular motion creating sine/cosine waves"""
        try:
            frames = []
            plt.style.use('dark_background')

            # Parameters
            radius = 1.0
            num_frames = 60
            theta_values = np.linspace(0, 2*np.pi, num_frames)

            for i, theta in enumerate(theta_values):
                fig, (ax_circle, ax_waves) = plt.subplots(1, 2, figsize=(14, 6))

                # Circle plot
                circle_x = np.linspace(-1.5, 1.5, 100)
                circle_y = np.sqrt(radius**2 - circle_x**2)
                ax_circle.plot(circle_x, circle_y, 'cyan', linewidth=2)
                ax_circle.plot(circle_x, -circle_y, 'cyan', linewidth=2)

                # Moving point
                point_x = radius * np.cos(theta)
                point_y = radius * np.sin(theta)
                ax_circle.plot(point_x, point_y, 'yo', markersize=15)

                # Lines to axes
                ax_circle.plot([0, point_x], [0, point_y], 'green', linewidth=2)
                ax_circle.plot([point_x, point_x], [0, point_y], 'yellow', linewidth=1, linestyle='--')
                ax_circle.plot([0, point_x], [point_y, point_y], 'magenta', linewidth=1, linestyle='--')

                # Labels
                ax_circle.set_xlim(-1.5, 1.5)
                ax_circle.set_ylim(-1.5, 1.5)
                ax_circle.set_aspect('equal')
                ax_circle.set_title('Circular Motion', color='white')
                ax_circle.grid(True, alpha=0.3)
                ax_circle.tick_params(colors='white')

                # Waves plot
                theta_range = np.linspace(0, theta, 50)
                sine_y = np.sin(theta_range)
                cosine_y = np.cos(theta_range)

                ax_waves.plot(theta_range, sine_y, 'magenta', linewidth=2, label='sin(θ)')
                ax_waves.plot(theta_range, cosine_y, 'green', linewidth=2, label='cos(θ)')
                ax_waves.plot(theta, np.sin(theta), 'mo', markersize=10)
                ax_waves.plot(theta, np.cos(theta), 'go', markersize=10)

                ax_waves.set_xlim(0, 2*np.pi)
                ax_waves.set_ylim(-1.5, 1.5)
                ax_waves.set_title('Sine and Cosine Waves', color='white')
                ax_waves.set_xlabel('θ (radians)', color='white')
                ax_waves.set_ylabel('Value', color='white')
                ax_waves.legend()
                ax_waves.grid(True, alpha=0.3)
                ax_waves.tick_params(colors='white')

                plt.tight_layout()

                # Save frame
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=80, bbox_inches='tight', facecolor='black')
                buf.seek(0)
                frame_b64 = base64.b64encode(buf.read()).decode()
                frames.append(frame_b64)
                plt.close()

            return frames
        except Exception as e:
            print(f"[Animation Generation] Error: {e}")
            return None

    def generate_graph_image(self, function_type, params=None):
        """Generate a graph using matplotlib and return as base64"""
        try:
            plt.style.use('dark_background')
            fig, ax = plt.subplots(figsize=(10, 6))

            if function_type == "exponential":
                x = np.linspace(-3, 3, 100)
                y = np.exp(x)
                ax.plot(x, y, 'cyan', linewidth=2, label='y = e^x')
                ax.axhline(y=0, color='white', linewidth=0.5)
                ax.axvline(x=0, color='white', linewidth=0.5)
                ax.grid(True, alpha=0.3)
                ax.set_xlabel('x', color='white')
                ax.set_ylabel('y', color='white')
                ax.set_title('Graph of y = e^x', color='white')
                ax.legend()
                ax.tick_params(colors='white')

            elif function_type == "logarithmic":
                x = np.linspace(0.1, 5, 100)
                y = np.log(x)
                ax.plot(x, y, 'cyan', linewidth=2, label='y = ln(x)')
                ax.axhline(y=0, color='white', linewidth=0.5)
                ax.axvline(x=0, color='white', linewidth=0.5)
                ax.grid(True, alpha=0.3)
                ax.set_xlabel('x', color='white')
                ax.set_ylabel('y', color='white')
                ax.set_title('Graph of y = ln(x)', color='white')
                ax.legend()
                ax.tick_params(colors='white')

            elif function_type == "parabola":
                x = np.linspace(-5, 5, 100)
                y = x**2
                ax.plot(x, y, 'cyan', linewidth=2, label='y = x^2')
                ax.axhline(y=0, color='white', linewidth=0.5)
                ax.axvline(x=0, color='white', linewidth=0.5)
                ax.grid(True, alpha=0.3)
                ax.set_xlabel('x', color='white')
                ax.set_ylabel('y', color='white')
                ax.set_title('Graph of y = x^2', color='white')
                ax.legend()
                ax.tick_params(colors='white')

            elif function_type == "sine":
                x = np.linspace(-2*np.pi, 2*np.pi, 100)
                y = np.sin(x)
                ax.plot(x, y, 'cyan', linewidth=2, label='y = sin(x)')
                ax.axhline(y=0, color='white', linewidth=0.5)
                ax.axvline(x=0, color='white', linewidth=0.5)
                ax.grid(True, alpha=0.3)
                ax.set_xlabel('x', color='white')
                ax.set_ylabel('y', color='white')
                ax.set_title('Graph of y = sin(x)', color='white')
                ax.legend()
                ax.tick_params(colors='white')

            # Save to buffer
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='black')
            buf.seek(0)
            img_str = base64.b64encode(buf.read()).decode()
            plt.close()

            return img_str
        except Exception as e:
            print(f"[Graph Generation] Error: {e}")
            return None
        
    def generate_lesson_commands(self, topic: str) -> list:
        """Generate JSON drawing commands for a topic using LLaVA"""
        print(f"[LLaVA] Generating lesson for: {topic}")

        # Build comprehensive teaching prompt
        prompt = f"""You are a professor teaching on a lightboard. Your student knows nothing about this topic. Teach the topic: "{topic}"

TEACHING METHODOLOGY:
1. Start with a clear definition and explanation of what the topic is
2. Explain WHY this concept matters and its real-world importance
3. Break down the concept into key components or principles
4. Show mathematical formulas or relationships step-by-step
5. Provide concrete examples and applications
6. Include derivations or proofs when appropriate
7. Summarize key takeaways

Your response must be ONLY JSON in this format:
[
  {{"type": "text", "content": "Introduction explaining what the topic is from scratch", "color": "white"}},
  {{"type": "text", "content": "Why this concept matters and its importance", "color": "cyan"}},
  {{"type": "text", "content": "Key principles or components", "color": "white"}},
  {{"type": "text", "content": "Mathematical relationships or formulas", "color": "white"}},
  {{"type": "math", "content": "formula in LaTeX", "color": "yellow"}},
  {{"type": "text", "content": "Step-by-step derivation or explanation", "color": "cyan"}},
  {{"type": "text", "content": "Real-world examples and applications", "color": "white"}},
  {{"type": "text", "content": "Key takeaways and summary", "color": "white"}}
]

Available types: text, math, shape, path
Available shapes: circle, rect, line, ellipse
Available colors: white, cyan, magenta, green, yellow, orange
For math: use LaTeX syntax like \\frac{{a}}{{b}}, \\theta, \\sum, \\int

IMPORTANT REQUIREMENTS:
- Teach from scratch as if the student knows nothing
- Provide detailed, comprehensive explanations (not just one sentence)
- Include multiple explanation steps
- Show mathematical formulas and derivations step-by-step
- Provide real-world examples and applications
- Be thorough and detailed like a university professor
- Generate 15-25 drawing commands for a complete lesson
- Do NOT include x, y coordinates - frontend will position automatically"""

        try:
            # Try to use actual LLaVA model
            commands = self._call_llava_model(prompt)
            if commands:
                print(f"[LLaVA] Generated {len(commands)} commands using LLaVA model")
                return commands
            else:
                print(f"[LLaVA] Model returned empty, using fallback")
                return self._generate_fallback_commands(topic)
        except Exception as e:
            print(f"[LLaVA] Error calling model: {e}, using fallback")
            return self._generate_fallback_commands(topic)

    def _call_llava_model(self, prompt: str) -> list:
        """Call the LLaVA model via llama.cpp API"""
        try:
            # First, check if server is available
            try:
                health_check = requests.get(f"{self.base_url}/health", timeout=5)
                print(f"[LLaVA] Server health check: {health_check.status_code}")
            except:
                print(f"[LLaVA] Server not available on {self.base_url}")
                return None

            url = f"{self.base_url}/completion"
            payload = {
                "prompt": prompt,
                "n_predict": 4000,  # Increased for longer explanations
                "temperature": 0.7,
                "top_p": 0.9,
                "stop": ["</s>", "\n\n\n", "```"]
            }

            print(f"[LLaVA] Sending request to model...")
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()

            result = response.json()
            content = result.get("content", "")
            print(f"[LLaVA] Response length: {len(content)} chars")
            print(f"[LLaVA] First 300 chars: {content[:300]}...")

            # Try to extract JSON from the response
            # Look for JSON array pattern
            json_match = re.search(r'\[\s*\{.*\}\s*\]', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                print(f"[LLaVA] Extracted JSON: {json_str[:200]}...")
                try:
                    commands = json.loads(json_str)
                    print(f"[LLaVA] Successfully parsed {len(commands)} commands")
                    return commands
                except json.JSONDecodeError as e:
                    print(f"[LLaVA] JSON decode error: {e}")
                    print(f"[LLaVA] JSON string: {json_str[:500]}")
                    return None
            else:
                print(f"[LLaVA] No JSON found in response")
                print(f"[LLaVA] Full response: {content[:1000]}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"[LLaVA] Request error: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"[LLaVA] JSON decode error: {e}")
            return None
        except Exception as e:
            print(f"[LLaVA] Unexpected error: {e}")
            return None
    
    def _generate_fallback_commands(self, topic: str) -> list:
        """Fallback generation when LLaVA is not available - now with better diagrams"""
        topic_lower = topic.lower()

        # Camera positioning
        commands = [{"action": "move_camera", "x": 500, "y": 0}]

        if "gravitation" in topic_lower or "newton" in topic_lower or "force" in topic_lower:
            commands.extend(self._generate_gravitation_commands())
        elif "law" in topic_lower and "motion" in topic_lower:
            commands.extend(self._generate_newton_laws_commands())
        elif "wave" in topic_lower or "sine" in topic_lower or "cosine" in topic_lower or "circular" in topic_lower:
            commands.extend(self._generate_wave_commands())
        elif "catapult" in topic_lower or "physics" in topic_lower:
            commands.extend(self._generate_catapult_commands())
        else:
            commands.extend(self._generate_generic_commands(topic))

        return commands
    
    def _generate_gravitation_commands(self) -> list:
        """Comprehensive teaching of Newton's Law of Universal Gravitation"""
        commands = []

        # Full teaching explanation
        commands.extend([
            {"type": "text", "content": "Let's learn about Newton's Law of Universal Gravitation", "color": "white"},
            {"type": "text", "content": "This is one of the most important laws in physics", "color": "cyan"},
            {"type": "text", "content": "What does it say?", "color": "cyan"},
            {"type": "text", "content": "Every particle attracts every other particle", "color": "white"},
            {"type": "text", "content": "The force is directly proportional to their masses", "color": "white"},
            {"type": "text", "content": "And inversely proportional to the square of distance", "color": "white"},
            {"type": "text", "content": "The formula is: F = G × (m1 × m2) / r²", "color": "cyan"},
            {"type": "text", "content": "Let me explain each part:", "color": "cyan"},
            {"type": "text", "content": "F = gravitational force between objects", "color": "white"},
            {"type": "text", "content": "G = gravitational constant (6.674 × 10⁻¹¹ N·m²/kg²)", "color": "white"},
            {"type": "text", "content": "m1, m2 = masses of the two objects", "color": "white"},
            {"type": "text", "content": "r = distance between the centers of the objects", "color": "white"},
        ])

        # Visual diagram
        commands.extend([
            {"type": "text", "content": "Visual representation:", "color": "cyan"},
            {"type": "shape", "shape": "circle", "w": 80, "color": "cyan"},
            {"type": "text", "content": "m1", "color": "cyan"},
            {"type": "shape", "shape": "circle", "w": 60, "color": "magenta"},
            {"type": "text", "content": "m2", "color": "magenta"},
            {"type": "path", "svgPath": "M 180 220 L 400 220 M 180 215 L 180 225 M 400 215 L 400 225", "color": "white"},
            {"type": "text", "content": "r", "color": "white"},
            {"type": "path", "svgPath": "M 140 220 L 140 100 M 135 110 L 140 100 L 145 110", "color": "green"},
            {"type": "text", "content": "F", "color": "green"},
            {"type": "path", "svgPath": "M 430 220 L 430 100 M 425 110 L 430 100 L 435 110", "color": "green"},
            {"type": "text", "content": "F", "color": "green"},
            {"type": "math", "content": "F = G \\frac{m_1 m_2}{r^2}", "color": "yellow"},
        ])

        # More explanation
        commands.extend([
            {"type": "text", "content": "Key implications:", "color": "cyan"},
            {"type": "text", "content": "Gravity gets weaker as distance increases", "color": "white"},
            {"type": "text", "content": "This is why gravity decreases with altitude", "color": "white"},
            {"type": "text", "content": "Larger masses create stronger gravitational force", "color": "white"},
            {"type": "text", "content": "This law explains planetary motion", "color": "white"},
            {"type": "text", "content": "It also explains tides on Earth", "color": "white"},
            {"type": "text", "content": "And the orbit of satellites", "color": "white"},
            {"type": "text", "content": "This law applies everywhere in the universe!", "color": "cyan"},
        ])

        return commands

    def _generate_newton_laws_commands(self) -> list:
        """Proper Newton's Laws of Motion with free body diagrams"""
        return [
            {"type": "text", "content": "Newton's Three Laws of Motion", "color": "white"},
            {"type": "text", "content": "Law 1: Law of Inertia", "color": "cyan"},
            {"type": "text", "content": "An object at rest stays at rest", "color": "white"},
            {"type": "text", "content": "An object in motion stays in motion", "color": "white"},
            {"type": "text", "content": "unless acted upon by a force", "color": "white"},
            {"type": "text", "content": "Law 2: F = ma", "color": "cyan"},
            {"type": "shape", "shape": "rect", "w": 80, "h": 40, "color": "magenta"},
            {"type": "text", "content": "m", "color": "magenta"},
            {"type": "path", "svgPath": "M 40 20 L 120 20 M 115 15 L 120 20 L 115 25", "color": "green"},
            {"type": "text", "content": "F", "color": "green"},
            {"type": "path", "svgPath": "M 40 20 L 20 40 M 25 35 L 20 40 L 25 45", "color": "yellow"},
            {"type": "text", "content": "a", "color": "yellow"},
            {"type": "math", "content": "F = ma", "color": "yellow"},
            {"type": "text", "content": "Law 3: Action-Reaction", "color": "cyan"},
            {"type": "shape", "shape": "circle", "w": 60, "color": "magenta"},
            {"type": "text", "content": "A", "color": "magenta"},
            {"type": "shape", "shape": "circle", "w": 60, "color": "cyan"},
            {"type": "text", "content": "B", "color": "cyan"},
            {"type": "path", "svgPath": "M 30 30 L 100 30 M 95 25 L 100 30 L 95 35", "color": "green"},
            {"type": "text", "content": "F_AB", "color": "green"},
            {"type": "path", "svgPath": "M 100 70 L 30 70 M 35 65 L 30 70 L 35 75", "color": "red"},
            {"type": "text", "content": "F_BA", "color": "red"},
            {"type": "math", "content": "F_{AB} = -F_{BA}", "color": "yellow"},
        ]

    def _generate_wave_commands(self) -> list:
        """Generate full teaching for circular motion creating sine/cosine waves"""
        commands = []

        # Full teaching from scratch
        commands.extend([
            {"type": "text", "content": "Let's understand how circular motion creates sine and cosine waves", "color": "white"},
            {"type": "text", "content": "Imagine a point moving around a circle", "color": "cyan"},
            {"type": "text", "content": "The circle has radius R", "color": "white"},
            {"type": "text", "content": "The point's position changes as it moves", "color": "white"},
            {"type": "text", "content": "We measure the angle θ from the positive x-axis", "color": "cyan"},
            {"type": "text", "content": "The x-coordinate of the point is: x = R × cos(θ)", "color": "white"},
            {"type": "text", "content": "The y-coordinate of the point is: y = R × sin(θ)", "color": "white"},
            {"type": "text", "content": "As the point moves, these values change", "color": "cyan"},
            {"type": "text", "content": "If we plot these values over time...", "color": "white"},
            {"type": "text", "content": "We get the sine and cosine wave patterns!", "color": "cyan"},
        ])

        # Generate animated frames
        animation_frames = self.generate_circular_motion_animation()
        if animation_frames:
            commands.append({
                "type": "animation",
                "frames": animation_frames,
                "duration": 3000  # 3 seconds total
            })

        # Mathematical explanation
        commands.extend([
            {"type": "text", "content": "Mathematical Proof:", "color": "cyan"},
            {"type": "text", "content": "On the unit circle (R=1):", "color": "white"},
            {"type": "text", "content": "Any point (x,y) satisfies x² + y² = 1", "color": "white"},
            {"type": "text", "content": "Using trigonometry:", "color": "cyan"},
            {"type": "math", "content": "x = \\cos(\\theta)", "color": "yellow"},
            {"type": "math", "content": "y = \\sin(\\theta)", "color": "yellow"},
            {"type": "text", "content": "Therefore:", "color": "cyan"},
            {"type": "math", "content": "\\cos^2(\\theta) + \\sin^2(\\theta) = 1", "color": "yellow"},
            {"type": "text", "content": "This is the fundamental identity!", "color": "white"},
            {"type": "text", "content": "Key observations:", "color": "cyan"},
            {"type": "text", "content": "Sine wave oscillates between -1 and 1", "color": "white"},
            {"type": "text", "content": "Cosine wave oscillates between -1 and 1", "color": "white"},
            {"type": "text", "content": "They are 90° (π/2 radians) out of phase", "color": "white"},
            {"type": "text", "content": "This creates the wave patterns we see in physics!", "color": "cyan"},
        ])

        return commands
    
    def _generate_catapult_commands(self) -> list:
        return [
            {"type": "text", "content": "Catapult Physics", "color": "white"},
            {"type": "shape", "shape": "rect", "w": 250, "h": 20, "color": "white"},
            {"type": "shape", "shape": "circle", "w": 60, "color": "white"},
            {"type": "shape", "shape": "circle", "w": 40, "color": "cyan"},
            {"type": "text", "content": "m_1", "color": "cyan"},
            {"type": "path", "svgPath": "M 0 0 L 100 -50 M 100 -50 L 80 -55 M 100 -50 L 90 -35", "color": "green"},
            {"type": "text", "content": "v", "color": "green"},
            {"type": "math", "content": "\\tau = (Force)(Lever Arm)", "color": "magenta"},
            {"type": "math", "content": "\\tau = I\\alpha", "color": "yellow"},
        ]
    
    def _generate_generic_commands(self, topic: str) -> list:
        """Generate comprehensive teaching for any topic with visual support"""
        topic_lower = topic.lower()
        commands = []

        # Start with comprehensive teaching
        commands.extend([
            {"type": "text", "content": f"Let's learn about {topic} from scratch", "color": "white"},
            {"type": "text", "content": "I'll explain this topic thoroughly like a professor would", "color": "cyan"},
            {"type": "text", "content": "First, let's understand what this topic is about", "color": "white"},
            {"type": "text", "content": f"{topic} is a fundamental concept in its field", "color": "white"},
            {"type": "text", "content": "It has practical applications in many areas", "color": "white"},
            {"type": "text", "content": "Let me break it down into key components:", "color": "cyan"},
            {"type": "text", "content": "1. Core definition and meaning", "color": "white"},
            {"type": "text", "content": "2. Mathematical principles (if applicable)", "color": "white"},
            {"type": "text", "content": "3. Key properties and characteristics", "color": "white"},
            {"type": "text", "content": "4. Real-world applications", "color": "white"},
            {"type": "text", "content": "5. Important relationships and formulas", "color": "white"},
        ])

        # Check if it's a graph request and add specific teaching
        if "graph" in topic_lower or "plot" in topic_lower or "function" in topic_lower:
            if "e^-x" in topic_lower or "e to the -x" in topic_lower or "exponential" in topic_lower:
                commands.extend(self._generate_exponential_graph())
            elif "log" in topic_lower and "e^x" in topic_lower:
                commands.extend(self._generate_log_exponential_graph())
            elif "log" in topic_lower or "logarithm" in topic_lower:
                commands.extend(self._generate_logarithmic_graph())
            elif "sin" in topic_lower or "cos" in topic_lower or "tan" in topic_lower:
                commands.extend(self._generate_trig_graph())
            elif "x^2" in topic_lower or "x squared" in topic_lower or "parabola" in topic_lower:
                commands.extend(self._generate_parabola_graph())
            elif "wave" in topic_lower or "circular" in topic_lower:
                commands.extend(self._generate_wave_commands())
        elif "pythagoras" in topic_lower or "pythagorean" in topic_lower or "theorem" in topic_lower and "triangle" in topic_lower:
            commands.extend(self._generate_pythagorean_commands())
        elif "triangle" in topic_lower:
            commands.extend(self._generate_pythagorean_commands())
        else:
            # For unknown topics, provide comprehensive text-only teaching
            commands.extend([
                {"type": "text", "content": f"Let's learn about {topic} from scratch", "color": "white"},
                {"type": "text", "content": "I'll explain this topic thoroughly like a professor would", "color": "cyan"},
                {"type": "text", "content": "First, let's understand what this topic is about", "color": "white"},
                {"type": "text", "content": f"{topic} is a fundamental concept in its field", "color": "white"},
                {"type": "text", "content": "It has practical applications in many areas", "color": "white"},
                {"type": "text", "content": "Let me break it down into key components:", "color": "cyan"},
                {"type": "text", "content": "1. Core definition and meaning", "color": "white"},
                {"type": "text", "content": "2. Key principles and concepts", "color": "white"},
                {"type": "text", "content": "3. Important properties and characteristics", "color": "white"},
                {"type": "text", "content": "4. Real-world applications", "color": "white"},
                {"type": "text", "content": "5. Important relationships (if applicable)", "color": "white"},
                {"type": "text", "content": "Note: For specific topics like graphs, functions, or theorems,", "color": "cyan"},
                {"type": "text", "content": "I can provide detailed diagrams and proofs", "color": "white"},
                {"type": "text", "content": "Try being more specific (e.g., 'graph of sin(x)', 'Pythagorean theorem')", "color": "yellow"},
            ])

        # Add summary and key takeaways
        commands.extend([
            {"type": "text", "content": "Key takeaways:", "color": "cyan"},
            {"type": "text", "content": "Understanding this concept helps in many areas", "color": "white"},
            {"type": "text", "content": "Practice applying this concept to problems", "color": "white"},
            {"type": "text", "content": "Connect it to related topics you've learned", "color": "white"},
            {"type": "text", "content": "This foundation will help with advanced topics", "color": "white"},
        ])

        return commands

    def _generate_log_exponential_graph(self) -> list:
        """Generate full teaching for log(e^x) = x"""
        commands = []

        # Full teaching from scratch
        commands.extend([
            {"type": "text", "content": "Let's understand log(e^x) = x from scratch", "color": "white"},
            {"type": "text", "content": "First, what is a logarithm?", "color": "cyan"},
            {"type": "text", "content": "A logarithm answers: to what power must we raise a base?", "color": "white"},
            {"type": "text", "content": "log_b(a) = c means b^c = a", "color": "white"},
            {"type": "text", "content": "What is the natural logarithm?", "color": "cyan"},
            {"type": "text", "content": "It uses e as the base, written as ln(x) or log_e(x)", "color": "white"},
            {"type": "text", "content": "What is the relationship between log and exponential?", "color": "cyan"},
            {"type": "text", "content": "They are inverse functions!", "color": "white"},
            {"type": "text", "content": "If y = e^x, then ln(y) = x", "color": "white"},
            {"type": "text", "content": "They undo each other", "color": "white"},
            {"type": "text", "content": "Now, what is log(e^x)?", "color": "cyan"},
            {"type": "text", "content": "First, we calculate e^x", "color": "white"},
            {"type": "text", "content": "Then, we take the natural log of that result", "color": "white"},
            {"type": "text", "content": "Since they are inverses, they cancel out", "color": "white"},
            {"type": "text", "content": "So log(e^x) = x", "color": "cyan"},
        ])

        # Generate matplotlib graph for e^x
        graph_b64 = self.generate_graph_image("exponential")
        if graph_b64:
            commands.append({
                "type": "image",
                "data": graph_b64,
                "width": 600,
                "height": 400
            })

        # More explanation
        commands.extend([
            {"type": "text", "content": "This graph shows y = e^x", "color": "white"},
            {"type": "text", "content": "If we apply ln to both sides:", "color": "cyan"},
            {"type": "text", "content": "ln(y) = ln(e^x)", "color": "white"},
            {"type": "text", "content": "Since ln and e^x are inverses:", "color": "white"},
            {"type": "text", "content": "ln(y) = x", "color": "white"},
            {"type": "text", "content": "So y = e^x is the same as x = ln(y)", "color": "cyan"},
            {"type": "math", "content": "\\log(e^x) = x", "color": "yellow"},
            {"type": "text", "content": "This is true for all real numbers x", "color": "white"},
        ])

        return commands

    def _generate_logarithmic_graph(self) -> list:
        """Generate full teaching for logarithmic functions"""
        commands = []

        commands.extend([
            {"type": "text", "content": "Let's learn about logarithmic functions", "color": "white"},
            {"type": "text", "content": "What is y = ln(x)?", "color": "cyan"},
            {"type": "text", "content": "It's the inverse of y = e^x", "color": "white"},
            {"type": "text", "content": "It answers: what power of e gives x?", "color": "white"},
            {"type": "text", "content": "Domain: x > 0 (can't take log of negative)", "color": "white"},
            {"type": "text", "content": "Range: all real numbers", "color": "white"},
        ])

        # Generate matplotlib graph for ln(x)
        graph_b64 = self.generate_graph_image("logarithmic")
        if graph_b64:
            commands.append({
                "type": "image",
                "data": graph_b64,
                "width": 600,
                "height": 400
            })

        commands.extend([
            {"type": "text", "content": "Key points on the graph:", "color": "cyan"},
            {"type": "text", "content": "At x=1, ln(1) = 0", "color": "white"},
            {"type": "text", "content": "At x=e, ln(e) = 1", "color": "white"},
            {"type": "text", "content": "As x→0+, ln(x)→-∞", "color": "white"},
            {"type": "text", "content": "As x→∞, ln(x)→∞", "color": "white"},
        ])

        return commands

    def _generate_exponential_graph(self) -> list:
        """Generate a proper graph of e^-x with full teaching"""
        commands = []

        # Full teaching explanation
        commands.extend([
            {"type": "text", "content": "Let's learn about exponential functions from scratch", "color": "white"},
            {"type": "text", "content": "What is e?", "color": "cyan"},
            {"type": "text", "content": "e is a special number ≈ 2.71828", "color": "white"},
            {"type": "text", "content": "It's called Euler's number", "color": "white"},
            {"type": "text", "content": "What is e^x?", "color": "cyan"},
            {"type": "text", "content": "It's exponential growth or decay", "color": "white"},
            {"type": "text", "content": "What is e^-x?", "color": "cyan"},
            {"type": "text", "content": "It's exponential decay", "color": "white"},
            {"type": "text", "content": "As x increases, e^-x decreases", "color": "white"},
            {"type": "text", "content": "The graph shows this decay", "color": "cyan"},
        ])

        # Generate matplotlib graph
        graph_b64 = self.generate_graph_image("exponential")
        if graph_b64:
            commands.append({
                "type": "image",
                "data": graph_b64,
                "width": 600,
                "height": 400
            })

        # Additional explanation
        commands.extend([
            {"type": "text", "content": "Key observations:", "color": "cyan"},
            {"type": "text", "content": "At x=0, e^-0 = 1", "color": "white"},
            {"type": "text", "content": "At x=1, e^-1 ≈ 0.37", "color": "white"},
            {"type": "text", "content": "As x→∞, e^-x→0", "color": "white"},
            {"type": "text", "content": "The curve never touches the x-axis", "color": "white"},
            {"type": "text", "content": "This is called an asymptote", "color": "cyan"},
            {"type": "math", "content": "\\lim_{x \\to \\infty} e^{-x} = 0", "color": "yellow"},
            {"type": "text", "content": "Domain: all real numbers (-∞, ∞)", "color": "white"},
            {"type": "text", "content": "Range: positive numbers (0, ∞)", "color": "white"},
        ])

        return commands

    def _generate_pythagorean_commands(self) -> list:
        """Comprehensive teaching of Pythagorean theorem and trigonometric derivations"""
        commands = []

        # Pythagorean theorem explanation
        commands.extend([
            {"type": "text", "content": "The Pythagorean Theorem", "color": "white"},
            {"type": "text", "content": "This is one of the most important theorems in mathematics", "color": "cyan"},
            {"type": "text", "content": "It applies to right triangles (triangles with one 90° angle)", "color": "white"},
            {"type": "text", "content": "The theorem states:", "color": "cyan"},
            {"type": "text", "content": "The square of the hypotenuse equals the sum of squares of the legs", "color": "white"},
            {"type": "math", "content": "a^2 + b^2 = c^2", "color": "yellow"},
            {"type": "text", "content": "Where c is the hypotenuse (longest side, opposite 90°)", "color": "white"},
            {"type": "text", "content": "a and b are the legs (the other two sides)", "color": "white"},
        ])

        # Right triangle diagram
        try:
            plt.style.use('dark_background')
            fig, ax = plt.subplots(figsize=(8, 6))

            # Draw right triangle
            triangle_x = [0, 4, 4, 0]
            triangle_y = [0, 0, 3, 0]
            ax.plot(triangle_x, triangle_y, 'cyan', linewidth=3)
            ax.fill(triangle_x, triangle_y, 'cyan', alpha=0.2)

            # Right angle mark
            ax.plot([3.5, 4], [0, 0.5], 'white', linewidth=2)
            ax.plot([3.5, 3.5], [0.5, 0], 'white', linewidth=2)

            # Labels
            ax.text(2, -0.3, 'a', color='magenta', fontsize=16, ha='center')
            ax.text(4.2, 1.5, 'b', color='magenta', fontsize=16, ha='center')
            ax.text(2, 1.5, 'c', color='yellow', fontsize=16, ha='center')
            ax.text(3.6, 0.2, '90°', color='white', fontsize=12)

            ax.set_xlim(-1, 6)
            ax.set_ylim(-1, 5)
            ax.set_aspect('equal')
            ax.set_title('Right Triangle', color='white')
            ax.axis('off')

            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='black')
            buf.seek(0)
            graph_b64 = base64.b64encode(buf.read()).decode()
            plt.close()

            commands.append({
                "type": "image",
                "data": graph_b64,
                "width": 500,
                "height": 400
            })
        except Exception as e:
            print(f"[Pythagorean Diagram] Error: {e}")

        # Practical example
        commands.extend([
            {"type": "text", "content": "Practical example (3-4-5 triangle):", "color": "cyan"},
            {"type": "text", "content": "If a = 3 and b = 4, then c = ?", "color": "white"},
            {"type": "text", "content": "c² = 3² + 4² = 9 + 16 = 25", "color": "white"},
            {"type": "text", "content": "c = √25 = 5", "color": "white"},
            {"type": "text", "content": "So the hypotenuse is 5 units long", "color": "white"},
        ])

        # Now transition to trigonometric functions
        commands.extend([
            {"type": "text", "content": "Now, how are sine, cosine, and tangent derived?", "color": "cyan"},
            {"type": "text", "content": "They are defined using the same right triangle!", "color": "white"},
            {"type": "text", "content": "Consider the same right triangle with angle θ at the origin", "color": "white"},
            {"type": "text", "content": "Sine (sin θ) = Opposite / Hypotenuse = a / c", "color": "cyan"},
            {"type": "text", "content": "Cosine (cos θ) = Adjacent / Hypotenuse = b / c", "color": "cyan"},
            {"type": "text", "content": "Tangent (tan θ) = Opposite / Adjacent = a / b", "color": "cyan"},
        ])

        # Trigonometric identity derivation
        commands.extend([
            {"type": "text", "content": "Now, let's derive the fundamental identity:", "color": "cyan"},
            {"type": "text", "content": "Start with Pythagorean theorem: a² + b² = c²", "color": "white"},
            {"type": "text", "content": "Divide both sides by c²:", "color": "white"},
            {"type": "math", "content": "\\frac{a^2}{c^2} + \\frac{b^2}{c^2} = 1", "color": "yellow"},
            {"type": "text", "content": "Since sin(θ) = a/c and cos(θ) = b/c:", "color": "white"},
            {"type": "math", "content": "\\sin^2(\\theta) + \\cos^2(\\theta) = 1", "color": "yellow"},
            {"type": "text", "content": "This is the fundamental trigonometric identity!", "color": "cyan"},
            {"type": "text", "content": "It comes directly from the Pythagorean theorem", "color": "white"},
        ])

        # Tangent relationship
        commands.extend([
            {"type": "text", "content": "Also, we can relate tangent to sine and cosine:", "color": "cyan"},
            {"type": "text", "content": "tan(θ) = sin(θ) / cos(θ)", "color": "white"},
            {"type": "text", "content": "Because:", "color": "white"},
            {"type": "math", "content": "\\frac{\\sin(\\theta)}{\\cos(\\theta)} = \\frac{a/c}{b/c} = \\frac{a}{b} = \\tan(\\theta)", "color": "yellow"},
            {"type": "text", "content": "This shows all three functions are interconnected", "color": "white"},
        ])

        # Applications
        commands.extend([
            {"type": "text", "content": "Applications:", "color": "cyan"},
            {"type": "text", "content": "Construction: calculating diagonal lengths", "color": "white"},
            {"type": "text", "content": "Navigation: calculating distances between points", "color": "white"},
            {"type": "text", "content": "Engineering: stress analysis in structures", "color": "white"},
            {"type": "text", "content": "Physics: wave analysis, signal processing", "color": "white"},
            {"type": "text", "content": "Computer graphics: 3D calculations and rotations", "color": "white"},
        ])

        return commands

    def _generate_trig_graph(self) -> list:
        """Generate a proper trigonometric graph"""
        return [
            {"type": "text", "content": "Sine Wave Graph", "color": "white"},
            {"type": "text", "content": "y = sin(x)", "color": "cyan"},
            # X-axis
            {"type": "path", "svgPath": "M 0 150 L 400 150 M 395 145 L 400 150 L 395 155", "color": "white"},
            {"type": "text", "content": "x", "color": "white"},
            # Y-axis
            {"type": "path", "svgPath": "M 50 250 L 50 50 M 45 55 L 50 50 L 55 55", "color": "white"},
            {"type": "text", "content": "y", "color": "white"},
            # Sine wave
            {"type": "path", "svgPath": "M 50 150 Q 75 50 100 150 T 150 150 T 200 150 T 250 150 T 300 150 T 350 150", "color": "green"},
            # Labels
            {"type": "text", "content": "π", "color": "yellow"},
            {"type": "text", "content": "2π", "color": "yellow"},
            {"type": "text", "content": "Amplitude: 1", "color": "white"},
            {"type": "text", "content": "Period: 2π", "color": "white"},
        ]

    def _generate_parabola_graph(self) -> list:
        """Generate a proper parabola graph"""
        return [
            {"type": "text", "content": "Parabola Graph", "color": "white"},
            {"type": "text", "content": "y = x^2", "color": "cyan"},
            # X-axis
            {"type": "path", "svgPath": "M 0 200 L 400 200 M 395 195 L 400 200 L 395 205", "color": "white"},
            {"type": "text", "content": "x", "color": "white"},
            # Y-axis
            {"type": "path", "svgPath": "M 200 300 L 200 0 M 195 5 L 200 0 L 205 5", "color": "white"},
            {"type": "text", "content": "y", "color": "white"},
            # Parabola curve
            {"type": "path", "svgPath": "M 50 180 Q 100 20 150 180 Q 200 340 250 180 Q 300 20 350 180", "color": "green"},
            # Vertex
            {"type": "shape", "shape": "circle", "w": 10, "color": "yellow"},
            {"type": "text", "content": "(0,0)", "color": "yellow"},
            {"type": "text", "content": "Vertex at origin", "color": "white"},
            {"type": "text", "content": "Symmetric about y-axis", "color": "white"},
        ]

# Global AI instance
llava_generator = LLaVADrawingGenerator(model_port=8081)

async def handle_websocket(websocket):
    """Handle WebSocket connections from the HTML frontend"""
    print(f"[WebSocket] Client connected from {websocket.remote_address}")
    
    try:
        # Send connection confirmation
        await websocket.send(json.dumps({
            "type": "connection_ok",
            "message": "LLaVA-v1.6-34B Drawing Server Ready"
        }))
        
        # Wait for messages from client
        async for message in websocket:
            data = json.loads(message)
            print(f"[WebSocket] Received: {data}")
            
            if data.get("type") == "start_lesson":
                topic = data.get("topic", "default topic")
                print(f"[WebSocket] Starting lesson on: {topic}")
                
                # Generate lesson commands
                commands = llava_generator.generate_lesson_commands(topic)
                
                # Stream commands to frontend with timing
                for command in commands:
                    await websocket.send(json.dumps(command))
                    await asyncio.sleep(0.6)  # Delay between commands for progressive drawing
                
                # Send completion signal
                await websocket.send(json.dumps({
                    "type": "lesson_complete",
                    "topic": topic
                }))
                print(f"[WebSocket] Lesson complete: {len(commands)} commands sent")
            
            elif data.get("type") == "test_connection":
                await websocket.send(json.dumps({"type": "connection_ok", "message": "Server is ready"}))
            
            elif data.get("type") == "ping":
                await websocket.send(json.dumps({"type": "pong"}))
            
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
    finally:
        print(f"[WebSocket] Client disconnected")

async def main():
    """Main entry point"""
    print("=" * 60)
    print("INFINITE VOID LIGHTBOARD SERVER")
    print("With LLaVA-v1.6-34B (Yi-34B) Integration")
    print("=" * 60)
    print()
    print("Starting WebSocket server on ws://localhost:8765")
    print("Open infinite_void_standalone.html in your browser")
    print("The HTML file will connect to the WebSocket server automatically")
    print()
    
    # Start WebSocket server
    async with websockets.serve(handle_websocket, "localhost", 8765):
        print("[Server] WebSocket server is running...")
        print("[Server] Waiting for connections...")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())

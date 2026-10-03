"""
Organ 54 — Brainstorming & Diagram Generation (HeyClicky Integration)

Responsibility: Generate diagrams, sketches, and visual brainstorming for projects.
Uses diagram_generator.py and omni_sketch_engine.py for visual content.

Features:
- Mathematical graph generation
- Geometric diagrams
- Physics force diagrams
- Animated sketches
- Function plotting
- Project visualization
- Flowchart generation
- Concept mapping
"""

import asyncio
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

if r"D:\new_automation\All codes" not in sys.path:
    sys.path.insert(0, r"D:\new_automation\All codes")

try:
    from diagram_generator import DiagramGenerator, TopicClassifier
    _HAS_DIAGRAM_GEN = True
except ImportError:
    _HAS_DIAGRAM_GEN = False
    DiagramGenerator = None
    TopicClassifier = None

try:
    from omni_sketch_engine import SceneValidator, SceneCompiler, SceneEventLog
    _HAS_OMNI_SKETCH = True
except ImportError:
    _HAS_OMNI_SKETCH = False
    SceneValidator = None
    SceneCompiler = None
    SceneEventLog = None

logger = logging.getLogger("hojaiga.organ54.brainstorming")


class DiagramType(Enum):
    """Types of diagrams/sketches."""
    MATHEMATICAL_GRAPH = "mathematical_graph"
    TRIGONOMETRIC = "trigonometric"
    CIRCULAR_MOTION = "circular_motion"
    GEOMETRIC = "geometric"
    PHYSICS_FORCE = "physics_force"
    FLOWCHART = "flowchart"
    CONCEPT_MAP = "concept_map"
    TIMELINE = "timeline"
    ORGANIZATION_CHART = "organization_chart"
    ANIMATED_SKETCH = "animated_sketch"


class BrainstormingOrgan:
    """
    Brainstorming and diagram generation organ.
    
    Features:
    - Generate mathematical graphs
    - Create geometric diagrams
    - Build physics force diagrams
    - Sketch animated diagrams
    - Visualize projects
    - Create flowcharts
    - Map concepts
    """
    
    def __init__(self):
        self.event_log = SceneEventLog() if _HAS_OMNI_SKETCH else None
        self.validator = SceneValidator() if _HAS_OMNI_SKETCH else None
        self.compiler = SceneCompiler(self.event_log) if _HAS_OMNI_SKETCH else None
        self._generated_diagrams: Dict[str, str] = {}
    
    async def generate_diagram(self, topic: str, diagram_type: Optional[DiagramType] = None) -> Dict[str, Any]:
        """
        Generate a diagram for a given topic.
        
        Args:
            topic: Topic to visualize
            diagram_type: Specific diagram type (auto-detected if None)
        
        Returns:
            Diagram data with base64 image
        """
        logger.info(f"[Brainstorming] Generating diagram for: {topic}")
        
        if not _HAS_DIAGRAM_GEN:
            return {"success": False, "error": "Diagram generator not available"}
        
        # Auto-detect diagram type if not specified
        if diagram_type is None:
            diagram_type = self._detect_diagram_type(topic)
        
        # Generate diagram based on type
        try:
            if diagram_type == DiagramType.MATHEMATICAL_GRAPH:
                result = await self._generate_math_graph(topic)
            elif diagram_type == DiagramType.TRIGONOMETRIC:
                result = await self._generate_trig_graph(topic)
            elif diagram_type == DiagramType.CIRCULAR_MOTION:
                result = await self._generate_circular_motion(topic)
            elif diagram_type == DiagramType.GEOMETRIC:
                result = await self._generate_geometric_diagram(topic)
            elif diagram_type == DiagramType.PHYSICS_FORCE:
                result = await self._generate_force_diagram(topic)
            else:
                result = await self._generate_generic_diagram(topic)
            
            return result
        except Exception as e:
            logger.error(f"[Brainstorming] Diagram generation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _detect_diagram_type(self, topic: str) -> DiagramType:
        """Auto-detect diagram type from topic."""
        if not _HAS_DIAGRAM_GEN:
            return DiagramType.MATHEMATICAL_GRAPH
        
        classification = TopicClassifier.classify(topic)
        
        mapping = {
            "graph": DiagramType.MATHEMATICAL_GRAPH,
            "trig": DiagramType.TRIGONOMETRIC,
            "circle": DiagramType.CIRCULAR_MOTION,
            "geometry": DiagramType.GEOMETRIC,
            "physics": DiagramType.PHYSICS_FORCE,
        }
        
        return mapping.get(classification, DiagramType.MATHEMATICAL_GRAPH)
    
    async def _generate_math_graph(self, topic: str) -> Dict[str, Any]:
        """Generate mathematical graph."""
        # Extract function from topic
        import re
        function_match = re.search(r'(?:y\s*=\s*)?([a-z0-9\^\+\-\*\/\(\)\s]+)', topic.lower())
        if function_match:
            function = function_match.group(1).strip()
        else:
            function = "sin(x)"  # Default
        
        img_data = DiagramGenerator.generate_graph(function)
        
        if img_data:
            diagram_id = f"graph_{asyncio.get_event_loop().time()}"
            self._generated_diagrams[diagram_id] = img_data
            return {
                "success": True,
                "diagram_id": diagram_id,
                "type": "mathematical_graph",
                "function": function,
                "image_data": img_data
            }
        
        return {"success": False, "error": "Failed to generate graph"}
    
    async def _generate_trig_graph(self, topic: str) -> Dict[str, Any]:
        """Generate trigonometric graph."""
        img_data = DiagramGenerator.generate_trigonometric_graph(title=topic)
        
        if img_data:
            diagram_id = f"trig_{asyncio.get_event_loop().time()}"
            self._generated_diagrams[diagram_id] = img_data
            return {
                "success": True,
                "diagram_id": diagram_id,
                "type": "trigonometric",
                "title": topic,
                "image_data": img_data
            }
        
        return {"success": False, "error": "Failed to generate trig graph"}
    
    async def _generate_circular_motion(self, topic: str) -> Dict[str, Any]:
        """Generate animated circular motion frames."""
        frames = DiagramGenerator.generate_circle_animation(title=topic, frames=30)
        
        if frames:
            diagram_id = f"circle_{asyncio.get_event_loop().time()}"
            self._generated_diagrams[diagram_id] = frames[0]  # Store first frame
            return {
                "success": True,
                "diagram_id": diagram_id,
                "type": "circular_motion",
                "title": topic,
                "frames": frames,
                "frame_count": len(frames)
            }
        
        return {"success": False, "error": "Failed to generate circular motion"}
    
    async def _generate_geometric_diagram(self, topic: str) -> Dict[str, Any]:
        """Generate geometric diagram."""
        img_data = DiagramGenerator.generate_pythagorean_triangle()
        
        if img_data:
            diagram_id = f"geo_{asyncio.get_event_loop().time()}"
            self._generated_diagrams[diagram_id] = img_data
            return {
                "success": True,
                "diagram_id": diagram_id,
                "type": "geometric",
                "title": topic,
                "image_data": img_data
            }
        
        return {"success": False, "error": "Failed to generate geometric diagram"}
    
    async def _generate_force_diagram(self, topic: str) -> Dict[str, Any]:
        """Generate physics force diagram."""
        img_data = DiagramGenerator.generate_force_diagram(force_type="gravity")
        
        if img_data:
            diagram_id = f"force_{asyncio.get_event_loop().time()}"
            self._generated_diagrams[diagram_id] = img_data
            return {
                "success": True,
                "diagram_id": diagram_id,
                "type": "physics_force",
                "title": topic,
                "image_data": img_data
            }
        
        return {"success": False, "error": "Failed to generate force diagram"}
    
    async def _generate_generic_diagram(self, topic: str) -> Dict[str, Any]:
        """Generate generic diagram (fallback)."""
        # Try math graph as fallback
        return await self._generate_math_graph(topic)
    
    async def generate_omni_sketch(self, scene_description: str) -> Dict[str, Any]:
        """
        Generate sketch using omni sketch engine.
        
        Args:
            scene_description: Description of scene to sketch
        
        Returns:
            Compiled scene data
        """
        logger.info(f"[Brainstorming] Generating omni sketch: {scene_description}")
        
        if not _HAS_OMNI_SKETCH:
            return {"success": False, "error": "Omni sketch engine not available"}
        
        # This would typically come from an LLM
        # For now, return placeholder
        return {
            "success": True,
            "message": "Omni sketch engine available - requires LLM integration for scene generation"
        }
    
    async def brainstorm_project(self, project_description: str) -> Dict[str, Any]:
        """
        Brainstorm a project with diagrams and visualizations.
        
        Args:
            project_description: Project to brainstorm
        
        Returns:
            Brainstorming results with diagrams
        """
        logger.info(f"[Brainstorming] Brainstorming project: {project_description}")
        
        # Extract key concepts from project description
        concepts = self._extract_concepts(project_description)
        
        # Generate diagrams for each concept
        diagrams = []
        for concept in concepts:
            diagram_result = await self.generate_diagram(concept)
            if diagram_result.get("success"):
                diagrams.append(diagram_result)
        
        return {
            "success": True,
            "project": project_description,
            "concepts": concepts,
            "diagrams": diagrams,
            "diagram_count": len(diagrams)
        }
    
    def _extract_concepts(self, description: str) -> List[str]:
        """Extract key concepts from description."""
        # Simple keyword extraction
        import re
        words = re.findall(r'\b[a-zA-Z]{4,}\b', description)
        # Remove common words
        common_words = {"project", "create", "build", "develop", "design", "system", "application"}
        concepts = [w for w in words if w.lower() not in common_words]
        return concepts[:5]  # Top 5 concepts
    
    def get_diagram(self, diagram_id: str) -> Optional[str]:
        """Get stored diagram data by ID."""
        return self._generated_diagrams.get(diagram_id)
    
    def list_diagrams(self) -> List[str]:
        """List all generated diagram IDs."""
        return list(self._generated_diagrams.keys())

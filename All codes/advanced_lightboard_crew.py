import json
from crewai import Agent, Task, Crew, Process
from langchain_community.llms import LlamaCpp
from langchain_core.callbacks import CallbackManager, StreamingStdOutCallbackHandler

# 1. LOAD THE HIGH-INTELLIGENCE VISION MODEL (InternVL2-26B)
# This model is significantly better at math, physics, and diagrammatic reasoning.
callback_manager = CallbackManager([StreamingStdOutCallbackHandler()])

llm_26b = LlamaCpp(
    model_path="./models/InternVL2-26B-Q4_K_M.gguf", # Download this specific model
    n_gpu_layers=16, # Offload vision layers to your 6GB RTX 3050
    n_ctx=8192,      # Large context for complex SVG generation
    f16_kv=True,
    callback_manager=callback_manager,
    verbose=True,
)

# 2. DEFINE AGENT 1: THE PHYSICS PROFESSOR (The Brain)
# This agent does NOT write JSON. It plans the lesson and the visual layout.
professor_agent = Agent(
    role='Elite Physics Professor & Visual Director',
    goal='Break down complex topics and meticulously plan the visual layout for a digital lightboard.',
    backstory="""You are a world-renowned physics professor. You never just list text. 
    You always explain concepts using real-world physical visual metaphors (like blocks, inclines, pulleys, or catapults). 
    When explaining a topic, you meticulously design the diagram in your mind first.""",
    verbose=True,
    allow_delegation=True, # Allowed to hand off the drawing to the Draftsman
    llm=llm_26b
)

# 3. DEFINE AGENT 2: THE LIGHTBOARD DRAFTSMAN (The Hands)
# This agent only cares about strict coordinates, SVG paths, and our JSON format.
draftsman_agent = Agent(
    role='Technical SVG Draftsman',
    goal='Translate the Professor\'s visual plan into strictly valid JSON coordinate arrays.',
    backstory="""You are a master draftsman. You receive layout instructions and convert them into 
    precise X,Y coordinates and SVG paths. You ONLY output a raw JSON array. No markdown, no conversational text.
    
    AVAILABLE COMMANDS FOR YOUR JSON:
    - text: {"type": "text", "content": "string", "x": int, "y": int, "color": "white|cyan|green|yellow"}
    - math: {"type": "math", "content": "LaTeX string", "x": int, "y": int, "color": "yellow"}
    - shape: {"type": "shape", "shape": "line|rect|circle", "w": int, "h": int, "x": int, "y": int, "color": "string"}
    - path: {"type": "path", "svgPath": "M x y L x y...", "x": int, "y": int, "color": "string"}""",
    verbose=True,
    allow_delegation=False,
    llm=llm_26b
)

# 4. DEFINE THE TASKS
def run_tutor_session(user_topic, image_path=None):
    
    # Task 1: Force the AI to think deeply about the visual representation first
    planning_task_description = f"Teach the topic: '{user_topic}'. "
    if image_path:
        planning_task_description += f"Analyze the image at {image_path}. "
        
    planning_task_description += """
    Do not output JSON yet. 
    1. Write the script of what you will say (using LaTeX for math).
    2. Design the diagram. If teaching Laws of Motion, do NOT draw a simple circle. 
       Design a complex scene (e.g., a Free Body Diagram of a block on a 30-degree incline with friction and gravity vectors).
    3. Provide precise spatial instructions to the Draftsman (e.g., 'Place the block in the center, draw an arrow pointing straight down for gravity').
    """
    
    plan_lesson_task = Task(
        description=planning_task_description,
        expected_output="A detailed script and a meticulous visual blueprint describing exact shapes and vectors.",
        agent=professor_agent
    )

    # Task 2: Convert the blueprint into our Lightboard JSON
    draw_lesson_task = Task(
        description="""Take the visual blueprint provided by the Professor. 
        Calculate the X and Y coordinates (assume a 1920x1080 canvas). 
        Output the final result as a STRICTLY VALID JSON array of objects using the Draftsman's available commands.
        Make sure to use the 'path' command for complex vectors (arrows).""",
        expected_output="[ { ... }, { ... } ] (Raw JSON Array ONLY)",
        agent=draftsman_agent
    )

    # 5. ASSEMBLE THE CREW
    crew = Crew(
        agents=[professor_agent, draftsman_agent],
        tasks=[plan_lesson_task, draw_lesson_task],
        process=Process.sequential # Professor plans it, Draftsman draws it
    )
    
    result = crew.kickoff()
    return result

# --- EXECUTION EXAMPLE ---
if __name__ == "__main__":
    # Now, instead of a lazy circle, the dual-agent setup forces the generation of a complex diagram
    print("Initiating Lightboard Crew...")
    json_payload = run_tutor_session("Explain Newton's Second Law using a Free Body Diagram.")
    
    print("\n--- Final Payload for HTML WebSockets ---")
    print(json_payload)
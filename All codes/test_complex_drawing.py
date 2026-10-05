import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

import app

class MockCanvas:
    def __init__(self):
        self.traced_images = []
    def start_auto_trace(self, image_path):
        print(f"[MockCanvas] Received start_auto_trace: {image_path}")
        assert os.path.exists(image_path), f"File must exist: {image_path}"
        self.traced_images.append(image_path)

def test_complex_drawing():
    mock_canvas = MockCanvas()
    orchestrator = app.ComplexDrawingOrchestrator(canvas_widget=mock_canvas)

    simulated_llm_output = """Hello student! Today we study neural circuits and physics vectors.
Here is the vector diagram on the board:
```latex
\\begin{tikzpicture}
\\draw[thick,->] (0,0) -- (3,2) node[anchor=south west] {Force};
\\draw[dashed] (0,0) -- (3,0);
\\end{tikzpicture}
```
Now look at how the neural signal routes through the network:
```dot
digraph Network {
    rankdir=LR;
    input -> hidden1;
    input -> hidden2;
    hidden1 -> output;
    hidden2 -> output;
}
```
As you can see, the feed-forward mechanism is direct and synchronized!"""

    print("--- Testing process_llm_response ---")
    results = orchestrator.process_llm_response(simulated_llm_output)
    print(f"Processed {len(results)} drawings.")
    for i, res in enumerate(results):
        print(f"Drawing {i+1}: type={res.drawing_type}, success={res.success}, path={res.image_path}")
        assert res.success, f"Drawing {i+1} failed: {res.error_message}"
        assert os.path.exists(res.image_path)

    assert len(mock_canvas.traced_images) == 2, f"Expected 2 traces, got {len(mock_canvas.traced_images)}"

    print("\n--- Testing clean_text_for_user ---")
    clean_speech = app.clean_text_for_user(simulated_llm_output)
    print("Cleaned speech output:")
    print(clean_speech)
    assert "```" not in clean_speech
    assert "tikzpicture" not in clean_speech
    assert "digraph" not in clean_speech
    assert "Hello student!" in clean_speech
    assert "As you can see, the feed-forward mechanism is direct and synchronized!" in clean_speech

    print("\n--- Testing TutorExtensions capability report ---")
    extensions = app.TutorExtensions(canvas_widget=mock_canvas)
    caps = extensions.get_complex_drawing_capabilities()
    print("Complex drawing capabilities:", caps)
    assert caps["miktex_available"] is True
    assert caps["graphviz_python_available"] is True
    assert caps["graphviz_exe_available"] is True
    assert caps["pdftoppm_available"] is True
    assert caps["can_draw_diagrams"] is True

    print("\nALL ORCHESTRATOR AND CLEANER TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_complex_drawing()

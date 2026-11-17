"""
professor.knowledge -- what the Professor KNOWS about an application beyond what it can see.

    app_knowledge   measured UI knowledge from Atlas (menu paths, shortcuts, what each control opens) + stored knowledge bases -> enrich a ScreenModel
    repo_graph      one or many source repositories -> files, symbols, imports, calls, UI-label strings, side effects (db / network / file / process)
    divisions       frames any repository in the seven sub-divisions of the Hojaiga system (Core Intelligence ... External)
    explain         fuses the three: a visible button -> its label -> the code that runs when it is pressed -> what that code touches

Rule inherited from Atlas: a fact is measured or sourced, never asserted. Every fact the explainer returns carries where it came from.
"""

from . import app_knowledge, divisions, explain, manual_rag, repo_graph      # noqa: F401

__all__ = ["app_knowledge", "divisions", "explain", "manual_rag", "repo_graph"]

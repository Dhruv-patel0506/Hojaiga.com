"""
Atlas -- the universal "learn how any application works" layer of Hojaiga.

    common      evidence-bound claims, trust classes, the store
    llm         bounded local-model client (Ollama on 127.0.0.1)
    devscan     developer-level static harvest of an installed program (stack, runtimes, plugins, COM, formats, config schema, CLI)
    comlib      COM type-library enumeration (an application's own object model)
    webknow     free, keyless public sources (Wikidata, Wikipedia, GitHub) with a provenance cache
    distill     public documents -> claims, every claim quote-verified against its source
    keymaps     shipped keymap / shortcut tables -> input grammar (any common shape)
    motion      image registration: tells pan / zoom / rotate / non-rigid / selection-rectangle / stroke from two pictures
    gestures    the gesture atlas: what each kind of region does for click / right-click / drag / wheel / hold / modifiers
    scanner     one orchestrator with four speed tiers (instant, fast, deep, full)
    coverage    independent recall, exhaustion proof, pluggable oracles
    architect   the developer-level application model + report
    planner     task -> grounded plan (routes, state-graph paths, verification)
    evolve      prediction ledger, active-learning priors, drift detection, overnight loop
    qa          ask anything about an application, answered only from stored evidence

Entry point: core_organs/hojaiga_atlas.py
"""

__all__ = ["common", "llm"]

"""
mind -- the layer that turns what the scanners and the RAG know into judgement.

    consequence   what a control or a plan WILL do (money, send, delete, sign-out ...), how reversible it is, and what to do instead
    persona       who a message is for, in which language, register and length, and whether a draft fits that brief
    workflow      a task as steps that survive the human leaving it half done: resume in place, start fresh, or ask; several tasks in lanes
    picker        the trained adapter served locally (idle-unloading, so the trainer can have the GPU) and called from the executor's judge
    train_rows    training rows for the adapter from REAL crawl data: control picking, "confirm instead of click", resume-or-replan

Nothing in here names an app. Every rule is about WORDS the control carries and the SHAPE of the task, so it applies to an app that was never seen.
"""

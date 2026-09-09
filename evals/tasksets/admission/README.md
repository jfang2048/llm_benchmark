# Agent admission task

A tiny, controlled repository used to gate models before expensive SWE runs.
The model (via mini-swe-agent) must inspect the repo, run the failing test,
fix the bug, and re-run the test to green. It exercises the minimum agent
capabilities: file inspection, test execution, file editing, patch production.

The bug: `calc.add` subtracts instead of adding.

Layout:

    admission/
        calc.py           (contains the bug)
        test_calc.py      (failing test)
        README.md         (this file)
        expected.patch    (the canonical one-line fix, for grading)

Grading is objective: `python test_calc.py` must pass after the agent's edit.
No LLM judge is used.

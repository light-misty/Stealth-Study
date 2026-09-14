"""campus — the exam-prep application layer (备考台).

A parallel application next to the agent runtime: its own SQLite database
(`campus.db`), its own router mounted under `/v1/campus`, its own service layer. It reads
the kernel only through providers, personas, pdf_support and the automation store, and it
never writes to `coworker.db` (01 §4.3).
"""

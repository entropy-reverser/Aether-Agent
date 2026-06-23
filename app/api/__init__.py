"""app.api — FastAPI route layer (thin controllers over app.core).

Routes here never contain business logic; they translate HTTP <-> Pydantic
models and delegate to the core modules.
"""

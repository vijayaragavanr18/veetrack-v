"""Data Transfer Objects shared between the API and application layers.

DTOs are plain Pydantic models used as the boundary contract between routers
and use cases. They must never import from infrastructure.
"""

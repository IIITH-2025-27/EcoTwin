from typing import Generic, List, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")


class PaginatedResponse(BaseModel, Generic[DataT]):
    items: List[DataT]
    total: int
    page: int
    page_size: int
    has_next: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    cache: str


class ErrorResponse(BaseModel):
    detail: str
    code: str

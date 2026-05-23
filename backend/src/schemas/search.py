"""Pydantic schemas for search API request/response."""

from pydantic import BaseModel


class SearchResult(BaseModel):
    """A single search result with snippet."""

    id: str
    url: str
    title: str
    snippet: str
    score: float | None = None


class SearchResponse(BaseModel):
    """Paginated search response."""

    query: str
    total_hits: int
    page: int
    limit: int
    results: list[SearchResult]

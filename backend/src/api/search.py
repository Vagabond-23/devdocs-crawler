"""Search API — full-text search via Meilisearch."""

from fastapi import APIRouter, Depends, Query
from meilisearch_python_sdk import AsyncClient as MeiliClient

from src.dependencies import get_meili
from src.schemas.search import SearchResponse, SearchResult

router = APIRouter()

SEARCH_INDEX = "pages"


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Results per page"),
    meili: MeiliClient = Depends(get_meili),
) -> SearchResponse:
    """
    Search indexed documentation pages.

    Returns ranked results with highlighted snippets.
    """
    index = meili.index(SEARCH_INDEX)
    offset = (page - 1) * limit

    results = await index.search(
        q,
        offset=offset,
        limit=limit,
        attributes_to_highlight=["title", "content"],
        attributes_to_crop=["content"],
        crop_length=200,
        show_ranking_score=True,
    )

    items = [
        SearchResult(
            id=hit["id"],
            url=hit.get("url", ""),
            title=hit.get("title", ""),
            snippet=hit.get("_formatted", {}).get("content", ""),
            score=hit.get("_rankingScore"),
        )
        for hit in results.hits
    ]

    return SearchResponse(
        query=q,
        total_hits=results.estimated_total_hits or 0,
        page=page,
        limit=limit,
        results=items,
    )

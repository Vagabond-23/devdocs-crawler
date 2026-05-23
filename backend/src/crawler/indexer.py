"""
Meilisearch indexer — pushes crawled content into the search index.

Handles:
- Index creation and configuration
- Document upserts (add/update)
- Searchable and filterable attribute configuration
"""

import logging

from meilisearch_python_sdk import AsyncClient as MeiliClient
from meilisearch_python_sdk.errors import MeilisearchApiError

from src.config import settings

logger = logging.getLogger(__name__)

INDEX_NAME = "pages"


class Indexer:
    """Meilisearch document indexer."""

    def __init__(self) -> None:
        self._client = MeiliClient(settings.meili_url, settings.meili_master_key)
        self._initialized = False

    async def ensure_index(self) -> None:
        """Create and configure the search index if it doesn't exist."""
        if self._initialized:
            return

        try:
            await self._client.create_index(INDEX_NAME, primary_key="id")
        except MeilisearchApiError:
            pass  # Index already exists

        index = self._client.index(INDEX_NAME)

        # Configure searchable attributes (order matters — title is most important)
        await index.update_searchable_attributes(["title", "content", "url"])

        # Configure displayed attributes
        await index.update_displayed_attributes(
            ["id", "title", "content", "url", "hostname", "crawled_at"]
        )

        # Configure ranking rules
        await index.update_ranking_rules([
            "words",
            "typo",
            "proximity",
            "attribute",
            "sort",
            "exactness",
        ])

        self._initialized = True
        logger.info(f"Meilisearch index '{INDEX_NAME}' configured")

    async def index_document(
        self,
        doc_id: str,
        title: str,
        content: str,
        url: str,
        hostname: str,
    ) -> None:
        """
        Index a single document in Meilisearch.

        Uses upsert semantics — if the document already exists, it's updated.
        """
        await self.ensure_index()

        index = self._client.index(INDEX_NAME)
        document = {
            "id": doc_id,
            "title": title,
            "content": content[:50000],  # Cap content at 50k chars for index
            "url": url,
            "hostname": hostname,
        }

        await index.add_documents([document])
        logger.debug(f"Indexed: {url}")

    async def close(self) -> None:
        """Close the Meilisearch client."""
        await self._client.aclose()

import os
from dataclasses import dataclass
from tavily import TavilyClient


@dataclass
class SearchResult:
    title: str
    url: str
    content: str


def search(query: str, max_results: int = 5) -> list[SearchResult]:
    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
    response = client.search(query=query, max_results=max_results, search_depth="basic")
    return [
        SearchResult(
            title=r.get("title", ""),
            url=r.get("url", ""),
            content=r.get("content", ""),
        )
        for r in response.get("results", [])
    ]

"use client";

import { useState, useEffect, useCallback, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SearchResult {
  id: string;
  url: string;
  title: string;
  snippet: string;
  score: number | null;
}

interface SearchResponse {
  query: string;
  total_hits: number;
  page: number;
  limit: number;
  results: SearchResult[];
}

interface Stats {
  pages_fetched: number;
  pages_indexed: number;
  urls_discovered: number;
  active_hosts: number;
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [crawlCompletedCount, setCrawlCompletedCount] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Real-time stats and job status via WebSocket
  useEffect(() => {
    const wsUrl = API_URL.replace(/^http/, 'ws') + '/api/v1/stats/live';
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setStats(data.stats);
        setJobStatus(data.job_status);
        
        // Check for completion
        if (data.job_status === "completed" && data.stats.pages_indexed > 0) {
          setCrawlCompletedCount(data.stats.pages_indexed);
        } else if (data.job_status === "running") {
          // Reset banner if a new job starts
          setCrawlCompletedCount(null);
        }
      } catch (err) {
        console.error("Failed to parse websocket message", err);
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  // Keyboard shortcut: "/" to focus search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "/" && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const search = useCallback(async (q: string, p: number = 1) => {
    if (!q.trim()) {
      setResults(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/search?q=${encodeURIComponent(q)}&page=${p}&limit=20`
      );
      if (!res.ok) throw new Error(`Search failed: ${res.status}`);
      const data: SearchResponse = await res.json();
      setResults(data);
      setPage(p);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInput = (value: string) => {
    setQuery(value);
    setPage(1);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(value, 1), 300);
  };

  const handleNextPage = () => {
    if (results && results.total_hits > page * 20) {
      search(query, page + 1);
    }
  };

  const handlePrevPage = () => {
    if (page > 1) {
      search(query, page - 1);
    }
  };

  return (
    <div className="app">
      {/* ── Hero + Search ── */}
      <section className="hero">
        <h1>DevDocs Search</h1>
        <p>Search across Python, MDN, FastAPI &amp; Kubernetes docs</p>

        <div className="search-container">
          <div className="search-input-wrapper">
            <span className="search-icon">🔍</span>
            <input
              ref={inputRef}
              id="search-input"
              className="search-input"
              type="text"
              placeholder="Search documentation..."
              value={query}
              onChange={(e) => handleInput(e.target.value)}
              autoFocus
            />
            <span className="search-shortcut">/</span>
          </div>
        </div>

        {stats && (
          <div className="stats-bar">
            <div className="stat">
              <div className="stat-value">
                {stats.pages_indexed.toLocaleString()}
              </div>
              <div className="stat-label">Pages Indexed</div>
            </div>
            <div className="stat">
              <div className="stat-value">
                {stats.urls_discovered.toLocaleString()}
              </div>
              <div className="stat-label">URLs Discovered</div>
            </div>
            <div className="stat">
              <div className="stat-value">{stats.active_hosts}</div>
              <div className="stat-label">Active Hosts</div>
            </div>
          </div>
        )}

        {crawlCompletedCount !== null && (
          <div className="completion-banner">
            🎉 Crawl Completed: {crawlCompletedCount.toLocaleString()} pages successfully indexed!
          </div>
        )}
      </section>

      {/* ── Results ── */}
      <section className="results-section">
        {loading && (
          <div className="loading">
            <div className="spinner" />
            <span className="loading-text">Searching...</span>
          </div>
        )}

        {error && (
          <div className="error-state">
            <p>⚠️ {error}</p>
          </div>
        )}

        {results && !loading && (
          <>
            <div className="results-meta">
              <span>
                {results.total_hits.toLocaleString()} results for &ldquo;
                {results.query}&rdquo;
              </span>
            </div>

            {results.results.length === 0 ? (
              <div className="empty-state">
                <div className="icon">📭</div>
                <p>No results found. Try a different search term.</p>
              </div>
            ) : (
              results.results.map((result) => (
                <a
                  key={result.id}
                  href={result.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ textDecoration: "none" }}
                >
                  <div className="result-card">
                    <div className="url">{result.url}</div>
                    <div className="title">
                      {result.title || "Untitled Page"}
                    </div>
                    <div
                      className="snippet"
                      dangerouslySetInnerHTML={{
                        __html: result.snippet || "No preview available.",
                      }}
                    />
                  </div>
                </a>
              ))
            )}

            {results.results.length > 0 && (
              <div className="pagination">
                <button
                  className="btn-page"
                  onClick={handlePrevPage}
                  disabled={page === 1}
                >
                  Previous
                </button>
                <span className="page-info">
                  Page {page} of {Math.ceil(results.total_hits / 20)}
                </span>
                <button
                  className="btn-page"
                  onClick={handleNextPage}
                  disabled={page >= Math.ceil(results.total_hits / 20)}
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}

        {!results && !loading && !error && (
          <div className="empty-state">
            <div className="icon">🔎</div>
            <p>Start typing to search documentation</p>
          </div>
        )}
      </section>

      {/* ── Footer ── */}
      <footer className="footer">
        DevDocs Crawler &amp; Search Engine — Distributed Systems Project
      </footer>
    </div>
  );
}

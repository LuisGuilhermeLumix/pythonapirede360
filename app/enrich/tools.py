"""
tools.py — Ferramentas externas (Tavily, BrasilAPI, Apify) e variantes de teste.

Princípio "não dê erros": TODA chamada é embrulhada — timeout, try/except,
retorno tipado. Nenhuma ferramenta levanta exceção; em falha, devolve vazio.
Se faltar a chave de uma ferramenta, ela simplesmente não age (degradação).

Os resolvers dependem da INTERFACE (search / cnpj_receita / fetch_site_text /
instagram_profile), então em teste injetamos FakeTools sem rede.
"""
from __future__ import annotations

import json
import os
import urllib.request

from app.normalize import digits_only
from app.enrich.models import SearchResult


def _http(method: str, url: str, *, headers: dict | None = None,
          body: dict | None = None, timeout: int = 20, max_bytes: int = 2_000_000):
    """GET/POST JSON robusto. Retorna dict/list em sucesso, None em qualquer falha."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes).decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return None


class HttpTools:
    """Implementação real. Lê chaves do ambiente (EasyPanel)."""

    def __init__(self, tavily_key: str | None = None, apify_token: str | None = None,
                 apify_ig_actor: str | None = None):
        self.tavily_key = tavily_key if tavily_key is not None else os.getenv("TAVILY_API_KEY", "")
        self.apify_token = apify_token if apify_token is not None else os.getenv("APIFY_TOKEN", "")
        self.apify_ig_actor = apify_ig_actor or os.getenv(
            "APIFY_IG_ACTOR", "coderx~instagram-profile-scraper-api"
        )

    # ----- busca web -----
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.tavily_key or not query.strip():
            return []
        resp = _http("POST", "https://api.tavily.com/search", body={
            "api_key": self.tavily_key,
            "query": query,
            "max_results": max_results,
            "include_raw_content": False,
        }, timeout=25)
        if not isinstance(resp, dict):
            return []
        out: list[SearchResult] = []
        for r in (resp.get("results") or []):
            if not isinstance(r, dict):
                continue
            out.append(SearchResult(
                title=r.get("title", "") or "",
                url=r.get("url", "") or "",
                content=r.get("content", "") or "",
                raw_content=r.get("raw_content", "") or "",
            ))
        return out

    # ----- Receita Federal via BrasilAPI (grátis, sem chave) -----
    def cnpj_receita(self, cnpj: str) -> dict | None:
        d = digits_only(cnpj)
        if len(d) != 14:
            return None
        resp = _http("GET", f"https://brasilapi.com.br/api/cnpj/v1/{d}", timeout=20)
        return resp if isinstance(resp, dict) else None

    # ----- conteúdo do site (fetch direto, grátis) -----
    def fetch_site_text(self, url: str) -> str:
        if not url:
            return ""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Rede360Bot)"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read(800_000).decode("utf-8", "replace")
        except Exception:
            return ""

    # ----- perfil do Instagram via Apify (run-sync, sem polling) -----
    def instagram_profile(self, username: str) -> dict | None:
        if not self.apify_token or not username:
            return None
        u = username.lstrip("@")
        url = (f"https://api.apify.com/v2/acts/{self.apify_ig_actor}"
               f"/run-sync-get-dataset-items?token={self.apify_token}")
        resp = _http("POST", url, body={"usernames": [u]}, timeout=90)
        if isinstance(resp, list):
            return resp[0] if resp else None
        return resp if isinstance(resp, dict) else None


class NullTools:
    """Sem rede / sem chaves: tudo vazio. O pipeline degrada graciosamente."""

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return []

    def cnpj_receita(self, cnpj: str) -> dict | None:
        return None

    def fetch_site_text(self, url: str) -> str:
        return ""

    def instagram_profile(self, username: str) -> dict | None:
        return None

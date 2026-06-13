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
import logging
import os
import time
import urllib.request

from app.normalize import digits_only
from app.enrich.models import SearchResult

logger = logging.getLogger("rede360.tools")

# UA de navegador — o default "Python-urllib" é bloqueado por alguns CDNs
# (ex.: BrasilAPI/Vercel). Causa de "funciona no curl, falha no servidor".
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def _http(method: str, url: str, *, headers: dict | None = None,
          body: dict | None = None, timeout: int = 20, max_bytes: int = 2_000_000):
    """GET/POST JSON robusto. Retorna dict/list em sucesso, None em qualquer falha."""
    h = {"User-Agent": _UA}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes).decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}
    except Exception as e:
        status = getattr(e, "code", "")
        logger.warning("HTTP %s %s falhou: %s %s", method, url[:90], type(e).__name__, status)
        return None


def _from_cnpjws(d: dict) -> dict:
    """Converte a resposta do cnpj.ws para o formato da BrasilAPI (que o resto lê)."""
    est = d.get("estabelecimento") or {}
    ap = est.get("atividade_principal") or {}

    def _cnae(x):
        # subclasse vem como "4744-0/99" — só os dígitos: "4744099"
        return digits_only((x or {}).get("subclasse", ""))[:7]

    return {
        "cnpj": digits_only(est.get("cnpj", "")) or digits_only(d.get("cnpj_raiz", "")),
        "razao_social": d.get("razao_social", "") or "",
        "nome_fantasia": est.get("nome_fantasia", "") or "",
        "cnae_fiscal": _cnae(ap),
        "cnaes_secundarios": [{"codigo": _cnae(a)} for a in (est.get("atividades_secundarias") or [])],
        "descricao_situacao_cadastral": (est.get("situacao_cadastral", "") or "").upper(),
        "natureza_juridica": (d.get("natureza_juridica") or {}).get("descricao", "") or "",
        "qsa": [{"nome_socio": s.get("nome", "")} for s in (d.get("socios") or []) if s.get("nome")],
        "uf": (est.get("estado") or {}).get("sigla", "") or "",
        "municipio": (est.get("cidade") or {}).get("nome", "") or "",
        "logradouro": est.get("logradouro", "") or "",
        "numero": str(est.get("numero", "") or ""),
        "bairro": est.get("bairro", "") or "",
        "cep": str(est.get("cep", "") or ""),
        "ddd_telefone_1": (str(est.get("ddd1", "") or "") + str(est.get("telefone1", "") or "")),
        "email": (est.get("email", "") or "").lower(),
        "capital_social": d.get("capital_social", 0),
        "descricao_porte": (d.get("porte") or {}).get("descricao", "") or "",
    }


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
        # BrasilAPI é flaky (timeout/429) — tenta até 3x antes de desistir.
        for tentativa in range(3):
            resp = _http("GET", f"https://brasilapi.com.br/api/cnpj/v1/{d}", timeout=25)
            if isinstance(resp, dict) and resp.get("cnpj"):
                return resp
            if tentativa < 2:
                time.sleep(1.2)
        # Fallback: cnpj.ws público (outra infra) — converte p/ o formato BrasilAPI.
        resp = _http("GET", f"https://publica.cnpj.ws/cnpj/{d}", timeout=25)
        if isinstance(resp, dict) and (resp.get("razao_social") or resp.get("estabelecimento")):
            logger.info("CNPJ %s via fallback cnpj.ws", d)
            return _from_cnpjws(resp)
        logger.warning("CNPJ %s: BrasilAPI e cnpj.ws falharam", d)
        return None

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

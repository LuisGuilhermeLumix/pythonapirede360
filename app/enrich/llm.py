"""
llm.py — A ÚNICA parte fuzzy: extrair produtos/marcas do HTML do site.

Determinismo não resolve "o que essa loja vende" a partir de HTML bagunçado —
isso é trabalho de LLM. Roda SÓ quando há texto de site E uma chave configurada.
Sem chave → retorna {} e o pipeline segue (degradação graciosa).

Provider-agnóstico (env LLM_PROVIDER = openai | anthropic). Default openai, p/
casar com a stack atual. Sem dependências externas (urllib). Nunca levanta erro.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

_SYS = (
    "Você extrai inteligência comercial do conteúdo bruto de sites de empresas "
    "brasileiras de materiais de construção. Responda APENAS JSON válido, sem "
    "markdown. Nunca invente: só inclua o que estiver explícito no texto."
)
_FORMAT = (
    'Formato: {"produtos_principais":["..."],"marcas_trabalhadas":["..."],'
    '"formas_pagamento":["..."],"tem_ecommerce":true,'
    '"contatos_extraidos":{"whatsapp":"ou null","email":"ou null"}}'
)


def _post(url: str, headers: dict, body: dict, timeout: int = 60):
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read(2_000_000).decode("utf-8", "replace"))
    except Exception:
        return None


def _strip_json(raw: str) -> dict:
    clean = re.sub(r"```json|```", "", raw or "").strip()
    try:
        return json.loads(clean)
    except Exception:
        m = re.search(r"\{.*\}", clean, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
        return {}


def _normalize(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    produtos = data.get("produtos_principais") or data.get("produtos") or []
    marcas = data.get("marcas_trabalhadas") or data.get("marcas") or []
    return {
        "produtos": [str(x) for x in produtos if x][:10],
        "marcas": [str(x) for x in marcas if x][:15],
        "tem_ecommerce": bool(data.get("tem_ecommerce")),
        "contatos": data.get("contatos_extraidos") or {},
    }


def extract_site_intel(site_text: str, names: list[str]) -> dict:
    """Extrai produtos/marcas/contatos do texto do site. {} se indisponível."""
    if not site_text:
        return {}
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    if provider == "anthropic":
        return _anthropic(site_text, names)
    return _openai(site_text, names)


def _openai(site_text: str, names: list[str]) -> dict:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return {}
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    user = f"Empresa: {', '.join(n for n in names if n)}\n\nConteúdo:\n{site_text[:60000]}\n\n{_FORMAT}"
    resp = _post(
        "https://api.openai.com/v1/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        {"model": model, "temperature": 0.2,
         "messages": [{"role": "system", "content": _SYS},
                      {"role": "user", "content": user}]},
    )
    try:
        raw = resp["choices"][0]["message"]["content"]
    except Exception:
        return {}
    return _normalize(_strip_json(raw))


def _anthropic(site_text: str, names: list[str]) -> dict:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        return {}
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    user = f"Empresa: {', '.join(n for n in names if n)}\n\nConteúdo:\n{site_text[:60000]}\n\n{_FORMAT}"
    resp = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        {"model": model, "max_tokens": 1024, "system": _SYS,
         "messages": [{"role": "user", "content": user}]},
    )
    try:
        raw = resp["content"][0]["text"]
    except Exception:
        return {}
    return _normalize(_strip_json(raw))

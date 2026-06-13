"""
orchestrator.py — Executa o pipeline com contexto compartilhado.

Ordem importa: CNPJ primeiro (descobre razão social/CNAE) -> Site -> Instagram,
cada um reaproveitando o que veio antes. Cada etapa é isolada: se uma falhar,
registra o erro e segue — o lead nunca se perde por causa de uma fonte.
"""
from __future__ import annotations

from app.enrich.models import LeadContext
from app.enrich.tools import HttpTools
from app.enrich.cnpj import resolve_cnpj
from app.enrich.site import resolve_site
from app.enrich.instagram import resolve_instagram
from app.enrich.decision import consolidate


def default_tools():
    """HttpTools degrada sozinho quando falta chave; serve como padrão seguro."""
    return HttpTools()


def enrich_lead(lead: dict, tools=None) -> dict:
    tools = tools or default_tools()
    ctx = LeadContext.from_lead(lead)

    for stage in (resolve_cnpj, resolve_site, resolve_instagram):
        try:
            stage(ctx, tools)
        except Exception as e:  # nenhuma fonte pode derrubar o lead
            ctx.errors.append(f"{stage.__name__}: {type(e).__name__}: {e}")

    try:
        return consolidate(ctx)
    except Exception as e:
        return {
            "e_icp": ctx.cadastrar_bitrix,
            "cadastrar_bitrix": ctx.cadastrar_bitrix,
            "title": ctx.title,
            "confianca": "baixa",
            "erros": ctx.errors + [f"consolidate: {type(e).__name__}: {e}"],
        }

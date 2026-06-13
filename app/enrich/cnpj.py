"""
cnpj.py — Resolve o CNPJ e puxa a Receita Federal.

Determinístico primeiro: regex sobre os resultados de busca + validação de
dígito + pontuação por contexto (nome/cidade/telefone). Só aceita o melhor
candidato acima do limiar. Depois consulta a Receita e GRAVA razão social /
CNAE no contexto — dados que Site e Instagram vão reaproveitar.
"""
from __future__ import annotations

import re

from app.normalize import is_valid_cnpj, digits_only, normalizar
from app.enrich.scoring import score_match, first_city_token

CNPJ_RX = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
LIMIAR_CNPJ = 30


def resolve_cnpj(ctx, tools) -> None:
    # 1. já veio do Maps?
    pre = digits_only(ctx.raw_lead.get("cnpj_google", ""))
    if is_valid_cnpj(pre):
        ctx.cnpj, ctx.cnpj_source, ctx.cnpj_score = pre, "maps", 100
    else:
        _buscar_cnpj(ctx, tools)

    if ctx.cnpj:
        _consultar_receita(ctx, tools)


def _buscar_cnpj(ctx, tools) -> None:
    query = f"CNPJ {ctx.title} {ctx.city}".strip()
    results = tools.search(query, max_results=5)
    nt, phones = ctx.name_tokens(), ctx.phones()

    agg: dict[str, dict] = {}
    for res in results:
        text = res.text()
        for m in CNPJ_RX.finditer(text):
            c = digits_only(m.group(0))
            if not is_valid_cnpj(c):
                continue
            s, motivos = score_match(
                text=text, names_tokens=nt, cidade_norm=ctx.cidade_norm,
                phones=phones, url=res.url, site_domain=ctx.site_domain or None,
            )
            janela = text[max(0, m.start() - 25): m.start() + 35].lower()
            if "cnpj" in janela:
                s += 20
                motivos = motivos + ["rotulo_cnpj"]
            cur = agg.setdefault(c, {"cnpj": c, "score": 0, "motivos": []})
            cur["score"] += s + 10
            cur["motivos"] = list(dict.fromkeys(cur["motivos"] + motivos))

    cands = sorted(agg.values(), key=lambda x: x["score"], reverse=True)
    ctx.cnpj_candidates = cands[:5]
    if cands and cands[0]["score"] >= LIMIAR_CNPJ:
        ctx.cnpj = cands[0]["cnpj"]
        ctx.cnpj_source = "tavily_regex"
        ctx.cnpj_score = cands[0]["score"]


def _to_float(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


# BrasilAPI v1 devolve situacao_cadastral como CÓDIGO numérico.
_SITUACAO = {
    "1": "NULA", "01": "NULA", "2": "ATIVA", "02": "ATIVA",
    "3": "SUSPENSA", "03": "SUSPENSA", "4": "INAPTA", "04": "INAPTA",
    "8": "BAIXADA", "08": "BAIXADA",
}


def _situacao(data: dict) -> str:
    desc = (data.get("descricao_situacao_cadastral") or "").upper()
    if desc:
        return desc
    code = str(data.get("situacao_cadastral", "")).strip()
    return _SITUACAO.get(code, "")


def _porte(data: dict) -> str:
    return (data.get("descricao_porte") or data.get("porte") or "").upper()


def _consultar_receita(ctx, tools) -> None:
    data = tools.cnpj_receita(ctx.cnpj)
    if not isinstance(data, dict) or not data:
        ctx.add_check("cnpj_receita", False, "Receita não retornou dados")
        return

    cnaes_sec = [str((c or {}).get("codigo", "")) for c in (data.get("cnaes_secundarios") or [])]
    razao = data.get("razao_social", "") or ""
    natureza = data.get("natureza_juridica", "") or ""
    socios = [s.get("nome_socio", "") for s in (data.get("qsa") or []) if s.get("nome_socio")]
    # Empresário Individual / EIRELI / MEI: a razão social É o nome do dono (decisor).
    if not socios and razao and any(k in natureza.lower() for k in ("individual", "empres", "eireli")):
        socios = [razao]

    ctx.receita = {
        "razao_social": razao,
        "nome_fantasia": data.get("nome_fantasia", "") or "",
        "cnae_primario": str(data.get("cnae_fiscal", "") or ""),
        "cnaes_secundarios": [c for c in cnaes_sec if c],
        "situacao": _situacao(data),
        "natureza_juridica": natureza,
        "capital_social": _to_float(data.get("capital_social")),
        "porte": _porte(data),
        "uf": data.get("uf", "") or "",
        "municipio": data.get("municipio", "") or "",
        "logradouro": data.get("logradouro", "") or "",
        "numero": str(data.get("numero", "") or ""),
        "bairro": data.get("bairro", "") or "",
        "cep": str(data.get("cep", "") or ""),
        "telefone": digits_only(data.get("ddd_telefone_1", "")),
        "email": (data.get("email", "") or "").lower(),
        "socios": socios,
    }

    ctx.add_check("cnpj_ativo", ctx.receita["situacao"] == "ATIVA", ctx.receita["situacao"])
    if ctx.cidade_norm and ctx.receita["municipio"]:
        ok = first_city_token(ctx.cidade_norm) in normalizar(ctx.receita["municipio"])
        ctx.add_check("cnpj_cidade_bate", ok, ctx.receita["municipio"])
    # cross-check de ouro: nome fantasia da Receita bate com o nome do Maps?
    if ctx.receita["nome_fantasia"] and ctx.nome_norm:
        nf = normalizar(ctx.receita["nome_fantasia"])
        ok = any(t in nf for t in ctx.name_tokens()) or any(t in ctx.nome_norm for t in nf.split())
        ctx.add_check("cnpj_nome_bate", ok, ctx.receita["nome_fantasia"])

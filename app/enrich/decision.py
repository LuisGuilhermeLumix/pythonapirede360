"""
decision.py — Consolida o dossiê, cruza as fontes e decide ICP + confiança.

Regra de ICP (alinhada ao pedido: "se é do segmento, vai pro Bitrix mesmo com
poucos dados"):
  - Base: segmento confirmado pela categoria do Google Maps (cadastrar_bitrix).
  - Se houver CNPJ: a Receita REFINA — CNPJ inativo ou CNAE bloqueado derruba;
    CNAE alvo confirma. Sem CNPJ, vale a categoria (lead magro ainda passa).
Confiança vem de quantas fontes independentes concordam.
"""
from __future__ import annotations

from app.normalize import normalizar
from app.enrich.scoring import first_city_token

# CNAEs de materiais de construção (alvo) e prefixos claramente fora do segmento.
CNAE_ALVO = {
    "4744001", "4744002", "4744003", "4744004", "4744005", "4744099",
    "4742300", "4741500", "4759801",
}
CNAE_BLOCK_PREFIX = ("45", "4761", "4762", "4763", "4781", "4782", "4783", "56", "96")


def _cnae_status(receita: dict) -> tuple[str, bool, bool]:
    if not receita:
        return ("", False, False)
    todos = [receita.get("cnae_primario", "")] + list(receita.get("cnaes_secundarios") or [])
    todos = [c for c in todos if c]
    alvo = any(c in CNAE_ALVO for c in todos)
    block = any(any(c.startswith(p) for p in CNAE_BLOCK_PREFIX) for c in todos)
    return (",".join(todos), alvo, block and not alvo)


def _montar_endereco(ctx) -> str:
    r = ctx.receita
    if r and r.get("logradouro"):
        partes = [r.get("logradouro", ""), r.get("numero", ""), r.get("bairro", "")]
        return ", ".join(p for p in partes if p)
    return ctx.raw_lead.get("address", "") or ""


def _cidade_estado(ctx) -> str:
    cidade = ctx.receita.get("municipio") or ctx.city
    uf = ctx.receita.get("uf") or ctx.state
    if not (cidade or uf):
        return ""
    return f"{cidade} - {uf}".strip(" -")


def consolidate(ctx) -> dict:
    cnae_str, cnae_alvo, cnae_block = _cnae_status(ctx.receita)
    situacao = ctx.receita.get("situacao", "")

    # ----- decisão ICP -----
    motivos: list[str] = []
    e_icp = ctx.cadastrar_bitrix  # base: categoria do Maps
    if ctx.receita:
        if situacao and situacao != "ATIVA":
            e_icp = False
            motivos.append(f"CNPJ {situacao} na Receita")
        elif cnae_block:
            e_icp = False
            motivos.append(f"CNAE fora do segmento ({cnae_str})")
        elif cnae_alvo:
            e_icp = True
            motivos.append("CNAE de materiais de construção confirmado")
    if e_icp and not motivos:
        motivos.append("Segmento confirmado pela categoria do Google Maps")

    # ----- confiança (quantas fontes concordam) -----
    ok = sum(1 for c in ctx.cross_checks if c["ok"])
    if ctx.cnpj and ctx.site and ok >= 2:
        conf = "alta"
    elif ctx.cnpj or ctx.site or ctx.instagram:
        conf = "media"
    else:
        conf = "baixa"

    # ----- contatos consolidados (melhor fonte primeiro) -----
    whatsapp = ctx.site_whatsapp or ctx.instagram_business_phone or ""
    telefone = ctx.phone_clean or ctx.receita.get("telefone", "") or ""
    email = ctx.site_email or ctx.receita.get("email", "") or ctx.email_maps or ""

    return {
        # decisão
        "e_icp": e_icp,
        "cadastrar_bitrix": e_icp,
        "icp_motivos": motivos,
        "confianca": conf,
        "consistencia": {"checks_ok": ok, "checks_total": len(ctx.cross_checks),
                         "detalhes": ctx.cross_checks},
        # identidade
        "title": ctx.title,
        "razao_social": ctx.receita.get("razao_social", ""),
        "nome_fantasia": ctx.receita.get("nome_fantasia", "") or ctx.title,
        "cnpj": ctx.cnpj,
        "cnpj_fonte": ctx.cnpj_source,
        "cnpj_score": ctx.cnpj_score,
        "cnae_primario": ctx.receita.get("cnae_primario", ""),
        "situacao_cadastral": situacao,
        "socios": ctx.receita.get("socios", []),
        # contato
        "telefone": telefone,
        "whatsapp": whatsapp,
        "email": email,
        "site": ctx.site,
        "site_dominio": ctx.site_domain,
        "instagram": ctx.instagram,
        "instagram_username": ctx.instagram_username,
        "instagram_seguidores": ctx.instagram_followers,
        # comercial
        "produtos": ctx.produtos,
        "marcas": ctx.marcas,
        "tem_ecommerce": ctx.tem_ecommerce,
        # endereço
        "endereco": _montar_endereco(ctx),
        "cidade": ctx.city,
        "estado": ctx.state,
        "cidade_estado": _cidade_estado(ctx),
        # rastreio
        "fontes": {"cnpj": ctx.cnpj_source, "site": ctx.site_source,
                   "instagram": ctx.instagram_source},
        "erros": ctx.errors,
    }

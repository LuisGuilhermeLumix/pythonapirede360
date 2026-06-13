"""
decision.py — Consolida o dossiê, cruza as fontes e qualifica como ICP Rede 360.

Usa a lógica REAL do workflow 03 (icp_rede360 + catalogo_rede360): compara o mix
da loja com as 11 categorias e os 84 fornecedores da rede, aplica os PASSOS de
qualificação e calcula o score de 7 critérios. Saída pronta p/ o briefing/PDF.
"""
from __future__ import annotations

from app.normalize import normalize_phone
from app.enrich.catalogo_rede360 import match_catalogo
from app.enrich.icp_rede360 import avaliar_icp


def _melhor_whatsapp(cands: list) -> str:
    """Escolhe o melhor número de WhatsApp — prefere celular (11 díg.) bem formado."""
    norm = [normalize_phone(c) for c in cands if c]
    norm = [n for n in norm if n]
    for n in norm:
        if len(n) == 11:        # celular com 9 dígitos = WhatsApp válido
            return n
    return norm[0] if norm else ""

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


def _decisor(ctx) -> dict:
    socios = ctx.receita.get("socios") or []
    return {"nome": socios[0] if socios else "", "cargo": "Sócio" if socios else "",
            "fonte": "Receita Federal (QSA)" if socios else ""}


def consolidate(ctx) -> dict:
    cnae_str, cnae_alvo, cnae_block = _cnae_status(ctx.receita)
    situacao = ctx.receita.get("situacao", "")

    # ----- catálogo Rede 360 + qualificação ICP (lógica do workflow 03) -----
    match = match_catalogo(ctx.marcas, ctx.produtos, ctx.site_text)
    icp = avaliar_icp(ctx, match, situacao, cnae_alvo, cnae_block)

    # ----- confiança (quantas fontes independentes concordam) -----
    ok = sum(1 for c in ctx.cross_checks if c["ok"])
    if match["fornecedores_rede360"] and (ctx.cnpj or ctx.site):
        conf = "alta"
    elif ctx.cnpj and ctx.site and ok >= 2:
        conf = "alta"
    elif ctx.cnpj or ctx.site or ctx.instagram:
        conf = "media"
    else:
        conf = "baixa"

    # ----- flag de REVISÃO: identidade não confirmada (o caso perigoso) -----
    checks = {c["check"]: c["ok"] for c in ctx.cross_checks}
    revisar, revisar_motivos = False, []
    if not ctx.cnpj:
        revisar = True
        revisar_motivos.append("CNPJ não confirmado na Receita Federal")
    else:
        if checks.get("cnpj_cidade_bate") is False:
            revisar = True
            revisar_motivos.append("Cidade do CNPJ diverge do Google Maps")
        if checks.get("cnpj_nome_bate") is False:
            revisar = True
            revisar_motivos.append("Razão social não confere com o nome da loja")
    if conf == "baixa" and not revisar_motivos:
        revisar = True
        revisar_motivos.append("Poucas fontes cruzadas — confirmar manualmente")

    # ----- contatos consolidados (melhor fonte primeiro) -----
    whatsapp = _melhor_whatsapp([ctx.site_whatsapp, ctx.instagram_business_phone])
    telefone = ctx.phone_clean or ctx.receita.get("telefone", "") or ""
    email = ctx.site_email or ctx.receita.get("email", "") or ctx.email_maps or ""
    # telefones extras (ex.: fixo da bio) — tira o principal e o WhatsApp p/ não repetir
    _princ = {normalize_phone(telefone), normalize_phone(whatsapp)}
    telefones_extra = [p for p in (ctx.site_phones or [])
                       if normalize_phone(p) and normalize_phone(p) not in _princ]
    # e-mails extras (vendas, financeiro, orçamento...) — tira o principal
    emails_extra = [e for e in (ctx.site_emails or []) if e and e != email]

    return {
        # ----- decisão / qualificação -----
        "e_icp": icp["e_icp"],
        "cadastrar_bitrix": icp["e_icp"],
        "dados_insuficientes": icp["dados_insuficientes"],
        "potencial": icp["potencial"],
        "motivo_icp": icp["motivo_icp"],
        "confianca": conf,
        "revisar": revisar,
        "revisar_motivos": revisar_motivos,
        "consistencia": {"checks_ok": ok, "checks_total": len(ctx.cross_checks),
                         "detalhes": ctx.cross_checks},
        # ----- score (7 critérios, do Agent11) -----
        "score_total": icp["score_total"],
        "score_breakdown": icp["score_breakdown"],
        "classificacao": icp["classificacao"],
        # ----- identidade -----
        "title": ctx.title,
        "razao_social": ctx.receita.get("razao_social", ""),
        "nome_fantasia": ctx.receita.get("nome_fantasia", "") or ctx.title,
        "cnpj": ctx.cnpj,
        "cnpj_fonte": ctx.cnpj_source,
        "cnae_primario": ctx.receita.get("cnae_primario", ""),
        "situacao_cadastral": situacao,
        "socios": ctx.receita.get("socios", []),
        "decisor": _decisor(ctx),
        "porte": ctx.receita.get("porte", ""),
        # ----- contato -----
        "telefone": telefone,
        "whatsapp": whatsapp,
        "email": email,
        "emails_site": emails_extra,
        "telefones_site": telefones_extra,
        "site": ctx.site,
        "site_dominio": ctx.site_domain,
        "instagram": ctx.instagram,
        "instagram_username": ctx.instagram_username,
        "instagram_seguidores": ctx.instagram_followers,
        "instagram_bio": ctx.instagram_bio,
        "bio_link": ctx.bio_link,
        # ----- comercial / mix (p/ o briefing do SDR) -----
        "produtos": ctx.produtos,
        "marcas": ctx.marcas,
        "tem_ecommerce": ctx.tem_ecommerce,
        "segmentos_principais": icp["segmentos_principais"],
        "evidencias_por_categoria": icp["evidencias_por_categoria"],
        "fornecedores_rede360": icp["fornecedores_rede360"],
        "nivel_afinidade": icp["nivel_afinidade"],
        "vende_marcas_rede360": match["vende_marcas_rede360"],
        # ----- endereço -----
        "endereco": _montar_endereco(ctx),
        "cidade": ctx.city,
        "estado": ctx.state,
        "cidade_estado": _cidade_estado(ctx),
        # ----- rastreio -----
        "fontes": {"cnpj": ctx.cnpj_source, "site": ctx.site_source,
                   "instagram": ctx.instagram_source},
        "erros": ctx.errors,
    }

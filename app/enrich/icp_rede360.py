"""
icp_rede360.py — Qualificação ICP da Rede 360 (determinística, do AI Agent11).

Reproduz a lógica do prompt original em código testável:
  - PASSO 1: desqualificação residual (atacadista é o gate determinístico forte).
  - PASSO 2/3: conta categorias confirmadas (2+ evidências) → profundidade do mix.
  - FALLBACK: sem site/Instagram, aprova provisoriamente pelo segmento (Maps/CNAE).
  - SCORE breakdown (7 critérios, máx 100) + classificação Quente/Morno/Frio.

Alinhado ao pedido do negócio: loja DO SEGMENTO entra mesmo com poucos dados
(potencial baixo, dados_insuficientes=true); só atacadista / CNPJ inativo /
CNAE bloqueado é barrado de fato.
"""
from __future__ import annotations

# Fabricantes que operam lojas de MARCA ÚNICA (franquia/concept/showroom).
# Loja "X Shop/Concept" é showroom exclusivo → fora do ICP (lojista multimarca).
FABRICANTES_FRANQUIA = {
    "portobello", "mutina", "eliane", "biancogres", "portinari", "ceusa",
    "villagres", "incepa", "roca", "deca", "docol", "tigre", "suvinil",
    "coral", "lorenzetti", "amanco", "duratex", "tramontina", "castelatto",
    "buschinelli", "embramaco", "cecrisa", "itagres", "elizabeth", "delta",
}
_SUFIXOS_FRANQUIA = ("shop", "concept", "store", "boutique", "showroom",
                     "espaco", "conceito", "studio")


def _franquia_monomarca(ctx) -> str:
    """Detecta franquia/showroom de marca única (Portobello Shop, Tigre Concept).
    Retorna a marca detectada ou "". Exige a marca ADJACENTE a shop/concept/...,
    ou o site ser o domínio do fabricante — não basta a loja só citar a marca."""
    toks = (ctx.nome_norm or "").split()
    for i, t in enumerate(toks):
        if t in FABRICANTES_FRANQUIA:
            viz = toks[max(0, i - 1):i] + toks[i + 1:i + 2]
            if any(v in _SUFIXOS_FRANQUIA for v in viz):
                return t
    dom = ctx.site_domain or ""
    for marca in FABRICANTES_FRANQUIA:
        if marca in dom and any(s in dom for s in _SUFIXOS_FRANQUIA):
            return marca
    return ""


def _potencial(n_categorias: int, tem_whatsapp: bool, tem_telefone: bool,
               tem_decisor: bool, fornecedores: list, rating: float,
               reviews: int, cnpj_ok: bool = False) -> str:
    contato = tem_whatsapp or tem_telefone
    presenca = rating > 4 and reviews >= 20
    # ALTO: mix confirmado (3+ categorias) OU já trabalha com marcas da Rede 360
    if n_categorias >= 3 and contato:
        return "alto"
    if fornecedores and contato and tem_decisor:
        return "alto"
    # MÉDIO: bem IDENTIFICADA (CNPJ ativo + contato direto), mesmo sem mix confirmado
    if cnpj_ok and contato:
        return "medio"
    if contato and presenca:
        return "medio"
    return "baixo"


def _score_breakdown(ctx, match, situacao: str) -> dict:
    rating = float(ctx.raw_lead.get("rating", 0) or 0)
    tem_whatsapp = bool(ctx.site_whatsapp or ctx.instagram_business_phone)
    tem_telefone = bool(ctx.phone_clean or ctx.receita.get("telefone"))
    tem_decisor = bool(ctx.receita.get("socios"))
    tem_email = bool(ctx.site_email or ctx.receita.get("email") or ctx.email_maps)
    seguidores = ctx.instagram_followers or 0

    # tem_cnpj
    if ctx.cnpj and situacao == "ATIVA":
        cnpj_pts = 20
    elif ctx.cnpj:
        cnpj_pts = 10
    else:
        cnpj_pts = 0

    # redes sociais
    if seguidores >= 500:
        redes = 10
    elif ctx.instagram:
        redes = 5
    else:
        redes = 0

    # loja independente (normalize já removeu grandes redes) + bônus fornecedor
    independente = 15 + (5 if match["fornecedores_rede360"] else 0)

    # presença digital
    if ctx.site and rating > 4:
        presenca = 10
    elif ctx.site or rating > 4:
        presenca = 5
    else:
        presenca = 0

    return {
        "tem_cnpj": cnpj_pts,
        "tem_contato_direto": 20 if tem_whatsapp else (10 if tem_telefone else 0),
        "tem_decisor": 15 if tem_decisor else 0,
        "tem_email": 5 if tem_email else 0,
        "tem_redes_sociais": redes,
        "e_loja_independente": independente,
        "tem_presenca_digital": presenca,
    }


def avaliar_icp(ctx, match, situacao: str, cnae: dict) -> dict:
    motivos: list[str] = []
    categorias = match["categorias_confirmadas"]
    segmentos = list(categorias.keys())
    n_cat = match["n_categorias"]
    tem_dados = bool(ctx.site_text or ctx.marcas or ctx.produtos)

    # ----- score (sempre calculado) -----
    breakdown = _score_breakdown(ctx, match, situacao)
    total = sum(breakdown.values())
    classificacao = "Quente" if total >= 70 else "Morno" if total >= 40 else "Frio"

    # ----- PASSO 1 / hard gates -----
    e_icp = True
    dados_insuficientes = False

    franquia = _franquia_monomarca(ctx)

    if situacao and situacao != "ATIVA":
        e_icp = False
        motivos.append(f"CNPJ {situacao} na Receita")
    elif franquia:
        e_icp = False
        motivos.append(f"Franquia/showroom de marca única ({franquia.title()}) — "
                       "não é lojista multimarca (Passo 1d)")
    elif cnae["block"]:
        e_icp = False
        motivos.append("CNAE fora do segmento de materiais de construção")
    elif match["e_atacadista"]:
        e_icp = False
        motivos.append("Atacadista/distribuidor — vende para lojas, não varejo (Passo 1b)")
    elif cnae["tem"] and not cnae["construcao"]:
        # CNPJ confirmado de OUTRO setor (farmácia, alimentos, correios, prefeitura,
        # transporte...) — o CNAE manda sobre a categoria do Google Maps.
        e_icp = False
        motivos.append(f"Setor fora de materiais de construção (CNAE {cnae['str']})")
    else:
        # ----- PASSO 2/3 + FALLBACK -----
        if not tem_dados:
            # sem SITE p/ confirmar o mix de produtos (pode ter Instagram, CNPJ, etc.)
            e_icp = bool(ctx.cadastrar_bitrix or cnae["alvo"] or cnae["construcao"])
            dados_insuficientes = True
            if ctx.categoria_grupo:
                segmentos = [ctx.categoria_grupo]
            if ctx.cnpj:
                motivos.append("Identidade confirmada pelo CNPJ; mix de produtos não "
                               "confirmado (sem site da loja).")
            else:
                motivos.append("Do segmento pelo Google Maps; sem CNPJ/site para confirmar — "
                               "revisar.")
        elif n_cat >= 3:
            motivos.append("Categorias confirmadas com evidência: " + ", ".join(
                f"{c} ({', '.join(categorias[c][:2])})" for c in segmentos[:4]))
        elif ctx.cadastrar_bitrix or cnae["alvo"] or cnae["construcao"]:
            # do segmento, mas profundidade rasa — entra como potencial baixo
            motivos.append(f"Do segmento, mas só {n_cat} categoria(s) confirmada(s) — "
                           "profundidade de mix baixa.")
        else:
            e_icp = False
            motivos.append("Profundidade insuficiente e fora do segmento conhecido (Passo 1e)")

    if e_icp and match["fornecedores_rede360"]:
        motivos.append("Já trabalha com parceiros Rede 360: "
                       + ", ".join(match["fornecedores_rede360"]))

    cnpj_ok = bool(ctx.cnpj) and (not situacao or situacao == "ATIVA")
    potencial = _potencial(
        n_cat,
        bool(ctx.site_whatsapp or ctx.instagram_business_phone),
        bool(ctx.phone_clean), bool(ctx.receita.get("socios")),
        match["fornecedores_rede360"],
        float(ctx.raw_lead.get("rating", 0) or 0),
        int(ctx.raw_lead.get("reviews_count", ctx.raw_lead.get("reviewsCount", 0)) or 0),
        cnpj_ok=cnpj_ok,
    ) if e_icp else "—"

    return {
        "e_icp": e_icp,
        "dados_insuficientes": dados_insuficientes,
        "potencial": potencial,
        "motivo_icp": " ".join(motivos),
        "segmentos_principais": segmentos,
        "evidencias_por_categoria": categorias,
        "fornecedores_rede360": match["fornecedores_rede360"],
        "nivel_afinidade": "alto" if match["fornecedores_rede360"] else "nenhum",
        "score_total": total,
        "score_breakdown": breakdown,
        "classificacao": classificacao,
    }

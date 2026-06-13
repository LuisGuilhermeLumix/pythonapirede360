"""
scoring.py — Decisão de ICP em camadas (híbrido: gate de NÃO-ICP -> score gradual).

Duas decisões SEPARADAS (não confundir):

  cadastrar_bitrix  -> "este lead é ICP?"  -> INCLUSIVO. Todo lead que não é
                       claramente fora-do-ICP é cadastrado no Bitrix. É o que a
                       empresa quer: não perder nenhum lojista do ICP.

  enriquecer        -> "vale gastar crédito de enriquecimento neste lead?" ->
                       otimização de CUSTO. Ordena a fila e decide quem passa
                       por Apify/ScrapingBee/LLM PRIMEIRO. NÃO bloqueia o
                       cadastro: quem não enriquece vai pro Bitrix mesmo assim,
                       só com o dado grátis do Google Maps.

  CAMADA 0 (gate de NÃO-ICP): regras determinísticas que ELIMINAM apenas quem
            nunca poderá ser cliente (rede grande, fabricante/atacado, categoria
            bloqueada, negócio fantasma). Reprovar aqui = não vai pro Bitrix.

  CAMADA 1 (score 0-100): pontua os ICPs e os ordena por prioridade. O limiar
            só decide ENRIQUECIMENTO, nunca o cadastro.

  CAMADA 2 (no n8n): enriquecimento + AI Agent rodam só nos `enriquecer=True`,
            na ORDEM definida aqui. Depois, TODOS os `cadastrar_bitrix=True`
            entram no Bitrix.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Configuração de pesos (ajustável sem mexer na lógica)
# --------------------------------------------------------------------------- #

@dataclass
class PesosICP:
    categoria_compativel: int = 25
    categoria_incerta: int = 8        # sem categoria conhecida -> CNAE decide depois
    nao_e_rede: int = 10
    tem_telefone: int = 18
    tem_site_real: int = 14
    tem_instagram: int = 8
    tem_email: int = 5
    rating_alto: int = 10             # >= 4.3
    rating_bom: int = 5               # >= 4.0
    muitos_reviews: int = 10          # >= 30
    reviews_suficientes: int = 5      # >= 10
    negocio_ativo: int = 8            # horário comercial 5+ dias
    operacao_varejo: int = 6          # entrega + retirada + loja física
    verified: int = 4
    perfil_engajado: int = 4          # photos_count >= 10

    # penalidades (subtraem do score — NÃO removem do Bitrix; só baixam prioridade)
    pen_perfil_problematico: int = 12  # mais reviews ruins que bons
    pen_sem_nenhum_contato: int = 14   # nem telefone, nem site, nem instagram


# Score mínimo para LIBERAR ENRIQUECIMENTO caro. NÃO afeta o cadastro no Bitrix.
# Suba este número para gastar crédito só nos leads mais fortes (cidade grande);
# baixe para enriquecer mais gente (cidade pequena, poucos leads).
LIMIAR_ENRIQUECER = 45


@dataclass
class ResultadoICP:
    is_icp: bool                       # passou no gate de não-ICP
    cadastrar_bitrix: bool             # = is_icp (nome explícito p/ o n8n)
    score: int
    classificacao: str                 # "quente" | "morno" | "frio" | "nao_icp"
    enriquecer: bool                   # gastar crédito de enriquecimento?
    motivos_descarte: list[str] = field(default_factory=list)
    motivos_score: list[str] = field(default_factory=list)
    prioridade: int = 0                # = score, usado para ordenar a fila


# --------------------------------------------------------------------------- #
# Camada 0 — gate de NÃO-ICP (a única coisa que tira o lead do Bitrix)
# --------------------------------------------------------------------------- #

def aplicar_gate(lead: dict) -> list[str]:
    """
    Retorna motivos para NÃO ser ICP. Vazio = é ICP -> vai pro Bitrix.

    Conservador de propósito: só barra quem é COMPROVADAMENTE fora do ICP.
    Na dúvida, o lead passa (a empresa prefere cadastrar um borderline a perder
    um lojista de verdade).
    """
    motivos: list[str] = []
    sinais = lead.get("sinais_maps", {})

    # Categoria bloqueada e grande rede já foram removidas na normalização.
    # Aqui pega só o que sobra e ainda assim não é cliente.

    # Fabricante/atacado: não revende ao consumidor final -> não é ICP.
    if lead.get("e_fabricante_atacado"):
        motivos.append("Nome indica fabricante/atacado, não revenda ao consumidor")

    # Negócio fantasma: sem QUALQUER contato, sem presença (reviews/rating) e
    # sem categoria ICP conhecida. Não dá nem pra trabalhar o lead.
    sem_contato = not (lead.get("phone_clean") or lead.get("website") or lead.get("instagram"))
    sem_presenca = lead.get("reviews_count", 0) == 0 and not lead.get("rating")
    if sem_contato and sem_presenca and lead.get("categoria_incerta"):
        motivos.append("Negócio fantasma: sem contato, sem presença e fora do ICP conhecido")

    return motivos


# --------------------------------------------------------------------------- #
# Camada 1 — score gradual (ordena os ICPs; decide só enriquecimento)
# --------------------------------------------------------------------------- #

def calcular_score(lead: dict, pesos: PesosICP = PesosICP()) -> tuple[int, list[str]]:
    score = 0
    motivos: list[str] = []

    def add(pts: int, label: str):
        nonlocal score
        score += pts
        motivos.append(f"{label} ({'+' if pts >= 0 else ''}{pts})")

    sinais = lead.get("sinais_maps", {})

    # categoria
    if not lead.get("categoria_incerta") and lead.get("categoria_grupo"):
        add(pesos.categoria_compativel, "categoria_compativel")
    elif lead.get("categoria_incerta"):
        add(pesos.categoria_incerta, "categoria_incerta_segue_cnae")

    add(pesos.nao_e_rede, "loja_independente")

    # contatos
    tem_phone = bool(lead.get("phone_clean"))
    tem_site = bool(lead.get("website"))
    tem_insta = bool(lead.get("instagram"))
    if tem_phone:
        add(pesos.tem_telefone, "tem_telefone")
    if tem_site:
        add(pesos.tem_site_real, "tem_site_real")
    if tem_insta:
        add(pesos.tem_instagram, "tem_instagram")
    if lead.get("email"):
        add(pesos.tem_email, "tem_email")

    # reputação
    rating = lead.get("rating", 0)
    if rating >= 4.3:
        add(pesos.rating_alto, "rating_alto")
    elif rating >= 4.0:
        add(pesos.rating_bom, "rating_bom")

    reviews = lead.get("reviews_count", 0)
    if reviews >= 30:
        add(pesos.muitos_reviews, "muitos_reviews")
    elif reviews >= 10:
        add(pesos.reviews_suficientes, "reviews_suficientes")

    # sinais de saúde do negócio (grátis, do Maps)
    if sinais.get("negocio_ativo"):
        add(pesos.negocio_ativo, "negocio_ativo_horario_comercial")
    if sinais.get("tem_entrega") and sinais.get("tem_retirada") and sinais.get("tem_loja_fisica"):
        add(pesos.operacao_varejo, "operacao_varejo_completa")
    if sinais.get("verified"):
        add(pesos.verified, "google_verified")
    if sinais.get("photos_count", 0) >= 10:
        add(pesos.perfil_engajado, "perfil_engajado_fotos")

    # penalidades (baixam prioridade, não removem do Bitrix)
    if sinais.get("perfil_problematico"):
        add(-pesos.pen_perfil_problematico, "perfil_com_reviews_ruins")
    if not (tem_phone or tem_site or tem_insta):
        add(-pesos.pen_sem_nenhum_contato, "sem_nenhum_canal_de_contato")

    score = max(0, min(100, score))
    return score, motivos


def classificar(score: int) -> str:
    if score >= 70:
        return "quente"
    if score >= 45:
        return "morno"
    return "frio"


# --------------------------------------------------------------------------- #
# Orquestrador
# --------------------------------------------------------------------------- #

def avaliar_lead(lead: dict, pesos: PesosICP = PesosICP(),
                 limiar_enriquecer: int = LIMIAR_ENRIQUECER) -> ResultadoICP:
    motivos_descarte = aplicar_gate(lead)
    if motivos_descarte:
        return ResultadoICP(
            is_icp=False, cadastrar_bitrix=False, score=0, classificacao="nao_icp",
            enriquecer=False, motivos_descarte=motivos_descarte, prioridade=0,
        )

    score, motivos_score = calcular_score(lead, pesos)
    return ResultadoICP(
        is_icp=True, cadastrar_bitrix=True, score=score,
        classificacao=classificar(score),
        enriquecer=score >= limiar_enriquecer,
        motivos_score=motivos_score, prioridade=score,
    )


def avaliar_lote(leads: list[dict], pesos: PesosICP = PesosICP(),
                 limiar_enriquecer: int = LIMIAR_ENRIQUECER) -> list[dict]:
    """
    Avalia todos, anexa o resultado e ORDENA por prioridade.
    Ordem: ICP primeiro; dentro do ICP, os que enriquecem primeiro; depois score.
    O n8n consome nessa ordem (enriquece o topo, cadastra TODOS os ICP).
    """
    saida = []
    for lead in leads:
        res = avaliar_lead(lead, pesos, limiar_enriquecer)
        saida.append({
            **lead,
            # decisões canônicas
            "is_icp": res.is_icp,
            "cadastrar_bitrix": res.cadastrar_bitrix,
            "icp_score": res.score,
            "icp_classificacao": res.classificacao,
            "icp_enriquecer": res.enriquecer,
            "icp_motivos_descarte": res.motivos_descarte,
            "icp_motivos_score": res.motivos_score,
            "icp_prioridade": res.prioridade,
            # back-compat / aliases p/ o contrato existente do n8n
            "icp_aprovado_gate": res.is_icp,
            "pre_score_enriquecimento": res.score,
            "pre_score_motivos": res.motivos_score,
            "enriquecimento_recomendado": res.enriquecer,
            "score_icp_rapido": round(res.score / 10),
            "pre_qualificado": res.is_icp,
        })

    saida.sort(
        key=lambda x: (x["cadastrar_bitrix"], x["icp_enriquecer"], x["icp_prioridade"]),
        reverse=True,
    )
    return saida

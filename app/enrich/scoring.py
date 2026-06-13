"""
scoring.py — Cruzamento DETERMINÍSTICO de evidências (sem LLM).

É o que torna o sistema assertivo: ao avaliar um candidato (um CNPJ, um site,
um @), pontuamos o quanto ele bate com TUDO que já sabemos do lead — nome,
cidade, telefone, domínio. Quanto mais fontes concordam, maior a confiança.

Sem LLM de propósito: cruzar nome/cidade/telefone é determinístico, grátis e
mais confiável que um palpite de modelo. O LLM fica reservado p/ ambiguidade real.
"""
from __future__ import annotations

from app.normalize import normalizar, digits_only, domain_of

# Palavras genéricas que não ajudam a identificar a empresa.
STOPWORDS = {
    "loja", "casa", "materiais", "material", "construcao", "deposito", "comercio",
    "ltda", "me", "eireli", "epp", "cia", "sa", "the", "and", "de", "da", "do",
    "dos", "das", "e", "em", "para", "com",
}


def name_tokens(name: str) -> list[str]:
    """Tokens significativos do nome (>=4 letras, fora das stopwords)."""
    return [t for t in normalizar(name).split() if len(t) >= 4 and t not in STOPWORDS]


def first_city_token(cidade_norm: str) -> str:
    """Primeira parte da cidade normalizada (antes da vírgula/UF)."""
    if not cidade_norm:
        return ""
    return cidade_norm.split(",")[0].strip()


def score_match(*, text: str, names_tokens: list[str], cidade_norm: str,
                phones: list[str], url: str | None = None,
                site_domain: str | None = None) -> tuple[int, list[str]]:
    """
    Pontua o quanto `text` (e opcionalmente `url`) corresponde ao lead conhecido.
    Retorna (score, motivos). Não levanta exceção.
    """
    tn = normalizar(text)
    dg = digits_only(text)
    score = 0
    motivos: list[str] = []

    # nome — sinal mais forte
    overlap = sum(1 for t in set(names_tokens) if t and t in tn)
    if overlap:
        pts = min(45, overlap * 15)
        score += pts
        motivos.append(f"nome({overlap})")

    # cidade
    ct = first_city_token(cidade_norm)
    if ct and ct in tn:
        score += 20
        motivos.append("cidade")

    # telefone (compara os últimos 8 dígitos — ignora DDD/formatação)
    for p in phones:
        d = digits_only(p)
        if len(d) >= 8 and d[-8:] in dg:
            score += 20
            motivos.append("telefone")
            break

    # domínio do site já conhecido
    if url and site_domain:
        d = domain_of(url)
        if d and d == site_domain:
            score += 15
            motivos.append("dominio")

    return score, motivos

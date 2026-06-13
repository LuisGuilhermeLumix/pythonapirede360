"""
catalogo_rede360.py — Marcas e categorias que a Rede 360 distribui.

>>> EDITE estas listas com o catálogo REAL da Rede 360. <<<
A semente abaixo são marcas comuns de material de construção no Brasil — troque
pelas que a Rede 360 realmente fornece para que o casamento fique preciso.

Uso: comparar os produtos/marcas que a loja vende (extraídos do site/Instagram)
com este catálogo. Bate = sinal forte de ICP + informação de ouro para o SDR
("a loja já trabalha com Quartzolit e Votorantim, marcas da Rede 360").
"""
from __future__ import annotations

from app.normalize import normalizar, contem_palavra

# Marcas distribuídas pela Rede 360 (EDITE).
MARCAS_REDE360 = {
    "votorantim", "quartzolit", "tigre", "amanco", "suvinil", "coral",
    "deca", "docol", "tramontina", "gerdau", "eternit", "brasilit", "precon",
    "sherwin williams", "lukscolor", "vedacit", "sika", "fortlev", "krona",
    "astra", "celite", "incepa", "portobello", "eliane", "biancogres", "roca",
    "atlas", "vonder", "tigre", "viapol", "denver", "weber", "votoran",
}

# Categorias de produto que a Rede 360 atende (EDITE).
CATEGORIAS_REDE360 = {
    "cimento", "argamassa", "tubos e conexoes", "tintas", "pisos",
    "revestimentos", "loucas", "metais", "ferragens", "hidraulica",
    "eletrica", "telhas", "madeiras", "impermeabilizante", "drywall", "gesso",
}

_MARCAS_NORM = {normalizar(m) for m in MARCAS_REDE360 if m}
_CATS_NORM = {normalizar(c) for c in CATEGORIAS_REDE360 if c}


def match_catalogo(marcas, produtos, texto_site: str = "") -> dict:
    """
    Compara marcas/produtos da loja (+ texto do site) com o catálogo Rede 360.
    Determinístico (match por palavra inteira) — funciona mesmo sem LLM.
    """
    base = " | ".join(str(x) for x in (list(marcas or []) + list(produtos or [])))
    alvo = normalizar(base + " " + (texto_site or "")[:200_000])

    marcas_match = sorted({m for m in _MARCAS_NORM if contem_palavra(alvo, m)})
    cats_match = sorted({c for c in _CATS_NORM if contem_palavra(alvo, c)})
    score = min(100, len(marcas_match) * 25 + len(cats_match) * 8)

    return {
        "marcas_rede360": marcas_match,
        "categorias_rede360": cats_match,
        "score": score,
        "vende_marcas_rede360": bool(marcas_match),
    }

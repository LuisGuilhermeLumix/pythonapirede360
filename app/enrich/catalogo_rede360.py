"""
catalogo_rede360.py — Catálogo OFICIAL da Rede 360 (lista do cliente).

- FORNECEDORES_REDE360: roster oficial dos parceiros (para exibir no briefing).
- CATEGORIAS_PRODUTO: as 11 categorias do ICP, com produtos/marcas-evidência.
- Matching: usa as grafias REAIS das marcas (como aparecem nos sites) e ignora
  parceiros de serviço/financeiro e nomes de palavra comum (evita falso positivo).
"""
from __future__ import annotations

from app.normalize import normalizar, contem_palavra

# --------------------------------------------------------------------------- #
# Roster oficial (lista do cliente). Exibido no briefing.
# --------------------------------------------------------------------------- #
FORNECEDORES_REDE360 = [
    "A.J. Rorato", "Açomóveis", "Agoracred", "Aliança", "Amanco", "Antares",
    "Assertiva", "Atacadão das Tintas", "Atacadão Lazer", "Atlas", "Bakof",
    "Barone", "Bestfer", "Bolt", "Bom Jesus Churrasqueiras", "Bosch",
    "Brasilcard", "Brasilit", "Carmelo Fior", "Cedasa", "Censi", "Certificaminas",
    "Cibra", "Cielo", "Classe A (Eccofer)", "Condor", "Construp", "Conecta360",
    "Cortag", "Cozimax", "Cria", "CRV", "D+Brindes", "Docol", "Dotte", "Dplastic",
    "Egaplast", "Embramaco", "Esquadromil", "Eternit", "Eucadoor", "Eucatex",
    "Fabrinox", "Fame", "Fassa Bortolo", "Fertak", "Formigres", "Fortlev",
    "Forusi", "Gekril", "HF", "Ical", "Incopisos", "Inflet", "Krona", "Lef",
    "Lorenzetti", "Lume", "Marfim", "Mebuki", "Metais Rainha", "MG Margirius",
    "MGM Moveis", "Nova Era", "Oriontec", "Pado", "Pagseguro", "Palma Plásticos",
    "Pix Revestimentos", "Plastubos", "Quartzolit", "Roca Brasil", "RS Chinelos",
    "Safol", "Safra", "Start Quimica", "Talita", "Tambasa", "Tigre",
    "Toyota Empilhadeiras", "Up+", "Urso Polar", "Zagonel",
]

# Grafia interna -> como a marca aparece nos sites (para casar de verdade).
_GRAFIA = {
    "mg margirius": "margirius",
    "roca brasil": "roca",
    "atacadao das tintas": "atacadao das tintas",
}

# Parceiros de serviço/financeiro e palavras comuns — NÃO casar em texto livre
# (gerariam falso positivo, ex.: "cria", "safra", "aliança").
_NAO_CASAR = {
    "agoracred", "assertiva", "brasilcard", "cielo", "pagseguro", "safra",
    "certificaminas", "conecta360", "cria", "bolt", "lume", "alianca", "nova era",
    "marfim", "talita", "barone", "antares", "dotte", "forusi", "censi",
    "rs chinelos", "d brindes", "d+brindes", "acomoveis", "aco moveis", "mgm moveis",
    "bom jesus churrasqueiras", "atacadao lazer", "toyota empilhadeiras",
    "urso polar", "safol", "gekril", "inflet", "oriontec", "construp", "classe a",
    "eccofer", "mebuki", "up", "up+", "hf", "lef", "crv", "ical", "cozimax",
    "a.j. rorato", "aj rorato", "mebuki", "dplastic", "egaplast",
}

# Conjunto de match: (display, grafia_normalizada), só nomes distintivos (>=5).
_FORN_MATCH = []
for _disp in FORNECEDORES_REDE360:
    _n = _GRAFIA.get(normalizar(_disp), normalizar(_disp))
    if len(_n) >= 5 and _n not in _NAO_CASAR:
        _FORN_MATCH.append((_disp, _n))

# --------------------------------------------------------------------------- #
# 11 categorias do ICP — produtos + marcas-evidência (grafias reais dos sites).
# --------------------------------------------------------------------------- #
CATEGORIAS_PRODUTO = {
    "hidraulico": {
        "produtos": ["tubos", "conexoes", "caixa d agua", "caixas d agua", "registro",
                     "registros", "joelho", "luva", "sifao", "fossa"],
        "marcas": ["tigre", "amanco", "krona", "fortlev"],
    },
    "eletrico": {
        "produtos": ["fios", "cabos", "tomadas", "disjuntores", "quadro de luz",
                     "interruptores", "eletroduto", "lampada", "luminaria", "led",
                     "iluminacao"],
        "marcas": ["fame", "margirius", "lorenzetti", "lume", "zagonel"],
    },
    "loucas_metais": {
        "produtos": ["torneiras", "chuveiros", "bacias", "vaso sanitario", "pia",
                     "cuba", "lavatorio", "ducha", "metais sanitarios"],
        "marcas": ["docol", "roca", "lorenzetti", "metais rainha"],
    },
    "argamassas_quimicos": {
        "produtos": ["argamassa", "rejunte", "impermeabilizante", "gesso", "drywall",
                     "massa corrida", "aditivo"],
        "marcas": ["quartzolit", "fassa bortolo", "start quimica"],
    },
    "telhas_coberturas": {
        "produtos": ["telhas", "telha", "cumeeira", "calhas", "telhado", "cobertura"],
        "marcas": ["brasilit", "eternit", "embramaco"],
    },
    "pisos_revestimentos": {
        "produtos": ["porcelanato", "ceramica", "laminado", "piso", "revestimento",
                     "azulejo", "rodape"],
        "marcas": ["carmelo fior", "incopisos", "cedasa", "formigres",
                   "pix revestimentos"],
    },
    "tintas_acabamentos": {
        "produtos": ["tintas", "tinta", "verniz", "massa", "pincel", "rolo",
                     "solvente", "textura", "selador"],
        "marcas": ["eucatex", "atlas", "condor", "atacadao das tintas"],
    },
    "ferragens_ferramentas": {
        "produtos": ["parafusos", "fechaduras", "ferramentas", "dobradica", "cadeado",
                     "broca", "furadeira", "rebite", "disco de corte"],
        "marcas": ["bosch", "bestfer", "pado", "cortag", "fertak", "tambasa"],
    },
    "portas_esquadrias": {
        "produtos": ["portas", "janelas", "batente", "esquadria", "portao", "guarnicao"],
        "marcas": ["eucadoor", "esquadromil", "fabrinox"],
    },
    "plasticos_utilidades": {
        "produtos": ["baldes", "caixa plastica", "embalagens", "mangueira", "lona",
                     "bombona"],
        "marcas": ["plastubos", "palma plasticos", "bakof"],
    },
    "cimento_insumos": {
        "produtos": ["cimento", "cal", "areia", "brita", "pedra", "argila", "bloco",
                     "tijolo"],
        "marcas": ["cibra"],
    },
}

# Sinais de atacado/distribuição (não é varejo ao consumidor → fora do ICP).
ATACADISTA_SINAIS = [
    "atendemos lojistas", "venda no atacado", "vendas no atacado", "somos atacadista",
    "distribuidor autorizado", "linha b2b", "exclusivo para lojistas",
    "revenda para lojas", "preço de atacado para revenda",
]

_CATS_NORM = {
    cat: {normalizar(t) for t in (ev["produtos"] + ev["marcas"])}
    for cat, ev in CATEGORIAS_PRODUTO.items()
}
_ATACADO_NORM = [normalizar(s) for s in ATACADISTA_SINAIS]


def match_catalogo(marcas, produtos, texto_site: str = "") -> dict:
    """
    Compara a loja com o catálogo Rede 360 (determinístico, palavra inteira):
      - quais FORNECEDORES da rede ela cita (grafia real, sem serviços/palavras comuns);
      - quais das 11 CATEGORIAS têm 2+ evidências (produtos/marcas reais);
      - sinais de atacadista.
    """
    base = " | ".join(str(x) for x in (list(marcas or []) + list(produtos or [])))
    alvo = normalizar(base + " " + (texto_site or "")[:200_000])

    fornecedores = sorted({disp for disp, n in _FORN_MATCH if contem_palavra(alvo, n)})

    categorias: dict[str, list[str]] = {}
    for cat, termos in _CATS_NORM.items():
        achados = sorted({t for t in termos if t and contem_palavra(alvo, t)})
        if len(achados) >= 2:
            categorias[cat] = achados

    e_atacadista = any(contem_palavra(alvo, s) for s in _ATACADO_NORM)
    score = min(100, len(fornecedores) * 15 + len(categorias) * 10)

    return {
        "fornecedores_rede360": fornecedores,
        "vende_marcas_rede360": bool(fornecedores),
        "categorias_confirmadas": categorias,
        "n_categorias": len(categorias),
        "e_atacadista": e_atacadista,
        "score": score,
    }

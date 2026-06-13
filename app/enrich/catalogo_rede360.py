"""
catalogo_rede360.py — Catálogo REAL da Rede 360 (extraído do workflow 03).

Fonte: AI Agent11 (definição de ICP) do workflow original. Contém:
  - FORNECEDORES_REDE360: os 84 parceiros oficiais da rede.
  - CATEGORIAS_PRODUTO: as 11 categorias do ICP, cada uma com produtos e marcas
    que servem de EVIDÊNCIA (uma categoria só "conta" com 2+ evidências reais).
  - ATACADISTA_SINAIS: linguagem que indica B2B/atacado (desqualifica — não é varejo).

Tudo determinístico (match por palavra inteira). Casar fornecedores = sinal
forte de ICP e argumento de venda nº 1 ("você já trabalha com a Tigre, que é
parceira da Rede 360").
"""
from __future__ import annotations

from app.normalize import normalizar, contem_palavra

# --------------------------------------------------------------------------- #
# 84 fornecedores/parceiros oficiais da Rede 360 (do AI Agent11)
# --------------------------------------------------------------------------- #
FORNECEDORES_REDE360 = [
    "A.J. Rorato", "Aço Móveis", "Agora Cred", "Aliança", "Amanco", "Antares",
    "Assertiva", "Atacadão das Tintas", "Atacadão Lazer", "Atlas", "Bakof",
    "Barone", "Bestfer", "Bolt", "Bom Jesus Churrasqueiras", "Bosch",
    "Brasilcard", "Brasilit", "Carmelo Fior", "Cedasa", "Censic",
    "Certifica Minas", "Cibrac", "Cielo", "Classe A", "Eccofer", "Condor",
    "Construp", "Conecta360", "Cortag", "Cozimax", "Cria", "CRVD", "D+Brindes",
    "Docol", "Dotte", "Dplastic", "Egaplast", "Embramaço", "Esquadromil",
    "Eternit", "Eucadoor", "Eucatex", "Fabrinox", "Fame", "Fassa Bortolo",
    "Fertak", "Formigrês", "Fortlev", "Forus", "Igekrilh", "Fical", "Incopiso",
    "Inflet", "Krona", "Leflo", "Renzetti", "Lume", "Marmif", "Mebuki",
    "Metais Rainha", "MG Mar", "Girius", "MGM Moveis", "Nova Era", "Oriontec",
    "Pado", "Pagseguro", "Palma Plásticos", "Pix Revestimentos", "Plastubos",
    "Quartzolit", "Roca Brasil", "RS Chinelos", "Safol", "Safra", "Start Quimica",
    "Talita", "Tambasa", "Tigre", "Toyota Empilhadeiras", "Up+", "Urso Polar",
    "Zagonel",
]
_FORN_NORM = [(f, normalizar(f)) for f in FORNECEDORES_REDE360]

# --------------------------------------------------------------------------- #
# 11 categorias do ICP (do AI Agent11, PASSO 2). produtos + marcas = evidência.
# Regras de agrupamento já aplicadas (iluminação→elétrica, gesso→argamassas, etc).
# --------------------------------------------------------------------------- #
CATEGORIAS_PRODUTO = {
    "hidraulico": {
        "produtos": ["tubos", "conexoes", "caixa d agua", "caixas d agua", "registro",
                     "registros", "joelho", "luva", "sifao", "torneira boia", "fossa"],
        "marcas": ["tigre", "amanco", "krona", "fortlev", "aliança"],
    },
    "eletrico": {
        "produtos": ["fios", "cabos", "tomadas", "disjuntores", "quadro de luz",
                     "interruptores", "eletroduto", "lampada", "luminaria", "led",
                     "iluminacao", "automacao"],
        "marcas": ["fame", "margirius", "lume", "zagonel"],
    },
    "loucas_metais": {
        "produtos": ["torneiras", "chuveiros", "bacias", "vaso sanitario", "pia",
                     "cuba", "lavatorio", "ducha", "metais sanitarios"],
        "marcas": ["docol", "roca", "metais rainha"],
    },
    "argamassas_quimicos": {
        "produtos": ["argamassa", "rejunte", "impermeabilizante", "gesso", "drywall",
                     "massa corrida", "aditivo", "cola"],
        "marcas": ["quartzolit", "fassa bortolo", "fassa", "start quimica", "igekrilh"],
    },
    "telhas_coberturas": {
        "produtos": ["telhas", "telha", "cumeeira", "calhas", "telhado", "cobertura"],
        "marcas": ["brasilit", "eternit", "embramaço"],
    },
    "pisos_revestimentos": {
        "produtos": ["porcelanato", "ceramica", "laminado", "piso", "revestimento",
                     "azulejo", "rodape"],
        "marcas": ["carmelo fior", "incopiso", "incepa", "formigrês", "cedasa",
                   "pix revestimentos"],
    },
    "tintas_acabamentos": {
        "produtos": ["tintas", "tinta", "verniz", "massa", "pincel", "rolo",
                     "solvente", "textura", "selador"],
        "marcas": ["eucatex", "atlas", "condor", "atacadão das tintas"],
    },
    "ferragens_ferramentas": {
        "produtos": ["parafusos", "fechaduras", "ferramentas", "dobradica", "cadeado",
                     "broca", "furadeira", "rebite", "disco de corte"],
        "marcas": ["bosch", "bestfer", "pado", "cortag", "fertak", "tambasa",
                   "classe a", "eccofer"],
    },
    "portas_esquadrias": {
        "produtos": ["portas", "janelas", "batente", "esquadria", "portao", "guarnicao"],
        "marcas": ["eucadoor", "esquadromil", "fabrinox"],
    },
    "plasticos_utilidades": {
        "produtos": ["baldes", "caixa plastica", "embalagens", "mangueira", "lona",
                     "bombona"],
        "marcas": ["plastubos", "palma plásticos", "dplastic", "egaplast", "bakof"],
    },
    "cimento_insumos": {
        "produtos": ["cimento", "cal", "areia", "brita", "pedra", "argila", "bloco",
                     "tijolo"],
        "marcas": ["cibrac"],
    },
}

# Sinais de atacado/distribuição (não é varejo ao consumidor → fora do ICP).
ATACADISTA_SINAIS = [
    "atendemos lojistas", "venda no atacado", "vendas no atacado", "somos atacadista",
    "distribuidor autorizado", "linha b2b", "exclusivo para lojistas",
    "revenda para lojas", "preço de atacado para revenda",
]

# Pré-normaliza para performance.
_CATS_NORM = {
    cat: {normalizar(t) for t in (ev["produtos"] + ev["marcas"])}
    for cat, ev in CATEGORIAS_PRODUTO.items()
}
_ATACADO_NORM = [normalizar(s) for s in ATACADISTA_SINAIS]


def match_catalogo(marcas, produtos, texto_site: str = "") -> dict:
    """
    Compara a loja com o catálogo Rede 360 (determinístico, palavra inteira):
      - quais FORNECEDORES da rede ela cita;
      - quais das 11 CATEGORIAS têm 2+ evidências (produtos/marcas reais);
      - sinais de atacadista.
    """
    base = " | ".join(str(x) for x in (list(marcas or []) + list(produtos or [])))
    alvo = normalizar(base + " " + (texto_site or "")[:200_000])

    fornecedores = sorted({orig for orig, norm in _FORN_NORM if norm and contem_palavra(alvo, norm)})

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

"""
normalize.py — Limpeza e extração de sinais do payload bruto do Outscraper.

Filosofia: extrair o MÁXIMO de sinal da resposta do Google Maps (que é barata)
antes de gastar qualquer crédito de enriquecimento (Tavily/Apify/ScrapingBee/LLM).

Trata os 5 problemas reais observados no payload de Alfredo Vasconcelos:
  1. Sites de plataforma (lojalocal.com / gofind) que NÃO são da loja.
  2. Telefone compartilhado entre lojas distintas (dedupe arriscado).
  3. phone_1 com DDD de outro estado (lixo da plataforma).
  4. Falsos positivos de categoria (assistência técnica, fabricante de blocos).
  5. E-mail placeholder de plataforma (info@lojalocal.com).
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Iterable
from urllib.parse import urlparse


# --------------------------------------------------------------------------- #
# Listas de domínio (constantes de negócio)
# --------------------------------------------------------------------------- #

# Plataformas de "comércio local" / agregadores que cadastram a loja com
# dados que NÃO são da loja. Problemas reais: Gofind (Agro Construções),
# Solutudo (Casa do Profissional).
PLATAFORMA_DOMINIOS = {
    "lojalocal.com", "gofind.online", "gofind.com.br", "linktr.ee",
    "beacons.ai", "bio.link", "linkbio.co", "campsite.bio",
    # diretórios/agregadores de empresas BR — listam a loja mas não são o site dela
    "solutudo.com.br", "solutudo.com", "apontador.com.br", "apontador.com",
    "telelistas.net", "guiamais.com.br", "hotfrog.com.br", "hotfrog.com",
    "econodata.com.br", "cnpj.biz", "cnpja.com", "consultasocio.com",
    "informecadastral.com.br", "empresascnpj.com", "guiafacil.com.br",
    "encontraempresa.com.br", "boaspraticas.com.br", "ondefica.com.br",
    "achecerto.com.br", "vrum.com.br", "estabelecimento.info",
}

SOCIAL_JUNK_DOMINIOS = {
    "instagram.com", "facebook.com", "fb.com", "wa.me", "api.whatsapp.com",
    "maps.google.com", "google.com", "g.page", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "tiktok.com",
}

# E-mails genéricos/placeholder que não pertencem à loja.
EMAIL_DOMINIOS_BLOQUEADOS = {
    "lojalocal.com", "gofind.online", "gofind.com.br", "example.com",
    "sentry.io", "wixpress.com", "solutudo.com.br", "solutudo.com",
    "apontador.com.br", "guiamais.com.br", "telelistas.net",
}

# Grandes redes / franquias — nunca são ICP (lojista independente).
NAO_ICP_REDES = [
    "leroy merlin", "sodimac", "telhanorte", "c&c", "cassol", "quero quero",
    "balaroti", "comfortlux", "construfacil", "construnorte", "obramax", "dicico",
    "home center", "lojas americanas", "magazine luiza", "casas bahia",
    "abc da construcao", "rede construai", "clube da casa", "casa show",
]

# Categorias do Google que indicam negócio FORA do ICP (palavra inteira).
CATEGORIAS_BLOQUEADAS = [
    "agencia de emprestimos", "financeira", "banco", "correspondente bancario",
    "seguradora", "imobiliaria", "contabilidade", "advocacia", "restaurante",
    "lanchonete", "mercado", "supermercado", "sacolao", "padaria", "farmacia",
    "clinica", "hospital", "academia", "barbearia", "salao de beleza",
    "centro de estetica", "estetica", "hotel", "pousada", "posto de gasolina",
    "oficina mecanica", "loja de roupas", "loja de moda", "loja de celulares",
    "assistencia tecnica", "assistencia tecnica de eletrodomesticos",
    "loja de moveis", "loja de presentes", "floricultura", "pet shop",
    "banho e tosa", "forum", "presidio", "prefeitura", "camara municipal",
    "cartorio", "delegacia", "escola", "creche", "igreja",
]

# Categorias do Google que CONTAM como ICP (grupo -> termos).
CATEGORIAS_ICP = {
    "materiais_construcao": [
        "loja de materiais de construcao", "deposito de materiais de construcao",
        "casa de materiais de construcao", "material de construcao",
        "deposito de construcao", "comercio de materiais de construcao",
        "building materials", "home improvement",
    ],
    "ferragens_ferramentas": [
        "ferragem", "ferragens e ferramentas", "ferragista", "ferramentaria",
        "loja de ferramentas", "loja de ferragens", "hardware store",
    ],
    "pisos_revestimentos": [
        "loja de pisos e revestimentos", "ceramica e porcelanato",
        "piso e revestimento", "loja de ceramica", "loja de pisos",
        "loja de azulejos", "tile", "flooring",
    ],
    "tintas_acabamentos": [
        "loja de tintas", "tintas e vernizes", "atacadao de tintas",
        "loja de acabamentos", "gesso e drywall", "paint",
    ],
    "hidraulica_eletrica": [
        "material hidraulico", "loja de material eletrico e hidraulico",
        "loja de materiais eletricos", "material eletrico", "eletrica e hidraulica",
        "loja de iluminacao", "plumbing", "electrical",
    ],
    "madeiras_esquadrias": [
        "madeireira", "loja de madeiras", "esquadrias e portas",
        "loja de portas e janelas", "loja de portas", "lumber",
    ],
}

# Nomes que indicam fabricante/atacado (não revenda ao consumidor final).
# "Fenix Blocos" no sample: fabricante de blocos, não loja de revenda.
NOME_FABRICANTE_ATACADO = [
    "blocos", "fabrica", "industria", "ceramica vermelha", "olaria",
    "concreto usinado", "pre-moldados", "premoldados", "distribuidora atacado",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def normalizar(texto: Any) -> str:
    """Lowercase, sem acentos, espaços colapsados."""
    s = str(texto or "")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def contem_palavra(texto_norm: str, termo_norm: str) -> bool:
    """Match por palavra inteira (evita 'mercado' casar com 'supermercadinho')."""
    if not texto_norm or not termo_norm:
        return False
    esc = re.escape(termo_norm)
    return re.search(rf"(^|[^a-z0-9]){esc}([^a-z0-9]|$)", texto_norm) is not None


def first_str(*values: Any) -> str:
    for v in values:
        if v is None:
            continue
        t = str(v).strip()
        if t and t.lower() not in ("null", "none", "undefined"):
            return t
    return ""


def digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_phone(value: Any) -> str:
    """Telefone BR: remove +55, normaliza para 10-11 dígitos."""
    d = digits_only(value)
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) > 11:
        d = d[-11:]
    return d


def is_valid_cnpj(cnpj: Any) -> bool:
    d = digits_only(cnpj)
    if len(d) != 14 or len(set(d)) == 1:
        return False

    def calc(base: str) -> int:
        factor = len(base) - 7
        total = 0
        for ch in base:
            total += int(ch) * factor
            factor -= 1
            if factor < 2:
                factor = 9
        rest = total % 11
        return 0 if rest < 2 else 11 - rest

    return calc(d[:12]) == int(d[12]) and calc(d[:13]) == int(d[13])


def domain_of(url: str) -> str:
    raw = str(url or "").strip().lower()
    if not raw:
        return ""
    if not re.match(r"^https?://", raw):
        raw = "https://" + raw
    try:
        return urlparse(raw).hostname.replace("www.", "", 1) if urlparse(raw).hostname else ""
    except Exception:
        return ""


def _dominio_em(host: str, blocklist: Iterable[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in blocklist)


# --------------------------------------------------------------------------- #
# Extração de campos individuais
# --------------------------------------------------------------------------- #

def normalize_real_site(raw_url: str) -> str:
    """
    Retorna site REAL da loja, ou "" se for rede social, plataforma ou junk.
    Trata o caso lojalocal.com/gofind do sample.
    """
    value = first_str(raw_url)
    if not value:
        return ""
    host = domain_of(value)
    if not host:
        return ""
    if _dominio_em(host, SOCIAL_JUNK_DOMINIOS):
        return ""
    if _dominio_em(host, PLATAFORMA_DOMINIOS):
        return ""
    if re.search(r"\.(gov|jus|mil)\.br$", host) or host.endswith(".gov.br"):
        return ""
    if not re.search(r"\.[a-z]{2,}$", host):  # domínio inventado
        return ""
    v = value if re.match(r"^https?://", value) else "https://" + value
    return re.sub(r"#.*$", "", v)


def normalize_instagram(raw_url: str) -> str:
    v = str(raw_url or "").strip()
    if "instagram.com" not in v.lower():
        return ""
    if re.search(r"instagram\.com/(p|reel|reels|stories|explore)/", v, re.I):
        return ""
    m = re.search(r"instagram\.com/([A-Za-z0-9._]+)", v, re.I)
    if not m or len(m.group(1)) < 2:
        return ""
    handle = m.group(1).lower()
    # handles de plataforma (gofind.online) não são da loja
    if handle in {"gofind.online", "gofind", "lojalocal"}:
        return ""
    return f"https://www.instagram.com/{m.group(1)}/"


def clean_email(raw: str) -> str:
    """Filtra e-mail placeholder de plataforma."""
    e = first_str(raw).lower()
    if "@" not in e:
        return ""
    dom = e.split("@", 1)[1]
    if dom in EMAIL_DOMINIOS_BLOQUEADOS:
        return ""
    return e


# --------------------------------------------------------------------------- #
# Classificação de categoria
# --------------------------------------------------------------------------- #

def detectar_categoria(place: dict, categorias_permitidas: dict) -> dict:
    campos = [place.get("category"), place.get("categoryName"),
              place.get("type"), place.get("subtypes")]
    texto = normalizar(" | ".join(str(c) for c in campos if c))

    if not texto:
        return {"aprovado": False, "bloqueado": False, "incerto": True,
                "grupo": "", "motivo": "Sem categoria oficial (segue para CNAE)"}

    for bloq in CATEGORIAS_BLOQUEADAS:
        if contem_palavra(texto, normalizar(bloq)):
            return {"aprovado": False, "bloqueado": True, "incerto": False,
                    "grupo": "", "motivo": f"Categoria bloqueada: {bloq}"}

    for grupo, termos in categorias_permitidas.items():
        for termo in termos:
            if contem_palavra(texto, normalizar(termo)):
                return {"aprovado": True, "bloqueado": False, "incerto": False,
                        "grupo": grupo, "motivo": ""}

    return {"aprovado": False, "bloqueado": False, "incerto": True,
            "grupo": "", "motivo": f"Categoria fora do ICP conhecido: {texto}"}


# --------------------------------------------------------------------------- #
# Dedupe — chaves seguras
# --------------------------------------------------------------------------- #

def make_dedupe_keys(*, place_id: str, cid: str, cnpj: str, telefone: str,
                     dominio: str, nome: str, cidade: str, address: str) -> list[str]:
    """
    Chaves de dedupe em ordem de confiança.
    IMPORTANTE: telefone NÃO é chave forte isolada — lojas distintas em cidade
    pequena compartilham linha (Agro Material x Agro Construções no sample).
    Telefone só dedupa quando combinado com nome.
    """
    keys = []
    if cnpj:
        keys.append(f"cnpj:{cnpj}")
    if place_id:
        keys.append(f"place:{place_id}")
    if cid:
        keys.append(f"cid:{cid}")
    if dominio:
        keys.append(f"domain:{dominio}")
    if nome and cidade:
        keys.append(f"name_city:{nome}|{cidade}")
    if nome and address:
        keys.append(f"name_address:{nome}|{normalizar(address)}")
    # telefone só com nome (evita fundir lojas que dividem linha)
    if telefone and len(telefone) >= 10 and nome:
        keys.append(f"phone_name:{telefone}|{nome}")
    return list(dict.fromkeys(k for k in keys if k))


# --------------------------------------------------------------------------- #
# Extração de sinais do Google Maps (de graça, antes de enriquecer)
# --------------------------------------------------------------------------- #

def extrair_sinais_maps(place: dict) -> dict:
    """Aproveita campos do Outscraper que indicam saúde do negócio."""
    wh = place.get("working_hours") or {}
    dias_abertos = sum(
        1 for v in wh.values()
        if isinstance(v, list) and v and "fechado" not in normalizar(v[0])
    )
    about = place.get("about") or {}
    servicos = about.get("Opções de serviço") or about.get("Opcoes de servico") or {}
    tem_entrega = bool(servicos.get("Entrega"))
    tem_retirada = bool(servicos.get("Retirada na loja"))
    tem_loja_fisica = bool(servicos.get("Compras na loja"))

    rps = place.get("reviews_per_score") or {}
    reviews_baixos = sum(int(rps.get(str(k), 0) or 0) for k in (1, 2, 3))
    reviews_altos = sum(int(rps.get(str(k), 0) or 0) for k in (4, 5))

    return {
        "dias_abertos_semana": dias_abertos,
        "negocio_ativo": dias_abertos >= 5,
        "tem_entrega": tem_entrega,
        "tem_retirada": tem_retirada,
        "tem_loja_fisica": tem_loja_fisica,
        "photos_count": int(place.get("photos_count") or 0),
        "verified": bool(place.get("verified")),
        "reviews_baixos": reviews_baixos,
        "reviews_altos": reviews_altos,
        "perfil_problematico": reviews_baixos > reviews_altos and reviews_baixos >= 3,
    }


# --------------------------------------------------------------------------- #
# Pipeline principal
# --------------------------------------------------------------------------- #

def flatten(value: Any) -> list:
    if not value:
        return []
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(flatten(v))
        return out
    if isinstance(value, dict):
        if "data" in value:
            return flatten(value["data"])
        if "results" in value:
            return flatten(value["results"])
        return [value]
    return [value]


def normalizar_lote(raw_payload: Any, cidade_base: str = "",
                    categoria: str = "Todas (recomendado)") -> list[dict]:
    """
    Recebe o payload bruto do Outscraper e devolve lista normalizada,
    deduplicada e com sinais extraídos. Pronta para o scoring.
    """
    if categoria == "Todas (recomendado)":
        permitidas = CATEGORIAS_ICP
    else:
        # mapeia label do form para grupos internos
        label_map = {
            "Materiais de Construção": ["materiais_construcao"],
            "Ferragens e Ferramentas": ["ferragens_ferramentas"],
            "Pisos e Revestimentos": ["pisos_revestimentos"],
            "Tintas e Acabamentos": ["tintas_acabamentos"],
            "Hidráulica e Elétrica": ["hidraulica_eletrica"],
            "Madeiras e Esquadrias": ["madeiras_esquadrias"],
        }
        grupos = label_map.get(categoria, list(CATEGORIAS_ICP.keys()))
        permitidas = {g: CATEGORIAS_ICP[g] for g in grupos if g in CATEGORIAS_ICP}

    places = flatten(raw_payload)
    vistos: set[str] = set()
    resultados: list[dict] = []

    for place in places:
        if not isinstance(place, dict):
            continue

        title = first_str(place.get("name"), place.get("title"),
                          place.get("owner_title"), place.get("name_for_emails"))
        if not title:
            continue

        nome_norm = normalizar(title)

        # 1. Fechado permanentemente
        if str(place.get("business_status") or "").upper() == "CLOSED_PERMANENTLY":
            continue

        # 2. Grandes redes
        if any(normalizar(r) in nome_norm for r in NAO_ICP_REDES):
            continue

        # 3. Fabricante/atacado pelo nome
        e_fabricante = any(contem_palavra(nome_norm, normalizar(t))
                           for t in NOME_FABRICANTE_ATACADO)

        address = first_str(place.get("address"), place.get("full_address"))
        place_id = first_str(place.get("place_id"), place.get("placeId"))
        cid = first_str(place.get("cid"))

        # telefone: SEMPRE place.phone, nunca phone_1 (lixo da plataforma)
        phone = first_str(place.get("phone"))
        phone_clean = normalize_phone(phone)

        raw_website = first_str(place.get("website"), place.get("site"))
        website = normalize_real_site(raw_website)
        website_domain = domain_of(website) if website else ""

        instagram = first_str(
            normalize_instagram(place.get("instagram")),
            normalize_instagram(raw_website),
        )
        email = clean_email(first_str(place.get("email_1"), place.get("email_2")))

        cnpj_google = digits_only(first_str(place.get("cnpj"), place.get("CNPJ")))
        if not is_valid_cnpj(cnpj_google):
            cnpj_google = ""

        cidade = first_str(place.get("city"), place.get("county"), cidade_base)
        cidade_norm = normalizar(cidade or cidade_base)

        cat = detectar_categoria(place, permitidas)
        if cat["bloqueado"]:
            continue

        dedupe_keys = make_dedupe_keys(
            place_id=place_id, cid=cid, cnpj=cnpj_google, telefone=phone_clean,
            dominio=website_domain, nome=nome_norm, cidade=cidade_norm, address=address,
        )
        if any(k in vistos for k in dedupe_keys):
            continue
        vistos.update(dedupe_keys)

        sinais = extrair_sinais_maps(place)

        category_name = first_str(place.get("category"), place.get("type"))
        rating = float(place.get("rating") or 0)
        reviews_count = int(place.get("reviews") or 0)
        postal_code = first_str(place.get("postal_code"))
        state = first_str(place.get("state"), place.get("state_code"))
        url = first_str(place.get("location_link"))
        working_hours = place.get("working_hours") or place.get("openingHours")

        resultados.append({
            "title": title,
            "nome_normalizado": nome_norm,
            "categoria_grupo": cat["grupo"],
            "categoria_incerta": cat["incerto"],
            "categoria_motivo": cat["motivo"],
            "e_fabricante_atacado": e_fabricante,
            "address": address,
            "city": cidade,
            "cidade_normalizada": cidade_norm,
            "state": state,
            "phone": phone,
            "phone_clean": phone_clean,
            "website": website,
            "website_domain": website_domain,
            "instagram": instagram,
            "facebook": "",  # facebook do Maps é quase sempre da plataforma; ignora
            "email": email,
            "rating": rating,
            "place_id": place_id,
            "cid": cid,
            "url": url,
            "cnpj_google": cnpj_google,
            "dedupe_keys": dedupe_keys,
            "sinais_maps": sinais,
            "origem_api": "outscraper",

            # ---- aliases p/ o contrato existente do n8n (Edit Fields / Bitrix) ----
            "categoryName": category_name,
            "category_name": category_name,
            "categoria_detectada": cat["grupo"],
            "termo_detectado": cat["grupo"],
            "motivo_reprovacao": cat["motivo"],
            "reviewsCount": reviews_count,
            "reviews_count": reviews_count,
            "placeId": place_id,
            "phoneUnformatted": phone_clean,
            "postalCode": postal_code,
            "postal_code": postal_code,
            "openingHours": json.dumps(working_hours, ensure_ascii=False) if working_hours else "",
        })

    return resultados

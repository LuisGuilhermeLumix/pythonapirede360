"""Testes do pipeline de normalização + scoring contra o sample real."""
from app.normalize import (
    normalizar_lote, normalize_real_site, normalize_instagram, clean_email,
    is_valid_cnpj, normalize_phone, make_dedupe_keys,
)
from app.scoring import avaliar_lote, avaliar_lead
from app.tests.sample_outscraper import SAMPLE


def _leads():
    return normalizar_lote(SAMPLE, cidade_base="Alfredo Vasconcelos, MG")


# --------- normalização de campos isolados ---------

def test_site_plataforma_e_bloqueado():
    assert normalize_real_site("https://www.lojalocal.com/quartzolit/65215972000149") == ""
    assert normalize_real_site("https://gofind.online/loja") == ""

def test_site_real_passa():
    assert normalize_real_site("materiaisxyz.com.br").startswith("https://")

def test_instagram_plataforma_bloqueado():
    assert normalize_instagram("https://www.instagram.com/gofind.online") == ""

def test_instagram_real_passa():
    assert normalize_instagram("https://instagram.com/lojamaterial").endswith("/lojamaterial/")

def test_email_placeholder_bloqueado():
    assert clean_email("info@lojalocal.com") == ""
    assert clean_email("contato@minhaloja.com.br") == "contato@minhaloja.com.br"

def test_cnpj_valido():
    assert is_valid_cnpj("11.222.333/0001-81")
    assert not is_valid_cnpj("11111111111111")

def test_telefone_normalizado():
    assert normalize_phone("+55 32 3367-1430") == "3233671430"

def test_dedupe_telefone_nao_funde_lojas_distintas():
    # mesmo telefone, nomes diferentes -> chaves diferentes
    k1 = make_dedupe_keys(place_id="", cid="", cnpj="", telefone="3233671430",
                          dominio="", nome="agro material", cidade="av", address="rua 36")
    k2 = make_dedupe_keys(place_id="", cid="", cnpj="", telefone="3233671430",
                          dominio="", nome="agro construcoes araujo", cidade="av", address="rua 16")
    assert not set(k1) & set(k2)  # nenhuma chave em comum


# --------- pipeline completo ---------

def test_assistencia_tecnica_removida():
    nomes = [l["title"] for l in _leads()]
    assert "Visius Assistência Técnica" not in nomes

def test_oito_de_nove_sobrevivem_normalizacao():
    assert len(_leads()) == 8

def test_fenix_blocos_descartado_no_gate():
    res = avaliar_lote(_leads())
    fenix = next(r for r in res if r["title"] == "Fenix Blocos")
    assert not fenix["icp_aprovado_gate"]
    assert fenix["icp_score"] == 0

def test_lojas_fortes_sao_quentes():
    res = avaliar_lote(_leads())
    casa = next(r for r in res if "Casa do Profissional" in r["title"])
    assert casa["icp_classificacao"] == "quente"
    assert casa["icp_enriquecer"]

def test_ordenado_por_prioridade():
    res = avaliar_lote(_leads())
    scores = [r["icp_prioridade"] for r in res]
    assert scores == sorted(scores, reverse=True)

def test_dados_gofind_nao_vazam():
    leads = _leads()
    araujo = next(l for l in leads if "Araújo" in l["title"])
    assert araujo["website"] == ""
    assert araujo["instagram"] == ""
    assert araujo["email"] == ""


# --------- nova semântica: ICP inclusivo (todos vão pro Bitrix) ---------

def test_todos_icp_vao_para_bitrix():
    # 8 normalizados; só Fenix (fabricante) é não-ICP -> 7 cadastram no Bitrix.
    res = avaliar_lote(_leads())
    cadastram = [r for r in res if r["cadastrar_bitrix"]]
    assert len(cadastram) == 7
    assert all(r["is_icp"] for r in cadastram)

def test_fenix_nao_cadastra_bitrix():
    res = avaliar_lote(_leads())
    fenix = next(r for r in res if r["title"] == "Fenix Blocos")
    assert fenix["cadastrar_bitrix"] is False
    assert fenix["icp_classificacao"] == "nao_icp"

def test_enriquecer_nao_bloqueia_bitrix():
    # Com limiar altíssimo ninguém enriquece, mas TODOS os ICP ainda cadastram.
    res = avaliar_lote(_leads(), limiar_enriquecer=999)
    assert sum(1 for r in res if r["icp_enriquecer"]) == 0
    assert sum(1 for r in res if r["cadastrar_bitrix"]) == 7

def test_aliases_contrato_n8n_presentes():
    res = avaliar_lote(_leads())
    casa = next(r for r in res if "Casa do Profissional" in r["title"])
    for campo in ("placeId", "reviewsCount", "categoryName", "phoneUnformatted",
                  "postalCode", "openingHours", "enriquecimento_recomendado",
                  "pre_score_enriquecimento", "score_icp_rapido", "categoria_detectada"):
        assert campo in casa, f"alias ausente: {campo}"
    assert casa["placeId"] == casa["place_id"]
    assert casa["reviewsCount"] == casa["reviews_count"]
    assert casa["enriquecimento_recomendado"] == casa["icp_enriquecer"]

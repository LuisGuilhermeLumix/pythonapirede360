"""
Testes do enriquecimento com contexto compartilhado — offline, com FakeTools.

Provam o ponto central: as etapas NÃO trabalham cegas. O resolver de Site usa a
razão social que o de CNPJ descobriu; a consolidação cruza tudo. E nada quebra
quando uma fonte falha (degradação graciosa).
"""
from app.enrich.models import SearchResult
from app.enrich.orchestrator import enrich_lead

CNPJ_VALIDO = "11.222.333/0001-81"  # válido nos dígitos verificadores


class FakeTools:
    """Devolve resultados canados conforme palavra-chave da query/URL. Sem rede."""

    def __init__(self, search_map=None, receita=None, site_html="", ig=None,
                 fetch_map=None):
        self.search_map = search_map or {}
        self.receita_data = receita
        self.site_html = site_html
        self.ig = ig
        self.fetch_map = fetch_map or {}   # substring da URL -> html
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        for chave, resultados in self.search_map.items():
            if chave.lower() in query.lower():
                return resultados
        return []

    def cnpj_receita(self, cnpj):
        return self.receita_data

    def fetch_site_text(self, url):
        for chave, html in self.fetch_map.items():
            if chave.lower() in (url or "").lower():
                return html
        return self.site_html

    def instagram_profile(self, username):
        return self.ig


def _lead():
    return {
        "title": "Casa do Construtor Barbacena",
        "nome_normalizado": "casa do construtor barbacena",
        "city": "Barbacena",
        "cidade_normalizada": "barbacena",
        "state": "MG",
        "phone_clean": "3233671430",
        "website": "",
        "instagram": "",
        "email": "",
        "categoria_grupo": "materiais_construcao",
        "cadastrar_bitrix": True,
        "icp_enriquecer": True,
    }


def _receita_ok():
    return {
        "razao_social": "CONSTRUTOR COMERCIO DE MATERIAIS LTDA",
        "nome_fantasia": "Casa do Construtor",
        "cnae_fiscal": "4744099",
        "cnaes_secundarios": [],
        "descricao_situacao_cadastral": "ATIVA",
        "uf": "MG",
        "municipio": "BARBACENA",
        "logradouro": "RUA OLEGARIO LEAL",
        "numero": "36",
        "bairro": "CENTRO",
        "ddd_telefone_1": "3233671430",
        "qsa": [{"nome_socio": "João da Silva"}],
        "capital_social": 50000,
        "descricao_porte": "MICRO EMPRESA",
    }


# --------------------------------------------------------------------------- #

def test_cnpj_resolvido_por_contexto():
    tools = FakeTools(
        search_map={"cnpj": [SearchResult(
            title="Casa do Construtor - Barbacena/MG",
            url="https://exemplo.com/empresa",
            content=f"CNPJ {CNPJ_VALIDO} - materiais em Barbacena",
        )]},
        receita=_receita_ok(),
    )
    out = enrich_lead(_lead(), tools)
    assert out["cnpj"] == "11222333000181"
    assert out["razao_social"] == "CONSTRUTOR COMERCIO DE MATERIAIS LTDA"
    assert out["e_icp"] is True  # CNAE 4744099 é alvo


def test_site_buscado_pelo_nome_do_outscraper():
    # Busca pelo nome do Outscraper (não razão social). Só aceita o site se o
    # NOME DA LOJA estiver no domínio (construtorbarbacena tem "construtor").
    tools = FakeTools(
        search_map={"site oficial": [SearchResult(
            title="Construtor Materiais", url="https://construtorbarbacena.com.br",
            content="Loja em Barbacena")]},
        site_html='<a href="https://wa.me/5532999990000">zap</a> contato@construtor.com.br',
    )
    out = enrich_lead(_lead(), tools)  # _lead title = "Casa do Construtor Barbacena"
    assert out["site_dominio"] == "construtorbarbacena.com.br"
    assert out["whatsapp"] == "5532999990000"
    assert out["email"] == "contato@construtor.com.br"


def test_site_de_terceiro_que_so_menciona_nome_e_rejeitado():
    # Página que cita nome+cidade mas o domínio não é da loja → NÃO adota.
    tools = FakeTools(
        search_map={"site oficial": [SearchResult(
            title="Notícia sobre Casa do Construtor Barbacena",
            url="https://portaldenoticias.com.br/materia-123",
            content="Casa do Construtor Barbacena inaugura nova unidade")]},
    )
    out = enrich_lead(_lead(), tools)
    assert out["site"] == ""        # domínio sem o nome da loja → rejeitado
    assert out["site_dominio"] == ""


def test_lead_magro_sem_fontes_ainda_e_icp():
    # NullTools-like: nada retorna. O lead do segmento NÃO se perde.
    tools = FakeTools()
    out = enrich_lead(_lead(), tools)
    assert out["e_icp"] is True
    assert out["cadastrar_bitrix"] is True
    assert out["confianca"] == "baixa"
    assert out["cnpj"] == ""
    assert out["erros"] == []


def test_cnae_bloqueado_derruba_icp():
    receita = _receita_ok()
    receita["cnae_fiscal"] = "5611201"  # restaurante -> bloqueado
    tools = FakeTools(
        search_map={"cnpj": [SearchResult(
            title="Empresa", url="https://x.com",
            content=f"CNPJ {CNPJ_VALIDO} Barbacena")]},
        receita=receita,
    )
    out = enrich_lead(_lead(), tools)
    assert out["e_icp"] is False
    assert "fora do segmento" in out["motivo_icp"]


def _receita_brasilapi():
    """Formato REAL da BrasilAPI v1 (situacao por código, qsa vazio)."""
    return {
        "cnpj": "18693875000181",
        "razao_social": "PRESLEY EDUARDO TEIXEIRA",
        "nome_fantasia": "CASA DO PROFISSIONAL",
        "cnae_fiscal": 4744099,
        "cnaes_secundarios": [{"codigo": 2599302, "descricao": "Corte e dobra"}],
        "situacao_cadastral": 2,                 # código (2 = ATIVA), sem descrição
        "natureza_juridica": "Empresário (Individual)",
        "qsa": [],
        "uf": "MG", "municipio": "ALFREDO VASCONCELOS",
        "capital_social": 20000, "descricao_porte": "EMPRESA DE PEQUENO PORTE",
        "ddd_telefone_1": "",
    }


def test_brasilapi_situacao_por_codigo_e_decisor_individual():
    lead = {
        "title": "Casa do Profissional Material de Construcao",
        "city": "Alfredo Vasconcelos", "cidade_normalizada": "alfredo vasconcelos",
        "state": "MG", "phone_clean": "32991423501", "cadastrar_bitrix": True,
        "categoria_grupo": "materiais_construcao", "cnpj_google": "18693875000181",
    }
    out = enrich_lead(lead, FakeTools(receita=_receita_brasilapi()))
    assert out["cnpj"] == "18693875000181"
    assert out["razao_social"] == "PRESLEY EDUARDO TEIXEIRA"
    assert out["situacao_cadastral"] == "ATIVA"                  # código 2 -> ATIVA
    assert out["decisor"]["nome"] == "PRESLEY EDUARDO TEIXEIRA"  # Empresário Individual
    assert out["e_icp"] is True


def test_whatsapp_da_bio_do_instagram():
    lead = {
        "title": "Casa do Profissional", "city": "Alfredo Vasconcelos",
        "cidade_normalizada": "alfredo vasconcelos", "state": "MG",
        "phone_clean": "32991423501", "cadastrar_bitrix": True,
        "categoria_grupo": "materiais_construcao",
        "instagram": "https://www.instagram.com/casadoprofissionalmg/",
    }
    tools = FakeTools(ig={
        "biography": "Material de Construcao e Madeiras em Geral\nWhatsapp 32 99142-3501\nTelefone 32 3367-1143",
        "followersCount": 2806,
        "externalUrl": "https://wa.me/5532991423501",
    })
    out = enrich_lead(lead, tools)
    assert out["instagram_seguidores"] == 2806
    assert "32991423501" in out["whatsapp"]      # WhatsApp da bio capturado


def test_cnpj_inativo_derruba_icp():
    receita = _receita_ok()
    receita["descricao_situacao_cadastral"] = "BAIXADA"
    tools = FakeTools(
        search_map={"cnpj": [SearchResult(
            title="Casa do Construtor", url="https://x.com",
            content=f"CNPJ {CNPJ_VALIDO} Barbacena")]},
        receita=receita,
    )
    out = enrich_lead(_lead(), tools)
    assert out["e_icp"] is False


def test_instagram_do_maps_tem_prioridade():
    lead = _lead()
    lead["instagram"] = "https://www.instagram.com/casadoconstrutor/"
    tools = FakeTools(ig={"followersCount": 1500, "biography": "Materiais de construção"})
    out = enrich_lead(lead, tools)
    assert out["instagram_username"] == "@casadoconstrutor"
    assert out["instagram_seguidores"] == 1500


def test_nunca_levanta_excecao_com_lixo():
    # entradas degeneradas não podem quebrar
    for lixo in [{}, {"title": None}, {"title": 123, "city": None}]:
        out = enrich_lead(lixo, FakeTools())
        assert "e_icp" in out


def test_fornecedores_rede360_detectados_no_site():
    lead = _lead()
    lead["website"] = "https://casadoprofissional.com.br"  # site direto do Maps
    tools = FakeTools(site_html=(
        "Trabalhamos com Quartzolit e tubos Tigre. Vendemos cimento, "
        "argamassa, registros, conexoes e telhas Brasilit."))
    out = enrich_lead(lead, tools)
    assert out["vende_marcas_rede360"] is True
    assert "Tigre" in out["fornecedores_rede360"]
    assert "Quartzolit" in out["fornecedores_rede360"]
    assert "parceiros Rede 360" in out["motivo_icp"]
    assert out["nivel_afinidade"] == "alto"
    assert out["confianca"] == "alta"


def test_categorias_confirmadas_do_mix():
    lead = _lead()
    lead["website"] = "https://x.com.br"
    tools = FakeTools(site_html=(
        "tubos e conexoes Tigre; fios, tomadas e disjuntores; "
        "tintas, verniz e pincel Eucatex"))
    out = enrich_lead(lead, tools)
    # hidráulico + elétrico + tintas confirmados (2+ evidências cada)
    assert set(out["segmentos_principais"]) >= {"hidraulico", "eletrico", "tintas_acabamentos"}
    assert out["e_icp"] is True
    assert out["score_total"] > 0
    assert out["classificacao"] in ("Quente", "Morno", "Frio")


def test_briefing_md_gerado():
    lead = _lead()
    lead["website"] = "https://casadoprofissional.com.br"
    tools = FakeTools(site_html="tubos e conexoes Tigre; tintas e verniz Eucatex; cimento")
    out = enrich_lead(lead, tools)
    md = out["briefing_md"]
    assert md.startswith("# BRIEFING COMERCIAL")
    assert "Casa do Construtor Barbacena" in md
    assert "### 5. SCORE DE QUALIFICAÇÃO" in md
    assert "Rede 360" in md
    # seção 4.2 com fornecedor detectado
    assert "Tigre" in md
    assert "ESTRATÉGIA DE ABORDAGEM" in md
    # versão HTML p/ o Gotenberg
    htmlb = out["briefing_html"]
    assert htmlb.startswith("<!doctype html>")
    assert "<table>" in htmlb
    assert "Casa do Construtor Barbacena" in htmlb


def test_solutudo_nao_contamina():
    # Caso real: a busca acha o diretório Solutudo + o @ da plataforma.
    # O enriquecimento NÃO pode adotar nada disso.
    lead = {
        "title": "Casa do Profissional Material de Construcao",
        "city": "Alfredo Vasconcelos", "cidade_normalizada": "alfredo vasconcelos",
        "state": "MG", "phone_clean": "32991423501", "cadastrar_bitrix": True,
        "categoria_grupo": "materiais_construcao",
    }
    sol = "https://www.solutudo.com.br/empresas/mg/alfredo-vasconcelos/casa-do-profissional7462792"
    tools = FakeTools(
        search_map={
            "site oficial": [SearchResult(title="Casa do Profissional - Solutudo",
                                          url=sol, content="Casa do Profissional Alfredo Vasconcelos")],
            "instagram": [SearchResult(title="Solutudo", url="https://instagram.com/solutudobrasil",
                                       content="Casa do Profissional Alfredo Vasconcelos instagram.com/solutudobrasil")],
        },
        fetch_map={"solutudo": 'wa.me/5514996340966 presleyeduardo@hotmail.com instagram.com/solutudobrasil'},
    )
    out = enrich_lead(lead, tools)
    assert out["site"] == ""                      # Solutudo rejeitado
    assert out["instagram"] == ""                 # @solutudobrasil rejeitado
    assert out["whatsapp"] == ""                  # WhatsApp do Solutudo não vaza
    assert "presley" not in (out["email"] or "")  # email do Solutudo não vaza
    assert out["fornecedores_rede360"] == []      # sem falso positivo "Cria"
    assert out["e_icp"] is True                   # segue ICP pelo segmento


def test_atacadista_e_reprovado():
    lead = _lead()
    lead["website"] = "https://atacado.com.br"
    tools = FakeTools(site_html="Somos atacadista. Atendemos lojistas com venda no atacado. Tigre, cimento, tubos.")
    out = enrich_lead(lead, tools)
    assert out["e_icp"] is False
    assert "tacadista" in out["motivo_icp"] or "varejo" in out["motivo_icp"]


def test_link_da_bio_linktree_extrai_site_e_whatsapp():
    lead = _lead()
    lead["instagram"] = "https://www.instagram.com/lojaconstrutor/"
    tools = FakeTools(
        ig={"followersCount": 800, "biography": "Materiais", "externalUrl": "https://linktr.ee/lojaconstrutor"},
        fetch_map={
            "linktr.ee": '<a href="https://lojaconstrutorreal.com.br">Nosso site</a> '
                         '<a href="https://wa.me/5532988887777">WhatsApp</a>',
            "lojaconstrutorreal.com.br": "Loja de materiais — Quartzolit",
        },
    )
    out = enrich_lead(lead, tools)
    assert out["bio_link"] == "https://linktr.ee/lojaconstrutor"
    assert out["site_dominio"] == "lojaconstrutorreal.com.br"
    assert out["whatsapp"] == "5532988887777"


def test_link_da_bio_site_direto():
    lead = _lead()
    lead["instagram"] = "https://www.instagram.com/loja/"
    tools = FakeTools(
        ig={"externalUrl": "https://minhalojareal.com.br", "followersCount": 100},
        fetch_map={"minhalojareal.com.br": "contato@minhaloja.com.br tubos Tigre"},
    )
    out = enrich_lead(lead, tools)
    assert out["bio_link"] == "https://minhalojareal.com.br"
    assert out["site_dominio"] == "minhalojareal.com.br"
    assert out["email"] == "contato@minhaloja.com.br"

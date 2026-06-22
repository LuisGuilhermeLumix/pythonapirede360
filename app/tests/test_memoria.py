"""Testes da memória de leads já enriquecidos."""
from app.enrich.memoria import Memoria, uuid_de


def test_uuid_deterministico_e_normalizado():
    # mesmo nome (com variação de caixa/espaço) + cidade -> mesmo UUID
    assert uuid_de("Casa do Profissional", "Varginha") == \
           uuid_de("casa do  PROFISSIONAL", "varginha")
    # nomes diferentes -> UUIDs diferentes
    assert uuid_de("Loja A", "X") != uuid_de("Loja B", "X")


def test_mesma_loja_cidades_diferentes_nao_colide():
    assert uuid_de("Agro Material", "Varginha") != uuid_de("Agro Material", "Andradas")


def test_marca_e_pula(tmp_path):
    m = Memoria(str(tmp_path / "m.db"))
    u = uuid_de("Loja X", "Varginha")
    assert m.ja_visto(u) is False        # 1ª vez: não visto
    m.marcar(u, "Loja X", "Varginha")
    assert m.ja_visto(u) is True         # agora visto -> pularia
    assert m.total() == 1


def test_marcar_e_idempotente(tmp_path):
    m = Memoria(str(tmp_path / "m.db"))
    u = uuid_de("Loja Y", "Varginha")
    m.marcar(u, "Loja Y", "Varginha")
    m.marcar(u, "Loja Y", "Varginha")   # de novo
    assert m.total() == 1                # não duplica


def test_persiste_entre_instancias(tmp_path):
    p = str(tmp_path / "m.db")
    u = uuid_de("Loja Z", "Varginha")
    Memoria(p).marcar(u, "Loja Z", "Varginha")
    assert Memoria(p).ja_visto(u) is True   # outra instância lê o mesmo arquivo


def test_limpar(tmp_path):
    m = Memoria(str(tmp_path / "m.db"))
    m.marcar(uuid_de("A", "C"), "A", "C")
    m.marcar(uuid_de("B", "C"), "B", "C")
    assert m.total() == 2
    assert m.limpar() == 2
    assert m.total() == 0

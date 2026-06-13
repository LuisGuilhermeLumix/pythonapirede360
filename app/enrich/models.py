"""
models.py — O "dossiê" compartilhado (LeadContext) e tipos de apoio.

LeadContext é o coração da solução: um único objeto que acumula tudo que
descobrimos. Cada resolver (CNPJ/Site/Instagram) recebe ele inteiro, então o
resolver de Site já sabe a razão social que o de CNPJ achou, e por aí vai.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.normalize import normalizar
from app.enrich.scoring import name_tokens


@dataclass
class SearchResult:
    """Um resultado de busca (Tavily ou equivalente)."""
    title: str = ""
    url: str = ""
    content: str = ""
    raw_content: str = ""

    def text(self) -> str:
        return " ".join(x for x in (self.title, self.content, self.raw_content, self.url) if x)


@dataclass
class LeadContext:
    # ----- entrada (do normalize / Google Maps) -----
    title: str = ""
    nome_norm: str = ""
    city: str = ""
    cidade_norm: str = ""
    state: str = ""
    phone_clean: str = ""
    site_maps: str = ""
    instagram_maps: str = ""
    email_maps: str = ""
    categoria_grupo: str = ""
    cadastrar_bitrix: bool = False
    icp_enriquecer: bool = True
    raw_lead: dict = field(default_factory=dict)

    # ----- CNPJ / Receita -----
    cnpj: str = ""
    cnpj_source: str = ""
    cnpj_score: int = 0
    cnpj_candidates: list = field(default_factory=list)
    receita: dict = field(default_factory=dict)

    # ----- Site -----
    site: str = ""
    site_domain: str = ""
    site_source: str = ""
    site_score: int = 0
    site_phones: list = field(default_factory=list)
    site_email: str = ""
    site_whatsapp: str = ""
    produtos: list = field(default_factory=list)
    marcas: list = field(default_factory=list)
    tem_ecommerce: bool = False

    # ----- Instagram -----
    instagram: str = ""
    instagram_username: str = ""
    instagram_source: str = ""
    instagram_score: int = 0
    instagram_followers: Optional[int] = None
    instagram_bio: str = ""
    instagram_business_phone: str = ""

    # ----- consolidação / rastreio -----
    cross_checks: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    # ------------------------------------------------------------------ #
    @classmethod
    def from_lead(cls, lead: dict) -> "LeadContext":
        lead = lead or {}
        return cls(
            title=lead.get("title", "") or "",
            nome_norm=lead.get("nome_normalizado") or normalizar(lead.get("title", "")),
            city=lead.get("city", "") or "",
            cidade_norm=lead.get("cidade_normalizada") or normalizar(lead.get("city", "")),
            state=lead.get("state", "") or "",
            phone_clean=lead.get("phone_clean", "") or "",
            site_maps=lead.get("website", "") or "",
            instagram_maps=lead.get("instagram", "") or "",
            email_maps=lead.get("email", "") or "",
            categoria_grupo=lead.get("categoria_grupo", "") or "",
            cadastrar_bitrix=bool(lead.get("cadastrar_bitrix", lead.get("is_icp", False))),
            icp_enriquecer=bool(lead.get("icp_enriquecer", True)),
            raw_lead=lead,
        )

    # ----- visões agregadas que os resolvers usam para cruzar fontes ----- #
    def names(self) -> list[str]:
        out = [self.title]
        if self.receita.get("razao_social"):
            out.append(self.receita["razao_social"])
        if self.receita.get("nome_fantasia"):
            out.append(self.receita["nome_fantasia"])
        return [n for n in out if n]

    def name_tokens(self) -> list[str]:
        toks: list[str] = []
        for n in self.names():
            toks += name_tokens(n)
        return list(dict.fromkeys(toks))

    def phones(self) -> list[str]:
        out = [self.phone_clean]
        if self.receita.get("telefone"):
            out.append(self.receita["telefone"])
        out += self.site_phones
        if self.instagram_business_phone:
            out.append(self.instagram_business_phone)
        return [p for p in out if p]

    def add_check(self, name: str, ok: bool, detail: str = "") -> None:
        self.cross_checks.append({"check": name, "ok": bool(ok), "detail": detail})

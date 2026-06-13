"""
site.py — Resolve o site oficial e extrai contatos do conteúdo.

Usa o contexto: a busca do site parte da RAZÃO SOCIAL achada pelo CNPJ (quando
existe), não só do nome do Maps — por isso casa melhor. Extração de contatos é
determinística (regex sobre o HTML). Sites de plataforma/social são descartados
pela mesma regra do normalize.
"""
from __future__ import annotations

import re

from app.normalize import (
    normalize_real_site, domain_of, digits_only, EMAIL_DOMINIOS_BLOQUEADOS,
)
from app.enrich.scoring import score_match
from app.enrich.llm import extract_site_intel

IG_RX = re.compile(r"instagram\.com/([A-Za-z0-9._]+)", re.I)
WA_RX = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\+?\d{10,13})", re.I)
MAIL_RX = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
TEL_RX = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?(?:9\d{4}|\d{4})[-\s]?\d{4}")
LIMIAR_SITE = 25


def resolve_site(ctx, tools) -> None:
    site = normalize_real_site(ctx.site_maps) if ctx.site_maps else ""
    if site:
        ctx.site, ctx.site_domain = site, domain_of(site)
        ctx.site_source, ctx.site_score = "maps", 100
    else:
        _buscar_site(ctx, tools)

    if ctx.site:
        _extrair_do_site(ctx, tools)


def _buscar_site(ctx, tools) -> None:
    base = ctx.receita.get("razao_social") or ctx.title  # <- usa o contexto
    results = tools.search(f"site oficial {base} {ctx.city}", max_results=5)
    nt, phones = ctx.name_tokens(), ctx.phones()

    best_url, best_s = "", 0
    for res in results:
        if not res.url or not normalize_real_site(res.url):  # ignora social/plataforma
            continue
        dom = domain_of(res.url)
        if not dom:
            continue
        s, _ = score_match(text=f"{res.text()} {res.url}", names_tokens=nt,
                           cidade_norm=ctx.cidade_norm, phones=phones)
        if any(t in dom for t in nt):  # nome no próprio domínio = forte
            s += 20
        if s > best_s:
            best_s, best_url = s, res.url

    if best_url and best_s >= LIMIAR_SITE:
        ctx.site = normalize_real_site(best_url)
        ctx.site_domain = domain_of(ctx.site)
        ctx.site_source, ctx.site_score = "tavily", best_s


def _mail_plataforma(mail: str) -> bool:
    dom = mail.split("@", 1)[1].lower() if "@" in mail else ""
    return dom in EMAIL_DOMINIOS_BLOQUEADOS


def _extrair_do_site(ctx, tools) -> None:
    html = tools.fetch_site_text(ctx.site)
    if not html:
        return

    phones = []
    for m in TEL_RX.finditer(html):
        d = digits_only(m.group(0))
        if len(d) >= 10:
            phones.append(d[-11:] if len(d) > 11 else d)
    ctx.site_phones = list(dict.fromkeys(phones))[:5]

    mail = MAIL_RX.search(html)
    if mail and not _mail_plataforma(mail.group(0)):
        ctx.site_email = mail.group(0).lower()

    wa = WA_RX.search(html)
    if wa:
        ctx.site_whatsapp = digits_only(wa.group(1))

    ig = IG_RX.search(html)
    if ig and not ctx.instagram_maps:
        # deixa pista p/ o resolver de Instagram (contexto compartilhado)
        ctx.raw_lead["_site_instagram"] = ig.group(1)

    # cruzamento: o telefone do site bate com o do Maps?
    if ctx.phone_clean and ctx.site_phones:
        ok = any(p[-8:] == ctx.phone_clean[-8:] for p in ctx.site_phones)
        ctx.add_check("site_telefone_bate", ok, ", ".join(ctx.site_phones))

    # parte FUZZY (única que usa LLM): produtos/marcas. Opcional — {} sem chave.
    intel = extract_site_intel(html, ctx.names())
    if intel:
        ctx.produtos = intel.get("produtos") or ctx.produtos
        ctx.marcas = intel.get("marcas") or ctx.marcas
        ctx.tem_ecommerce = bool(intel.get("tem_ecommerce")) or ctx.tem_ecommerce
        contatos = intel.get("contatos") or {}
        if not ctx.site_whatsapp and contatos.get("whatsapp"):
            ctx.site_whatsapp = digits_only(contatos["whatsapp"])
        if not ctx.site_email and contatos.get("email"):
            ctx.site_email = str(contatos["email"]).lower()

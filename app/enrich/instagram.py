"""
instagram.py — Resolve o @ oficial e (opcional) puxa o perfil via Apify.

Usa o contexto: prioriza o @ já achado pelo Maps ou pelo site; senão busca
usando o nome fantasia. O perfil traz seguidores, bio e telefone comercial —
mais um telefone p/ cruzar com as outras fontes.
"""
from __future__ import annotations

import re

from app.normalize import normalize_instagram, digits_only, domain_of, normalize_real_site
from app.enrich.scoring import score_match
from app.enrich.extract import (
    is_aggregator, extract_links, pick_real_site, absorver_contatos,
)

IG_RX = re.compile(r"instagram\.com/([A-Za-z0-9._]+)", re.I)
JUNK_HANDLES = {"p", "reel", "reels", "explore", "stories", "tv", "accounts"}
# Perfis de PLATAFORMAS/diretórios (não são a loja). Problema real: solutudobrasil.
PLATFORM_HANDLES = {
    "solutudobrasil", "solutudo", "gofind", "gofindonline", "gofind.online",
    "lojalocal", "apontador", "guiamais", "telelistas", "linktree", "hotfrog",
}
LIMIAR_IG = 25


def _handle(url: str) -> str:
    m = IG_RX.search(url or "")
    return m.group(1) if m else ""


def _handle_valido(handle: str, nt: list[str]) -> bool:
    """
    @ é da LOJA? Rejeita perfis de plataforma e exige que o handle contenha
    um token do nome da loja (senão é provavelmente de outra empresa/diretório).
    """
    h = (handle or "").lower().strip().lstrip("@")
    if not h or h in PLATFORM_HANDLES or any(p in h for p in PLATFORM_HANDLES):
        return False
    return any(t in h for t in nt) if nt else False


def resolve_instagram(ctx, tools) -> None:
    nt = ctx.name_tokens()
    # 1) @ do Google Maps é confiável (veio da ficha da loja) — usa direto.
    ig = normalize_instagram(ctx.instagram_maps) if ctx.instagram_maps else ""
    # 2) @ achado no site só vale se for da loja (não de plataforma).
    if not ig and ctx.raw_lead.get("_site_instagram"):
        cand = ctx.raw_lead["_site_instagram"]
        if _handle_valido(cand, nt):
            ig = normalize_instagram("https://instagram.com/" + cand)

    if ig:
        ctx.instagram = ig
        ctx.instagram_username = "@" + _handle(ig)
        ctx.instagram_source = "maps_ou_site"
        ctx.instagram_score = 90
    else:
        _buscar_ig(ctx, tools)

    if ctx.instagram_username:
        _perfil_ig(ctx, tools)


def _buscar_ig(ctx, tools) -> None:
    base = ctx.receita.get("nome_fantasia") or ctx.title  # <- usa o contexto
    results = tools.search(f"instagram {base} {ctx.city}", max_results=5)
    nt, phones = ctx.name_tokens(), ctx.phones()

    best_handle, best_s = "", 0
    for res in results:
        for m in IG_RX.finditer(res.text()):
            handle = m.group(1)
            if handle.lower() in JUNK_HANDLES or len(handle) < 3:
                continue
            if not _handle_valido(handle, nt):  # @ tem que ser da loja
                continue
            s, _ = score_match(text=res.text(), names_tokens=nt,
                               cidade_norm=ctx.cidade_norm, phones=phones)
            s += 20  # token do nome já garantido no handle
            if s > best_s:
                best_s, best_handle = s, handle

    if best_handle and best_s >= LIMIAR_IG:
        ctx.instagram = f"https://www.instagram.com/{best_handle}/"
        ctx.instagram_username = "@" + best_handle
        ctx.instagram_source = "tavily"
        ctx.instagram_score = best_s


def _perfil_ig(ctx, tools) -> None:
    prof = tools.instagram_profile(ctx.instagram_username)
    if not isinstance(prof, dict) or not prof:
        return

    def first(*keys):
        for k in keys:
            v = prof.get(k)
            if v not in (None, "", 0):
                return v
        return None

    fol = first("followersCount", "followers", "followed_by_count")
    try:
        ctx.instagram_followers = int(fol) if fol is not None else None
    except (TypeError, ValueError):
        ctx.instagram_followers = None

    ctx.instagram_bio = first("biography", "bio", "description") or ""
    ph = first("businessPhoneNumber", "publicPhoneNumber", "phone")
    if ph:
        ctx.instagram_business_phone = digits_only(ph)

    ext = first("externalUrl", "external_url", "website", "urlInBio")
    if ext:
        ctx.instagram_external_url = str(ext).strip()


def resolve_bio_link(ctx, tools) -> None:
    """
    Segue o link da bio do Instagram. Pode ser o SITE real ou um LINKTREE —
    neste caso, abre o agregador e pega os links de dentro (site, WhatsApp).
    Tudo que achar reforça os contatos do dossiê (informação p/ o PDF do SDR).
    """
    url = (ctx.instagram_external_url or "").strip()
    if not url:
        return

    if is_aggregator(url):
        ctx.bio_link = url
        html = tools.fetch_site_text(url)
        site = pick_real_site(extract_links(html))
        if site and not ctx.site:
            ctx.site = site
            ctx.site_domain = domain_of(site)
            ctx.site_source = "instagram_linktree"
            absorver_contatos(ctx, tools.fetch_site_text(site))
        absorver_contatos(ctx, html)  # WhatsApp/telefone direto no Linktree
    else:
        real = normalize_real_site(url)
        if real:
            ctx.bio_link = real
            if not ctx.site:
                ctx.site = real
                ctx.site_domain = domain_of(real)
                ctx.site_source = "instagram_bio"
            absorver_contatos(ctx, tools.fetch_site_text(real))

"""
instagram.py — Resolve o @ oficial e (opcional) puxa o perfil via Apify.

Usa o contexto: prioriza o @ já achado pelo Maps ou pelo site; senão busca
usando o nome fantasia. O perfil traz seguidores, bio e telefone comercial —
mais um telefone p/ cruzar com as outras fontes.
"""
from __future__ import annotations

import re

from app.normalize import normalize_instagram, digits_only
from app.enrich.scoring import score_match

IG_RX = re.compile(r"instagram\.com/([A-Za-z0-9._]+)", re.I)
JUNK_HANDLES = {"p", "reel", "reels", "explore", "stories", "tv", "accounts"}
LIMIAR_IG = 25


def _handle(url: str) -> str:
    m = IG_RX.search(url or "")
    return m.group(1) if m else ""


def resolve_instagram(ctx, tools) -> None:
    ig = normalize_instagram(ctx.instagram_maps) if ctx.instagram_maps else ""
    if not ig and ctx.raw_lead.get("_site_instagram"):
        ig = normalize_instagram("https://instagram.com/" + ctx.raw_lead["_site_instagram"])

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
            s, _ = score_match(text=res.text(), names_tokens=nt,
                               cidade_norm=ctx.cidade_norm, phones=phones)
            if any(t in handle.lower() for t in nt):
                s += 20
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

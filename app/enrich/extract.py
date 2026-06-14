"""
extract.py — Extração reutilizável de contatos e links de qualquer HTML.

Usado tanto no site da empresa quanto no link da bio do Instagram (que às vezes
é o próprio site, às vezes um Linktree com vários links dentro). Tudo regex,
determinístico, à prova de falha.
"""
from __future__ import annotations

import re

from app.normalize import (
    digits_only, domain_of, normalize_real_site, EMAIL_DOMINIOS_BLOQUEADOS,
)

WA_RX = re.compile(
    r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp\.com/send\?phone=)(\+?\d{10,13})", re.I
)
# "Whatsapp 32 99142-3501", "zap (32) 99142-3501", "wpp: 3299142-3501"
WA_TEXT_RX = re.compile(r"(?:whats?app|whats|wpp|zap)\b[\s:.\-]*(\+?[\d][\d\s().\-]{8,16})", re.I)

# DDDs válidos no Brasil — descarta sequências de dígitos que não são telefone.
VALID_DDD = {
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "21", "22", "24", "27",
    "28", "31", "32", "33", "34", "35", "37", "38", "41", "42", "43", "44", "45",
    "46", "47", "48", "49", "51", "53", "54", "55", "61", "62", "63", "64", "65",
    "66", "67", "68", "69", "71", "73", "74", "75", "77", "79", "81", "82", "83",
    "84", "85", "86", "87", "88", "89", "91", "92", "93", "94", "95", "96", "97",
    "98", "99",
}


def telefone_valido(raw) -> str:
    """Devolve o telefone BR normalizado se for plausível; senão "". Mata o lixo
    do tipo '1199999973', '8000000119' que vem de JS/IDs no HTML."""
    d = digits_only(raw)
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) not in (10, 11):
        return ""
    if d[:2] not in VALID_DDD:
        return ""
    sub = d[2:]
    if len(set(sub)) <= 2:                       # 00000000, 99999999, 12121212
        return ""
    if len(d) == 11 and d[2] != "9":             # celular começa com 9
        return ""
    if len(d) == 10 and d[2] not in "2345":      # fixo começa com 2-5
        return ""
    return d
MAIL_RX = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
TEL_RX = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?(?:9\d{4}|\d{4})[-\s]?\d{4}")
HREF_RX = re.compile(r'href=["\']([^"\']+)["\']', re.I)
IG_RX = re.compile(r"instagram\.com/([A-Za-z0-9._]+)", re.I)

# Agregadores de "link na bio" — não são o site, mas contêm os links reais.
AGREGADORES = (
    "linktr.ee", "linktree", "beacons.ai", "bio.link", "linkbio.co",
    "campsite.bio", "lit.link", "flowpage", "linkfly", "linklist",
)


def is_aggregator(url: str) -> bool:
    d = domain_of(url)
    return any(a in d for a in AGREGADORES)


# Falsos e-mails comuns em HTML: nomes de arquivo/assets e sprites @2x.
_EMAIL_JUNK = re.compile(r"\.(png|jpe?g|gif|svg|webp|css|js|woff2?|ico)$|@\d+x$", re.I)


def _mail_plataforma(mail: str) -> bool:
    dom = mail.split("@", 1)[1].lower() if "@" in mail else ""
    return dom in EMAIL_DOMINIOS_BLOQUEADOS


def _email_ok(e: str) -> bool:
    return bool(e) and not _mail_plataforma(e) and not _EMAIL_JUNK.search(e)


def extract_contacts(html: str) -> dict:
    """Telefones, WhatsApp, TODOS os e-mails e @ de Instagram de um HTML/texto."""
    html = html or ""
    phones = []
    for m in TEL_RX.finditer(html):
        v = telefone_valido(m.group(0))
        if v and v not in phones:
            phones.append(v)

    emails: list[str] = []
    for m in MAIL_RX.finditer(html):
        e = m.group(0).lower()
        if _email_ok(e) and e not in emails:
            emails.append(e)

    wa = WA_RX.search(html)
    ig = IG_RX.search(html)

    return {
        "phones": list(dict.fromkeys(phones))[:8],
        "whatsapp": telefone_valido(wa.group(1)) if wa else "",
        "email": emails[0] if emails else "",
        "emails": emails[:8],
        "instagram": ig.group(1) if ig else "",
    }


def whatsapp_from_text(text: str) -> str:
    """Pega o WhatsApp citado em texto (ex.: bio do Instagram 'Whatsapp 32 ...')."""
    m = WA_RX.search(text or "")
    if m:
        return telefone_valido(m.group(1))
    m = WA_TEXT_RX.search(text or "")
    if m:
        return telefone_valido(m.group(1))
    return ""


def whatsapp_from_link(url: str) -> str:
    """Número de um link wa.me / api.whatsapp."""
    m = WA_RX.search(url or "")
    return telefone_valido(m.group(1)) if m else ""


def extract_links(html: str) -> list[str]:
    """Todos os hrefs de uma página (ex.: os links dentro de um Linktree)."""
    return [m.group(1) for m in HREF_RX.finditer(html or "")]


def pick_real_site(links: list[str]) -> str:
    """Primeiro link que é um site real (não social, não agregador)."""
    for u in links:
        if is_aggregator(u):
            continue
        s = normalize_real_site(u)
        if s:
            return s
    return ""


def absorver_contatos(ctx, html: str, max_text: int = 200_000) -> None:
    """
    Funde os contatos de `html` no dossiê (sem sobrescrever o que já é melhor) e
    acumula o texto p/ o casamento determinístico de marcas Rede 360.
    """
    if not html:
        return
    c = extract_contacts(html)
    if c["phones"]:
        ctx.site_phones = list(dict.fromkeys((ctx.site_phones or []) + c["phones"]))[:8]
    if not ctx.site_whatsapp and c["whatsapp"]:
        ctx.site_whatsapp = c["whatsapp"]
    for e in c.get("emails", []):
        if e and e not in ctx.site_emails:
            ctx.site_emails.append(e)
    if not ctx.site_email and ctx.site_emails:
        ctx.site_email = ctx.site_emails[0]
    if c["instagram"] and not ctx.instagram_maps and not ctx.raw_lead.get("_site_instagram"):
        ctx.raw_lead["_site_instagram"] = c["instagram"]
    ctx.site_text = (ctx.site_text + " " + html)[:max_text]

"""
briefing.py — Gera o BRIEFING COMERCIAL em Markdown (estrutura do AI Agent12).

Pronto para o Gotenberg virar PDF. Partes factuais (dados, score, fornecedores)
são determinísticas; as persuasivas (dores, argumentos, mensagem) vêm do
llm.gerar_insights_comerciais (com fallback estático). Nunca levanta exceção.
"""
from __future__ import annotations

import html as _html
import re
from datetime import date

from app.normalize import normalizar
from app.enrich.catalogo_rede360 import CATEGORIAS_PRODUTO, FORNECEDORES_REDE360
from app.enrich.llm import gerar_insights_comerciais

EMOJI = {"Quente": "🟢", "Morno": "🟡", "Frio": "🔴"}

SEG_LABEL = {
    "hidraulico": "Hidráulico", "eletrico": "Elétrico", "loucas_metais": "Louças e Metais",
    "argamassas_quimicos": "Argamassas e Químicos", "telhas_coberturas": "Telhas e Coberturas",
    "pisos_revestimentos": "Pisos e Revestimentos", "tintas_acabamentos": "Tintas e Acabamentos",
    "ferragens_ferramentas": "Ferragens e Ferramentas", "portas_esquadrias": "Portas e Esquadrias",
    "plasticos_utilidades": "Plásticos e Utilidades", "cimento_insumos": "Cimento e Insumos",
}

SCORE_LABEL = {
    "tem_cnpj": "CNPJ ativo", "tem_contato_direto": "Contato direto (WhatsApp/Tel.)",
    "tem_decisor": "Decisor identificado", "tem_email": "E-mail comercial",
    "tem_redes_sociais": "Redes sociais ativas", "e_loja_independente": "Loja independente",
    "tem_presenca_digital": "Presença digital",
}
SCORE_MAX = {"tem_cnpj": 20, "tem_contato_direto": 20, "tem_decisor": 15, "tem_email": 5,
             "tem_redes_sociais": 10, "e_loja_independente": 20, "tem_presenca_digital": 10}


def _seg(s: str) -> str:
    return SEG_LABEL.get(s, s)


def sugerir_fornecedores(segmentos: list, max_n: int = 3) -> list[str]:
    """Fornecedores Rede 360 relevantes para os segmentos da loja."""
    sug: list[str] = []
    for seg in segmentos:
        for marca in CATEGORIAS_PRODUTO.get(seg, {}).get("marcas", []):
            for f in FORNECEDORES_REDE360:
                if normalizar(f) == normalizar(marca) and f not in sug:
                    sug.append(f)
    if not sug:
        sug = ["Tigre", "Quartzolit", "Eucatex"]
    return sug[:max_n]


def _v(x) -> str:
    return str(x).strip() if x not in (None, "", [], {}) else "Não identificado"


def gerar_briefing_md(dossie: dict, insights: dict | None = None,
                      hoje: str | None = None) -> str:
    d = dossie
    ins = insights or gerar_insights_comerciais(d)
    hoje = hoje or date.today().strftime("%d/%m/%Y")

    classe = d.get("classificacao", "Frio")
    emoji = EMOJI.get(classe, "🔴")
    segs = d.get("segmentos_principais") or []
    seg_txt = ", ".join(_seg(s) for s in segs) or "Materiais de construção"
    decisor = d.get("decisor") or {}
    forn = d.get("fornecedores_rede360") or []

    L = []
    L.append("# BRIEFING COMERCIAL")
    L.append(f"## {_v(d.get('nome_fantasia'))}")
    L.append(f"**Segmento** — {seg_txt}")
    L.append(f"**Data:** {hoje}")
    L.append(f"**Classificação:** {emoji} {classe} — Score: {d.get('score_total', 0)}/100")
    if d.get("dados_insuficientes"):
        L.append("> ⚠️ Aprovação provisória (dados de site/Instagram insuficientes) — revisar.")
    L.append("\n---\n")

    # 1. Dados gerais
    L.append("### 1. DADOS GERAIS DA EMPRESA\n")
    L.append("| Campo | Informação |")
    L.append("|---|---|")
    L.append(f"| Razão Social | {_v(d.get('razao_social'))} |")
    L.append(f"| CNPJ | {_v(d.get('cnpj'))} |")
    L.append(f"| Situação | {_v(d.get('situacao_cadastral'))} |")
    L.append(f"| Cidade/UF | {_v(d.get('cidade_estado'))} |")
    L.append(f"| Endereço | {_v(d.get('endereco'))} |")
    L.append(f"| Telefone | {_v(d.get('telefone'))} |")
    L.append(f"| WhatsApp | {_v(d.get('whatsapp'))} |")
    if d.get("telefones_site"):
        L.append(f"| Outros telefones | {', '.join(d['telefones_site'])} |")
    L.append(f"| E-mail | {_v(d.get('email'))} |")
    L.append(f"| Site | {_v(d.get('site'))} |")
    ig = d.get("instagram")
    seg_ig = f" ({d.get('instagram_seguidores')} seguidores)" if d.get("instagram_seguidores") else ""
    L.append(f"| Instagram | {_v(ig)}{seg_ig} |")
    if d.get("bio_link"):
        L.append(f"| Link da bio | {d.get('bio_link')} |")

    # 2. Decisor
    L.append("\n### 2. DECISOR IDENTIFICADO\n")
    if decisor.get("nome"):
        L.append(f"- **Nome:** {decisor.get('nome')}")
        L.append(f"- **Cargo:** {_v(decisor.get('cargo'))}")
        L.append(f"- **Fonte:** {_v(decisor.get('fonte'))}")
    else:
        L.append("Decisor não identificado nas fontes consultadas.")

    # 3. Perfil do negócio
    L.append("\n### 3. PERFIL DO NEGÓCIO\n")
    L.append(f"- **Porte:** {_v(d.get('porte'))}")
    L.append(f"- **Segmentos confirmados:** {seg_txt}")
    if d.get("marcas"):
        L.append(f"- **Marcas no mix:** {', '.join(d['marcas'][:12])}")
    if d.get("produtos"):
        L.append(f"- **Produtos:** {', '.join(d['produtos'][:12])}")
    L.append(f"- **E-commerce:** {'Sim' if d.get('tem_ecommerce') else 'Não identificado'}")

    # 4. Qualificação
    L.append("\n### 4. QUALIFICAÇÃO PARA A REDE 360\n")
    L.append("#### 4.1 Enquadramento no ICP")
    L.append(f"- **É ICP:** {'✅ Sim' if d.get('e_icp') else '❌ Não'}  |  **Potencial:** {_v(d.get('potencial'))}")
    L.append(f"- {_v(d.get('motivo_icp'))}")
    ev = d.get("evidencias_por_categoria") or {}
    if ev:
        L.append("- **Evidências por categoria:**")
        for cat, termos in ev.items():
            L.append(f"  - {_seg(cat)}: {', '.join(termos[:4])}")

    L.append("\n#### 4.2 Conexão com Fornecedores da Rede 360")
    if forn:
        L.append(f"🤝 **Esta empresa já tem afinidade com a Rede 360!** Já trabalha com "
                 f"**{', '.join(forn)}**, que são parceiros da rede — imagine ter condições "
                 f"exclusivas com eles através da central!")
    else:
        sug = ", ".join(sugerir_fornecedores(segs))
        L.append(f"A Rede 360 pode conectar esta empresa a fornecedores líderes como "
                 f"**{sug}**, relevantes para o mix da loja.")

    L.append("\n#### 4.3 Pontos de Dor Identificados")
    for p in ins.get("pontos_de_dor", []):
        L.append(f"- {p}")

    L.append("\n#### 4.4 Argumentos de Venda Recomendados")
    for a in ins.get("argumentos", []):
        L.append(f"- {a}")

    L.append("\n#### 4.5 Objeções e Contra-Argumentos\n")
    L.append("| Objeção | Contra-Argumento |")
    L.append("|---|---|")
    for o in ins.get("objecoes", []):
        L.append(f"| {o.get('objecao', '')} | {o.get('resposta', '')} |")

    # 5. Score
    L.append("\n### 5. SCORE DE QUALIFICAÇÃO\n")
    L.append("| Critério | Pontos |")
    L.append("|---|---|")
    bd = d.get("score_breakdown") or {}
    for k, label in SCORE_LABEL.items():
        L.append(f"| {label} | {bd.get(k, 0)}/{SCORE_MAX[k]} |")
    L.append(f"| **TOTAL** | **{d.get('score_total', 0)}/100** |")

    # 6. Estratégia
    L.append("\n### 6. ESTRATÉGIA DE ABORDAGEM\n")
    L.append(f"- **Canal preferencial:** {_v(ins.get('canal'))}")
    L.append("- **Mensagem de primeiro contato:**")
    L.append(f"> {_v(ins.get('mensagem'))}")
    L.append(f"- **Cadência de follow-up:** {_v(ins.get('cadencia'))}")

    # 7. Observações
    L.append("\n### 7. OBSERVAÇÕES E PRÓXIMOS PASSOS\n")
    conf = d.get("confianca", "baixa")
    L.append(f"- Confiança do enriquecimento: **{conf}** "
             f"({(d.get('consistencia') or {}).get('checks_ok', 0)} cruzamentos confirmados).")
    if d.get("erros"):
        L.append(f"- Limitações técnicas: {len(d['erros'])} fonte(s) com falha — revisar manualmente.")
    L.append("- Próximo passo: abordar pelo canal preferencial com a mensagem acima.")

    L.append("\n---\n*Rede 360 — Briefing Confidencial*")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Markdown -> HTML (p/ o Gotenberg gerar o PDF direto, sem conversão no n8n)
# --------------------------------------------------------------------------- #

_CSS = (
    "<style>body{font-family:Arial,Helvetica,sans-serif;color:#1a1a2e;max-width:780px;"
    "margin:24px auto;line-height:1.5;font-size:13px}"
    "h1{color:#0b3d91;border-bottom:3px solid #0b3d91;padding-bottom:6px}"
    "h2{color:#0b3d91;margin-top:2px}"
    "h3{color:#16213e;border-bottom:1px solid #ddd;padding-bottom:4px;margin-top:22px}"
    "h4{color:#0b3d91;margin-bottom:4px}"
    "table{border-collapse:collapse;width:100%;margin:8px 0}"
    "th,td{border:1px solid #cbd5e1;padding:6px 8px;text-align:left;font-size:12px}"
    "th{background:#0b3d91;color:#fff}"
    "blockquote{background:#f1f5f9;border-left:4px solid #0b3d91;margin:8px 0;padding:8px 12px;font-style:italic}"
    "hr{border:none;border-top:1px solid #e2e8f0;margin:14px 0}"
    "ul{margin:4px 0 4px 18px}strong{color:#0b3d91}</style>"
)


def _inline(t: str) -> str:
    t = _html.escape(t)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)


def markdown_to_html(md: str) -> str:
    lines = (md or "").split("\n")
    out: list[str] = []
    i, in_list = 0, False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < len(lines):
        s = lines[i].strip()
        if not s:
            close_list(); i += 1; continue
        # tabela
        if s.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].strip()) <= set("|-: "):
            close_list()
            header = [c.strip() for c in s.strip("|").split("|")]
            out.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in header)
                       + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue
        if s.startswith("####"):
            close_list(); out.append(f"<h4>{_inline(s[4:].strip())}</h4>")
        elif s.startswith("###"):
            close_list(); out.append(f"<h3>{_inline(s[3:].strip())}</h3>")
        elif s.startswith("##"):
            close_list(); out.append(f"<h2>{_inline(s[2:].strip())}</h2>")
        elif s.startswith("#"):
            close_list(); out.append(f"<h1>{_inline(s[1:].strip())}</h1>")
        elif s == "---":
            close_list(); out.append("<hr>")
        elif s.startswith(">"):
            close_list(); out.append(f"<blockquote>{_inline(s[1:].strip())}</blockquote>")
        elif s.startswith("- "):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{_inline(s[2:].strip())}</li>")
        else:
            close_list(); out.append(f"<p>{_inline(s)}</p>")
        i += 1
    close_list()
    return "\n".join(out)


def gerar_briefing_html(md: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'>{_CSS}</head><body>{markdown_to_html(md)}</body></html>"

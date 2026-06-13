"""
main.py — API Rede 360 (tratamento + scoring de leads do Outscraper).

Endpoints:
  POST /process       -> payload bruto do Outscraper -> leads normalizados +
                         scored + ordenados. Resposta com estatísticas.
  POST /process/items -> igual, mas devolve só o ARRAY de leads (ideal p/ o n8n
                         iterar direto no Loop Over Items, sem Split Out).
  POST /process/raw   -> aceita o array cru do Outscraper direto no body.
  GET  /health        -> healthcheck para o EasyPanel.

Decisões que o n8n consome (por lead):
  cadastrar_bitrix  -> True = é ICP, REGISTRA no Bitrix (inclusivo).
  icp_enriquecer    -> True = vale gastar crédito de enriquecimento antes.

Auth: header  X-API-Key: <token>   (defina API_KEY no ambiente do EasyPanel).
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.normalize import normalizar_lote
from app.scoring import avaliar_lote, PesosICP, LIMIAR_ENRIQUECER
from app.enrich.orchestrator import enrich_lead

logger = logging.getLogger("rede360")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Rede 360 — Lead Processor", version="2.6.0")

API_KEY = os.getenv("API_KEY", "")


@app.on_event("startup")
def _aviso_seguranca():
    if not API_KEY:
        logger.warning(
            "API_KEY não definida — a API está ABERTA (modo dev). "
            "Defina a env var API_KEY no EasyPanel antes de usar em produção."
        )


def _check_auth(x_api_key: str | None):
    if not API_KEY:
        return  # sem API_KEY = modo aberto (dev). Aviso emitido no startup.
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="X-API-Key inválida ou ausente")


class ProcessRequest(BaseModel):
    payload: Any = Field(..., description="Resposta bruta do Outscraper")
    cidade: str = Field("", description="Cidade base (ex: 'Uberlândia, MG')")
    categoria: str = Field("Todas (recomendado)")
    limiar_enriquecer: int | None = Field(
        None, description="Sobrescreve o limiar de ENRIQUECIMENTO (default 45). "
                          "NÃO afeta o cadastro no Bitrix."
    )


class LeadOut(BaseModel):
    leads: list[dict]
    total_recebido: int
    total_apos_normalizacao: int
    total_icp: int                 # = quantos vão pro Bitrix (cadastrar_bitrix)
    total_descartado_nao_icp: int  # barrados no gate (fabricante, fantasma, etc.)
    total_para_enriquecer: int     # subconjunto do ICP que gasta crédito
    limiar_enriquecer: int


def _contar_recebido(payload: Any) -> int:
    """Conta places de graça, lidando com [{data:[...]}], {data:[...]} e array cru."""
    brutos = payload if isinstance(payload, list) else [payload]
    total = 0
    for b in brutos:
        if isinstance(b, dict):
            inner = b.get("data") or b.get("results")
            total += len(inner) if isinstance(inner, list) else 1
        else:
            total += 1
    return total


def _run(payload: Any, cidade: str, categoria: str, limiar: int | None) -> dict:
    lim = limiar if limiar is not None else LIMIAR_ENRIQUECER

    leads = normalizar_lote(payload, cidade_base=cidade, categoria=categoria)
    scored = avaliar_lote(leads, PesosICP(), limiar_enriquecer=lim)

    return {
        "leads": scored,
        "total_recebido": _contar_recebido(payload),
        "total_apos_normalizacao": len(leads),
        "total_icp": sum(1 for r in scored if r["cadastrar_bitrix"]),
        "total_descartado_nao_icp": sum(1 for r in scored if not r["cadastrar_bitrix"]),
        "total_para_enriquecer": sum(1 for r in scored if r["icp_enriquecer"]),
        "limiar_enriquecer": lim,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "rede360-lead-processor", "version": "2.6.0"}


@app.post("/process", response_model=LeadOut)
def process(req: ProcessRequest, x_api_key: str | None = Header(default=None)):
    _check_auth(x_api_key)
    return _run(req.payload, req.cidade, req.categoria, req.limiar_enriquecer)


@app.post("/process/items")
def process_items(req: ProcessRequest, x_api_key: str | None = Header(default=None)):
    """Devolve só o array de leads — o n8n itera direto, sem Split Out."""
    _check_auth(x_api_key)
    return _run(req.payload, req.cidade, req.categoria, req.limiar_enriquecer)["leads"]


@app.post("/process/raw", response_model=LeadOut)
def process_raw(payload: Any, x_api_key: str | None = Header(default=None)):
    """Aceita o array cru do Outscraper direto no body."""
    _check_auth(x_api_key)
    return _run(payload, "", "Todas (recomendado)", None)


# --------------------------------------------------------------------------- #
# Enriquecimento com contexto compartilhado (CNPJ + Site + Instagram cruzados)
# --------------------------------------------------------------------------- #

class EnrichRequest(BaseModel):
    lead: dict = Field(..., description="Um lead (saída do /process) a enriquecer")


class EnrichBatchRequest(BaseModel):
    leads: list[dict] = Field(..., description="Lista de leads a enriquecer")


@app.post("/enrich")
def enrich(req: EnrichRequest, x_api_key: str | None = Header(default=None)):
    """Recebe 1 lead, devolve o dossiê consolidado (pronto p/ o Bitrix)."""
    _check_auth(x_api_key)
    return enrich_lead(req.lead)


@app.post("/enrich/batch")
def enrich_batch(req: EnrichBatchRequest, x_api_key: str | None = Header(default=None)):
    """Enriquece vários leads de uma vez."""
    _check_auth(x_api_key)
    return {"leads": [enrich_lead(l) for l in req.leads]}

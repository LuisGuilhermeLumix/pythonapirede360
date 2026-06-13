"""
Pacote de enriquecimento com CONTEXTO COMPARTILHADO.

Resolve o problema do fluxo antigo (cada agente trabalhava cego): aqui um único
"dossiê" do lead (LeadContext) acumula evidências e passa por CNPJ -> Site ->
Instagram. Cada etapa LÊ tudo que as anteriores descobriram e CONFERE a
consistência entre as fontes.

Entrada: o lead normalizado (saída de app.normalize / API /process).
Saída:   dict consolidado e pronto p/ o Bitrix, com confiança e rastreio.

Ponto de entrada: app.enrich.orchestrator.enrich_lead(lead, tools=None)
"""
from app.enrich.orchestrator import enrich_lead  # noqa: F401

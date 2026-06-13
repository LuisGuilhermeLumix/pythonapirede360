# Rede 360 — Lead Processor (FastAPI)

Microserviço que recebe o payload bruto do **Outscraper Google Maps**, faz a
limpeza pesada e o **scoring de ICP** em camadas, e devolve os leads prontos
para o n8n cadastrar no **Bitrix**.

### Duas decisões SEPARADAS (importante)

| Campo | Pergunta | Comportamento |
|---|---|---|
| **`cadastrar_bitrix`** | "É ICP?" | **Inclusivo.** Todo lead que não é claramente fora-do-ICP **vai pro Bitrix**. A empresa não perde lojista. |
| **`icp_enriquecer`** | "Vale gastar crédito?" | **Otimização de custo.** Decide quem passa por Apify/ScrapingBee/LLM **primeiro** — mas **não bloqueia o cadastro**. |

Quem não enriquece **ainda é cadastrado** no Bitrix, só com o dado grátis do
Google Maps. O gate de NÃO-ICP só barra: grande rede/franquia, categoria
bloqueada, fabricante/atacado e negócio fantasma (sem contato, sem presença e
fora do ICP conhecido).

---

## O que ele trata (problemas reais do Outscraper)

1. **Sites de plataforma** (`lojalocal.com`, `gofind.online`) que NÃO são da
   loja — zerados, não vazam pro enriquecimento.
2. **Telefone compartilhado** entre lojas distintas — não funde leads.
3. **`phone_1`** com DDD de outro estado (lixo da plataforma) — ignorado.
4. **Falsos positivos de categoria** (assistência técnica, fabricante de
   blocos) — descartados no gate.
5. **E-mail placeholder** (`info@lojalocal.com`) — filtrado.

Além disso, extrai sinais que o Outscraper já dá de graça e que o fluxo atual
ignorava: `working_hours` (negócio ativo), `reviews_per_score` (perfil
problemático), `about` (operação de varejo), `photos_count`, `verified`.

---

## Estrutura

```
app/
  normalize.py     # limpeza + extração de sinais + aliases do contrato n8n
  scoring.py       # gate de NÃO-ICP + score 0-100 + decisão de enriquecimento
  main.py          # API FastAPI
  tests/           # 18 testes contra o sample real
Dockerfile
requirements.txt
```

---

## Deploy no EasyPanel

1. Suba este projeto num repositório Git (ou use o build por upload).
2. No EasyPanel: **Create Service → App**.
3. **Source:** aponte para o repositório / Dockerfile.
4. **Build:** Dockerfile (já incluído).
5. **Environment variables:**
   - `API_KEY` = um token forte (ex.: gere com `openssl rand -hex 32`).
   - `PORT` = `8000` (o EasyPanel normalmente injeta sozinho).
6. **Port:** `8000`.
7. Deploy. Teste: `https://<seu-dominio>/health`.

> Sem `API_KEY` definida o serviço fica **aberto** (modo dev). Em produção,
> sempre defina a `API_KEY`.

---

## Integração no n8n

Substitui o Code node **"Filtrar e Normalizar"** por um **HTTP Request**. O
output do Python já entrega os mesmos campos que o nó antigo entregava
(`title`, `phone`, `phone_clean`, `placeId`, `website`, `website_domain`,
`instagram`, `facebook`, `rating`, `reviewsCount`, `categoryName`,
`cidade_normalizada`, `nome_normalizado`, `dedupe_keys`,
`score_icp_rapido`, `pre_score_enriquecimento`, `enriquecimento_recomendado`),
**mais** as decisões novas. Os nós seguintes (Edit Fields → Bitrix) continuam
funcionando sem mexer.

### 1. Nó HTTP Request (no lugar do "Filtrar e Normalizar")

- **Method:** POST
- **URL:** `https://<seu-dominio>/process/items`  ← devolve o **array** direto
- **Headers:** `X-API-Key: <seu-token>`  (use uma credential, não hardcode)
- **Body (JSON):**
  ```
  {
    "payload": {{ JSON.stringify($json) }},
    "cidade": "{{ $('Montar Queries').first().json.cidade }}",
    "categoria": "{{ $('Montar Queries').first().json.categoria }}",
    "limiar_enriquecer": 45
  }
  ```

> Use **`/process/items`** para o HTTP Request já devolver os leads como itens
> (cada elemento do array vira um item do n8n → liga direto no `Loop Over Items1`).
> Se preferir `/process` (resposta com estatísticas), adicione um nó **Split Out**
> no campo `leads` antes do loop.

### 2. Fluxo: enriquecer o topo, cadastrar TODOS os ICP

A lista já vem **ordenada**: ICP primeiro, e dentro do ICP os `icp_enriquecer`
no topo. Monte o fluxo assim:

```
HTTP /process/items
        │
   Loop Over Items1
        │
   IF  cadastrar_bitrix == true ?  ──(false)──►  descarta / loga "não-ICP"
        │ (true)
   IF  icp_enriquecer == true ?
        │ (true)                         (false)
   enriquecimento (Apify/LLM)  ┐          │
        └──────────────────────┴──────────┘
                       │
              Criar/Atualizar Lead Bitrix   ◄── TODOS os ICP passam por aqui
```

- **`cadastrar_bitrix`** decide quem entra no Bitrix (inclusivo).
- **`icp_enriquecer`** só decide quem desvia para o enriquecimento caro antes.
- No gate de enriquecimento, use `icp_enriquecer` (alias: `enriquecimento_recomendado`).

Campos extras por lead: `is_icp`, `icp_score`, `icp_classificacao`
(`quente`/`morno`/`frio`/`nao_icp`), `icp_prioridade`, `icp_motivos_descarte`,
`icp_motivos_score`, `sinais_maps`.

---

## Ajuste de custo

`limiar_enriquecer` controla quantos leads recebem enriquecimento caro —
**não** quantos vão pro Bitrix (todos os ICP vão):
- **Cidade pequena:** 45 (default) — enriquece quase todos os ICP.
- **Capital / alto volume:** 60–70 — enriquece só os mais fortes; o resto
  ainda é cadastrado no Bitrix com o dado grátis do Maps.

Pode mandar por request (campo `limiar_enriquecer`) sem redeploy.

---

## Enriquecimento com contexto compartilhado (`/enrich`)

Substitui as ~40 etapas de enriquecimento do n8n (CNPJ + Site + Instagram +
agentes de IA soltos) por **um pipeline coerente** onde as fontes se cruzam.

**O problema que resolve:** no n8n cada agente trabalhava cego — a IA do CNPJ
não sabia o que a do site achou, e o Merge juntava tudo no escuro. Aqui existe
um **dossiê único** (`LeadContext`) que passa por `CNPJ → Site → Instagram`,
e cada etapa lê tudo que as anteriores descobriram:

```
app/enrich/
  models.py        # LeadContext — o dossiê compartilhado
  scoring.py       # cruzamento determinístico (nome/cidade/telefone/domínio)
  tools.py         # Tavily / BrasilAPI / Apify — nunca levantam exceção
  cnpj.py          # acha CNPJ (regex+validação) → Receita → grava razão social
  site.py          # busca o site USANDO a razão social → extrai contatos
  instagram.py     # acha o @ → perfil (seguidores, WhatsApp comercial)
  decision.py      # cruza fontes, decide ICP (CNAE/categoria) + confiança
  orchestrator.py  # enrich_lead(lead) — isola falhas, nada derruba o lead
```

**Princípios:** determinístico onde dá (regex, BrasilAPI, validação de dígito —
grátis e confiável); robusto (toda chamada externa com timeout/try-except);
graciosa (lead do segmento com poucos dados **ainda é ICP** e vai pro Bitrix).

**Endpoint:** `POST /enrich` recebe 1 lead (saída do `/process`) e devolve o
dossiê consolidado pronto pro Bitrix (`razao_social`, `cnpj`, `telefone`,
`whatsapp`, `instagram`, `produtos`, `e_icp`, `confianca`, ...). No n8n: dentro
do `Loop Over Items1`, um HTTP Request pro `/enrich` substitui o bloco de
enriquecimento. `POST /enrich/batch` processa vários.

**Env vars (EasyPanel) p/ o enriquecimento ao vivo:**
- `TAVILY_API_KEY` — busca web (sem ela, busca é pulada; resto funciona).
- `APIFY_TOKEN` — perfil do Instagram (opcional).
- BrasilAPI (Receita) não precisa de chave.

> Migração incremental recomendada: ativar `/enrich` rodando lado a lado com o
> n8n e comparar acerto, uma fonte por vez. Começar pelo CNPJ.

---

## Rodar local

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
python -m pytest app/tests -q
```

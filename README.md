# 🛠️ BDU Backend — FastAPI Core

O **BDU Backend** é o motor de processamento e orquestração do **Banco de Dados Único (BDU)** da Meta Consultoria. Ele é responsável por conectar a aplicação front-end à base de dados relacional (MySQL), além de gerenciar a ingestão e sincronização de dados externos (como planilhas de Controle Contábil e cartões do Pipefy) através da integração com webhooks do **n8n** e APIs do SharePoint.

---

## 🚀 Tecnologias Utilizadas

- **Linguagem:** Python 3.12
- **Framework Web:** [FastAPI](https://fastapi.tiangolo.com/) (rápido, tipado e com documentação automática)
- **Banco de Dados:** MySQL (utilizando `mysql-connector-python` com pool de conexões)
- **Integração:** Webhooks do n8n para sincronização com Office 365 / SharePoint
- **Testes:** Pytest (94 testes unitários ativos de consistência e regras de negócio)

---

## 📁 Estrutura de Pastas Simplificada

```text
backend/
├── ingestion/               # Módulos de carga e transformação de dados
│   ├── contabil/            # Importador e parser de planilhas Excel Contábil
│   ├── pipefy/              # Integração de contratos e finanças via Pipefy
│   └── pipefy_comercial/    # Integração de Leads e Funil Comercial
├── routers/                 # Rotas da API divididas por escopo
│   └── bdu.py               # Endpoints de leitura de dados para o painel BDU
├── tests/                   # Suíte de testes automatizados (pytest)
├── database.py              # Pool de conexões MySQL e gerenciador de transações
├── main.py                  # Ponto de entrada da API e rotas de edição/PAPE
├── models.py                # Modelos Pydantic para validação de dados
└── requirements.txt         # Dependências do Python
```

---

## ⚡ Fluxo Geral de Arquitetura

O backend opera como um gateway e integrador de dados:

```text
  [ Next.js Frontend ] ──( HTTP POST /api/pape )──► [ FastAPI Backend ]
                                                           │
                                        ┌──────────────────┴──────────────────┐
                                        ▼                                     ▼
                                [ MySQL Database ]                    [ n8n Webhook ]
                          (Salva resposta localmente)            (Dispara fluxo de sync)
                                                                              │
                                                                              ▼
                                                                     [ SharePoint Excel ]
                                                                 (Atualiza planilha oficial)
```

---

## ⚙️ Configuração Local

### 1. Pré-requisitos
Certifique-se de possuir o Python 3.12+ instalado em sua máquina.

### 2. Instalar dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente
Copie o arquivo de exemplo e configure suas variáveis locais:
```bash
cp .env.example .env
```
Abra o arquivo `.env` e configure a conexão com o seu banco de dados MySQL local e a chave de segurança:
```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=sua_senha
DB_NAME=banco_de_dados
DB_PORT=3306
DB_POOL_SIZE=5

ADMIN_API_TOKEN=seu_token_super_secreto
N8N_WEBHOOK_URL=http://localhost:5678/webhook/pape
```

### 4. Executar o Servidor de Desenvolvimento
```bash
python main.py
```
A API iniciará por padrão em `http://localhost:8000`.

Acesse a documentação interativa oficial (Swagger UI) para testar e visualizar os endpoints em:
👉 **[http://localhost:8000/docs](http://localhost:8000/docs)**

---

## 🧪 Executando Testes Unitários

A suíte de testes valida as regras de negócio, parser contábil e transformações do Pipefy sem tocar no banco de dados de produção (usando mocks do cursor de banco).

Para rodar os testes locally, configure a variável `ADMIN_API_TOKEN` no terminal e execute o pytest:
```bash
# Windows (PowerShell)
$env:ADMIN_API_TOKEN="test_token"; pytest

# Linux / macOS
ADMIN_API_TOKEN="test_token" pytest
```

---

## 🐳 Produção & VPS

Para implantar em servidores de produção (VPS), o backend conta com suporte a contêineres Docker e orquestração por Gunicorn:

- **Docker:** Utilize o `Dockerfile` incluso para construir a imagem da aplicação.
- **Gunicorn:** Execute com múltiplos workers para gerenciar alta concorrência:
  ```bash
  gunicorn -w 4 -b 0.0.0.0:8000 main:app
  ```

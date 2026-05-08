# PAPE Backend — FastAPI

API do formulário PAPE (Plano de Acompanhamento de Projetos Externos) integrada ao MySQL e n8n.

## Setup

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar environment variables

Copie `.env.example` para `.env` e preencha com seus dados:

```bash
cp .env.example .env
```

Edite `.env` com as credenciais do MySQL:

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=sua_senha
DB_NAME=banco_de_dados
DB_PORT=3306

N8N_WEBHOOK_URL=http://localhost:5678/webhook/pape
```

### 3. Executar a API

```bash
python main.py
```

A API estará disponível em `http://localhost:8000`

Documentação automática (Swagger):
- `http://localhost:8000/docs`

## Endpoints

### GET `/api/projetos`
Retorna lista de projetos ativos.

**Response:**
```json
[
  {
    "id": 1,
    "nome": "Miller P(AI)",
    "numero_contrato": "111.0001",
    "valor_total": 50000.00
  }
]
```

### GET `/api/projetos/{projeto_id}`
Retorna detalhes do projeto + serviços + coordenações.

### GET `/api/coordenacoes`
Retorna lista de coordenações.

### GET `/api/membros`
Retorna lista de membros.

### POST `/api/pape`
Submete resposta do formulário PAPE.

**Body:**
```json
{
  "respondente_nome": "João Silva",
  "projeto_externo_id": 1,
  "primeira_resposta": "Sim",
  "modelo_gerenciamento": "Ágil",
  "pct_conclusao": "41-60%",
  "status_cronograma": "Dentro do prazo",
  "capacitacao_equipe": 4,
  "eficacia_metodologia": 4,
  "nivel_retrabalho": 2,
  "comunicacao_cliente": 4,
  "abertura_cliente": 4,
  "satisfacao_cliente": 4,
  ...mais campos
}
```

**Response:**
```json
{
  "success": true,
  "message": "Formulário enviado com sucesso",
  "acompanhamento_id": 123
}
```

## Fluxo de dados

```
Next.js (front-end)
    ↓ POST /api/pape
FastAPI (backend)
    ├─ Insere em MySQL (acompanhamento_projeto + tabelas filhas)
    └─ Dispara webhook do n8n com os 29 campos do formulário
        ↓
    n8n
        └─ Atualiza Excel no SharePoint (via Microsoft Graph API)
```

## Desenvolvimento

Para desenvolvimento com auto-reload:

```bash
pip install uvicorn[standard]
uvicorn main:app --reload
```

## Production

Na VPS, use o Gunicorn:

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:8000 main:app
```

Ou use systemd para auto-start:

```ini
[Unit]
Description=PAPE FastAPI
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/home/usuario/pape-backend
Environment="PATH=/home/usuario/.venv/bin"
ExecStart=/home/usuario/.venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 main:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

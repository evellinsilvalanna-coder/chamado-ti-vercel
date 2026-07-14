# Chamado TI 🎫

Sistema completo de Service Desk / Help Desk para gerenciamento de chamados de suporte técnico, com autoatendimento, SLA, base de conhecimento e indicadores.

## Stack

- **Backend:** Python 3 + Flask
- **Banco:** SQLite (relacional, pronto para PostgreSQL)
- **Frontend:** Bootstrap 5 + Chart.js + CSS custom
- **Autenticação:** Flask-Login + bcrypt
- **Tempo Real:** Notificações via polling (AJAX)

## Requisitos

```bash
pip install -r requirements.txt
```

**Principais dependências:** Flask, Flask-SQLAlchemy, Flask-Login, bcrypt, pytz, Pillow, reportlab, openpyxl

## Como Executar

```bash
cd chamado-ti
python app.py
```

Acesse: **http://localhost:5000**

## Primeiro Acesso

O sistema cria automaticamente:
- **Departamentos:** Administrativo, Financeiro, RH, Comercial, Marketing, TI, Produção, Logística
- **Categorias:** Computador, Notebook, Impressora, Internet, Rede, Sistema, Office, E-mail, Telefonia, Hardware, Software, Acesso e mais
- **Soluções Rápidas:** 20+ scripts de autoatendimento (Rede, Impressoras, Windows, Office, Navegadores, Utilidades)

**Crie sua conta** → Faça login como Solicitante.
Para perfil Técnico ou Admin, outro admin precisa cadastrar ou alterar seu perfil.

---

## Perfis

### 👤 Solicitante
- Abrir e acompanhar chamados
- Anexar arquivos
- Chat com o técnico
- Avaliar atendimento
- Reabrir chamados
- **Autoatendimento:** Executar soluções rápidas antes de abrir chamado

### 🔧 Técnico
- Dashboard completo com gráficos
- Fila de chamados
- Assumir, transferir, alterar prioridade/categoria
- Registrar tempo de atendimento
- Mensagens internas e públicas
- Indicadores individuais

### 🛡️ Administrador
- CRUD completo de usuários, departamentos, categorias
- Configuração de SLA (prazos, alertas, escalonamento)
- Gerenciamento de Soluções Rápidas (upload de .bat/.ps1/.cmd)
- Base de Conhecimento (tutoriais, FAQs, documentos)
- Relatórios e indicadores
- Logs do sistema
- Visualização global de chamados

---

## Funcionalidades

### Chamados
- Protocolo automático (TI-2026-000001)
- 9 status com cores distintas
- Prioridades: Baixa, Média, Alta, Crítica
- Categorias customizáveis
- SLA com alertas visuais
- Chat em tempo real com mensagens internas
- Upload de múltiplos arquivos
- Histórico completo de alterações

### Autoatendimento (Soluções Rápidas)
- **Rede:** Renovar IP, Limpar DNS, Resetar Winsock, TCP/IP, Diagnóstico
- **Impressoras:** Reiniciar Spooler, Limpar fila, Testar impressão
- **Windows:** Limpar temporários, SFC, DISM, GPUpdate, Serviços
- **Office:** Reparar, Corrigir Outlook, Limpar credenciais
- **Navegadores:** Limpar cache, cookies, restaurar
- **Utilidades:** Reiniciar Explorer, CMD, PowerShell, Painel de Controle

### Base de Conhecimento
- Artigos com conteúdo HTML
- Categorias e tags
- Upload de PDFs e documentos
- Pesquisa inteligente
- Contador de visualizações

### Relatórios e Indicadores
- Quantidade de chamados por período
- SLA cumprido vs vencido
- Tempo médio de atendimento
- Chamados por categoria, departamento, técnico, mês
- Produtividade da equipe
- Índice de satisfação (avaliação 1-5 estrelas)
- Exportação futura: PDF, Excel, CSV

### Segurança
- Senhas com hash bcrypt
- Controle de sessão
- Permissões por perfil (decorator @has_role)
- Logs completos de auditoria
- Proteção CSRF via Flask-WTF (preparado)
- Agente de TI para execução local de scripts (arquitetura preparada)

### Interface
- Design responsivo (mobile, tablet, desktop)
- Modo claro/escuro
- Sidebar recolhível
- Animações suaves
- Cores: Azul (#2563eb), Branco, Cinza, Verde (sucesso), Vermelho (erro), Amarelo (aviso)

---

## APIs

O sistema já possui endpoints JSON para integração:

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/api/chamados/<id>/messages` | Lista mensagens do chamado |
| POST | `/api/chamados/<id>/message` | Enviar mensagem |
| POST | `/api/chamados/<id>/status` | Atualizar status |
| POST | `/api/chamados/<id>/assumir` | Assumir chamado |
| POST | `/api/chamados/<id>/transferir` | Transferir chamado |
| POST | `/api/chamados/<id>/prioridade` | Alterar prioridade |
| POST | `/api/chamados/<id>/categoria` | Alterar categoria |
| POST | `/api/chamados/<id>/tempo` | Registrar tempo |
| POST | `/api/chamados/<id>/reabrir` | Reabrir chamado |
| POST | `/api/chamados/<id>/avaliar` | Avaliar atendimento |
| POST | `/api/chamados/<id>/anexo` | Upload de arquivo |
| POST | `/api/solucoes/<id>/executar` | Executar solução |
| GET | `/api/notificacoes` | Listar notificações |
| POST | `/api/notificacoes/<id>/read` | Marcar como lida |
| POST | `/api/notificacoes/read-all` | Marcar todas lidas |

---

## Próximas Integrações (Arquitetura Preparada)

- ✅ Microsoft Teams (webhooks)
- ✅ Slack (webhooks)
- ✅ WhatsApp (API)
- ✅ E-mail (SMTP)
- ✅ Active Directory / LDAP
- ✅ **Agente de TI** — aplicativo Windows para execução local segura de scripts (.bat, .ps1, .cmd)

---

## Estrutura do Projeto

```
chamado-ti/
├── app.py              # Rotas e lógica principal
├── config.py           # Configurações
├── models.py           # Modelos do banco
├── requirements.txt    # Dependências
├── static/
│   ├── css/style.css   # Estilos customizados
│   ├── js/main.js      # JavaScript principal
│   └── img/            # Imagens
├── templates/          # Templates Jinja2
│   ├── base.html       # Layout base
│   ├── login.html      # Tela de login
│   ├── dashboard_*.html
│   ├── chamados/       # Gestão de chamados
│   ├── admin_*.html    # Painel admin
│   └── ...
├── uploads/            # Arquivos enviados
└── solutions/          # Scripts de soluções
```

---

**Chamado TI** © 2026 — Criado com ❤️ para simplificar o suporte de TI.
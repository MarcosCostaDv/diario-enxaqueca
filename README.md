# Diário de enxaqueca com aura (MVP N=1)

App Streamlit para coletar o diário pelo celular, só com toques. Gera relatórios descritivos e exporta CSV.

## Estrutura

| Arquivo | Papel |
| --- | --- |
| `db.py` | Esquema e acesso ao banco (única camada que fala SQL) |
| `app.py` | Telas: Aura (1 toque), Manhã, Noite, Crise, Relatórios |
| `reports.py` | Relatórios descritivos e exportação |

## Rodar no computador

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # edite a senha
streamlit run app.py
```

Os dados ficam em `diario.db` (SQLite), na mesma pasta.

## Usar pelo celular (em qualquer lugar)

O SQLite local só funciona com o computador ligado e na mesma rede. Para usar na rua:

1. Crie um PostgreSQL gerenciado (Neon e Supabase têm plano gratuito) e copie a URL de conexão.
2. Suba este código para um repositório **privado** no GitHub (o `.gitignore` já exclui banco e segredos).
3. Publique no Streamlit Community Cloud e cole o conteúdo do `secrets.toml` em *Settings → Secrets*,
   incluindo `DATABASE_URL`. O disco desses servidores é temporário: sem `DATABASE_URL`, os dados se perdem.
4. Deixe o app privado nas configurações de compartilhamento, além da senha.
5. No celular, "Adicionar à tela inicial" para abrir como um app.

## Decisões de armazenamento (para escalar)

- **Troca de banco sem mudar código:** tudo via `DATABASE_URL` (SQLAlchemy).
- **Multiusuário desde já:** toda tabela tem `id_usuario` (UUID pseudônimo); identidade fica fora destas tabelas.
- **Tempo:** instantes em UTC (`*_utc`) + `fuso` por registro; hora local é derivada na análise.
- **IDs de crise em UUID:** permitem sincronizar vários dispositivos.
- **Camada de repositório (`db.py`):** uma futura API (FastAPI) reutiliza as mesmas funções.
- **Pendências antes de ter outros usuários:** migrations (Alembic), autenticação real por usuário,
  criptografia e backups, termo de consentimento (LGPD, dado sensível de saúde).
- **Wearables:** dados de alta frequência irão para tabela própria em formato longo
  (`id_usuario, ts_utc, fonte, metrica, valor`), não para `diario`.

## Diferenças em relação ao dicionário de dados do documento

- `retroativo` foi dividido em `retroativo_manha` e `retroativo_noite`.
- `aura_duracao_min = 61` significa "mais de 60 min".
- Escalas numéricas não têm valor padrão: campo não marcado não é salvo como 0.

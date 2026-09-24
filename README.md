# Diário de enxaqueca (MVP, crises com ou sem aura)

App Streamlit para coletar o diário pelo celular, só com toques. Gera relatórios descritivos e exporta CSV.

## Estrutura

| Arquivo | Papel |
| --- | --- |
| `db.py` | Esquema e acesso ao banco (única camada que fala SQL) |
| `app.py` | Telas: Início (aura em 1 toque + o que falta preencher), Manhã, Noite, Crise, Relatórios |
| `.streamlit/config.toml` | Tema e menu simplificado |
| `reports.py` | Relatórios descritivos e exportação |

## Rodar no computador

Windows (PowerShell), dentro da pasta do projeto:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml   # edite a senha
python -m streamlit run app.py
```

Não use `python app.py`: apps Streamlit são iniciados com `streamlit run`.

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
- **Campos novos no diário:** `sono_motivos` (só quando a qualidade do sono é 1 ou 2; noites boas ficam
  NULL = "não perguntado"), `tela_horas` (faixa) e `tela_finalidade`. Tabelas antigas recebem essas
  colunas automaticamente; dias anteriores ficam NULL.
- **Crise explícita:** a noite pergunta "Teve crise hoje?" (`diario.teve_crise`). Dia sem crise =
  `teve_crise = false`; dia sem registro = faltante, nunca "sem crise". Crise esquecida pode ser
  registrada pela noite e fica com `crises.registro_retroativo = true`.
- **Esquema v2:** o rótulo da crise é `inicio_utc` = primeiro sintoma (`inicio_tipo` = aura ou dor),
  com `teve_aura` separado. Bancos da v1 são migrados automaticamente na primeira execução
  (registros antigos viram "começou com aura"; no SQLite a tabela antiga fica guardada como `crises_v1`).
- Escalas numéricas não têm valor padrão: campo não marcado não é salvo como 0.

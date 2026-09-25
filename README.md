# Diário de Enxaqueca (MVP)

Diário digital para investigar se existem sinais mensuráveis que antecedem crises de enxaqueca, com ou sem aura. O registro é feito pelo celular, só com toques. O app gera relatórios descritivos e exporta CSV.

> **Não é diagnóstico** e não substitui acompanhamento médico. É uma ferramenta de coleta de dados para investigação individual (N=1).

## Estado atual

| Etapa | Situação |
| --- | --- |
| Coleta (diário, crises, dias sem crise) | em uso |
| Relatórios descritivos e referências clínicas | em uso |
| Área do pesquisador (visão geral, pacientes, literatura) | em uso |
| Integração com wearables e clima | planejada |
| Análise estatística e modelos preditivos | só depois de haver dados suficientes |

## Estrutura

| Arquivo | Papel |
| --- | --- |
| `app.py` | Login, papéis e menus. Paciente: Hoje · Relatórios · Sobre. Pesquisador: Visão geral · Pacientes · Literatura · Fontes |
| `db.py` | Esquema e acesso ao banco (única camada que fala SQL); migrações automáticas |
| `reports.py` | Relatórios descritivos, exportação e área do pesquisador |
| `referencias.py` | Valores da literatura, com fonte, tipo de estudo e limitação |
| `.streamlit/config.toml` | Tema e menu simplificado |
| `.streamlit/secrets.toml.example` | Modelo de configuração (a configuração real nunca vai para o Git) |

## Papéis de acesso

- **Paciente:** registra o próprio diário e vê só os próprios dados.
- **Pesquisador:** não tem diário; acompanha os participantes por códigos pseudônimos.

Nome, e-mail ou qualquer dado de identificação nunca entram no banco.

## Rodar no computador

Windows (PowerShell), dentro da pasta do projeto:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
python -m streamlit run app.py
```

Não use `python app.py`: apps Streamlit são iniciados com `streamlit run`.

Sem `DATABASE_URL` configurado, os dados ficam em `diario.db` (SQLite), na mesma pasta.

> **Atenção:** se a configuração local apontar para o banco de produção, o app no seu computador grava **nos dados reais**. Para testar, use o SQLite local.

## Publicar (uso pelo celular)

1. Crie um PostgreSQL gerenciado (Neon ou Supabase têm plano gratuito). No Neon, use a conexão **direta** (sem pooling), com o prefixo `postgresql+psycopg://`.
2. Suba o código para um repositório **privado** no GitHub. O `.gitignore` já exclui banco, `.env`, `.venv` e configurações sensíveis.
3. Publique no Streamlit Community Cloud e informe a configuração em **Settings → Secrets**, incluindo `DATABASE_URL`. O disco desses servidores é temporário: sem `DATABASE_URL`, os dados se perdem.
4. Deixe o app privado em **Settings → Sharing**.
5. No celular, use "Adicionar à tela inicial".

Para atualizar: `git add`, `git commit`, `git pull --rebase` e `git push`. O Streamlit Cloud reinstala e reinicia sozinho.

## Modelo de dados

Três tabelas, todas com o código pseudônimo do participante (`id_usuario`):

| Tabela | Uma linha por | Conteúdo |
| --- | --- | --- |
| `usuarios` | pessoa | código pseudônimo e fuso |
| `diario` | pessoa e dia | manhã (sono) e noite (sintomas, estado, hábitos, "teve crise hoje?") |
| `crises` | crise | início, tipo de início, aura, dor, remédio, fim |

Regras que importam para a análise:

- **Rótulo da crise:** `inicio_utc` = primeiro sintoma; `inicio_tipo` = `aura` ou `dor`; `teve_aura` fica separado.
- **Dia sem crise é explícito:** `diario.teve_crise = false`. Dia sem registro é **faltante**, nunca "sem crise".
- **Crise esquecida** pode ser registrada pela noite e fica com `crises.registro_retroativo = true` (horário aproximado).
- **Retroatividade:** `retroativo_manha` e `retroativo_noite` marcam registros feitos depois do dia de referência.
- **Escalas sem valor padrão:** campo não marcado fica NULL, nunca 0.
- **Campos condicionais:** `sono_motivos` só existe quando a qualidade do sono é 1 ou 2; noites boas ficam NULL ("não perguntado").
- **Códigos:** `aura_duracao_min = 61` significa "mais de 60 min".
- **Tempo:** instantes em UTC (`*_utc`) com o fuso de cada registro; a hora local é derivada na análise.

Consultas de exemplo (SQL Editor do Neon):

```sql
-- crises de um participante, em hora de Brasília
SELECT inicio_utc AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo' AS inicio_local,
       inicio_tipo, teve_aura, dor_max
FROM crises WHERE id_usuario = 'CODIGO_DO_PARTICIPANTE' ORDER BY inicio_utc DESC;

-- adesão por participante
SELECT id_usuario, COUNT(preenchido_manha_em_utc) AS manhas, COUNT(preenchido_noite_em_utc) AS noites
FROM diario GROUP BY id_usuario;
```

## Privacidade e exclusão de dados

Os dados são de saúde (sensíveis pela LGPD). Cada participante deve assinar um termo de consentimento antes de começar.

Para excluir **todos** os dados de um participante, a pedido dele (nesta ordem):

```sql
DELETE FROM crises   WHERE id_usuario = 'CODIGO_DO_PARTICIPANTE';
DELETE FROM diario   WHERE id_usuario = 'CODIGO_DO_PARTICIPANTE';
DELETE FROM usuarios WHERE id_usuario = 'CODIGO_DO_PARTICIPANTE';
```

Antes de qualquer exclusão em massa, crie um backup instantâneo no Neon (**Branches → Create branch**).

## Referências da área do pesquisador

Só entram em `referencias.py` números conferidos no resumo do artigo original, cada um com tipo de estudo e limitação:
ICHD-3 (2018), Viana et al. (Cephalalgia), Laurell et al. (2016), Queiroz et al. (2009) e Stubberud et al. (2023).
A comparação é qualitativa: os estudos usam populações e métodos diferentes dos deste diário.

## Decisões de arquitetura (para escalar)

- **Troca de banco sem mudar código:** tudo via `DATABASE_URL` (SQLAlchemy).
- **Multiusuário desde o início:** identidade fica fora das tabelas; só o código pseudônimo entra no banco.
- **IDs de crise em UUID:** permitem sincronizar vários dispositivos.
- **Camada de repositório (`db.py`):** uma futura API (FastAPI) reutiliza as mesmas funções.
- **Migrações automáticas e idempotentes:** colunas novas são acrescentadas às tabelas existentes; o esquema v1 de crises é convertido para o v2 na primeira execução.
- **Wearables:** dados de alta frequência irão para uma tabela própria em formato longo (`id_usuario, ts_utc, fonte, metrica, valor`), não para `diario`.

## Pendências antes de ampliar para mais participantes

- Migrações versionadas (Alembic) no lugar das automáticas
- Autenticação mais robusta
- Rotina de backup e política de retenção
- Termo de consentimento formal; Comitê de Ética em Pesquisa se houver publicação

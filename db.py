"""Camada de dados do diário de enxaqueca.

Decisões de arquitetura (pensadas para escalar de N=1 para vários usuários):

1. Banco definido por DATABASE_URL (SQLAlchemy). Trocar SQLite -> PostgreSQL
   é mudar uma variável de ambiente; o código não muda.
       local:  sqlite:///diario.db
       nuvem:  postgresql+psycopg://usuario:senha@host:5432/banco
2. Toda tabela tem `id_usuario` desde já (UUID pseudônimo). Nome, e-mail etc.
   NUNCA ficam nestas tabelas: identidade e dados de saúde separados (LGPD).
3. Instantes gravados em UTC (colunas *_utc) + o fuso IANA do usuário naquele
   registro (`fuso`). A hora local é derivada na análise. Evita ambiguidade
   com viagens, horário de verão e usuários em fusos diferentes.
4. Horários "de relógio" autorrelatados (hora que deitou/acordou) ficam como
   hh:mm locais, porque é assim que a pessoa os percebe.
5. IDs de crise são UUID: permitem sincronizar dados de vários dispositivos
   sem colisão de chaves.
6. O app só acessa o banco por este módulo (camada de repositório). Uma futura
   API (FastAPI) reutiliza as mesmas funções.

Próximo passo quando o esquema estabilizar: migrations com Alembic.
Dados de wearable (alta frequência) irão para uma tabela própria em formato
longo (id_usuario, ts_utc, fonte, métrica, valor), não para estas tabelas.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, MetaData, String,
    Table, Text, create_engine, insert, select, update,
)

SCHEMA_VERSION = 2   # v2: crise com início genérico (aura OU dor)
FUSO_PADRAO = "America/Sao_Paulo"

# Checklist de sintomas premonitórios: chave da coluna -> rótulo exibido
PREMONITORIOS = {
    "cansaco": "Cansaço / sonolência",
    "bocejos": "Bocejos frequentes",
    "pescoco": "Rigidez no pescoço",
    "concentracao": "Dificuldade de concentração",
    "humor": "Irritabilidade / humor",
    "luz": "Sensibilidade à luz",
    "som": "Sensibilidade a som",
    "desejo_comida": "Vontade de comer algo",
    "sede": "Sede / urinar mais",
    "nausea": "Náusea leve",
}

# Motivo do sono ruim (só perguntado quando a qualidade é 1 ou 2): chave -> rótulo.
# "dor_sintoma" separa sono ruim causado pela própria crise/pródromo de causas externas.
SONO_MOTIVOS = {
    "dor_sintoma": "dor ou sintoma",
    "estresse": "estresse/preocupação",
    "telas": "telas até tarde",
    "cafeina_alcool": "cafeína/álcool",
    "ambiente": "barulho/ambiente",
    "horario": "horário apertado",
    "outra_pessoa": "outra pessoa/criança",
    "nao_sei": "não sei",
}

# Tempo de tela no dia (faixas ordinais) e finalidade principal
TELA_FAIXAS = ["0-2", "2-4", "4-6", "6-8", "8+"]
TELA_FINALIDADES = ["trabalho/estudo", "lazer", "os dois"]

metadata = MetaData()

usuarios = Table(
    "usuarios", metadata,
    Column("id_usuario", String(36), primary_key=True),   # UUID pseudônimo
    Column("fuso", String(64), nullable=False, default=FUSO_PADRAO),
    Column("criado_em_utc", DateTime, nullable=False),
)

diario = Table(
    "diario", metadata,
    Column("id_usuario", String(36), ForeignKey("usuarios.id_usuario"), primary_key=True),
    Column("data_referencia", Date, primary_key=True),   # dia LOCAL do usuário
    Column("fuso", String(64)),
    # --- metadados de preenchimento ---
    Column("preenchido_manha_em_utc", DateTime),
    Column("retroativo_manha", Boolean),
    Column("preenchido_noite_em_utc", DateTime),
    Column("retroativo_noite", Boolean),
    # --- manhã: sono da noite anterior ---
    Column("sono_deitou", String(5)),      # hh:mm local (noite anterior)
    Column("sono_acordou", String(5)),     # hh:mm local
    Column("sono_despertares", Integer),   # 0,1,2,3 (3 = 3+)
    Column("sono_qualidade", Integer),     # 1-5
    Column("sono_motivos", String(200)),   # chaves de SONO_MOTIVOS separadas por vírgula; só se qualidade <= 2
    Column("acordou_com_sintoma", Boolean),
    # --- noite: o dia ---
    *[Column(f"prem_{k}", Boolean) for k in PREMONITORIOS],
    Column("previsao_subjetiva", Integer),  # 0-10
    Column("estresse", Integer),            # 0-10
    Column("humor", Integer),               # 1-5
    Column("cafeina_doses", Integer),
    Column("cafeina_ultima", String(5)),    # hh:mm local ou NULL
    Column("alcool_doses", Integer),
    Column("pulou_refeicao", Boolean),
    Column("exercicio_nivel", String(10)),  # nenhum / leve / intenso
    Column("exercicio_min", Integer),
    Column("outra_cefaleia", Integer),      # 0-10
    Column("analgesico_sem_crise", String(100)),
    Column("dia_atipico", Text),
    Column("tela_horas", String(5)),        # faixa: 0-2 / 2-4 / 4-6 / 6-8 / 8+
    Column("tela_finalidade", String(20)),  # trabalho/estudo / lazer / os dois
)

crises = Table(
    "crises", metadata,
    Column("id_crise", String(36), primary_key=True),     # UUID
    Column("id_usuario", String(36), ForeignKey("usuarios.id_usuario"), nullable=False, index=True),
    Column("fuso", String(64), nullable=False),
    Column("registrado_em_utc", DateTime, nullable=False),
    # RÓTULO (tempo zero) = primeiro sintoma da crise, seja aura ou dor.
    # Serve para quem tem crises com e sem aura; análises depois podem estratificar por teve_aura.
    Column("inicio_utc", DateTime, nullable=False, index=True),
    Column("inicio_tipo", String(10)),                 # "aura" ou "dor" (o que veio primeiro)
    Column("inicio_precisao", String(10)),             # exato / ±15 min / ±1 h
    Column("teve_aura", Boolean),                      # NULL até completar a crise
    Column("aura_inicio_utc", DateTime),               # só quando houve aura e o horário é conhecido
    Column("aura_tipo", String(100)),                  # lista separada por vírgula
    Column("aura_duracao_min", Integer),
    Column("sem_dor", Boolean),
    Column("dor_inicio_utc", DateTime),
    Column("dor_max", Integer),
    Column("dor_lado", String(15)),
    Column("nausea", String(10)),
    Column("medicacao", String(100)),
    Column("medicacao_hora", String(5)),               # hh:mm local
    Column("crise_fim_utc", DateTime),
    Column("sintomas_48h_retro", Text),
    Column("gatilho_suspeito", Text),
    Column("completado_em_utc", DateTime),
)

_engine = None


def engine():
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL", "sqlite:///diario.db")
        _engine = create_engine(url, pool_pre_ping=True)
        metadata.create_all(_engine)
        _migrar_v1_para_v2(_engine)
        _adicionar_colunas_novas(_engine)
    return _engine


def _adicionar_colunas_novas(eng) -> None:
    """Idempotente. Acrescenta às tabelas existentes as colunas novas (opcionais) do modelo.
    Linhas antigas ficam com NULL nesses campos: "não perguntado", diferente de "não"."""
    from sqlalchemy import inspect, text
    insp = inspect(eng)
    for tabela in metadata.sorted_tables:
        existentes = {c["name"] for c in insp.get_columns(tabela.name)}
        faltando = [c for c in tabela.columns if c.name not in existentes and c.nullable]
        if faltando:
            with eng.begin() as c:
                for col in faltando:
                    tipo = col.type.compile(dialect=eng.dialect)
                    c.execute(text(f"ALTER TABLE {tabela.name} ADD COLUMN {col.name} {tipo}"))


def _migrar_v1_para_v2(eng) -> None:
    """Idempotente. Tabelas criadas na v1 tinham só a aura como início da crise.
    Acrescenta as colunas genéricas e copia os registros antigos como 'começou com aura'.
    (Quando o esquema estabilizar, isto vira uma migration do Alembic.)"""
    from sqlalchemy import inspect, text
    colunas = {c["name"] for c in inspect(eng).get_columns("crises")}
    if "inicio_utc" in colunas:
        return
    if eng.dialect.name == "sqlite":
        _migrar_sqlite_recriando(eng)
        return
    tipo_ts = "TIMESTAMP"
    with eng.begin() as c:
        c.execute(text(f"ALTER TABLE crises ADD COLUMN inicio_utc {tipo_ts}"))
        c.execute(text("ALTER TABLE crises ADD COLUMN inicio_tipo VARCHAR(10)"))
        c.execute(text("ALTER TABLE crises ADD COLUMN inicio_precisao VARCHAR(10)"))
        c.execute(text("ALTER TABLE crises ADD COLUMN teve_aura BOOLEAN"))
        c.execute(text("UPDATE crises SET inicio_utc = aura_inicio_utc, inicio_tipo = 'aura', "
                       "inicio_precisao = aura_precisao, teve_aura = TRUE"))
        c.execute(text("ALTER TABLE crises ALTER COLUMN aura_inicio_utc DROP NOT NULL"))
        c.execute(text("ALTER TABLE crises ALTER COLUMN inicio_utc SET NOT NULL"))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_crises_inicio_utc ON crises (inicio_utc)"))


def _migrar_sqlite_recriando(eng) -> None:
    """SQLite não remove NOT NULL com ALTER: recria a tabela e copia os dados.
    A tabela antiga fica guardada como crises_v1 (nada é apagado)."""
    from sqlalchemy import text
    with eng.begin() as c:
        c.execute(text("ALTER TABLE crises RENAME TO crises_v1"))
        for idx in ("ix_crises_id_usuario", "ix_crises_aura_inicio_utc", "ix_crises_inicio_utc"):
            c.execute(text(f"DROP INDEX IF EXISTS {idx}"))
    crises.create(eng)
    comuns = ("id_crise, id_usuario, fuso, registrado_em_utc, aura_inicio_utc, aura_tipo, aura_duracao_min, "
              "sem_dor, dor_inicio_utc, dor_max, dor_lado, nausea, medicacao, medicacao_hora, crise_fim_utc, "
              "sintomas_48h_retro, gatilho_suspeito, completado_em_utc")
    with eng.begin() as c:
        c.execute(text(f"INSERT INTO crises ({comuns}, inicio_utc, inicio_tipo, inicio_precisao, teve_aura) "
                       f"SELECT {comuns}, aura_inicio_utc, 'aura', aura_precisao, 1 FROM crises_v1"))


# ---------------------------------------------------------------- tempo

def utc_agora() -> datetime:
    """Instante atual em UTC, sem tzinfo (formato de armazenamento)."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def local_agora(fuso: str) -> datetime:
    return datetime.now(ZoneInfo(fuso)).replace(tzinfo=None, microsecond=0)


def local_para_utc(dt_local: datetime, fuso: str) -> datetime:
    return dt_local.replace(tzinfo=ZoneInfo(fuso)).astimezone(timezone.utc).replace(tzinfo=None)


def utc_para_local(dt_utc: datetime, fuso: str) -> datetime:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(fuso)).replace(tzinfo=None)


# Retroatividade (avaliada no horário LOCAL do usuário):
#   manhã: prospectivo se preenchido no próprio dia de referência;
#   noite: prospectivo se preenchido até 06:00 do dia seguinte.

def retroativo_manha(data_ref: date, preenchido_local: datetime) -> bool:
    return preenchido_local.date() > data_ref


def retroativo_noite(data_ref: date, preenchido_local: datetime) -> bool:
    return preenchido_local > datetime.combine(data_ref + timedelta(days=1), time(6, 0))


def data_padrao_noite(momento_local: datetime) -> date:
    """Entre 00:00 e 06:00, o registro da noite refere-se ao dia anterior."""
    d = momento_local.date()
    return d - timedelta(days=1) if momento_local.hour < 6 else d


# ---------------------------------------------------------------- usuários

def garantir_usuario(id_usuario: str | None, fuso: str = FUSO_PADRAO) -> str:
    """Cria o usuário se não existir e devolve o id. Sem dados identificáveis."""
    id_usuario = id_usuario or str(uuid.uuid4())
    with engine().begin() as c:
        if not c.execute(select(usuarios.c.id_usuario).where(usuarios.c.id_usuario == id_usuario)).first():
            c.execute(insert(usuarios).values(id_usuario=id_usuario, fuso=fuso, criado_em_utc=utc_agora()))
    return id_usuario


def fuso_do_usuario(id_usuario: str) -> str:
    with engine().connect() as c:
        f = c.execute(select(usuarios.c.fuso).where(usuarios.c.id_usuario == id_usuario)).scalar()
    return f or FUSO_PADRAO


# ---------------------------------------------------------------- diário

def _filtro_dia(id_usuario: str, data_ref: date):
    return (diario.c.id_usuario == id_usuario) & (diario.c.data_referencia == data_ref)


def ler_dia(id_usuario: str, data_ref: date) -> dict | None:
    with engine().connect() as c:
        row = c.execute(select(diario).where(_filtro_dia(id_usuario, data_ref))).mappings().first()
    return dict(row) if row else None


def salvar_parte_do_dia(id_usuario: str, data_ref: date, valores: dict) -> None:
    """Upsert portátil (SQLite e Postgres): atualiza só as colunas enviadas."""
    with engine().begin() as c:
        if c.execute(select(diario.c.data_referencia).where(_filtro_dia(id_usuario, data_ref))).first():
            c.execute(update(diario).where(_filtro_dia(id_usuario, data_ref)).values(**valores))
        else:
            c.execute(insert(diario).values(id_usuario=id_usuario, data_referencia=data_ref, **valores))


def primeiro_dia(id_usuario: str) -> date | None:
    """Primeiro dia com registro no diário (None se ainda não há nenhum)."""
    from sqlalchemy import func
    with engine().connect() as c:
        return c.execute(select(func.min(diario.c.data_referencia))
                         .where(diario.c.id_usuario == id_usuario)).scalar()


# ---------------------------------------------------------------- crises

def registrar_crise(id_usuario: str, inicio_local: datetime, precisao: str, fuso: str, tipo: str) -> str:
    """Registra o primeiro sintoma de uma crise. tipo = "aura" ou "dor"."""
    assert tipo in ("aura", "dor")
    inicio = local_para_utc(inicio_local, fuso)
    id_crise = str(uuid.uuid4())
    with engine().begin() as c:
        c.execute(insert(crises).values(
            id_crise=id_crise, id_usuario=id_usuario, fuso=fuso,
            registrado_em_utc=utc_agora(),
            inicio_utc=inicio, inicio_tipo=tipo, inicio_precisao=precisao,
            teve_aura=True if tipo == "aura" else None,          # se começou com dor, pergunta depois
            aura_inicio_utc=inicio if tipo == "aura" else None,
            dor_inicio_utc=inicio if tipo == "dor" else None,
        ))
    return id_crise


def crise_recente(id_usuario: str, horas: int = 3) -> dict | None:
    """Crise registrada nas últimas `horas` (protege contra toque duplo)."""
    corte = utc_agora() - timedelta(hours=horas)
    with engine().connect() as c:
        row = c.execute(
            select(crises)
            .where((crises.c.id_usuario == id_usuario) & (crises.c.inicio_utc >= corte))
            .order_by(crises.c.inicio_utc.desc())
        ).mappings().first()
    return dict(row) if row else None


def crises_incompletas(id_usuario: str) -> list[dict]:
    with engine().connect() as c:
        rows = c.execute(
            select(crises)
            .where((crises.c.id_usuario == id_usuario) & crises.c.completado_em_utc.is_(None))
            .order_by(crises.c.inicio_utc.desc())
        ).mappings().all()
    return [dict(r) for r in rows]


def completar_crise(id_usuario: str, id_crise: str, valores: dict) -> None:
    with engine().begin() as c:
        c.execute(
            update(crises)
            .where((crises.c.id_crise == id_crise) & (crises.c.id_usuario == id_usuario))
            .values(completado_em_utc=utc_agora(), **valores)
        )


# ---------------------------------------------------------------- leitura para análise

def df_diario(id_usuario: str) -> pd.DataFrame:
    with engine().connect() as c:
        df = pd.read_sql(
            select(diario).where(diario.c.id_usuario == id_usuario).order_by(diario.c.data_referencia), c)
    df["data_referencia"] = pd.to_datetime(df["data_referencia"])
    return df


def df_crises(id_usuario: str) -> pd.DataFrame:
    """Crises com colunas UTC originais + equivalentes locais (*_local)."""
    with engine().connect() as c:
        df = pd.read_sql(
            select(crises).where(crises.c.id_usuario == id_usuario).order_by(crises.c.inicio_utc), c)
    for col in ("registrado_em_utc", "inicio_utc", "aura_inicio_utc", "dor_inicio_utc", "crise_fim_utc", "completado_em_utc"):
        df[col] = pd.to_datetime(df[col])
        loc = col.replace("_utc", "_local")
        df[loc] = [
            utc_para_local(v.to_pydatetime(), f) if pd.notna(v) else pd.NaT
            for v, f in zip(df[col], df["fuso"])
        ]
        df[loc] = pd.to_datetime(df[loc])
    return df

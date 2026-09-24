"""Diário de enxaqueca com aura — app de coleta (Streamlit, pensado para celular).

Rodar localmente:   streamlit run app.py
Configuração:       .streamlit/secrets.toml (veja secrets.toml.example)
"""
from __future__ import annotations

import hmac
import os
from datetime import date, datetime, time, timedelta

import streamlit as st

st.set_page_config(page_title="Diário de enxaqueca", page_icon="🧠", layout="centered")

# Configuração vem de st.secrets (nuvem) ou variáveis de ambiente (local).
def cfg(chave: str, padrao=None):
    try:
        if chave in st.secrets:
            return st.secrets[chave]
    except Exception:  # sem secrets.toml
        pass
    return os.environ.get(chave, padrao)


if cfg("DATABASE_URL"):
    os.environ["DATABASE_URL"] = cfg("DATABASE_URL")

import db  # noqa: E402  (depois de definir DATABASE_URL)
import reports  # noqa: E402

MEDICACOES = list(cfg("MEDICACOES", ["Analgésico comum", "Anti-inflamatório", "Triptano", "Outro"]))

# ---------------------------------------------------------------- acesso


def exigir_senha() -> None:
    senha = cfg("APP_PASSWORD")
    if not senha:
        st.warning("APP_PASSWORD não definida: app sem proteção. Só use assim no seu computador.")
        return
    if st.session_state.get("autenticado"):
        return
    tentativa = st.text_input("Senha", type="password")
    if tentativa and hmac.compare_digest(tentativa, str(senha)):
        st.session_state["autenticado"] = True
        st.rerun()
    elif tentativa:
        st.error("Senha incorreta.")
    st.stop()


exigir_senha()

USUARIO = db.garantir_usuario(cfg("USER_ID", "usuario-local"), cfg("FUSO", db.FUSO_PADRAO))
FUSO = db.fuso_do_usuario(USUARIO)

# ---------------------------------------------------------------- utilidades de formulário


def hhmm_para_time(v: str | None, padrao: time) -> time:
    if not v:
        return padrao
    h, m = map(int, v.split(":"))
    return time(h, m)


def time_para_hhmm(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def escolha(rotulo: str, opcoes: list, atual, key: str):
    """Botões de toque único (segmented control) com valor pré-selecionado."""
    return st.segmented_control(rotulo, opcoes, default=atual if atual in opcoes else None, key=key)


def escala(rotulo: str, minimo: int, maximo: int, atual, key: str, ajuda: str | None = None):
    """Escala numérica em botões, SEM valor padrão: evita gravar um 0 que você não marcou
    (um slider sempre tem valor, e isso mascara dado faltante)."""
    return st.segmented_control(rotulo, list(range(minimo, maximo + 1)), default=atual,
                                key=key, help=ajuda)


# ---------------------------------------------------------------- telas

agora_local = db.local_agora(FUSO)
st.markdown("#### Diário de enxaqueca")

abas = st.tabs(["⚡ Aura", "🌅 Manhã", "🌙 Noite", "📝 Crise", "📊 Relatórios"])

# ---------------------------------------------------------------- AURA (registro em 1 toque)
with abas[0]:
    st.subheader("Início da aura")
    st.caption("Registre na hora. Os detalhes podem ser completados depois, na aba Crise.")

    quando = st.segmented_control(
        "Começou", ["Agora", "~15 min atrás", "~30 min atrás", "~1 h atrás"], default="Agora", key="aura_quando")
    ajuste = {"Agora": (0, "exato"), "~15 min atrás": (15, "±15 min"),
              "~30 min atrás": (30, "±15 min"), "~1 h atrás": (60, "±1 h")}
    minutos, precisao = ajuste.get(quando or "Agora")

    recente = db.crise_recente(USUARIO)
    confirmar = True
    if recente:
        hora = db.utc_para_local(recente["aura_inicio_utc"], recente["fuso"]).strftime("%H:%M")
        st.warning(f"Já existe uma aura registrada às {hora}.")
        confirmar = st.checkbox("É uma nova aura, registrar mesmo assim", key="aura_confirma")

    if st.button("REGISTRAR AURA", type="primary", width="stretch", disabled=not confirmar):
        inicio = db.local_agora(FUSO) - timedelta(minutes=minutos)
        db.registrar_aura(USUARIO, inicio, precisao, FUSO)
        st.success(f"Aura registrada: {inicio:%d/%m %H:%M} ({precisao}).")

# ---------------------------------------------------------------- MANHÃ (sono)
with abas[1]:
    st.subheader("Sono da última noite")
    d_m = st.date_input("Dia (data em que acordou)", value=agora_local.date(),
                        max_value=agora_local.date(), format="DD/MM/YYYY", key="m_data")
    atual = db.ler_dia(USUARIO, d_m) or {}
    k = f"m_{d_m}_"  # chave depende da data: ao trocar o dia, os campos recarregam

    if atual.get("preenchido_manha_em_utc"):
        st.info("Este dia já tem registro da manhã. Salvar de novo substitui os valores.")

    c1, c2 = st.columns(2)
    deitou = c1.time_input("Deitou", hhmm_para_time(atual.get("sono_deitou"), time(23, 0)),
                           step=900, key=k + "deitou")
    acordou = c2.time_input("Acordou", hhmm_para_time(atual.get("sono_acordou"), time(7, 0)),
                            step=900, key=k + "acordou")
    desp_atual = {0: "0", 1: "1", 2: "2", 3: "3+"}.get(atual.get("sono_despertares"))
    despertares = escolha("Despertares", ["0", "1", "2", "3+"], desp_atual, k + "desp")
    qualidade = escolha("Qualidade do sono (1 péssima · 5 excelente)", [1, 2, 3, 4, 5],
                        atual.get("sono_qualidade"), k + "qual")
    sintoma = st.toggle("Acordei já com algum sintoma", value=bool(atual.get("acordou_com_sintoma")),
                        key=k + "sint")

    if st.button("Salvar manhã", type="primary", width="stretch", key=k + "salvar"):
        if despertares is None or qualidade is None:
            st.error("Marque despertares e qualidade do sono.")
        else:
            db.salvar_parte_do_dia(USUARIO, d_m, {
                "fuso": FUSO,
                "preenchido_manha_em_utc": db.utc_agora(),
                "retroativo_manha": db.retroativo_manha(d_m, db.local_agora(FUSO)),
                "sono_deitou": time_para_hhmm(deitou),
                "sono_acordou": time_para_hhmm(acordou),
                "sono_despertares": {"0": 0, "1": 1, "2": 2, "3+": 3}[despertares],
                "sono_qualidade": qualidade,
                "acordou_com_sintoma": sintoma,
            })
            st.success("Manhã salva.")

# ---------------------------------------------------------------- NOITE (o dia)
with abas[2]:
    st.subheader("Como foi o dia")
    d_n = st.date_input("Dia", value=db.data_padrao_noite(agora_local),
                        max_value=agora_local.date(), format="DD/MM/YYYY", key="n_data")
    atual = db.ler_dia(USUARIO, d_n) or {}
    k = f"n_{d_n}_"

    if atual.get("preenchido_noite_em_utc"):
        st.info("Este dia já tem registro da noite. Salvar de novo substitui os valores.")

    marcados = [rot for chave, rot in db.PREMONITORIOS.items() if atual.get(f"prem_{chave}")]
    prem = st.pills("Sintomas fora do seu normal hoje", list(db.PREMONITORIOS.values()),
                    selection_mode="multi", default=marcados, key=k + "prem")

    previsao = escala("Sinto que vem uma crise (0 nada · 10 certeza)", 0, 10,
                      atual.get("previsao_subjetiva"), k + "prev")
    estresse = escala("Estresse (0 nenhum · 10 máximo)", 0, 10, atual.get("estresse"), k + "estr")
    humor = escolha("Humor (1 muito ruim · 5 muito bom)", [1, 2, 3, 4, 5], atual.get("humor"), k + "humor")

    st.divider()
    caf_atual = None if atual.get("cafeina_doses") is None else (
        "4+" if atual["cafeina_doses"] >= 4 else str(atual["cafeina_doses"]))
    cafeina = escolha("Cafeína (doses)", ["0", "1", "2", "3", "4+"], caf_atual, k + "caf")
    caf_ultima = None
    if cafeina and cafeina != "0":
        caf_ultima = st.time_input("Hora da última dose", hhmm_para_time(atual.get("cafeina_ultima"), time(15, 0)),
                                   step=1800, key=k + "cafh")
    alc_atual = None if atual.get("alcool_doses") is None else (
        "3+" if atual["alcool_doses"] >= 3 else str(atual["alcool_doses"]))
    alcool = escolha("Álcool (doses)", ["0", "1", "2", "3+"], alc_atual, k + "alc")
    pulou = st.toggle("Pulei alguma refeição", value=bool(atual.get("pulou_refeicao")), key=k + "ref")
    exerc = escolha("Exercício", ["nenhum", "leve", "intenso"], atual.get("exercicio_nivel"), k + "ex")
    ex_min = None
    if exerc and exerc != "nenhum":
        ex_min = escolha("Duração (min)", [15, 30, 45, 60, 90], atual.get("exercicio_min"), k + "exmin")

    st.divider()
    outra = escala("Outra dor de cabeça (não enxaqueca), 0 a 10", 0, 10, atual.get("outra_cefaleia"), k + "outra")
    analg = st.pills("Remédio para dor tomado SEM crise", MEDICACOES, selection_mode="multi",
                     default=[m for m in (atual.get("analgesico_sem_crise") or "").split(",") if m in MEDICACOES],
                     key=k + "analg")
    with st.expander("Dia atípico? (opcional)"):
        atipico = st.text_input("Viagem, doença, evento marcante...", value=atual.get("dia_atipico") or "",
                                key=k + "atip")

    if st.button("Salvar noite", type="primary", width="stretch", key=k + "salvar"):
        faltando = [n for n, v in [("previsão", previsao), ("estresse", estresse), ("humor", humor),
                                   ("cafeína", cafeina), ("álcool", alcool), ("exercício", exerc),
                                   ("outra dor de cabeça", outra)]
                    if v is None]
        if faltando:
            st.error("Marque: " + ", ".join(faltando) + ".")
        else:
            valores = {f"prem_{chave}": (rot in (prem or [])) for chave, rot in db.PREMONITORIOS.items()}
            valores.update({
                "fuso": FUSO,
                "preenchido_noite_em_utc": db.utc_agora(),
                "retroativo_noite": db.retroativo_noite(d_n, db.local_agora(FUSO)),
                "previsao_subjetiva": previsao,
                "estresse": estresse,
                "humor": humor,
                "cafeina_doses": 4 if cafeina == "4+" else int(cafeina),
                "cafeina_ultima": time_para_hhmm(caf_ultima),
                "alcool_doses": 3 if alcool == "3+" else int(alcool),
                "pulou_refeicao": pulou,
                "exercicio_nivel": exerc,
                "exercicio_min": ex_min if exerc != "nenhum" else 0,
                "outra_cefaleia": outra,
                "analgesico_sem_crise": ",".join(analg) if analg else None,
                "dia_atipico": atipico or None,
            })
            db.salvar_parte_do_dia(USUARIO, d_n, valores)
            st.success("Noite salva.")

# ---------------------------------------------------------------- CRISE (completar depois)
with abas[3]:
    st.subheader("Completar crise")
    pendentes = db.crises_incompletas(USUARIO)
    if not pendentes:
        st.info("Nenhuma crise pendente. Registre o início da aura na aba ⚡ Aura.")
    else:
        rotulos = {c["id_crise"]: db.utc_para_local(c["aura_inicio_utc"], c["fuso"]).strftime("Aura de %d/%m às %H:%M")
                   for c in pendentes}
        id_sel = st.selectbox("Crise", list(rotulos), format_func=rotulos.get)
        crise = next(c for c in pendentes if c["id_crise"] == id_sel)
        aura_local = db.utc_para_local(crise["aura_inicio_utc"], crise["fuso"])
        k = f"c_{id_sel}_"

        precisao = escolha("Precisão do horário da aura", ["exato", "±15 min", "±1 h"],
                           crise["aura_precisao"], k + "prec")
        tipos = st.pills("Tipo de aura", ["visual", "sensitiva", "fala", "outra"],
                         selection_mode="multi", default=["visual"], key=k + "tipo")
        duracao = escolha("Duração da aura (min)", [5, 10, 15, 20, 30, 45, 60, "mais de 60"], None, k + "dur")
        if duracao == "mais de 60":
            st.warning("Aura acima de 60 minutos foge do padrão típico. Vale comentar com seu médico.")

        sem_dor = st.toggle("Não houve dor depois da aura", key=k + "semdor")
        dor_inicio = dor_max = lado = None
        if not sem_dor:
            c1, c2 = st.columns(2)
            dor_d = c1.date_input("Dor começou (dia)", aura_local.date(), format="DD/MM/YYYY", key=k + "dord")
            dor_t = c2.time_input("Hora", (aura_local + timedelta(minutes=30)).time(), step=900, key=k + "dort")
            dor_inicio = datetime.combine(dor_d, dor_t)
            dor_max = escala("Dor máxima (0 a 10)", 0, 10, None, k + "dormax")
            lado = escolha("Lado da dor", ["direito", "esquerdo", "ambos", "alternou"], None, k + "lado")
        nausea = escolha("Náusea", ["nenhum", "náusea", "vômito"], None, k + "nau")

        meds = st.pills("Medicação para a crise", MEDICACOES, selection_mode="multi", key=k + "med")
        med_hora = st.time_input("Hora da medicação", (aura_local + timedelta(minutes=30)).time(),
                                 step=900, key=k + "medh") if meds else None

        c1, c2 = st.columns(2)
        fim_d = c1.date_input("Crise terminou (dia)", aura_local.date(), format="DD/MM/YYYY", key=k + "fimd")
        fim_t = c2.time_input("Hora", (aura_local + timedelta(hours=6)).time(), step=900, key=k + "fimt")

        with st.expander("Notas (opcional)"):
            retro = st.text_area("Sintomas que você lembra das 48 h anteriores (retrospectivo)", key=k + "retro")
            gatilho = st.text_input("Gatilho que você suspeita (hipótese, não causa)", key=k + "gat")

        if st.button("Salvar crise", type="primary", width="stretch", key=k + "salvar"):
            fim = datetime.combine(fim_d, fim_t)
            erros = []
            if duracao is None:
                erros.append("marque a duração da aura")
            if not sem_dor and (dor_max is None or lado is None):
                erros.append("marque intensidade e lado da dor")
            if fim <= aura_local:
                erros.append("o fim precisa ser depois do início da aura")
            if erros:
                st.error("Antes de salvar: " + "; ".join(erros) + ".")
            else:
                f = crise["fuso"]
                db.completar_crise(USUARIO, id_sel, {
                    "aura_precisao": precisao,
                    "aura_tipo": ",".join(tipos or []),
                    "aura_duracao_min": 61 if duracao == "mais de 60" else duracao,  # 61 = ">60"
                    "sem_dor": sem_dor,
                    "dor_inicio_utc": db.local_para_utc(dor_inicio, f) if dor_inicio else None,
                    "dor_max": dor_max,
                    "dor_lado": lado,
                    "nausea": nausea,
                    "medicacao": ",".join(meds) if meds else None,
                    "medicacao_hora": time_para_hhmm(med_hora),
                    "crise_fim_utc": db.local_para_utc(fim, f),
                    "sintomas_48h_retro": retro or None,
                    "gatilho_suspeito": gatilho or None,
                })
                st.toast("Crise completa.")
                st.rerun()

# ---------------------------------------------------------------- RELATÓRIOS
with abas[4]:
    reports.render(USUARIO, FUSO)

"""Relatórios DESCRITIVOS do diário e área do pesquisador.

Nada aqui testa hipóteses ou estima risco: com poucos eventos, qualquer
comparação "dias pré-crise × outros dias" fica para a etapa de análise,
com método definido antes de olhar os dados.

Organização:
  render(...)            -> relatório de UM paciente, em abas (Resumo, Diário, Crises, Referências, Exportar)
  pesquisa_visao(...)    -> pesquisador: todos os pacientes num olhar
  pesquisa_paciente(...) -> pesquisador: relatório de um paciente
  pesquisa_literatura()  -> pesquisador: pacientes × dados publicados, por tema
  pesquisa_fontes()      -> pesquisador: fontes, tipo de estudo e limitações
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import db
import referencias as ref

AZUL = "#2a78d6"     # série medida / crise que começou com aura
LARANJA = "#eb6834"  # marcador de crise / crise que começou com dor

ICHD3 = f"[ICHD-3, 2018]({ref.FONTES['ichd3']['link']})"
SONO_REF = "[AASM/SRS, Watson et al. 2015](https://doi.org/10.5665/sleep.4716)"


# ================================================================ utilidades

def _mediana(serie: pd.Series) -> float | None:
    s = pd.to_numeric(serie, errors="coerce").dropna()
    return float(s.median()) if len(s) else None


def _fmt(v, sufixo="", casas=0) -> str:
    return "—" if v is None or pd.isna(v) else f"{v:.{casas}f}{sufixo}".replace(".", ",")


def _pct(v, casas=0) -> str:
    return "—" if v is None or pd.isna(v) else f"{v * 100:.{casas}f}%".replace(".", ",")


def _periodo(dia: pd.DataFrame, cri: pd.DataFrame, hoje: pd.Timestamp) -> tuple[pd.Timestamp, int]:
    """Primeiro dia com qualquer registro e número de dias desde então (inclusive hoje)."""
    candidatos = [x for x in (dia["data_referencia"].min() if len(dia) else None,
                              cri["inicio_local"].min().normalize() if len(cri) else None) if x is not None]
    inicio = min(candidatos, default=hoje)
    return inicio, (hoje - inicio).days + 1


def _grade(cards: list[tuple[str, object]], colunas: int = 3) -> None:
    """Números em grade compacta que continua em colunas no celular (st.columns empilharia)."""
    html = "".join(
        f'<div style="padding:4px 0"><div style="font-size:0.75rem;opacity:.7">{r}</div>'
        f'<div style="font-size:1.35rem;font-weight:600">{v}</div></div>' for r, v in cards)
    st.markdown(f'<div style="display:grid;grid-template-columns:repeat({colunas},1fr);gap:4px 12px">'
                f'{html}</div>', unsafe_allow_html=True)


def _vazio(texto: str = "Ainda não há registros suficientes.") -> None:
    st.caption(texto)


# ================================================================ relatório de um paciente

def _resumo(dia, cri, hoje) -> None:
    _, n = _periodo(dia, cri, hoje)
    manha = dia["preenchido_manha_em_utc"].notna().sum() if len(dia) else 0
    noite = dia["preenchido_noite_em_utc"].notna().sum() if len(dia) else 0
    mensal = _fmt(len(cri) / (n / 30.44), "", 1) if n >= 30 else "—"
    ultimo = (hoje - cri["inicio_local"].max().normalize()).days if len(cri) else "—"
    _grade([("Dias acompanhados", n), ("Adesão manhã", _pct(manha / n)), ("Adesão noite", _pct(noite / n)),
            ("Crises", len(cri)), ("Crises por mês", mensal), ("Dias desde a última", ultimo)])
    if n < 30:
        st.caption("\"Crises por mês\" aparece a partir de 30 dias de acompanhamento.")

    if len(cri):
        st.markdown("**Crises por mês**")
        por_mes = (cri.assign(mes=cri["inicio_local"].dt.to_period("M").dt.to_timestamp())
                   .groupby("mes").size().rename("crises").reset_index())
        # meses sem crise aparecem com zero (ausência de crise também é informação)
        todos = pd.date_range(por_mes["mes"].min(), hoje.to_period("M").to_timestamp(), freq="MS")
        por_mes = por_mes.set_index("mes").reindex(todos, fill_value=0).rename_axis("mes").reset_index()
        por_mes["rotulo"] = por_mes["mes"].dt.strftime("%m/%Y")
        st.altair_chart(alt.Chart(por_mes).mark_bar(color=AZUL, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("rotulo:O", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("crises:Q", title=None, axis=alt.Axis(tickMinStep=1)),
            tooltip=[alt.Tooltip("rotulo:O", title="Mês"), alt.Tooltip("crises:Q", title="Crises")],
        ).properties(height=160), width="stretch")

    if len(dia):
        retro = int(dia["retroativo_manha"].fillna(False).sum() + dia["retroativo_noite"].fillna(False).sum())
        if retro:
            st.caption(f"{retro} registro(s) preenchido(s) depois do dia; ficam marcados para a análise.")


def _linha_com_crises(dia, cri, coluna, titulo, dominio):
    base = dia[["data_referencia", coluna]].dropna()
    linha = alt.Chart(base).mark_line(color=AZUL, strokeWidth=2, point=alt.OverlayMarkDef(color=AZUL, size=36)).encode(
        x=alt.X("data_referencia:T", title=None, axis=alt.Axis(format="%d/%m")),
        y=alt.Y(f"{coluna}:Q", title=None, scale=alt.Scale(domain=dominio)),
        tooltip=[alt.Tooltip("data_referencia:T", title="Dia", format="%d/%m/%Y"),
                 alt.Tooltip(f"{coluna}:Q", title=titulo)],
    )
    camadas = [linha]
    if len(cri):
        marcas = cri[["inicio_local", "inicio_tipo"]].rename(columns={"inicio_local": "inicio"})
        camadas.append(alt.Chart(marcas).mark_rule(color=LARANJA, strokeWidth=2, strokeDash=[4, 3]).encode(
            x="inicio:T", tooltip=[alt.Tooltip("inicio:T", title="Início da crise", format="%d/%m %H:%M"),
                                   alt.Tooltip("inicio_tipo:N", title="Começou com")]))
    return alt.layer(*camadas).properties(title=titulo, height=140)


def _diario(dia, cri, hoje) -> None:
    if dia.empty:
        return _vazio()
    st.caption("Linhas laranja tracejadas = início de crise.")
    for col, tit, dom in [("sono_qualidade", "Qualidade do sono (1–5)", [1, 5]),
                          ("estresse", "Estresse (0–10)", [0, 10]),
                          ("previsao_subjetiva", "\"Sinto que vem crise\" (0–10)", [0, 10])]:
        if dia[col].notna().any():
            st.altair_chart(_linha_com_crises(dia, cri, col, tit, dom), width="stretch")

    ult30 = pd.date_range(hoje - pd.Timedelta(days=29), hoje, freq="D")
    feitos = dia.set_index("data_referencia")
    faltas = [d for d in ult30 if d not in feitos.index
              or pd.isna(feitos.loc[d, "preenchido_manha_em_utc"])
              or pd.isna(feitos.loc[d, "preenchido_noite_em_utc"])]
    if faltas:
        with st.expander(f"{len(faltas)} dia(s) incompletos nos últimos 30"):
            st.write(", ".join(d.strftime("%d/%m") for d in faltas))


def _crises(cri) -> None:
    if cri.empty:
        return _vazio("Nenhuma crise registrada.")

    def num(serie, casas=0):
        return serie.map(lambda v: "—" if pd.isna(v) else _fmt(v, "", casas))

    tab = pd.DataFrame({
        "Início": cri["inicio_local"].dt.strftime("%d/%m/%Y %H:%M"),
        "Começou com": cri["inicio_tipo"],
        "Teve aura": cri["teve_aura"].map({True: "sim", False: "não"}).fillna("—"),
        "Duração aura (min)": cri["aura_duracao_min"].map(
            lambda v: "—" if pd.isna(v) else (">60" if v == 61 else f"{v:.0f}")),
        "Início→dor (min)": num((cri["dor_inicio_local"] - cri["inicio_local"]).dt.total_seconds() / 60),
        "Dor máx": num(cri["dor_max"]),
        "Duração (h)": num((cri["crise_fim_local"] - cri["inicio_local"]).dt.total_seconds() / 3600, 1),
        "Precisão": cri["inicio_precisao"].fillna("—"),
        "Registro": cri["registro_retroativo"].map({True: "depois", False: "na hora"}).fillna("na hora"),
        "Completa": cri["completado_em_utc"].notna().map({True: "sim", False: "pendente"}),
    }).iloc[::-1]
    st.dataframe(tab, hide_index=True, width="stretch")
    st.caption("\"Registro: depois\" = crise registrada pela pergunta da noite, com horário aproximado.")


def _referencias(dia, cri, hoje, pessoa: str) -> None:
    """Valores do paciente ao lado de referências clínicas publicadas. Descritivo: não é diagnóstico."""
    st.caption("Referência não é diagnóstico. Valores fora da faixa são motivo para conversar com o médico, "
               "não para concluir algo sozinho.")
    linhas = []

    dur = cri.loc[cri["teve_aura"] == True, "aura_duracao_min"].dropna()  # noqa: E712
    if len(dur):
        dentro = ((dur >= 5) & (dur <= 60)).mean()
        linhas.append(("Duração da aura (mediana)", _fmt(_mediana(dur.clip(upper=61)), " min") +
                       f" · {_pct(dentro)} entre 5 e 60 min", "cada sintoma dura 5 a 60 min", ICHD3))
    com_aura = cri[(cri["inicio_tipo"] == "aura") & cri["dor_inicio_local"].notna()]
    if len(com_aura):
        interv = (com_aura["dor_inicio_local"] - com_aura["inicio_local"]).dt.total_seconds() / 60
        linhas.append(("Da aura até a dor (mediana)", _fmt(_mediana(interv), " min") +
                       f" · {_pct((interv <= 60).mean())} em até 60 min",
                       "dor junto com a aura ou em até 60 min", ICHD3))
    completas = cri[cri["crise_fim_local"].notna()]
    if len(completas):
        horas = (completas["crise_fim_local"] - completas["inicio_local"]).dt.total_seconds() / 3600
        linhas.append(("Duração da crise (mediana)", _fmt(_mediana(horas), " h", 1),
                       "4 a 72 h sem tratamento eficaz; com remédio tende a ser menor", ICHD3))

    # frequências mensais: últimos 90 dias acompanhados; exige 30+ dias
    inicio, _ = _periodo(dia, cri, hoje)
    janela_ini = max(inicio, hoje - pd.Timedelta(days=89))
    n = (hoje - janela_ini).days + 1
    if n >= 30 and len(dia):
        fator = 30.44 / n
        d_jan = dia[dia["data_referencia"] >= janela_ini]
        c_jan = cri[cri["inicio_local"] >= janela_ini]
        dias_crise = set(c_jan["inicio_local"].dt.normalize())
        dias_dor = dias_crise | set(d_jan.loc[d_jan["outra_cefaleia"].fillna(0) > 0, "data_referencia"])
        linhas.append(("Dias com dor de cabeça por mês", _fmt(len(dias_dor) * fator, "", 1),
                       "15 ou mais por mês, por mais de 3 meses, define enxaqueca crônica", ICHD3))
        dias_med = set(d_jan.loc[d_jan["analgesico_sem_crise"].notna(), "data_referencia"]) | \
            set(c_jan.loc[c_jan["medicacao"].notna(), "inicio_local"].dt.normalize())
        tript = set(d_jan.loc[d_jan["analgesico_sem_crise"].fillna("").str.contains("tript", case=False),
                              "data_referencia"]) | \
            set(c_jan.loc[c_jan["medicacao"].fillna("").str.contains("tript", case=False),
                          "inicio_local"].dt.normalize())
        linhas.append(("Dias com remédio para dor por mês", _fmt(len(dias_med) * fator, "", 1),
                       "uso regular em 15+ dias/mês (analgésicos comuns) pode causar cefaleia por uso excessivo",
                       ICHD3))
        linhas.append(("Dias com triptano por mês", _fmt(len(tript) * fator, "", 1),
                       "uso regular em 10+ dias/mês pode causar cefaleia por uso excessivo", ICHD3))
    else:
        st.caption("As frequências por mês aparecem a partir de 30 dias de acompanhamento.")

    if len(dia) and dia["sono_deitou"].notna().any():
        dei = pd.to_datetime(dia["sono_deitou"], format="%H:%M", errors="coerce")
        aco = pd.to_datetime(dia["sono_acordou"], format="%H:%M", errors="coerce")
        horas = ((aco - dei).dt.total_seconds() / 3600) % 24
        linhas.append(("Tempo na cama (mediana)", _fmt(_mediana(horas), " h", 1),
                       "adultos: 7 h ou mais de sono; tempo na cama é maior que o tempo dormindo", SONO_REF))

    if not linhas:
        return _vazio("Ainda não há dados suficientes para comparar com as referências.")
    # cartões empilhados: uma tabela de 4 colunas fica ilegível no celular
    for indicador, valor, referencia, fonte in linhas:
        with st.container(border=True):
            st.markdown(f"**{indicador}**  \n{pessoa}: **{valor}**  \nReferência: {referencia} · {fonte}")
    st.caption("Contagens por dia usam o dia de início da crise. Triptanos são reconhecidos pelo nome "
               "contendo \"tript\".")


def render(id_usuario: str, fuso: str, pessoa: str = "Você", chave: str = "") -> None:
    """Relatório de um paciente, dividido em abas por assunto."""
    dia = db.df_diario(id_usuario)
    cri = db.df_crises(id_usuario)
    if dia.empty and cri.empty:
        st.info("Ainda não há registros.")
        return
    hoje = pd.Timestamp(db.local_agora(fuso).date())
    st.caption("Resumo descritivo. Não indica causa nem risco de crise.")

    a1, a2, a3, a4, a5 = st.tabs(["Resumo", "Diário", "Crises", "Referências", "Exportar"])
    with a1:
        _resumo(dia, cri, hoje)
    with a2:
        _diario(dia, cri, hoje)
    with a3:
        _crises(cri)
    with a4:
        _referencias(dia, cri, hoje, pessoa)
    with a5:
        st.caption("Arquivos CSV com todos os registros, para análise em Python/pandas ou planilha.")
        c1, c2 = st.columns(2)
        c1.download_button("⬇ diario.csv", dia.to_csv(index=False).encode("utf-8"), f"diario_{id_usuario}.csv",
                           "text/csv", width="stretch", key=f"{chave}dl_diario")
        c2.download_button("⬇ crises.csv", cri.to_csv(index=False).encode("utf-8"), f"crises_{id_usuario}.csv",
                           "text/csv", width="stretch", key=f"{chave}dl_crises")


# ================================================================ área do pesquisador

def _status(dias_sem_registro: int):
    """Estado da coleta com ícone + rótulo (nunca só cor)."""
    if dias_sem_registro <= 1:
        return "Em dia", ":material/check_circle:", "green"
    if dias_sem_registro <= 3:
        return f"{dias_sem_registro} dias sem registro", ":material/schedule:", "orange"
    return f"{dias_sem_registro} dias sem registro", ":material/error:", "red"


def _resumo_paciente(uid: str, hoje: pd.Timestamp) -> dict:
    dia, cri = db.df_diario(uid), db.df_crises(uid)
    if dia.empty and cri.empty:
        return {"uid": uid, "vazio": True}
    inicio, n = _periodo(dia, cri, hoje)
    ultimo = max([x for x in (dia["data_referencia"].max() if len(dia) else None,
                              cri["inicio_local"].max().normalize() if len(cri) else None) if x is not None])
    return {
        "uid": uid, "vazio": False, "cri": cri, "inicio": inicio, "n": n,
        "manha": dia["preenchido_manha_em_utc"].notna().sum() / n if len(dia) else 0,
        "noite": dia["preenchido_noite_em_utc"].notna().sum() / n if len(dia) else 0,
        "resposta_crise": int(dia["teve_crise"].notna().sum()) if len(dia) else 0,
        "crises": len(cri),
        "com_aura": int((cri["teve_aura"] == True).sum()),  # noqa: E712
        "depois": int((cri["registro_retroativo"] == True).sum()),  # noqa: E712
        "pendentes": int(cri["completado_em_utc"].isna().sum()),
        "mensal": _fmt(len(cri) / (n / 30.44), "", 1) if n >= 30 else "—",
        "ultimo": ultimo, "sem_registro": (hoje - ultimo).days,
    }


def pesquisa_visao(ids: list[str], fuso: str) -> None:
    hoje = pd.Timestamp(db.local_agora(fuso).date())
    resumos = [_resumo_paciente(uid, hoje) for uid in ids]
    if not resumos:
        return _vazio("Nenhum paciente cadastrado.")

    st.markdown("**Situação da coleta**")
    for i in range(0, len(resumos), 2):
        colunas = st.columns(2)
        for col, r in zip(colunas, resumos[i:i + 2]):
            with col.container(border=True):
                st.markdown(f"**Paciente {r['uid']}**")
                if r["vazio"]:
                    st.caption("Ainda sem registros.")
                    continue
                rot, icone, cor = _status(r["sem_registro"])
                st.badge(rot, icon=icone, color=cor)
                _grade([("Dias", r["n"]), ("Adesão média", _pct((r["manha"] + r["noite"]) / 2)),
                        ("Crises", r["crises"]), ("Com aura", r["com_aura"]),
                        ("Crises/mês", r["mensal"]), ("Pendentes", r["pendentes"])])

    pontos = [{"Paciente": r["uid"], "inicio": c["inicio_local"], "Começou com": c["inicio_tipo"]}
              for r in resumos if not r["vazio"] for _, c in r["cri"].iterrows()]
    if pontos:
        st.markdown("**Crises ao longo do tempo**")
        st.altair_chart(alt.Chart(pd.DataFrame(pontos)).mark_point(filled=True, size=90).encode(
            x=alt.X("inicio:T", title=None, axis=alt.Axis(format="%d/%m")),
            y=alt.Y("Paciente:N", title=None),
            color=alt.Color("Começou com:N", scale=alt.Scale(domain=["aura", "dor"], range=[AZUL, LARANJA]),
                            legend=alt.Legend(orient="top", title=None)),
            shape=alt.Shape("Começou com:N", scale=alt.Scale(domain=["aura", "dor"], range=["circle", "triangle"]),
                            legend=None),
            tooltip=[alt.Tooltip("Paciente:N"), alt.Tooltip("inicio:T", title="Início", format="%d/%m %H:%M"),
                     alt.Tooltip("Começou com:N")],
        ).properties(height=80 + 60 * len(ids)), width="stretch")

    with st.expander("Tabela completa"):
        linhas = {}
        for r in resumos:
            if r["vazio"]:
                continue
            linhas[r["uid"]] = {
                "Início": r["inicio"].strftime("%d/%m/%Y"), "Dias acompanhados": r["n"],
                "Adesão manhã": _pct(r["manha"]), "Adesão noite": _pct(r["noite"]),
                "Noites com \"teve crise?\"": r["resposta_crise"], "Crises": r["crises"],
                "Com aura": r["com_aura"], "Registradas depois": r["depois"], "Pendentes": r["pendentes"],
                "Crises/mês": r["mensal"], "Último registro": r["ultimo"].strftime("%d/%m"),
                "Dias sem registro": r["sem_registro"],
            }
        if linhas:
            tabela = pd.DataFrame(linhas).astype(str)
            st.dataframe(tabela, width="stretch", height=36 * (len(tabela) + 1) + 3)


def pesquisa_paciente(ids: list[str], fuso: str) -> None:
    if not ids:
        return _vazio("Nenhum paciente cadastrado.")
    uid = st.segmented_control("Paciente", ids, default=ids[0], key="pesq_paciente") or ids[0]
    render(uid, fuso, pessoa="Paciente", chave=f"pesq_{uid}")


def _sequencia_aura_dor(cri: pd.DataFrame) -> pd.Series:
    """Classifica cada crise com aura nas categorias de Viana et al. (tolerância de 5 min)."""
    cats = []
    for _, c in cri[cri["teve_aura"] == True].iterrows():  # noqa: E712
        if c["inicio_tipo"] == "dor":
            cats.append("dor antes da aura")
            continue
        if c.get("sem_dor") or pd.isna(c["dor_inicio_local"]):
            continue
        dt = (c["dor_inicio_local"] - c["inicio_local"]).total_seconds() / 60
        dur = c["aura_duracao_min"]
        if dt <= 5:
            cats.append("dor junto com a aura")
        elif pd.isna(dur) or dur == 61:
            continue
        elif dt < dur - 5:
            cats.append("dor durante a aura")
        elif dt <= dur + 5:
            cats.append("dor quando a aura terminou")
        else:
            cats.append("dor depois de um intervalo")
    return pd.Series(cats, dtype="object")


def _premonitorios_vespera(dia: pd.DataFrame, cri: pd.DataFrame) -> dict:
    """Sintomas marcados na NOITE ANTERIOR a cada crise (registro prospectivo),
    comparados com os dias comuns da mesma pessoa."""
    if dia.empty:
        return {}
    cols = [f"prem_{k}" for k in db.PREMONITORIOS]
    noites = dia[dia["preenchido_noite_em_utc"].notna()].set_index("data_referencia")
    if noites.empty:
        return {}
    dias_crise = set(cri["inicio_local"].dt.normalize())
    vesperas = [d - pd.Timedelta(days=1) for d in dias_crise]
    vesp = noites.loc[[d for d in vesperas if d in noites.index], cols].fillna(False).astype(bool)
    excluir = dias_crise | set(vesperas)
    comuns = noites.loc[[d for d in noites.index if d not in excluir], cols].fillna(False).astype(bool)
    top = vesp.mean().sort_values(ascending=False) if len(vesp) else pd.Series(dtype=float)
    return {
        "n_vesp": len(vesp), "vesp_algum": vesp.any(axis=1).mean() if len(vesp) else None,
        "n_comuns": len(comuns), "comuns_algum": comuns.any(axis=1).mean() if len(comuns) else None,
        "top": [(db.PREMONITORIOS[c.removeprefix("prem_")], v) for c, v in top.head(3).items() if v > 0],
    }


def _tabela_comparacao(ids, linhas, fonte_md: str) -> None:
    """linhas: [(indicador, {uid: valor}, literatura)]"""
    dados = {"Indicador": [l[0] for l in linhas]}
    for uid in ids:
        dados[uid] = [l[1].get(uid, "—") for l in linhas]
    dados["Literatura"] = [l[2] for l in linhas]
    st.dataframe(pd.DataFrame(dados), hide_index=True, width="stretch", height=36 * (len(linhas) + 1) + 3)
    st.caption(f"Fonte: {fonte_md}")


def pesquisa_literatura(ids: list[str]) -> None:
    F = ref.FONTES
    st.caption("Cada paciente ao lado de dados publicados. Os métodos são diferentes (diário deste app × "
               "estudos com outras populações): a comparação é qualitativa, para ver se os registros estão "
               "coerentes com o que se conhece, não para classificar ninguém. Detalhes em **Fontes**.")
    dados = {uid: (db.df_diario(uid), db.df_crises(uid)) for uid in ids}
    t1, t2, t3 = st.tabs(["Aura", "Sintomas premonitórios", "Contexto"])

    with t1:
        n_aura, med, acima, seqs = {}, {}, {}, {}
        for uid, (_, cri) in dados.items():
            dur = cri.loc[cri["teve_aura"] == True, "aura_duracao_min"].dropna()  # noqa: E712
            n_aura[uid] = str(len(dur))
            med[uid] = _fmt(_mediana(dur.clip(upper=61)), " min") if len(dur) else "—"
            acima[uid] = _pct((dur > 60).mean()) if len(dur) else "—"
            seqs[uid] = _sequencia_aura_dor(cri)
        st.markdown("**Duração**")
        _tabela_comparacao(ids, [
            ("Auras com duração registrada", n_aura, "216 auras de 72 pacientes"),
            ("Duração (mediana)", med, f"{ref.VIANA_AURA_MEDIANA_MIN} min (IQR {ref.VIANA_AURA_IQR})"),
            ("Acima de 60 min", acima, f"{_pct(ref.VIANA_SINTOMAS_ACIMA_60)} dos sintomas de aura"),
        ], f"[Viana et al.]({F['viana']['link']})")
        st.markdown("**Quando a dor começa em relação à aura**")
        _tabela_comparacao(ids, [
            (cat.capitalize(),
             {uid: (f"{_pct((s == cat).mean())} ({(s == cat).sum()}/{len(s)})" if len(s) else "—")
              for uid, s in seqs.items()},
             _pct(v)) for cat, v in ref.VIANA_SEQUENCIA.items()
        ], f"[Viana et al.]({F['viana']['link']}), 157 auras com horário de início da dor")

    with t2:
        vesp, comuns, top = {}, {}, {}
        for uid, (dia, cri) in dados.items():
            p = _premonitorios_vespera(dia, cri)
            vesp[uid] = f"{_pct(p.get('vesp_algum'))} (n={p.get('n_vesp', 0)})" if p else "—"
            comuns[uid] = f"{_pct(p.get('comuns_algum'))} (n={p.get('n_comuns', 0)})" if p else "—"
            top[uid] = (", ".join(f"{s} {_pct(v)}" for s, v in p.get("top", [])) or "—") if p else "—"
        _tabela_comparacao(ids, [
            ("Crises com ≥1 sintoma na noite anterior", vesp,
             f"{_pct(ref.LAURELL_COM_PREMONITORIO)} das pessoas relatam ter"),
            ("Dias comuns com ≥1 sintoma", comuns, "sem dado comparável publicado"),
            ("Mais frequentes na véspera", top, f"bocejos {_pct(ref.LAURELL_BOCEJO)}; humor e cansaço ~1/3"),
        ], f"[Laurell et al., 2016]({F['laurell']['link']})")
        st.info("A linha **dias comuns** é a que importa: se os sintomas aparecem tanto na véspera quanto em "
                "dias comuns, eles não antecipam a crise. Com poucas crises, as porcentagens ainda são instáveis.",
                icon=":material/lightbulb:")

    with t3:
        pv = ref.QUEIROZ_PREVALENCIA
        with st.container(border=True):
            st.markdown(f"**Prevalência de enxaqueca no Brasil**  \n"
                        f"{_pct(pv['geral'], 1)} da população (mulheres {_pct(pv['mulheres'], 1)}, "
                        f"homens {_pct(pv['homens'], 1)})  \n"
                        f"[Queiroz et al., 2009]({F['queiroz']['link']})")
        with st.container(border=True):
            st.markdown(f"**Melhor previsão publicada com diário + wearable que encontramos**  \n"
                        f"AUC {_fmt(ref.STUBBERUD_AUC, '', 2)} em 18 pacientes; no teste, não acertou nenhuma "
                        f"crise. Referência de quanto o problema é difícil.  \n"
                        f"[Stubberud et al., 2023]({F['stubberud']['link']})")


def pesquisa_fontes() -> None:
    st.caption("Só entram números conferidos no resumo do artigo original.")
    nomes = {"ichd3": "ICHD-3", "viana": "Viana", "laurell": "Laurell", "queiroz": "Queiroz",
             "stubberud": "Stubberud"}
    for chave, f in ref.FONTES.items():
        with st.container(border=True):
            st.markdown(f"**{nomes.get(chave, chave)}** · [{f['citacao']}]({f['link']})  \n"
                        f":material/science: {f['tipo']}  \n:material/warning: {f['limitacao']}")

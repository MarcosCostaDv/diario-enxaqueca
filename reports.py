"""Relatórios DESCRITIVOS do diário.

Nada aqui testa hipóteses ou estima risco: com poucos eventos, qualquer
comparação "dias pré-crise × outros dias" fica para a etapa de análise,
com método definido antes de olhar os dados.
"""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import db

AZUL = "#2a78d6"     # série medida
LARANJA = "#eb6834"  # marcador de crise

ICHD3 = "[ICHD-3, 2018](https://doi.org/10.1177/0333102417738202)"
SONO_REF = "[AASM/SRS, Watson et al. 2015](https://doi.org/10.5665/sleep.4716)"


def _mediana(serie: pd.Series) -> float | None:
    s = pd.to_numeric(serie, errors="coerce").dropna()
    return float(s.median()) if len(s) else None


def _fmt(v, sufixo="", casas=0) -> str:
    return "—" if v is None else f"{v:.{casas}f}{sufixo}".replace(".", ",")


def _referencias(dia: pd.DataFrame, cri: pd.DataFrame, hoje: pd.Timestamp) -> None:
    """Seus valores ao lado de referências clínicas publicadas. Descritivo: não é diagnóstico."""
    st.markdown("**Seus valores e referências clínicas**")
    st.caption("Referência não é diagnóstico. Valores fora da faixa são motivo para conversar com seu médico, "
               "não para concluir algo sozinho.")
    linhas = []

    # --- aura
    auras = cri[cri["teve_aura"] == True]  # noqa: E712
    dur = auras["aura_duracao_min"].dropna()
    if len(dur):
        dentro = ((dur >= 5) & (dur <= 60)).mean()
        linhas.append(("Duração da aura (mediana)", _fmt(_mediana(dur.clip(upper=61)), " min") +
                       f" · {dentro:.0%} entre 5 e 60 min", "cada sintoma dura 5 a 60 min", ICHD3))
    com_aura = cri[(cri["inicio_tipo"] == "aura") & cri["dor_inicio_local"].notna()]
    if len(com_aura):
        interv = (com_aura["dor_inicio_local"] - com_aura["inicio_local"]).dt.total_seconds() / 60
        linhas.append(("Da aura até a dor (mediana)", _fmt(_mediana(interv), " min") +
                       f" · {(interv <= 60).mean():.0%} em até 60 min",
                       "dor junto com a aura ou em até 60 min", ICHD3))
    completas = cri[cri["crise_fim_local"].notna()]
    if len(completas):
        horas = (completas["crise_fim_local"] - completas["inicio_local"]).dt.total_seconds() / 3600
        linhas.append(("Duração da crise (mediana)", _fmt(_mediana(horas), " h", 1),
                       "4 a 72 h sem tratamento eficaz; com remédio tende a ser menor", ICHD3))

    # --- frequências mensais (janela: últimos 90 dias acompanhados; exige 30+ dias)
    inicio = min([x for x in (dia["data_referencia"].min() if len(dia) else None,
                              cri["inicio_local"].min().normalize() if len(cri) else None) if x is not None],
                 default=hoje)
    janela_ini = max(inicio, hoje - pd.Timedelta(days=89))
    n = (hoje - janela_ini).days + 1
    if n >= 30:
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

    # --- sono (tempo na cama, não tempo dormindo)
    if len(dia) and dia["sono_deitou"].notna().any():
        dei = pd.to_datetime(dia["sono_deitou"], format="%H:%M", errors="coerce")
        aco = pd.to_datetime(dia["sono_acordou"], format="%H:%M", errors="coerce")
        horas = ((aco - dei).dt.total_seconds() / 3600) % 24
        linhas.append(("Tempo na cama (mediana)", _fmt(_mediana(horas), " h", 1),
                       "adultos: 7 h ou mais de sono; tempo na cama é maior que o tempo dormindo", SONO_REF))

    if linhas:
        # cartões empilhados: uma tabela de 4 colunas fica ilegível na tela do celular
        for indicador, valor, ref, fonte in linhas:
            with st.container(border=True):
                st.markdown(f"**{indicador}**  \nVocê: **{valor}**  \nReferência: {ref} · {fonte}")
        st.caption("Contagens por dia usam o dia de início da crise. Os remédios são reconhecidos pelos nomes "
                   "configurados no app; triptanos pelo nome contendo \"tript\".")
    else:
        st.caption("Ainda não há dados suficientes para comparar com as referências.")


def render_pesquisa(ids: list[str], fuso: str) -> None:
    """Tela do pesquisador: participantes lado a lado, só descritivo."""
    st.subheader("🔬 Pesquisa")
    st.caption("Visível apenas para o pesquisador. Participantes identificados só pelo código. "
               "Comparação descritiva: cada pessoa é analisada separadamente (N=1).")
    hoje = pd.Timestamp(db.local_agora(fuso).date())
    linhas, pontos = [], []
    for uid in ids:
        dia, cri = db.df_diario(uid), db.df_crises(uid)
        if dia.empty and cri.empty:
            linhas.append({"Participante": uid, "Dias acompanhados": 0})
            continue
        inicio = min([x for x in (dia["data_referencia"].min() if len(dia) else None,
                                  cri["inicio_local"].min().normalize() if len(cri) else None) if x is not None])
        n = (hoje - inicio).days + 1
        ultimo = max([x for x in (dia["data_referencia"].max() if len(dia) else None,
                                  cri["inicio_local"].max().normalize() if len(cri) else None) if x is not None])
        linhas.append({
            "Participante": uid,
            "Início": inicio.strftime("%d/%m/%Y"),
            "Dias acompanhados": n,
            "Adesão manhã": f"{dia['preenchido_manha_em_utc'].notna().sum() / n:.0%}",
            "Adesão noite": f"{dia['preenchido_noite_em_utc'].notna().sum() / n:.0%}",
            "Noites com \"teve crise?\"": int(dia["teve_crise"].notna().sum()) if "teve_crise" in dia else 0,
            "Crises": len(cri),
            "Com aura": int((cri["teve_aura"] == True).sum()),  # noqa: E712
            "Registradas depois": int((cri["registro_retroativo"] == True).sum()),  # noqa: E712
            "Pendentes": int(cri["completado_em_utc"].isna().sum()),
            "Crises/mês": _fmt(len(cri) / (n / 30.44), "", 1) if n >= 30 else "—",
            "Último registro": ultimo.strftime("%d/%m"),
            "Dias sem registro": (hoje - ultimo).days,
        })
        for _, c in cri.iterrows():
            pontos.append({"Participante": uid, "inicio": c["inicio_local"], "Começou com": c["inicio_tipo"]})

    # participantes nas colunas, indicadores nas linhas: cabe na tela do celular
    tabela = pd.DataFrame(linhas).set_index("Participante").T.astype(str).replace({"nan": "—"})
    st.dataframe(tabela, width="stretch", height=36 * (len(tabela) + 1) + 3)  # sem rolagem interna
    st.caption("\"Dias sem registro\" alto indica que a pessoa pode ter parado de preencher.")

    if pontos:
        st.markdown("**Crises ao longo do tempo**")
        st.altair_chart(alt.Chart(pd.DataFrame(pontos)).mark_point(filled=True, size=90).encode(
            x=alt.X("inicio:T", title=None),
            y=alt.Y("Participante:N", title=None),
            color=alt.Color("Começou com:N", scale=alt.Scale(domain=["aura", "dor"], range=[AZUL, LARANJA]),
                            legend=alt.Legend(orient="top", title=None)),
            shape=alt.Shape("Começou com:N", scale=alt.Scale(domain=["aura", "dor"], range=["circle", "triangle"]),
                            legend=None),
            tooltip=[alt.Tooltip("Participante:N"), alt.Tooltip("inicio:T", title="Início", format="%d/%m %H:%M"),
                     alt.Tooltip("Começou com:N")],
        ).properties(height=80 + 60 * len(ids)), width="stretch")


def _metricas(dia: pd.DataFrame, cri: pd.DataFrame, hoje: pd.Timestamp) -> None:
    inicio = min([x for x in (dia["data_referencia"].min() if len(dia) else None,
                              cri["inicio_local"].min().normalize() if len(cri) else None) if x is not None],
                 default=hoje)
    n_dias = (hoje - inicio).days + 1
    manha = dia["preenchido_manha_em_utc"].notna().sum()
    noite = dia["preenchido_noite_em_utc"].notna().sum()

    mensal = f"{len(cri) / (n_dias / 30.44):.1f}" if n_dias >= 30 else "—"
    ultimo = (hoje - cri["inicio_local"].max().normalize()).days if len(cri) else "—"
    cards = [("Dias acompanhados", n_dias), ("Adesão manhã", f"{manha / n_dias:.0%}"),
             ("Adesão noite", f"{noite / n_dias:.0%}"), ("Crises", len(cri)),
             ("Crises por mês", mensal), ("Dias desde a última", ultimo)]
    # grade compacta de 3 colunas que continua em 3 colunas no celular (st.columns empilharia)
    html = "".join(
        f'<div style="padding:6px 0"><div style="font-size:0.75rem;opacity:.7">{r}</div>'
        f'<div style="font-size:1.4rem;font-weight:600">{v}</div></div>' for r, v in cards)
    st.markdown(f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px 12px">{html}</div>',
                unsafe_allow_html=True)
    if n_dias < 30:
        st.caption("Crises por mês só é calculado com 30 dias ou mais de acompanhamento.")

    retro = int(dia["retroativo_manha"].fillna(False).sum() + dia["retroativo_noite"].fillna(False).sum())
    if retro:
        st.caption(f"{retro} registro(s) preenchido(s) retroativamente; ficam marcados para a análise.")


def _linha_com_crises(dia: pd.DataFrame, cri: pd.DataFrame, coluna: str, titulo: str, dominio: list[int]):
    base = dia[["data_referencia", coluna]].dropna()
    linha = alt.Chart(base).mark_line(color=AZUL, strokeWidth=2, point=alt.OverlayMarkDef(color=AZUL, size=36)).encode(
        x=alt.X("data_referencia:T", title=None),
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


def render(id_usuario: str, fuso: str) -> None:
    st.subheader("Relatórios")
    st.caption("Resumo descritivo. Não indica causa nem risco de crise.")

    dia = db.df_diario(id_usuario)
    cri = db.df_crises(id_usuario)
    if dia.empty and cri.empty:
        st.info("Ainda não há registros.")
        return

    hoje = pd.Timestamp(db.local_agora(fuso).date())
    _metricas(dia, cri, hoje)

    # --- crises por mês
    if len(cri):
        st.markdown("**Crises por mês**")
        por_mes = cri.assign(mes=cri["inicio_local"].dt.to_period("M").dt.to_timestamp()) \
                     .groupby("mes").size().rename("crises").reset_index()
        # meses sem crise aparecem com zero (ausência de crise também é informação)
        todos = pd.date_range(por_mes["mes"].min(), hoje.to_period("M").to_timestamp(), freq="MS")
        por_mes = por_mes.set_index("mes").reindex(todos, fill_value=0).rename_axis("mes").reset_index()
        por_mes["rotulo"] = por_mes["mes"].dt.strftime("%m/%Y")
        st.altair_chart(alt.Chart(por_mes).mark_bar(color=AZUL, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
            x=alt.X("rotulo:O", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("crises:Q", title=None, axis=alt.Axis(tickMinStep=1)),
            tooltip=[alt.Tooltip("rotulo:O", title="Mês"), alt.Tooltip("crises:Q", title="Crises")],
        ).properties(height=160), width="stretch")

    # --- séries diárias com as crises marcadas (um gráfico por medida, sem eixo duplo)
    if len(dia):
        st.markdown("**Registros diários** · linhas laranja tracejadas = início de crise")
        for col, tit, dom in [("sono_qualidade", "Qualidade do sono (1–5)", [1, 5]),
                              ("estresse", "Estresse (0–10)", [0, 10]),
                              ("previsao_subjetiva", "\"Sinto que vem crise\" (0–10)", [0, 10])]:
            if dia[col].notna().any():
                st.altair_chart(_linha_com_crises(dia, cri, col, tit, dom), width="stretch")

    # --- tabela de crises
    if len(cri):
        st.markdown("**Crises**")
        tab = pd.DataFrame({
            "Início": cri["inicio_local"].dt.strftime("%d/%m/%Y %H:%M"),
            "Começou com": cri["inicio_tipo"],
            "Teve aura": cri["teve_aura"].map({True: "sim", False: "não"}).fillna("—"),
            "Precisão": cri["inicio_precisao"],
            "Registro": cri["registro_retroativo"].map({True: "depois", False: "na hora"}).fillna("na hora"),
            "Duração aura (min)": cri["aura_duracao_min"].map(lambda v: ">60" if v == 61 else v),
            "Início→dor (min)": ((cri["dor_inicio_local"] - cri["inicio_local"]).dt.total_seconds() / 60).round(),
            "Dor máx": cri["dor_max"],
            "Duração total (h)": ((cri["crise_fim_local"] - cri["inicio_local"]).dt.total_seconds() / 3600).round(1),
            "Completa": cri["completado_em_utc"].notna().map({True: "sim", False: "pendente"}),
        }).iloc[::-1]
        st.dataframe(tab, hide_index=True, width="stretch")

    _referencias(dia, cri, hoje)

    # --- dias sem registro (últimos 30)
    if len(dia):
        ult30 = pd.date_range(hoje - pd.Timedelta(days=29), hoje, freq="D")
        feitos = dia.set_index("data_referencia")
        faltas = [d for d in ult30 if d not in feitos.index
                  or pd.isna(feitos.loc[d, "preenchido_manha_em_utc"])
                  or pd.isna(feitos.loc[d, "preenchido_noite_em_utc"])]
        if faltas:
            with st.expander(f"{len(faltas)} dia(s) incompletos nos últimos 30"):
                st.write(", ".join(d.strftime("%d/%m") for d in faltas))

    # --- exportação
    st.markdown("**Exportar dados**")
    c1, c2 = st.columns(2)
    c1.download_button("diario.csv", dia.to_csv(index=False).encode("utf-8"), "diario.csv", "text/csv",
                       width="stretch")
    c2.download_button("crises.csv", cri.to_csv(index=False).encode("utf-8"), "crises.csv", "text/csv",
                       width="stretch")

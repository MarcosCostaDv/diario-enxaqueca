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

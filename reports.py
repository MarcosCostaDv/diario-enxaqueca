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


def _visao_geral(ids: list[str], hoje: pd.Timestamp) -> None:
    linhas, pontos = [], []
    for uid in ids:
        dia, cri = db.df_diario(uid), db.df_crises(uid)
        if dia.empty and cri.empty:
            linhas.append({"Paciente": uid, "Dias acompanhados": 0})
            continue
        inicio = min([x for x in (dia["data_referencia"].min() if len(dia) else None,
                                  cri["inicio_local"].min().normalize() if len(cri) else None) if x is not None])
        n = (hoje - inicio).days + 1
        ultimo = max([x for x in (dia["data_referencia"].max() if len(dia) else None,
                                  cri["inicio_local"].max().normalize() if len(cri) else None) if x is not None])
        linhas.append({
            "Paciente": uid,
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
            pontos.append({"Paciente": uid, "inicio": c["inicio_local"], "Começou com": c["inicio_tipo"]})

    # pacientes nas colunas, indicadores nas linhas: cabe na tela do celular
    tabela = pd.DataFrame(linhas).set_index("Paciente").T.astype(str).replace({"nan": "—"})
    st.dataframe(tabela, width="stretch", height=36 * (len(tabela) + 1) + 3)  # sem rolagem interna
    st.caption("\"Dias sem registro\" alto indica que a pessoa pode ter parado de preencher.")

    if pontos:
        st.markdown("**Crises ao longo do tempo**")
        st.altair_chart(alt.Chart(pd.DataFrame(pontos)).mark_point(filled=True, size=90).encode(
            x=alt.X("inicio:T", title=None),
            y=alt.Y("Paciente:N", title=None),
            color=alt.Color("Começou com:N", scale=alt.Scale(domain=["aura", "dor"], range=[AZUL, LARANJA]),
                            legend=alt.Legend(orient="top", title=None)),
            shape=alt.Shape("Começou com:N", scale=alt.Scale(domain=["aura", "dor"], range=["circle", "triangle"]),
                            legend=None),
            tooltip=[alt.Tooltip("Paciente:N"), alt.Tooltip("inicio:T", title="Início", format="%d/%m %H:%M"),
                     alt.Tooltip("Começou com:N")],
        ).properties(height=80 + 60 * len(ids)), width="stretch")


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
        "n_vesp": len(vesp),
        "vesp_algum": vesp.any(axis=1).mean() if len(vesp) else None,
        "n_comuns": len(comuns),
        "comuns_algum": comuns.any(axis=1).mean() if len(comuns) else None,
        "top": [(db.PREMONITORIOS[c.removeprefix("prem_")], v) for c, v in top.head(3).items() if v > 0],
    }


def _literatura(ids: list[str]) -> None:
    import referencias as ref
    F = ref.FONTES
    st.caption("Cada paciente ao lado de dados publicados. Os métodos são diferentes (diário deste app × "
               "estudos com outras populações), então a comparação é qualitativa: serve para ver se os "
               "registros estão coerentes com o que se conhece, não para classificar ninguém.")

    def pct(v):
        return "—" if v is None or pd.isna(v) else f"{v:.0%}"

    dados = {uid: (db.df_diario(uid), db.df_crises(uid)) for uid in ids}
    tabela = {"Indicador": [], **{uid: [] for uid in ids}, "Literatura": [], "Fonte": []}

    def linha(indicador, valores, literatura, fonte):
        tabela["Indicador"].append(indicador)
        for uid in ids:
            tabela[uid].append(valores.get(uid, "—"))
        tabela["Literatura"].append(literatura)
        tabela["Fonte"].append(fonte)

    aura_med, aura_60, n_aura = {}, {}, {}
    seqs, prem_v, prem_c, prem_top = {}, {}, {}, {}
    for uid, (dia, cri) in dados.items():
        dur = cri.loc[cri["teve_aura"] == True, "aura_duracao_min"].dropna()  # noqa: E712
        n_aura[uid] = f"{len(dur)}"
        aura_med[uid] = _fmt(_mediana(dur.clip(upper=61)), " min") if len(dur) else "—"
        aura_60[uid] = pct((dur > 60).mean()) if len(dur) else "—"
        seqs[uid] = _sequencia_aura_dor(cri)
        p = _premonitorios_vespera(dia, cri) if len(dia) else {}
        prem_v[uid] = f"{pct(p.get('vesp_algum'))} (n={p.get('n_vesp', 0)})" if p else "—"
        prem_c[uid] = f"{pct(p.get('comuns_algum'))} (n={p.get('n_comuns', 0)})" if p else "—"
        prem_top[uid] = ", ".join(f"{s} {v:.0%}" for s, v in p.get("top", [])) or "—"

    linha("Auras com duração registrada", n_aura, "72 pacientes, 216 auras", "Viana")
    linha("Duração da aura (mediana)", aura_med,
          f"{ref.VIANA_AURA_MEDIANA_MIN} min (IQR {ref.VIANA_AURA_IQR})", "Viana")
    linha("Auras acima de 60 min", aura_60,
          f"{ref.VIANA_SINTOMAS_ACIMA_60:.0%} dos sintomas de aura", "Viana")
    for cat, v in ref.VIANA_SEQUENCIA.items():
        vals = {uid: (pct((s == cat).mean()) + f" ({(s == cat).sum()}/{len(s)})" if len(s) else "—")
                for uid, s in seqs.items()}
        linha(f"Sequência: {cat}", vals, f"{v:.0%} das auras", "Viana")
    linha("Crises com ≥1 sintoma premonitório na noite anterior", prem_v,
          f"{ref.LAURELL_COM_PREMONITORIO:.0%} das pessoas relatam ter", "Laurell")
    linha("Dias comuns com ≥1 sintoma premonitório", prem_c,
          "sem dado comparável publicado", "—")
    linha("Sintomas mais frequentes na véspera", prem_top,
          f"bocejos {ref.LAURELL_BOCEJO:.0%}; humor e cansaço ~1/3 cada", "Laurell")

    st.dataframe(pd.DataFrame(tabela), hide_index=True, width="stretch",
                 height=36 * (len(tabela["Indicador"]) + 1) + 3)
    st.caption("A linha \"dias comuns\" é essencial: se os sintomas aparecem tanto na véspera quanto em dias "
               "comuns, eles não antecipam a crise. Com poucas crises, qualquer porcentagem ainda é instável.")

    with st.container(border=True):
        st.markdown("**Contexto (não comparável diretamente)**")
        pv = ref.QUEIROZ_PREVALENCIA
        st.markdown(
            f"- Prevalência de enxaqueca no Brasil: {pv['geral']:.1%} (mulheres {pv['mulheres']:.1%}, "
            f"homens {pv['homens']:.1%}) · [Queiroz et al., 2009]({F['queiroz']['link']})\n"
            f"- Melhor previsão publicada com diário + wearable que encontramos: AUC {ref.STUBBERUD_AUC} "
            f"(18 pacientes; não acertou nenhuma crise no teste) · [Stubberud et al., 2023]({F['stubberud']['link']})")

    st.markdown("**Fontes**")
    nomes = {"viana": "Viana", "laurell": "Laurell", "queiroz": "Queiroz", "stubberud": "Stubberud", "ichd3": "ICHD-3"}
    for chave, f in F.items():
        with st.container(border=True):
            st.markdown(f"**{nomes[chave]}** · [{f['citacao']}]({f['link']})  \n"
                        f"Tipo: {f['tipo']}  \nLimitação: {f['limitacao']}")


def render_pesquisa(ids: list[str], fuso: str) -> None:
    """Área do pesquisador: visão geral, histórico de cada paciente e comparação com a literatura."""
    st.caption("Pacientes identificados só pelo código. Cada pessoa é analisada separadamente (N=1).")
    hoje = pd.Timestamp(db.local_agora(fuso).date())
    aba1, aba2, aba3 = st.tabs(["Visão geral", "Histórico por paciente", "Literatura"])
    with aba1:
        _visao_geral(ids, hoje)
    with aba2:
        if ids:
            uid = st.selectbox("Paciente", ids, key="pesq_paciente")
            render(uid, fuso, titulo=f"Paciente {uid}", chave=f"pesq_{uid}")
    with aba3:
        _literatura(ids)


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


def render(id_usuario: str, fuso: str, titulo: str = "Relatórios", chave: str = "") -> None:
    st.subheader(titulo)
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
    c1.download_button("diario.csv", dia.to_csv(index=False).encode("utf-8"), f"diario_{id_usuario}.csv",
                       "text/csv", width="stretch", key=f"{chave}dl_diario")
    c2.download_button("crises.csv", cri.to_csv(index=False).encode("utf-8"), f"crises_{id_usuario}.csv",
                       "text/csv", width="stretch", key=f"{chave}dl_crises")

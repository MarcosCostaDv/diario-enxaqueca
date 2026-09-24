"""Diário de enxaqueca (com ou sem aura) — app de coleta (Streamlit, pensado para celular).

Navegação:
  Início  -> botão de início de crise (aura ou dor) + o que falta preencher hoje
  Manhã   -> sono da última noite
  Noite   -> como foi o dia
  Crise   -> completar detalhes de uma crise registrada
  Relatórios

Rodar localmente:   python -m streamlit run app.py
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
DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

INTRO_CURTA = (
    "Um diário para investigar uma pergunta: **o corpo dá sinais, horas antes, "
    "de que uma crise de enxaqueca está chegando?**"
)

INTRO = """
Muitas pessoas percebem sinais antes de uma crise, como cansaço, bocejos, rigidez no pescoço
ou mudanças de humor. Este diário registra esses sinais, junto com sono, estresse e hábitos,
para descobrir se algum padrão se repete antes das crises. Mais adiante, a ideia é incluir
dados de relógio ou pulseira, como frequência cardíaca e sono.

**Como funciona**
- **Manhã (~30 s):** como foi o sono.
- **Noite (~1 min):** sintomas, estresse, humor e hábitos do dia.
- **Quando uma crise começar:** um toque em *Começou com aura* ou *Começou com dor*.
- **Depois que a crise passar:** completar os detalhes.

Os dias **sem** crise são tão importantes quanto os dias com crise: é comparando os dois
que dá para ver se algo muda.

**O que isto não é:** não é diagnóstico nem tratamento e não substitui acompanhamento médico.
É uma investigação, e pode não encontrar padrão nenhum, o que também é um resultado.

**Seus dados:** ficam guardados com um código, sem o seu nome. Você pode parar quando quiser
e pedir a exclusão de tudo.
"""

# CSS mínimo: menos espaço no topo e títulos de seção discretos (tela de celular)
st.markdown("""
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem;}
h3 {margin-bottom: 0 !important;}
/* botões de início de crise em vermelho: é a ação mais urgente e não pode se confundir com as outras */
.st-key-aura button[kind="primary"] {background:#d63a3a; border-color:#d63a3a; font-weight:700;}
.st-key-aura button[kind="primary"]:hover {background:#b82f2f; border-color:#b82f2f;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------- acesso


def contas() -> dict[str, dict]:
    """Contas de acesso. Vários usuários: tabela [USUARIOS] no secrets.toml
    (login -> {senha, id}). Sem ela, modo de um usuário só (APP_PASSWORD + USER_ID)."""
    tabela = cfg("USUARIOS")
    if tabela:
        return {str(login).lower(): {"senha": str(v["senha"]), "id": str(v["id"]),
                                     "pesquisador": bool(dict(v).get("pesquisador", False))}
                for login, v in dict(tabela).items()}
    if cfg("APP_PASSWORD"):
        return {"": {"senha": str(cfg("APP_PASSWORD")), "id": str(cfg("USER_ID", "usuario-local"))}}
    return {}


def autenticar() -> str:
    """Devolve o id pseudônimo de quem entrou. Cada pessoa só enxerga os próprios dados."""
    if uid := st.session_state.get("id_usuario"):
        return uid
    todas = contas()
    if not todas:
        st.warning("Nenhuma senha configurada: app sem proteção. Só use assim no seu computador.")
        return str(cfg("USER_ID", "usuario-local"))

    st.markdown("### 🧠 Diário de enxaqueca")
    st.markdown(INTRO_CURTA)
    with st.expander("Sobre o projeto"):
        st.markdown(INTRO)
    multiusuario = "" not in todas
    with st.form("login"):
        login = st.text_input("Usuário").strip().lower() if multiusuario else ""
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", type="primary", width="stretch")
    if entrar:
        conta = todas.get(login)
        # compara mesmo quando o usuário não existe, para não revelar quais logins existem
        ok = hmac.compare_digest(senha, conta["senha"] if conta else "\0" * 16) and conta is not None
        if ok:
            st.session_state["id_usuario"] = conta["id"]
            st.session_state["pesquisador"] = conta.get("pesquisador", False)
            st.rerun()
        st.error("Usuário ou senha incorretos.")
    st.stop()


def sair() -> None:
    for chave in list(st.session_state.keys()):
        del st.session_state[chave]


USUARIO = db.garantir_usuario(autenticar(), cfg("FUSO", db.FUSO_PADRAO))
FUSO = db.fuso_do_usuario(USUARIO)
AGORA = db.local_agora(FUSO)

# ---------------------------------------------------------------- navegação


def ir(tela: str, data_ref: date | None = None, id_crise: str | None = None) -> None:
    """Callback de botão: troca de tela (e opcionalmente o dia/crise que ela vai abrir)."""
    st.session_state["tela"] = tela
    st.session_state["data_ref"] = data_ref
    st.session_state["id_crise"] = id_crise


def concluir(mensagem: str) -> None:
    """Depois de salvar: volta ao Início mostrando a confirmação."""
    st.session_state["aviso"] = mensagem
    ir("inicio")
    st.rerun()


def cabecalho(titulo: str, subtitulo: str) -> None:
    st.button("← Início", on_click=ir, args=("inicio",), type="tertiary")
    st.markdown(f"## {titulo}")
    st.caption(subtitulo)


def secao(numero: int, titulo: str):
    """Bloco numerado com borda: deixa claro em que parte do formulário você está."""
    caixa = st.container(border=True)
    caixa.markdown(f"**{numero}. {titulo}**")
    return caixa


def rotulo_dia(d: date) -> str:
    if d == AGORA.date():
        return f"hoje ({d:%d/%m})"
    if d == AGORA.date() - timedelta(days=1):
        return f"ontem ({d:%d/%m})"
    return f"{DIAS_SEMANA[d.weekday()]} {d:%d/%m}"


# ---------------------------------------------------------------- utilidades de formulário


def hhmm_para_time(v: str | None, padrao: time) -> time:
    if not v:
        return padrao
    h, m = map(int, v.split(":"))
    return time(h, m)


def time_para_hhmm(t: time | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def escolha(onde, rotulo: str, opcoes: list, atual, key: str):
    """Botões de toque único com valor pré-selecionado (se já houver)."""
    return onde.segmented_control(rotulo, opcoes, default=atual if atual in opcoes else None, key=key)


def escala(onde, rotulo: str, minimo: int, maximo: int, atual, key: str):
    """Escala numérica em botões, SEM valor padrão: um slider sempre tem valor
    e acabaria gravando um 0 que você não marcou."""
    return onde.segmented_control(rotulo, list(range(minimo, maximo + 1)), default=atual, key=key)


# ================================================================ TELAS


def tela_inicio() -> None:
    st.markdown(f"### 🧠 Diário · {DIAS_SEMANA[AGORA.weekday()]} {AGORA:%d/%m}")
    primeiro_uso = db.primeiro_dia(USUARIO) is None and not db.crises_incompletas(USUARIO) \
        and db.df_crises(USUARIO).empty

    if aviso := st.session_state.pop("aviso", None):
        st.success(aviso)

    # --- 1. Início de crise: sempre no topo, registro em um toque.
    # Genérico: vale para quem tem crise com aura, sem aura, ou os dois tipos.
    with st.container(border=True, key="aura"):
        st.markdown("**⚡ Começou uma crise?**")
        st.caption("Registre o primeiro sinal, na hora. Os detalhes ficam para depois.")
        quando = st.segmented_control(
            "Quando começou", ["Agora", "~15 min", "~30 min", "~1 h"], default="Agora",
            key="crise_quando", label_visibility="collapsed")
        minutos, precisao = {"Agora": (0, "exato"), "~15 min": (15, "±15 min"),
                             "~30 min": (30, "±15 min"), "~1 h": (60, "±1 h")}[quando or "Agora"]

        recente = db.crise_recente(USUARIO)
        liberado = True
        if recente:
            hora = db.utc_para_local(recente["inicio_utc"], recente["fuso"]).strftime("%H:%M")
            st.caption(f"Já existe uma crise registrada às {hora}. Se ela ainda está acontecendo, "
                       "não precisa registrar de novo.")
            liberado = st.checkbox("É uma nova crise", key="crise_confirma")

        c1, c2 = st.columns(2)
        tipo = None
        if c1.button("COMEÇOU COM AURA", type="primary", width="stretch", disabled=not liberado,
                     help="Sintomas visuais, formigamento ou fala alterada antes da dor"):
            tipo = "aura"
        if c2.button("COMEÇOU COM DOR", type="primary", width="stretch", disabled=not liberado,
                     help="A dor veio primeiro, sem aura antes"):
            tipo = "dor"
        if tipo:
            inicio = db.local_agora(FUSO) - timedelta(minutes=minutos)
            db.registrar_crise(USUARIO, inicio, precisao, FUSO, tipo)
            st.session_state["aviso"] = (f"Crise registrada: {tipo} às {inicio:%H:%M}. "
                                         "Quando passar, complete os detalhes abaixo.")
            st.session_state.pop("crise_confirma", None)
            st.rerun()

    # Boas-vindas no primeiro uso: abaixo do bloco de crise, que continua sendo o primeiro da tela
    if primeiro_uso:
        with st.container(border=True):
            st.markdown("**👋 Bem-vindo(a)**  \n" + INTRO_CURTA)
            st.markdown(INTRO)

    # --- 2. O que falta hoje
    st.markdown("**📋 Para preencher**")
    hoje = AGORA.date()
    dia_noite = db.data_padrao_noite(AGORA)
    reg_hoje = db.ler_dia(USUARIO, hoje) or {}
    reg_noite = db.ler_dia(USUARIO, dia_noite) or {}
    pendencias = 0

    def cartao(icone, titulo, descricao, feito, tela, data_ref=None, id_crise=None, botao="Preencher",
               destaque=False):
        with st.container(border=True):
            c1, c2 = st.columns([3, 2], vertical_alignment="center")
            status = "✅" if feito else "⏳"
            c1.markdown(f"{status} **{icone} {titulo}**  \n{descricao}")
            c2.button("Editar" if feito else botao, key=f"btn_{tela}_{data_ref}_{id_crise}",
                      on_click=ir, args=(tela, data_ref, id_crise), width="stretch",
                      type="primary" if destaque else "secondary")

    # Crises a completar (prioridade: aparecem primeiro)
    for c in db.crises_incompletas(USUARIO):
        ini = db.utc_para_local(c["inicio_utc"], c["fuso"])
        cartao("📝", "Completar crise", f"começou com {c['inicio_tipo']} · {rotulo_dia(ini.date())} às {ini:%H:%M}",
               False, "crise", id_crise=c["id_crise"], botao="Completar", destaque=True)
        pendencias += 1

    manha_ok = bool(reg_hoje.get("preenchido_manha_em_utc"))
    cartao("🌅", "Manhã", "sono da última noite · ~30 s", manha_ok, "manha", hoje)
    pendencias += not manha_ok

    noite_ok = bool(reg_noite.get("preenchido_noite_em_utc"))
    desc_noite = "como foi o dia · ~1 min"
    if not noite_ok and dia_noite == hoje and AGORA.hour < 18:
        desc_noite += " · melhor preencher à noite"
    cartao("🌙", "Noite", desc_noite, noite_ok, "noite", dia_noite)
    pendencias += not noite_ok

    # Noite de ontem esquecida (só se hoje ainda for "hoje" para a noite)
    ontem = hoje - timedelta(days=1)
    primeiro = db.primeiro_dia(USUARIO)
    if dia_noite == hoje and primeiro is not None and primeiro <= ontem:
        if not (db.ler_dia(USUARIO, ontem) or {}).get("preenchido_noite_em_utc"):
            cartao("🌙", "Noite de ontem", "ficou sem registro · ficará marcada como retroativa",
                   False, "noite", ontem)

    if pendencias == 0:
        st.caption("Tudo em dia por hoje.")

    st.divider()
    if not primeiro_uso:
        with st.expander("ℹ️ Sobre o projeto"):
            st.markdown(INTRO_CURTA + "\n" + INTRO)
    st.button("📊 Relatórios", on_click=ir, args=("relatorios",), width="stretch")
    if st.session_state.get("pesquisador"):
        st.button("🔬 Pesquisa (participantes)", on_click=ir, args=("pesquisa",), width="stretch")
    if len(contas()) > 1:
        st.button("Sair", on_click=sair, type="tertiary")


def tela_manha() -> None:
    d = st.session_state.get("data_ref") or AGORA.date()
    cabecalho("🌅 Manhã", f"Sono da noite que terminou em {rotulo_dia(d)}. Toque nas opções e salve.")
    atual = db.ler_dia(USUARIO, d) or {}
    k = f"m_{d}_"
    if atual.get("preenchido_manha_em_utc"):
        st.info("Este dia já foi preenchido. Salvar de novo substitui os valores.")

    s1 = secao(1, "Horários")
    c1, c2 = s1.columns(2)
    deitou = c1.time_input("Deitou", hhmm_para_time(atual.get("sono_deitou"), time(23, 0)), step=900, key=k + "deitou")
    acordou = c2.time_input("Acordou", hhmm_para_time(atual.get("sono_acordou"), time(7, 0)), step=900, key=k + "acordou")

    s2 = secao(2, "Como foi o sono")
    desp = escolha(s2, "Quantas vezes acordou durante a noite?", ["0", "1", "2", "3+"],
                   {0: "0", 1: "1", 2: "2", 3: "3+"}.get(atual.get("sono_despertares")), k + "desp")
    qual = escolha(s2, "Qualidade (1 péssima · 5 excelente)", [1, 2, 3, 4, 5], atual.get("sono_qualidade"), k + "qual")
    motivos = None
    if qual in (1, 2):
        ja = [db.SONO_MOTIVOS[m] for m in (atual.get("sono_motivos") or "").split(",") if m in db.SONO_MOTIVOS]
        motivos = s2.pills("O que atrapalhou o sono? (pode marcar mais de um)", list(db.SONO_MOTIVOS.values()),
                           selection_mode="multi", default=ja, key=k + "motivos")
    sint = s2.toggle("Acordei já com algum sintoma", value=bool(atual.get("acordou_com_sintoma")), key=k + "sint")

    if st.button("Salvar manhã", type="primary", width="stretch"):
        faltando = [n for n, v in [("despertares", desp), ("qualidade", qual)] if v is None]
        if qual in (1, 2) and not motivos:
            faltando.append("o que atrapalhou o sono (ou \"não sei\")")
        if faltando:
            st.error("Falta marcar: " + ", ".join(faltando) + ".")
            return
        db.salvar_parte_do_dia(USUARIO, d, {
            "fuso": FUSO,
            "preenchido_manha_em_utc": db.utc_agora(),
            "retroativo_manha": db.retroativo_manha(d, db.local_agora(FUSO)),
            "sono_deitou": time_para_hhmm(deitou),
            "sono_acordou": time_para_hhmm(acordou),
            "sono_despertares": {"0": 0, "1": 1, "2": 2, "3+": 3}[desp],
            "sono_qualidade": qual,
            # só existe para noites ruins; noites boas ficam NULL ("não perguntado")
            "sono_motivos": ",".join(ch for ch, r in db.SONO_MOTIVOS.items() if r in (motivos or [])) or None,
            "acordou_com_sintoma": sint,
        })
        concluir("Manhã salva.")


def tela_noite() -> None:
    d = st.session_state.get("data_ref") or db.data_padrao_noite(AGORA)
    cabecalho("🌙 Noite", f"Como foi {rotulo_dia(d)}. São 5 blocos; o 6º é opcional.")
    atual = db.ler_dia(USUARIO, d) or {}
    k = f"n_{d}_"
    if atual.get("preenchido_noite_em_utc"):
        st.info("Este dia já foi preenchido. Salvar de novo substitui os valores.")

    # --- 1. Crise no dia: resposta explícita (ausência de registro não é "sem crise")
    s0 = secao(1, "Crise")
    do_dia = db.crises_do_dia(USUARIO, d, FUSO)
    if do_dia:
        s0.caption("Registrada: " + "; ".join(
            f"começou com {c['inicio_tipo']} às {db.utc_para_local(c['inicio_utc'], c['fuso']):%H:%M}" for c in do_dia))
    padrao_crise = "sim" if do_dia else {True: "sim", False: "não"}.get(atual.get("teve_crise"))
    teve = s0.segmented_control(f"Teve crise {rotulo_dia(d).split(' (')[0]}?", ["não", "sim"],
                                default=padrao_crise, key=k + "tevecrise")
    retro_tipo = retro_hora = retro_prec = None
    if teve == "sim" and not do_dia:
        s0.caption("Ela não foi registrada na hora. Registre agora com o horário aproximado; "
                   "depois complete os detalhes no Início.")
        retro_tipo = s0.segmented_control("Começou com", ["aura", "dor"], key=k + "rtipo")
        c1, c2 = s0.columns(2)
        retro_hora = c1.time_input("Por volta de", time(12, 0), step=900, key=k + "rhora")
        retro_prec = c2.segmented_control("Precisão", ["±15 min", "±1 h", "não lembro"], key=k + "rprec")

    s1 = secao(2, "Sintomas fora do seu normal")
    marcados = [rot for chave, rot in db.PREMONITORIOS.items() if atual.get(f"prem_{chave}")]
    prem = s1.pills("Marque os que sentiu (ou nenhum)", list(db.PREMONITORIOS.values()),
                    selection_mode="multi", default=marcados, key=k + "prem")

    s2 = secao(3, "Como você está")
    prev = escala(s2, "Sinto que vem uma crise (0 nada · 10 certeza)", 0, 10, atual.get("previsao_subjetiva"), k + "prev")
    estr = escala(s2, "Estresse (0 nenhum · 10 máximo)", 0, 10, atual.get("estresse"), k + "estr")
    humor = escolha(s2, "Humor (1 muito ruim · 5 muito bom)", [1, 2, 3, 4, 5], atual.get("humor"), k + "humor")

    s3 = secao(4, "Hábitos do dia")
    caf_at = None if atual.get("cafeina_doses") is None else ("4+" if atual["cafeina_doses"] >= 4 else str(atual["cafeina_doses"]))
    caf = escolha(s3, "Cafeína (doses)", ["0", "1", "2", "3", "4+"], caf_at, k + "caf")
    caf_h = None
    if caf and caf != "0":
        caf_h = s3.time_input("Hora da última dose", hhmm_para_time(atual.get("cafeina_ultima"), time(15, 0)),
                              step=1800, key=k + "cafh")
    alc_at = None if atual.get("alcool_doses") is None else ("3+" if atual["alcool_doses"] >= 3 else str(atual["alcool_doses"]))
    alc = escolha(s3, "Álcool (doses)", ["0", "1", "2", "3+"], alc_at, k + "alc")
    ex = escolha(s3, "Exercício", ["nenhum", "leve", "intenso"], atual.get("exercicio_nivel"), k + "ex")
    ex_min = None
    if ex and ex != "nenhum":
        ex_min = escolha(s3, "Duração (min)", [15, 30, 45, 60, 90], atual.get("exercicio_min"), k + "exmin")
    pulou = s3.toggle("Pulei alguma refeição", value=bool(atual.get("pulou_refeicao")), key=k + "ref")
    rot_tela = {f: f.replace("-", "–") + " h" for f in db.TELA_FAIXAS}
    tela = s3.segmented_control("Tempo de tela no dia (computador, celular, TV, videogame)", db.TELA_FAIXAS,
                                format_func=rot_tela.get, default=atual.get("tela_horas"), key=k + "tela")
    tela_fin = escolha(s3, "Tela principalmente para", db.TELA_FINALIDADES, atual.get("tela_finalidade"), k + "telafin")

    s4 = secao(5, "Outras dores e remédios")
    outra = escala(s4, "Dor de cabeça que NÃO foi enxaqueca (0 = nenhuma)", 0, 10, atual.get("outra_cefaleia"), k + "outra")
    analg = s4.pills("Remédio para dor tomado sem crise (se tomou)", MEDICACOES, selection_mode="multi",
                     default=[m for m in (atual.get("analgesico_sem_crise") or "").split(",") if m in MEDICACOES],
                     key=k + "analg")

    s5 = secao(6, "Observação (opcional)")
    atip = s5.text_input("Viagem, doença, evento marcante...", value=atual.get("dia_atipico") or "",
                         key=k + "atip", label_visibility="collapsed", placeholder="Viagem, doença, evento marcante...")

    if st.button("Salvar noite", type="primary", width="stretch"):
        faltando = [n for n, v in [("previsão de crise", prev), ("estresse", estr), ("humor", humor),
                                   ("cafeína", caf), ("álcool", alc), ("exercício", ex),
                                   ("tempo de tela", tela), ("finalidade da tela", tela_fin),
                                   ("outra dor de cabeça", outra)] if v is None]
        if ex and ex != "nenhum" and ex_min is None:
            faltando.append("duração do exercício")
        if teve is None:
            faltando.insert(0, "se teve crise")
        elif teve == "não" and do_dia:
            faltando.insert(0, "há crise registrada neste dia: marque \"sim\"")
        elif teve == "sim" and not do_dia:
            if retro_tipo is None:
                faltando.insert(0, "como a crise começou")
            if retro_prec is None:
                faltando.insert(0, "precisão do horário da crise")
            elif datetime.combine(d, retro_hora) > db.local_agora(FUSO):
                faltando.insert(0, "horário da crise no futuro")
        if faltando:
            st.error("Falta marcar: " + ", ".join(faltando) + ".")
            return
        valores = {f"prem_{c}": (r in (prem or [])) for c, r in db.PREMONITORIOS.items()}
        valores.update({
            "fuso": FUSO,
            "preenchido_noite_em_utc": db.utc_agora(),
            "retroativo_noite": db.retroativo_noite(d, db.local_agora(FUSO)),
            "previsao_subjetiva": prev, "estresse": estr, "humor": humor,
            "cafeina_doses": 4 if caf == "4+" else int(caf),
            "cafeina_ultima": time_para_hhmm(caf_h),
            "alcool_doses": 3 if alc == "3+" else int(alc),
            "pulou_refeicao": pulou,
            "tela_horas": tela,
            "tela_finalidade": tela_fin,
            "exercicio_nivel": ex,
            "exercicio_min": ex_min if ex != "nenhum" else 0,
            "outra_cefaleia": outra,
            "analgesico_sem_crise": ",".join(analg) if analg else None,
            "dia_atipico": atip or None,
        })
        valores["teve_crise"] = teve == "sim"
        db.salvar_parte_do_dia(USUARIO, d, valores)
        if teve == "sim" and not do_dia:
            db.registrar_crise(USUARIO, datetime.combine(d, retro_hora), retro_prec, FUSO, retro_tipo,
                               retroativo=True)
            concluir("Noite salva e crise registrada. Complete os detalhes da crise no cartão abaixo.")
        concluir("Noite salva.")


def tela_crise() -> None:
    pendentes = {c["id_crise"]: c for c in db.crises_incompletas(USUARIO)}
    id_sel = st.session_state.get("id_crise")
    if id_sel not in pendentes:
        id_sel = next(iter(pendentes), None)
    if id_sel is None:
        cabecalho("📝 Crise", "Nenhuma crise para completar.")
        return

    crise = pendentes[id_sel]
    f = crise["fuso"]
    inicio = db.utc_para_local(crise["inicio_utc"], f)
    comecou_aura = crise["inicio_tipo"] == "aura"
    cabecalho("📝 Completar crise",
              f"Começou com {crise['inicio_tipo']} · {rotulo_dia(inicio.date())} às {inicio:%H:%M}. "
              "Preencha depois que a crise passar.")
    k = f"c_{id_sel}_"

    s1 = secao(1, "Início")
    prec = escolha(s1, "O horário registrado é", ["exato", "±15 min", "±1 h", "não lembro"],
                   crise["inicio_precisao"], k + "prec")
    if crise.get("registro_retroativo"):
        s1.caption("Registrada depois, pela pergunta da noite.")

    # --- Aura: obrigatória se começou com aura; pergunta se começou com dor
    s2 = secao(2, "Aura")
    if comecou_aura:
        teve_aura = True
    else:
        teve_aura = s2.segmented_control("Teve aura em algum momento desta crise?", ["não", "sim"],
                                         key=k + "teveaura")
        teve_aura = None if teve_aura is None else teve_aura == "sim"
    tipos = dur = None
    if teve_aura:
        tipos = s2.pills("Tipo", ["visual", "sensitiva", "fala", "outra"], selection_mode="multi",
                         default=["visual"], key=k + "tipo")
        dur = escolha(s2, "Duração (min)", [5, 10, 15, 20, 30, 45, 60, "mais de 60"], None, k + "dur")
        if dur == "mais de 60":
            s2.warning("Aura acima de 60 minutos foge do padrão típico. Vale comentar com seu médico.")

    # --- Dor: se começou com dor, o início já é conhecido
    s3 = secao(3, "Dor")
    sem_dor = False
    dor_ini = dor_max = lado = None
    if comecou_aura:
        sem_dor = s3.toggle("Não houve dor depois da aura", key=k + "semdor")
        if not sem_dor:
            c1, c2 = s3.columns(2)
            dor_d = c1.date_input("Dor começou (dia)", inicio.date(), format="DD/MM/YYYY", key=k + "dord")
            dor_t = c2.time_input("Hora", (inicio + timedelta(minutes=30)).time(), step=900, key=k + "dort")
            dor_ini = datetime.combine(dor_d, dor_t)
    else:
        dor_ini = inicio
    if not sem_dor:
        dor_max = escala(s3, "Intensidade máxima (0 a 10)", 0, 10, None, k + "dormax")
        lado = escolha(s3, "Lado", ["direito", "esquerdo", "ambos", "alternou"], None, k + "lado")
    nausea = escolha(s3, "Náusea", ["nenhum", "náusea", "vômito"], None, k + "nau")

    s4 = secao(4, "Remédio")
    meds = s4.pills("O que tomou para a crise (se tomou)", MEDICACOES, selection_mode="multi", key=k + "med")
    med_h = s4.time_input("Hora", (inicio + timedelta(minutes=30)).time(), step=900, key=k + "medh") if meds else None

    s5 = secao(5, "Fim da crise")
    c1, c2 = s5.columns(2)
    fim_d = c1.date_input("Dia", inicio.date(), format="DD/MM/YYYY", key=k + "fimd")
    fim_t = c2.time_input("Hora", (inicio + timedelta(hours=6)).time(), step=900, key=k + "fimt")

    s6 = secao(6, "Notas (opcional)")
    retro = s6.text_area("Sintomas que você lembra das 48 h anteriores", key=k + "retro")
    gat = s6.text_input("Gatilho que você suspeita (hipótese, não causa)", key=k + "gat")

    if st.button("Salvar crise", type="primary", width="stretch"):
        fim = datetime.combine(fim_d, fim_t)
        erros = []
        if teve_aura is None:
            erros.append("se teve aura")
        if teve_aura and dur is None:
            erros.append("duração da aura")
        if not sem_dor and (dor_max is None or lado is None):
            erros.append("intensidade e lado da dor")
        if dor_ini is not None and dor_ini < inicio:
            erros.append("a dor não pode começar antes do início registrado")
        if nausea is None:
            erros.append("náusea")
        if fim <= inicio:
            erros.append("o fim precisa ser depois do início")
        if erros:
            st.error("Falta: " + "; ".join(erros) + ".")
            return
        db.completar_crise(USUARIO, id_sel, {
            "inicio_precisao": prec,
            "teve_aura": teve_aura,
            "aura_tipo": ",".join(tipos or []) if teve_aura else None,
            "aura_duracao_min": (61 if dur == "mais de 60" else dur) if teve_aura else None,  # 61 = ">60"
            "sem_dor": sem_dor,
            "dor_inicio_utc": db.local_para_utc(dor_ini, f) if dor_ini else None,
            "dor_max": dor_max,
            "dor_lado": lado,
            "nausea": nausea,
            "medicacao": ",".join(meds) if meds else None,
            "medicacao_hora": time_para_hhmm(med_h),
            "crise_fim_utc": db.local_para_utc(fim, f),
            "sintomas_48h_retro": retro or None,
            "gatilho_suspeito": gat or None,
        })
        concluir("Crise completa.")


def tela_relatorios() -> None:
    st.button("← Início", on_click=ir, args=("inicio",), type="tertiary")
    reports.render(USUARIO, FUSO)


def tela_pesquisa() -> None:
    st.button("← Início", on_click=ir, args=("inicio",), type="tertiary")
    if not st.session_state.get("pesquisador"):
        st.error("Acesso restrito ao pesquisador.")
        return
    ids = sorted({c["id"] for c in contas().values()} | set(db.listar_usuarios()))
    reports.render_pesquisa(ids, FUSO)


# ---------------------------------------------------------------- roteador

TELAS = {"inicio": tela_inicio, "manha": tela_manha, "noite": tela_noite,
         "crise": tela_crise, "relatorios": tela_relatorios, "pesquisa": tela_pesquisa}
TELAS.get(st.session_state.get("tela", "inicio"), tela_inicio)()

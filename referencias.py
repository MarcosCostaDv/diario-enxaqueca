"""Referências da literatura usadas na área do pesquisador.

Regra: só entram números conferidos na fonte original (resumo do artigo lido),
com o tipo de estudo e a principal limitação. Nada aqui é "valor normal"
de uma pessoa: são dados de grupos, com métodos diferentes dos deste diário.
"""

FONTES = {
    "ichd3": {
        "citacao": "Headache Classification Committee of the IHS. ICHD-3. Cephalalgia, 2018",
        "link": "https://doi.org/10.1177/0333102417738202",
        "tipo": "Critério diagnóstico internacional (consenso)",
        "limitacao": "Define critérios clínicos; não descreve distribuições de uma população.",
    },
    "viana": {
        "citacao": "Viana M et al. Cephalalgia (online 2016)",
        "link": "https://doi.org/10.1177/0333102416657147",
        "tipo": "Estudo prospectivo com diário; 72 pacientes, 216 auras",
        "limitacao": "Centro terciário na Itália (casos possivelmente mais graves); "
                     "durações contadas por sintoma de aura, não por crise.",
    },
    "laurell": {
        "citacao": "Laurell K et al. Premonitory symptoms in migraine: a cross-sectional study "
                   "in 2714 persons. Cephalalgia, 2016",
        "link": "https://doi.org/10.1177/0333102415620251",
        "tipo": "Estudo transversal; 2223 pessoas com enxaqueca",
        "limitacao": "Autorrelato retrospectivo, por pessoa (\"você costuma ter...\"), "
                     "não por crise registrada no momento.",
    },
    "queiroz": {
        "citacao": "Queiroz LP et al. A nationwide population-based study of migraine in Brazil. "
                   "Cephalalgia, 2009",
        "link": "https://doi.org/10.1111/j.1468-2982.2008.01782.x",
        "tipo": "Estudo populacional nacional; 3848 participantes",
        "limitacao": "Prevalência de enxaqueca na população; não descreve as crises individuais.",
    },
    "stubberud": {
        "citacao": "Stubberud A et al. Forecasting migraine with machine learning based on mobile "
                   "phone diary and wearable data. Cephalalgia, 2023",
        "link": "https://doi.org/10.1177/03331024231169244",
        "tipo": "Estudo prospectivo exploratório; 18 pacientes, ~1 mês",
        "limitacao": "Amostra pequena, pouco tempo de coleta, modelo mal calibrado.",
    },
}

# Valores publicados (conferidos no resumo de cada artigo)
VIANA_AURA_MEDIANA_MIN = 30          # mediana da duração da aura (IQR 25–60)
VIANA_AURA_IQR = "25–60 min"
VIANA_SINTOMAS_ACIMA_60 = 0.15       # 15% dos sintomas de aura duraram > 60 min
# Relação temporal aura × dor, em 157 auras com dado de início da dor
VIANA_SEQUENCIA = {
    "dor antes da aura": 0.12,
    "dor junto com a aura": 0.10,
    "dor durante a aura": 0.28,
    "dor quando a aura terminou": 0.12,
    "dor depois de um intervalo": 0.37,
}
LAURELL_COM_PREMONITORIO = 0.77      # 77% relatam ao menos um sintoma premonitório
LAURELL_BOCEJO = 0.34                # bocejos: 34%; humor e cansaço: cerca de 1/3 cada
QUEIROZ_PREVALENCIA = {"geral": 0.152, "mulheres": 0.209, "homens": 0.093}
STUBBERUD_AUC = 0.62                 # AUC no conjunto de teste (sensibilidade 0)

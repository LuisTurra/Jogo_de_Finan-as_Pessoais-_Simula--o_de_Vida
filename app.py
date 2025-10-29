import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import matplotlib.pyplot as plt
import yfinance as yf
import requests
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch

# ===================== CONFIGURAÇÃO =====================
st.set_page_config(page_title="Simulador Financeiro", layout="wide")
st.title("De R$ 3.000 a Milionário em até 20 Anos")
st.markdown("### Vida real × Cenário ideal × Poupança")

# ===================== DADOS EM TEMPO REAL =====================
@st.cache_data(ttl=86400)
def get_dados_reais():
    try:
        ipca_resp = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/12?formato=json", timeout=10)
        ipca_data = ipca_resp.json()
        inflacao = float(np.mean([float(d['valor']) for d in ipca_data]) / 100)
    except:
        inflacao = 0.045

    try:
        cdi_data = yf.download("^IRX", period="1y", progress=False)['Close']
        cdi_anual = float((1 + cdi_data.mean() / 100) ** 12 - 1)
    except:
        cdi_anual = 0.11

    try:
        ibov = yf.download("^BVSP", period="2y", progress=False)['Close']
        retorno_ibov = float((ibov.iloc[-1] / ibov.iloc[0]) ** (1/2) - 1)
        volatilidade = float(ibov.pct_change().std() * np.sqrt(252))
    except:
        retorno_ibov = 0.08
        volatilidade = 0.12

    retorno_medio = float(0.6 * cdi_anual + 0.4 * retorno_ibov)
    cresc_sal = 0.03
    poupanca_taxa = 0.06

    return inflacao, cresc_sal, retorno_medio, volatilidade, poupanca_taxa

INFLACAO, CRESC_SALARIO, RETORNO, VOLATILIDADE, POUPANCA_TAXA = get_dados_reais()

# ===================== SIDEBAR =====================
with st.sidebar:
    st.header("Seus Dados")
    idade = st.slider("Idade atual", 18, 50, 25)
    salario = st.number_input("Salário inicial (R$)", 2000, 15000, 3000)
    anos = st.selectbox("Prever por quantos anos?", [1, 5, 10, 15, 20], index=2)
    st.info(f"**Início:** R$ 3.000 | **Previsão:** {anos} anos")

    st.markdown("### Parâmetros")
    st.write(f"**Inflação:** {float(INFLACAO):.1%}")
    st.write(f"**Cresc. Salarial:** {float(CRESC_SALARIO):.1%}")
    st.write(f"**Retorno Médio:** {float(RETORNO):.1%}")
    st.write(f"**Poupança:** {float(POUPANCA_TAXA):.1%}")

MESES_TOTAIS = anos * 12

# ===================== ESTADO =====================
if 'initialized' not in st.session_state:
    st.session_state.escolhas = {}
    st.session_state.salario_atual = float(salario)
    st.session_state.initialized = True

# ===================== SIMULAÇÃO COM EVENTOS =====================
def prever_patrimonio(pat_ini, sal_ini, escolhas, meses):
    sim = 500
    res = np.zeros((sim, meses + 1))
    res_poup = np.zeros((sim, meses + 1))
    res[:, 0] = pat_ini
    res_poup[:, 0] = pat_ini

    for s in range(sim):
        pat = pat_ini
        pat_poup = pat_ini
        sal = sal_ini
        eventos = np.random.choice(['none', 'demissao', 'bonus', 'filho', 'promocao'], size=meses, p=[0.9, 0.03, 0.03, 0.02, 0.02])
        filho_ativa = False
        demissao_meses = 0

        for m in range(1, meses + 1):
            ano = (m - 1) // 12
            infl = (1 + INFLACAO) ** ano
            gastos = sum(escolhas.get(k, 0) for k in ['moradia','transporte','lazer','educacao']) * infl
            if filho_ativa: gastos += 800 * infl
            sobra = max(sal - gastos, 0)
            invest = min(escolhas.get('investimento', 0), sobra)

            evento = eventos[m-1]
            if evento == 'demissao' and demissao_meses == 0:
                sal *= 0.5
                demissao_meses = 6
            if demissao_meses > 0:
                demissao_meses -= 1
                if demissao_meses == 0: sal = sal_ini * (1 + CRESC_SALARIO) ** ano
            elif evento == 'bonus': pat += 5000
            elif evento == 'filho': filho_ativa = True
            elif evento == 'promocao': sal *= 1.2

            if m % 12 == 1 and m > 1: sal *= (1 + CRESC_SALARIO)
            ret = np.random.normal(RETORNO/12, VOLATILIDADE/np.sqrt(12))
            pat = max(pat * (1 + ret) + invest, 0)
            res[s, m] = pat

            pat_poup = pat_poup * (1 + POUPANCA_TAXA/12) + invest
            res_poup[s, m] = pat_poup

    return res, res_poup

# ===================== SIMULAÇÃO SEM EVENTOS (IDEAL) =====================
def prever_patrimonio_sem_eventos(pat_ini, sal_ini, escolhas, meses):
    res = np.zeros(meses + 1)
    pat = pat_ini
    sal = sal_ini
    res[0] = pat_ini

    for m in range(1, meses + 1):
        ano = (m - 1) // 12
        infl = (1 + INFLACAO) ** ano
        gastos = sum(escolhas.get(k, 0) for k in ['moradia','transporte','lazer','educacao']) * infl
        sobra = max(sal - gastos, 0)
        invest = min(escolhas.get('investimento', 0), sobra)

        if m % 12 == 1 and m > 1: sal *= (1 + CRESC_SALARIO)
        ret = RETORNO / 12
        pat = pat * (1 + ret) + invest
        res[m] = pat

    return res

# ===================== ESCOLHAS =====================
st.markdown("### Faça suas escolhas mensais")
col1, col2 = st.columns(2)
with col1:
    moradia = st.selectbox("Moradia", [("Quitinete", 800), ("1 quarto", 1400), ("Com pais", 0)])
    transporte = st.selectbox("Transporte", [("Ônibus", 300), ("Moto", 500), ("Carro", 1200),("Sem Transporte", 0)])
    investimento = st.slider("Investir por mês", 0, 2000, 400)
with col2:
    lazer = st.selectbox("Lazer", [("Baixo", 200), ("Médio", 500), ("Alto", 1000)])
    educacao = st.selectbox("Educação", [("Nenhum", 0), ("Curso", 150), ("Faculdade", 800)])

gastos = moradia[1] + transporte[1] + lazer[1] + educacao[1]
sobra = st.session_state.salario_atual - gastos
invest_real = min(investimento, max(sobra, 0))

st.metric("Salário", f"R$ {st.session_state.salario_atual:,.0f}")
st.metric("Gastos Totais", f"R$ {gastos:,.0f}")
st.metric("Sobra Líquida", f"R$ {sobra:,.0f}", delta=sobra)

if sobra < -1000:
    st.error("Reduza gastos para simular!")
elif investimento > sobra:
    st.warning(f"Investimento ajustado para R$ {sobra:,.0f}")

# ===================== BOTÃO =====================
if st.button("PULAR PARA O FINAL", type="primary", use_container_width=True):
    if sobra >= -1000:
        st.session_state.escolhas = {
            'moradia': moradia[1], 'transporte': transporte[1],
            'lazer': lazer[1], 'educacao': educacao[1],
            'investimento': invest_real
        }

        with st.spinner("Calculando..."):
            previsoes, poupanca = prever_patrimonio(3000, salario, st.session_state.escolhas, MESES_TOTAIS)
            df = pd.DataFrame(previsoes.T)
            df['mês'] = range(MESES_TOTAIS + 1)
            df['mediana'] = df.median(axis=1)
            df['p10'] = df.quantile(0.1, axis=1)
            df['p90'] = df.quantile(0.9, axis=1)

            df_poup = pd.DataFrame(poupanca.T)
            df_poup['mês'] = range(MESES_TOTAIS + 1)
            df_poup['mediana_poup'] = df_poup.median(axis=1)

            sem_eventos = prever_patrimonio_sem_eventos(3000, salario, st.session_state.escolhas, MESES_TOTAIS)
            df_sem = pd.DataFrame({'mês': range(MESES_TOTAIS + 1), 'sem_eventos': sem_eventos})

        st.success("Cálculo concluído!")
        st.balloons()

        # === GRÁFICO COM 3 CENÁRIOS ===
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(df['mês']) + list(df['mês'])[::-1], y=list(df['p10']) + list(df['p90'])[::-1],
                                fill='toself', fillcolor='rgba(0,176,246,0.2)', line=dict(color='rgba(255,255,255,0)'), name='Intervalo 80%'))
        fig.add_trace(go.Scatter(x=df['mês'], y=df['mediana'], mode='lines', name='Com Eventos (vida real)', line=dict(color='green', width=3)))
        fig.add_trace(go.Scatter(x=df_sem['mês'], y=df_sem['sem_eventos'], mode='lines', name='Sem Eventos (ideal)', line=dict(color='purple', width=3, dash='dot')))
        fig.add_trace(go.Scatter(x=df_poup['mês'], y=df_poup['mediana_poup'], mode='lines', name='Poupança', line=dict(color='orange', dash='dash')))
        fig.update_layout(title="Comparação: Vida Real × Ideal × Poupança", xaxis_title="Mês", yaxis_title="R$", height=500)
        st.plotly_chart(fig, use_container_width=True)

        final = df.iloc[-1]
        final_poup = df_poup.iloc[-1]
        final_sem = df_sem.iloc[-1]['sem_eventos']

        st.markdown("### Métricas Finais")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("**Com Eventos**", f"R$ {final['mediana']:,.0f}")
        c2.metric("**Sem Eventos**", f"R$ {final_sem:,.0f}", delta=f"+R$ {final_sem - final['mediana']:,.0f}")
        c3.metric("**Poupança**", f"R$ {final_poup['mediana_poup']:,.0f}")
        c4.metric("**Pior 10%**", f"R$ {final['p10']:,.0f}")
        c5.metric("**Melhor 10%**", f"R$ {final['p90']:,.0f}")

        # === PDF (atualizado com 3 cenários) ===
        def gerar_imagem_png():
            plt.figure(figsize=(10, 6))
            plt.fill_between(df['mês'], df['p10'], df['p90'], color='lightblue', alpha=0.5, label='Intervalo 80%')
            plt.plot(df['mês'], df['mediana'], 'g-', label='Com Eventos', linewidth=3)
            plt.plot(df_sem['mês'], df_sem['sem_eventos'], 'purple', label='Sem Eventos', linewidth=3, linestyle=':')
            plt.plot(df_poup['mês'], df_poup['mediana_poup'], 'orange', label='Poupança', linestyle='--')
            plt.title(f"Comparação em {anos} ano(s)")
            plt.xlabel("Mês")
            plt.ylabel("Patrimônio (R$)")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=150)
            plt.close()
            buf.seek(0)
            return buf

        def gerar_pdf():
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            story.append(Paragraph("<b>Relatório Financeiro</b>", styles['Title']))
            story.append(Spacer(1, 12))
            story.append(Table([
                ["Salário Inicial", f"R$ {salario:,.0f}"],
                ["Anos", str(anos)],
                ["Com Eventos", f"R$ {final['mediana']:,.0f}"],
                ["Sem Eventos", f"R$ {final_sem:,.0f}"],
                ["Poupança", f"R$ {final_poup['mediana_poup']:,.0f}"],
            ]))
            img = gerar_imagem_png()
            story.append(Spacer(1, 12))
            story.append(Image(img, width=6*inch, height=3.5*inch))
            doc.build(story)
            return buf.getvalue()

        st.markdown("---")
        st.subheader("Baixar Relatório")
        pdf_data = gerar_pdf()
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button("PDF", data=pdf_data, file_name="relatorio.pdf", mime="application/pdf")
        with col_d2:
            st.download_button("CSV", data=df[['mês','mediana','p10','p90']].to_csv(index=False), file_name="dados.csv", mime="text/csv")

        if st.button("Nova Simulação"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

# ===================== FONTES =====================
st.markdown("---")
st.markdown("### Fontes Oficiais")
st.markdown("""
- **Inflação (IPCA):** [BCB](https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados)  
- **Ibovespa:** [Yahoo Finance](https://finance.yahoo.com/quote/%5EBVSP/)  
- **Poupança:** [BCB](https://www.bcb.gov.br/estabilidadefinanceira/poupanca)  
""")
st.caption("Simulação educativa.")
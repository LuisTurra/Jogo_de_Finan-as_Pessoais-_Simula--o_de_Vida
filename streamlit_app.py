import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io
import yfinance as yf
import requests
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch

# ===================== CONFIGURAÇÃO =====================
st.set_page_config(page_title="Simulador Financeiro", layout="wide", initial_sidebar_state="expanded")

# ===================== FUNÇÕES =====================
@st.cache_data(ttl=86400)
def get_dados_reais():
    try:
        ipca = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/12?formato=json", timeout=10).json()
        inflacao = float(np.mean([float(d['valorr']) for d in ipca]) / 100)
    except:
        inflacao = 0.045

    try:
        cdi = yf.download("^IRX", period="1y", progress=False)['Close'].mean()
        cdi_anual = float((1 + cdi / 100) ** 12 - 1)
    except:
        cdi_anual = 0.11

    try:
        ibov = yf.download("^BVSP", period="2y", progress=False)['Close']
        retorno_ibov = float((ibov.iloc[-1] / ibov.iloc[0]) ** (1/2) - 1)
        volatilidade = float(ibov.pct_change().std() * np.sqrt(252))
    except:
        retorno_ibov, volatilidade = 0.08, 0.12

    retorno_medio = float(0.6 * cdi_anual + 0.4 * retorno_ibov)
    return inflacao, 0.03, retorno_medio, volatilidade, 0.06

def prever_patrimonio(pat_ini, sal_ini, escolhas, meses, aporte_percentual=0.3):
    sim = 500
    res = np.zeros((sim, meses + 1))
    res_poup = np.zeros((sim, meses + 1))
    res[:, 0] = res_poup[:, 0] = pat_ini

    ret_mensal_medio = (1 + RETORNO)**(1/12) - 1
    vol_mensal = VOLATILIDADE / np.sqrt(12)
    poup_mensal = (1 + POUPANCA_TAXA)**(1/12) - 1

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

            # APORTE = 30% DA SOBRA (ou valor fixo, se menor)
            invest = min(sobra * aporte_percentual, sobra)

            evento = eventos[m-1]
            if evento == 'demissao' and demissao_meses == 0:
                sal *= 0.5; demissao_meses = 6
            if demissao_meses > 0:
                demissao_meses -= 1
                if demissao_meses == 0: sal = sal_ini * (1 + CRESC_SALARIO) ** ano
            elif evento == 'bonus': pat += 5000
            elif evento == 'filho': filho_ativa = True
            elif evento == 'promocao': sal *= 1.2

            if m % 12 == 1 and m > 1: sal *= (1 + CRESC_SALARIO)

            ret = np.random.normal(ret_mensal_medio, vol_mensal)
            pat = max(pat * (1 + ret) + invest, 0)
            pat_poup = pat_poup * (1 + poup_mensal) + invest

            res[s, m] = pat
            res_poup[s, m] = pat_poup

    return res, res_poup

def prever_patrimonio_sem_eventos(pat_ini, sal_ini, escolhas, meses, aporte_percentual=0.3):
    res = np.zeros(meses + 1)
    pat = pat_ini
    sal = sal_ini
    res[0] = pat_ini

    ret_mensal = (1 + RETORNO)**(1/12) - 1

    for m in range(1, meses + 1):
        ano = (m - 1) // 12
        infl = (1 + INFLACAO) ** ano
        gastos = sum(escolhas.get(k, 0) for k in ['moradia','transporte','lazer','educacao']) * infl
        sobra = max(sal - gastos, 0)
        invest = sobra * aporte_percentual

        if m % 12 == 1 and m > 1: sal *= (1 + CRESC_SALARIO)
        pat = pat * (1 + ret_mensal) + invest
        res[m] = pat

    return res

def gerar_tabela_anual(df, sem_eventos, df_poup, anos):
    meses_por_ano = 12
    tabela = []
    for ano in range(anos + 1):
        mes = ano * meses_por_ano
        if mes >= len(df): break
        tabela.append({
            "Ano": ano,
            "Vida Real": f"R$ {df['mediana'].iloc[mes]:,.0f}",
            "Ideal": f"R$ {sem_eventos[mes]:,.0f}",
            "Poupança": f"R$ {df_poup.iloc[mes]:,.0f}"
        })
    return pd.DataFrame(tabela)

def sugerir_otimizacao(gastos, sobra, salario,escolhas):
    sugestoes = []
    if gastos > salario * 0.7:
        sugestoes.append("Reduza moradia ou lazer para < 50% do salário.")
    if sobra < salario * 0.3:
        sugestoes.append("Aumente a sobra para pelo menos 30% do salário.")
    if 'investimento' in escolhas and escolhas['investimento'] < sobra * 0.5:
        sugestoes.append("Invista pelo menos 50% da sobra.")
    if 'moradia' in escolhas and escolhas['moradia'] > 1000:
        sugestoes.append("Morar com pais ou quitinete economiza R$1.000+/mês.")
    return sugestoes or ["Você já está no caminho certo!"]

def gerar_pdf(vida_real, ideal, poupanca, salario, anos):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Relatório Financeiro", styles['Title']),
        Spacer(1, 12),
        Table([
            ["Salário Inicial", f"R$ {salario:,.0f}"],
            ["Período", f"{anos} ano(s)"],
            ["Vida Real", f"R$ {vida_real:,.0f}"],
            ["Ideal", f"R$ {ideal:,.0f}"],
            ["Poupança", f"R$ {poupanca:,.0f}"],
        ])
    ]
    doc.build(story)
    return buffer.getvalue()

# ===================== DADOS REAIS + SEGURANÇA =====================
INFLACAO, CRESC_SALARIO, RETORNO, VOLATILIDADE, POUPANCA_TAXA = get_dados_reais()
RETORNO = min(RETORNO, 0.20)
VOLATILIDADE = min(VOLATILIDADE, 0.50)

# ===================== JS + CSS =====================
st.markdown("""
<script>
    function hideSidebar() {
        const sidebar = parent.document.querySelector('[data-testid="stSidebar"]');
        const main = parent.document.querySelector('.main');
        if (sidebar) sidebar.style.display = 'none';
        if (main) main.style.marginLeft = '0';
    }
    function showSidebar() {
        const sidebar = parent.document.querySelector('[data-testid="stSidebar"]');
        const main = parent.document.querySelector('.main');
        if (sidebar) sidebar.style.display = 'block';
        if (main) main.style.marginLeft = '18rem';
    }
</script>
<style>
    .main > div { padding-left: 2rem; padding-right: 2rem; }
    @media (max-width: 768px) {
        .main > div { padding-left: 1rem; padding-right: 1rem; }
        h1 { font-size: 1.8rem !important; }
    }
</style>
""", unsafe_allow_html=True)

# ===================== ESTADO =====================
if 'simulacao_feita' not in st.session_state:
    st.session_state.simulacao_feita = False
if 'sidebar_hidden' not in st.session_state:
    st.session_state.sidebar_hidden = False

# ===================== BOTÃO FLUTUANTE =====================
if st.session_state.sidebar_hidden:
    st.markdown("""
    <button onclick="showSidebar(); window.location.reload();" 
            style="position:fixed; top:15px; left:15px; z-index:9999; 
                   background:#1a1a2e; color:white; border:none; padding:10px 16px; 
                   border-radius:8px; font-size:14px; cursor:pointer; box-shadow:0 2px 5px rgba(0,0,0,0.2);">
        Opções
    </button>
    """, unsafe_allow_html=True)

# ===================== SIDEBAR =====================
if not st.session_state.sidebar_hidden:
    with st.sidebar:
        st.markdown("### Seus Dados")
        idade = st.slider("Idade atual", 18, 50, 25)
        salario = st.number_input("Salário inicial (R$)", 2000, 15000, 3000, step=100)
        anos = st.selectbox("Prever por quantos anos?", [1, 5, 10, 15, 20], index=2)

        st.markdown("---")
        st.markdown("### Parâmetros Econômicos")
        st.markdown(f"**Inflação:** {INFLACAO:.1%}")
        st.markdown(f"**Cresc. Salarial:** {CRESC_SALARIO:.1%}")
        st.markdown(f"**Retorno Médio:** {RETORNO:.1%}")
        st.markdown(f"**Poupança:** {POUPANCA_TAXA:.1%}")

MESES_TOTAIS = anos * 12 if 'anos' in locals() else 120

# ===================== TÍTULO =====================
st.markdown("<h1 style='text-align:center; color:#ffffff;'>De R$ 3.000 a Milionário</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#ffffff;'>Vida real × Ideal × Poupança</p>", unsafe_allow_html=True)

# ===================== ESCOLHAS =====================
if not st.session_state.simulacao_feita and not st.session_state.sidebar_hidden:
    col1, col2 = st.columns(2)
    with col1:
        moradia = st.selectbox("Moradia", ["Quitinete (R$800)", "1 quarto (R$1.400)", "Com pais (R$0)"])
        transporte = st.selectbox("Transporte", ["Ônibus (R$300)", "Moto (R$500)", "Carro (R$1.200)", "Sem (R$0)"])
    with col2:
        lazer = st.selectbox("Lazer", ["Baixo (R$200)", "Médio (R$500)", "Alto (R$1.000)"])
        educacao = st.selectbox("Educação", ["Nenhum (R$0)", "Curso (R$150)", "Faculdade (R$800)"])

    gastos_map = {
        "Quitinete (R$800)": 800, "1 quarto (R$1.400)": 1400, "Com pais (R$0)": 0,
        "Ônibus (R$300)": 300, "Moto (R$500)": 500, "Carro (R$1.200)": 1200, "Sem (R$0)": 0,
        "Baixo (R$200)": 200, "Médio (R$500)": 500, "Alto (R$1.000)": 1000,
        "Nenhum (R$0)": 0, "Curso (R$150)": 150, "Faculdade (R$800)": 800
    }
    
    gastos = sum(gastos_map[x] for x in [moradia, transporte, lazer, educacao])
    sobra = salario - gastos

    st.markdown("### Resumo Atual")
    c1, c2, c3 = st.columns(3)
    c1.metric("Salário", f"R$ {salario:,.0f}")
    c2.metric("Gastos", f"R$ {gastos:,.0f}")
    c3.metric("Sobra", f"R$ {sobra:,.0f}")

    if sobra < 0:
        st.error("Déficit! Reduza gastos.")
    else:
        st.info(f"**Aporte mensal:** R$ {sobra * 0.3:,.0f} (30% da sobra)")

    # BOTÃO OTIMIZAR
    if st.button("OTIMIZAR MINHAS ESCOLHAS", type="secondary", use_container_width=True):
        escolhas_temp = {'moradia': gastos_map[moradia], 'transporte': gastos_map[transporte],
                        'lazer': gastos_map[lazer], 'educacao': gastos_map[educacao]}
        sugestoes = sugerir_otimizacao(gastos, sobra, salario, escolhas_temp)
        st.markdown("### Sugestões para Melhorar")
        for s in sugestoes:
            st.markdown(f"- {s}")

# ===================== SIMULAR =====================
if not st.session_state.simulacao_feita and not st.session_state.sidebar_hidden:
    if st.button("PULAR PARA O FINAL", type="primary", use_container_width=True):
        if sobra < 0:
            st.error("Corrija o déficit.")
        else:
            escolhas = {k: gastos_map[v] for k, v in zip(['moradia','transporte','lazer','educacao'], [moradia,transporte,lazer,educacao])}

            with st.spinner("Simulando 500 cenários com 30% da sobra..."):
                previsoes, poupanca = prever_patrimonio(3000, salario, escolhas, MESES_TOTAIS, aporte_percentual=0.3)
                df = pd.DataFrame(previsoes.T)
                df['mês'] = range(MESES_TOTAIS + 1)
                df['mediana'] = df.iloc[:, :500].median(axis=1)
                df['p10'] = df.iloc[:, :500].quantile(0.1, axis=1)
                df['p90'] = df.iloc[:, :500].quantile(0.9, axis=1)
                df_poup = pd.DataFrame(poupanca.T).median(axis=1)
                sem_eventos = prever_patrimonio_sem_eventos(3000, salario, escolhas, MESES_TOTAIS, aporte_percentual=0.3)

            st.session_state.resultados = {
                'df': df, 'df_poup': df_poup, 'sem_eventos': sem_eventos,
                'final': df.iloc[-1], 'anos': anos, 'salario': salario
            }
            st.session_state.simulacao_feita = True
            st.session_state.sidebar_hidden = True

            st.markdown("<script>hideSidebar();</script>", unsafe_allow_html=True)
            st.rerun()

# ===================== RESULTADO =====================
if st.session_state.simulacao_feita:
    res = st.session_state.resultados
    df, df_poup, sem_eventos = res['df'], res['df_poup'], res['sem_eventos']
    final, anos, salario = res['final'], res['anos'], res['salario']

    st.success("Simulação concluída!")
    st.balloons()

    # GRÁFICO
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['mês'], y=df['p10'], fill=None, mode='lines', line_color='lightgray'))
    fig.add_trace(go.Scatter(x=df['mês'], y=df['p90'], fill='tonexty', fillcolor='rgba(100,100,255,0.15)', line_color='lightgray', name='80%'))
    fig.add_trace(go.Scatter(x=df['mês'], y=df['mediana'], name='Vida Real', line=dict(color='#28a745', width=3)))
    fig.add_trace(go.Scatter(x=df['mês'], y=sem_eventos, name='Ideal', line=dict(color='#9c27b0', width=3, dash='dot')))
    fig.add_trace(go.Scatter(x=df['mês'], y=df_poup, name='Poupança', line=dict(color='#ff9800', width=3, dash='dash')))
    fig.update_layout(title="Evolução do Patrimônio", xaxis_title="Meses", yaxis_title="R$", height=500)
    st.plotly_chart(fig, use_container_width=True)

    # RESULTADO FINAL
    st.markdown(f"### Resultado em {anos} ano(s)")
    cols = st.columns(5)
    cols[0].metric("Vida Real", f"R$ {float(final['mediana']):,.0f}")
    cols[1].metric("Ideal", f"R$ {float(sem_eventos[-1]):,.0f}")
    cols[2].metric("Poupança", f"R$ {float(df_poup.iloc[-1]):,.0f}")
    cols[3].metric("Pior 10%", f"R$ {float(final['p10']):,.0f}")
    cols[4].metric("Melhor 10%", f"R$ {float(final['p90']):,.0f}")

    # TABELA ANUAL
    st.markdown("### Evolução Ano a Ano")
    tabela_anual = gerar_tabela_anual(df, sem_eventos, df_poup, anos)
    st.dataframe(tabela_anual, use_container_width=True)

    # DOWNLOADS
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        csv = df[['mês','mediana','p10','p90']].to_csv(index=False).encode()
        st.download_button("CSV", csv, "dados.csv", "text/csv", use_container_width=True)
    with col_d2:
        pdf = gerar_pdf(float(final['mediana']), float(sem_eventos[-1]), float(df_poup.iloc[-1]), salario, anos)
        st.download_button("PDF", pdf, "relatorio.pdf", "application/pdf", use_container_width=True)

    if st.button("RESETAR E REABRIR OPÇÕES", type="secondary", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.markdown("<script>showSidebar();</script>", unsafe_allow_html=True)
        st.rerun()

# ===================== RODAPÉ =====================
st.markdown("---")
st.caption("Fontes: BCB, Yahoo Finance. Simulação educativa. Aporte = 30% da sobra.")
import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Processador de RH Pro", layout="wide")
st.title("📂 Sistema de Consolidação de Documentos de RH (Versão Completa)")

# --- FUNÇÕES AUXILIARES ---
def limpar_valor(valor_str):
    """Converte string '1.234,56' para float 1234.56"""
    if pd.isna(valor_str) or valor_str == "":
        return 0.0
    if isinstance(valor_str, float):
        return valor_str
    # Remove pontos de milhar e troca vírgula decimal por ponto
    return float(valor_str.replace('.', '').replace(',', '.'))

def limpar_cnpj(cnpj_str):
    """Remove pontuação do CNPJ para garantir o merge (apenas números)"""
    if pd.isna(cnpj_str) or cnpj_str == "Não Encontrado":
        return "N/A"
    # Remove tudo que não for dígito
    return re.sub(r'\D', '', str(cnpj_str))

# --- 1. FUNÇÃO: EXTRAIR LÍQUIDO ---
def processar_liquidos(uploaded_files):
    dados_extraidos = []
    # Regex do Notebook
    padrao_liquido = re.compile(r'^\s*(\d+)\s+(.+?)\s+(\d{3}\.\d{3}\.\d{3}-\d{2})\s+(\d{2}/\d{2}/\d{4})\s+([\d\.,]+)')
    # [ALTERAÇÃO] Regex genérico para capturar CNPJ no cabeçalho da página
    regex_cnpj_generico = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if not texto: continue
                    
                    # [ALTERAÇÃO] Busca CNPJ na página atual
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"

                    for linha in texto.split('\n'):
                        match = padrao_liquido.search(linha)
                        if match:
                            codigo, nome, cpf, data, valor = match.groups()
                            dados_extraidos.append({
                                "Empresa CNPJ": cnpj_encontrado, # [ALTERAÇÃO] Campo Adicionado
                                "Código": codigo,
                                "Funcionário": nome.strip(),
                                "CPF": cpf,
                                "Data Pagto": data,
                                "Valor Líquido": limpar_valor(valor),
                                "Arquivo": file.name
                            })
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")
            
    return pd.DataFrame(dados_extraidos)

# --- 2. FUNÇÃO: EXTRAIR ASSISTENCIAL ---
def processar_assistencial(uploaded_files):
    dados_assistencial = []
    # Regex do Notebook
    regex_linha_nome = re.compile(r'Código:\s*(\d+)\s+Nome\s*:\s*(.+?)\s+Função\s*:\s*(.*)')
    regex_linha_valores = re.compile(r'Admissão\s*:\s*(\d{2}/\d{2}/\d{4})\s*Salário\s*:\s*([,.\d]+)\s*Valor\s*:\s*([,.\d]+)')
    # [ALTERAÇÃO] Regex genérico para CNPJ
    regex_cnpj_generico = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if not texto: continue
                    
                    # [ALTERAÇÃO] Busca CNPJ na página
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"

                    linhas = texto.split('\n')
                    for i, linha in enumerate(linhas):
                        match_nome = regex_linha_nome.search(linha)
                        if match_nome:
                            # Tenta pegar valores na linha seguinte
                            if i + 1 < len(linhas):
                                linha_baixo = linhas[i+1]
                                match_valores = regex_linha_valores.search(linha_baixo)
                                if match_valores:
                                    cod, nome, funcao = match_nome.groups()
                                    admissao, salario, valor_desc = match_valores.groups()
                                    dados_assistencial.append({
                                        "Empresa CNPJ": cnpj_encontrado, # [ALTERAÇÃO] Campo Adicionado
                                        "Código": cod,
                                        "Funcionário": nome.strip(),
                                        "Função": funcao.strip(),
                                        "Admissão": admissao,
                                        "Salário Base": limpar_valor(salario),
                                        "Valor Assistencial": limpar_valor(valor_desc),
                                        "Arquivo Original": file.name
                                    })
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    return pd.DataFrame(dados_assistencial)

# --- 3. FUNÇÃO: EXTRAIR EXTRAS (AGRUPADO) ---
def processar_extras(uploaded_files):
    dados_extras = []
    # Regex do Notebook
    regex_linha = re.compile(r'^\s*(\d+)\s+(.+?)\s+([\d\.,]+)\s+([\d\.,]+)$')
    # [ALTERAÇÃO] Regex genérico para CNPJ
    regex_cnpj_generico = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if not texto: continue

                    # [ALTERAÇÃO] Busca CNPJ na página
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"

                    for linha in texto.split('\n'):
                        match_dados = regex_linha.search(linha)
                        if match_dados:
                            cod, nome, referencia, valor = match_dados.groups()
                            dados_extras.append({
                                "Empresa CNPJ": cnpj_encontrado, # [ALTERAÇÃO] Campo Adicionado
                                "Código": str(int(cod)), 
                                "Funcionário": nome.strip(),
                                "Valor (R$)": limpar_valor(valor)
                            })
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    if dados_extras:
        df = pd.DataFrame(dados_extras)
        # [ALTERAÇÃO] Agrupa por Código, Funcionário E CNPJ
        df_agrupado = df.groupby(['Empresa CNPJ', 'Código', 'Funcionário'], as_index=False)['Valor (R$)'].sum()
        return df_agrupado
    return pd.DataFrame()

# --- 4. FUNÇÃO: EXTRAIR FOLHA COMPLETA ---
def processar_folha(uploaded_files):
    dados_folha = []
    
    # --- REGEX COMPILADOS ---
    regex_inicio = re.compile(r'Cód:\s*(\d+).*?Nome:\s*(.*?)\s+Função:(.*?)(?:Dep|$)')
    regex_contrato = re.compile(r'Admissão:\s*(\d{2}/\d{2}/\d{4}).*?Salário:\s*([,.\d]+)')
    
    regex_razao_social = re.compile(r'(?:Apelido:.*?|\s*)Razão Social:\s*(.*?)(?:\s+CNPJ/CEI:|\s+Pág:|\n|$)', re.IGNORECASE)
    regex_cnpj_cei = re.compile(r'CNPJ/CEI:([\d\./\-]+)', re.IGNORECASE)
    
    regex_base_inss_empresa = re.compile(r'Base INSS Empresa:\s*([\d\.,]+)')
    regex_base_inss_funcionario = re.compile(r'Base INSS Funcionário:\s*([\d\.,]+)')
    regex_base_fgts = re.compile(r'Base F\.G\.T\.S\.:\s*([\d\.,]+)')
    regex_fgts = re.compile(r'F\.G\.T\.S\.:\s*([\d\.,]+)')
    regex_totais = re.compile(r'Proventos:\s*([\d\.,]+).*?Descontos:\s*([\d\.,]+).*?Liquido:\s*([\d\.,]+)')
    
    regex_item_salario = re.compile(r'\d+Salário\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_dsr_he = re.compile(r'\d+D\.S\.R\. Sobre Horas Extras\s+([\d\.,]+)')
    regex_item_horas_extras_50 = re.compile(r'\d+Horas Extras 50%\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_reembolso_vt = re.compile(r'\d+Reembolso Vale Transporte\s+([\d\.,]+)')
    regex_item_inss_salario = re.compile(r'\d+INSS Sobre Salário\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_irrf_salario = re.compile(r'\d+IRRF Sobre Salário\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_desc_vt = re.compile(r'\d+Desc\. Vale Transporte\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_contr_assist = re.compile(r'\d+Contribuição Assistencial\s+[\d\.,]+')

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                empresa_nome = "Não Encontrado"
                empresa_cnpj = "Não Encontrado"
                
                # Tenta pegar dados da empresa na primeira página
                if len(pdf.pages) > 0:
                    first_text = pdf.pages[0].extract_text()
                    match_rz = regex_razao_social.search(first_text)
                    if match_rz: empresa_nome = match_rz.group(1).strip()
                    match_cnpj = regex_cnpj_cei.search(first_text)
                    if match_cnpj: empresa_cnpj = match_cnpj.group(1).strip()

                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if not texto: continue
                    
                    # Se a folha tiver empresas diferentes por página, tenta atualizar aqui
                    match_cnpj_pag = regex_cnpj_cei.search(texto)
                    if match_cnpj_pag:
                        empresa_cnpj = match_cnpj_pag.group(1).strip()
                    
                    func_atual = {}
                    
                    for linha in texto.split('\n'):
                        match_inicio = regex_inicio.search(linha)
                        if match_inicio:
                            cod, nome, funcao = match_inicio.groups()
                            func_atual = {
                                "Empresa": empresa_nome,
                                "Empresa CNPJ": empresa_cnpj,
                                "Código": cod,
                                "Funcionário": nome.strip(),
                                "Função": funcao.strip(),
                                "Arquivo": file.name,
                                "Salário Base Contratual": "0,00",
                                "Salário Provento": "0,00",
                                "D.S.R. Sobre Horas Extras": "0,00",
                                "Horas Extras 50%": "0,00",
                                "Reembolso Vale Transporte": "0,00",
                                "INSS Sobre Salário": "0,00",
                                "IRRF Sobre Salário": "0,00",
                                "Desc. Vale Transporte": "0,00",
                                "Contribuição Assistencial": "0,00",
                                "Base INSS Empresa": "0,00",
                                "Base INSS Funcionário": "0,00",
                                "Base F.G.T.S.": "0,00",
                                "F.G.T.S.": "0,00",
                                "Total Proventos": "0,00",
                                "Total Descontos": "0,00",
                                "Líquido a Receber": "0,00"
                            }
                            continue

                        if func_atual:
                            match_contrato = regex_contrato.search(linha)
                            if match_contrato:
                                adm, sal = match_contrato.groups()
                                func_atual["Admissão"] = adm
                                func_atual["Salário Base Contratual"] = sal
                            
                            if regex_item_salario.search(linha): func_atual["Salário Provento"] = regex_item_salario.search(linha).group(1)
                            if regex_item_dsr_he.search(linha): func_atual["D.S.R. Sobre Horas Extras"] = regex_item_dsr_he.search(linha).group(1)
                            if regex_item_horas_extras_50.search(linha): func_atual["Horas Extras 50%"] = regex_item_horas_extras_50.search(linha).group(1)
                            if regex_item_reembolso_vt.search(linha): func_atual["Reembolso Vale Transporte"] = regex_item_reembolso_vt.search(linha).group(1)
                            if regex_item_inss_salario.search(linha): func_atual["INSS Sobre Salário"] = regex_item_inss_salario.search(linha).group(1)
                            if regex_item_irrf_salario.search(linha): func_atual["IRRF Sobre Salário"] = regex_item_irrf_salario.search(linha).group(1)
                            if regex_item_desc_vt.search(linha): func_atual["Desc. Vale Transporte"] = regex_item_desc_vt.search(linha).group(1)
                            if regex_item_contr_assist.search(linha): func_atual["Contribuição Assistencial"] = "10,00" 

                            if regex_base_inss_empresa.search(linha): func_atual["Base INSS Empresa"] = regex_base_inss_empresa.search(linha).group(1)
                            if regex_base_inss_funcionario.search(linha): func_atual["Base INSS Funcionário"] = regex_base_inss_funcionario.search(linha).group(1)
                            if regex_base_fgts.search(linha): func_atual["Base F.G.T.S."] = regex_base_fgts.search(linha).group(1)
                            if regex_fgts.search(linha): func_atual["F.G.T.S."] = regex_fgts.search(linha).group(1)
                            
                            match_totais = regex_totais.search(linha)
                            if match_totais:
                                prov, desc, liq = match_totais.groups()
                                func_atual["Total Proventos"] = prov
                                func_atual["Total Descontos"] = desc
                                func_atual["Líquido a Receber"] = liq
                                dados_folha.append(func_atual)
                                func_atual = {}

        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    if dados_folha:
        df = pd.DataFrame(dados_folha)
        cols_valores = [c for c in df.columns if c not in ["Empresa", "Empresa CNPJ", "Código", "Funcionário", "Função", "Arquivo", "Admissão"]]
        for col in cols_valores:
            df[col] = df[col].apply(limpar_valor)
        return df
    
    return pd.DataFrame()


# --- INTERFACE E PROCESSAMENTO ---

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📄 Folha", 
    "🚑 Assistencial", 
    "💰 Líquido", 
    "➕ Extras", 
    "📊 Consolidação",
    "📈 Dashboard"
])

if 'dfs' not in st.session_state:
    st.session_state.dfs = {}

# --- ABA 1: FOLHA ---
with tab1:
    st.header("Upload da Folha de Pagamento (Holerites)")
    with st.expander("ℹ️ Ver arquivos permitidos para Folha"):
        st.markdown("""
        **Arquivos Aceitos:**
        * `Folha de Pagamento -Normal*.pdf`
        * `Folha de Adiantamento -Normal*.pdf`
        """)
    up_folha = st.file_uploader("Selecione os PDFs da Folha", type="pdf", accept_multiple_files=True, key="u_folha")
    if up_folha:
        with st.spinner("Processando Folha complexa..."):
            df_folha = processar_folha(up_folha)
            st.session_state.dfs['Folha'] = df_folha
            st.success(f"{len(df_folha)} registros extraídos.")
            st.dataframe(df_folha.head())

# --- ABA 2: ASSISTENCIAL ---
with tab2:
    st.header("Upload da Relação Assistencial")
    with st.expander("ℹ️ Ver arquivos permitidos para Assistencial"):
        st.markdown("""
        **Arquivos Aceitos:**
        * `Relação Assistencial *.pdf`
        """)
    up_assist = st.file_uploader("Selecione PDF Assistencial", type="pdf", accept_multiple_files=True, key="u_assist")
    if up_assist:
        df_assist = processar_assistencial(up_assist)
        st.session_state.dfs['Assistencial'] = df_assist
        st.success(f"{len(df_assist)} registros extraídos.")
        st.dataframe(df_assist.head())

# --- ABA 3: LÍQUIDO ---
with tab3:
    st.header("Upload Relatório de Líquidos")
    with st.expander("ℹ️ Ver arquivos permitidos para Líquidos"):
        st.markdown("""
        **Arquivos Aceitos:**
        * `Liquido de Pagamento *.pdf`
        * `Relatorio Liquido de Adiantamento *.pdf`
        """)
    up_liq = st.file_uploader("Selecione PDF Líquido", type="pdf", accept_multiple_files=True, key="u_liq")
    if up_liq:
        df_liq = processar_liquidos(up_liq)
        st.session_state.dfs['Liquido'] = df_liq
        st.success(f"{len(df_liq)} registros extraídos.")
        st.dataframe(df_liq.head())

# --- ABA 4: EXTRAS ---
with tab4:
    st.header("Upload de Extras (Bonificações, HE separadas)")
    with st.expander("ℹ️ Ver arquivos permitidos para Extras"):
        st.markdown("""         
        **Padrões Identificados:**
        * `**** - Bonificação Extraordinária.pdf`
        * `** - Horas Extras 50%.pdf`
        * `* - D.S.R. Sobre Horas Extras.pdf`
        * `** - Hora Extras 100%.pdf`
        """)
    up_extras = st.file_uploader("Selecione PDFs de Extras", type="pdf", accept_multiple_files=True, key="u_extras")
    if up_extras:
        df_extras = processar_extras(up_extras)
        st.session_state.dfs['Extras'] = df_extras
        st.success(f"{len(df_extras)} registros agrupados.")
        st.dataframe(df_extras.head())

# --- ABA 5: CONSOLIDAÇÃO ---
with tab5:
    st.header("Mesclar e Baixar Relatório Final")
    
    if st.button("Gerar Relatório Consolidado"):
        dfs = st.session_state.dfs
        
        if 'Folha' not in dfs or dfs['Folha'].empty:
            st.warning("⚠️ Você precisa processar a Folha de Pagamento primeiro (Aba 1).")
        else:
            with st.spinner("Consolidando bases de dados com chave composta (Código + CNPJ)..."):
                df_final = dfs['Folha'].copy()
                
                # [ALTERAÇÃO CRÍTICA] Normalização de Chaves
                # Garante que Código e CNPJ estejam no mesmo formato em todas as tabelas
                df_final['Código'] = df_final['Código'].astype(str).str.strip()
                df_final['Empresa CNPJ Norm'] = df_final['Empresa CNPJ'].apply(limpar_cnpj) # Cria chave limpa

                # 1. Merge com Assistencial
                if 'Assistencial' in dfs and not dfs['Assistencial'].empty:
                    df_assist = dfs['Assistencial'].copy()
                    df_assist['Código'] = df_assist['Código'].astype(str).str.strip()
                    # Normaliza CNPJ do assistencial para bater com a folha
                    df_assist['Empresa CNPJ Norm'] = df_assist['Empresa CNPJ'].apply(limpar_cnpj)
                    
                    # Merge usando Código E CNPJ
                    df_final = pd.merge(
                        df_final, 
                        df_assist[['Código', 'Empresa CNPJ Norm', 'Salário Base', 'Valor Assistencial']], 
                        on=['Código', 'Empresa CNPJ Norm'], 
                        how='left', 
                        suffixes=('', '_assist')
                    )

                # 2. Merge com Líquido
                if 'Liquido' in dfs and not dfs['Liquido'].empty:
                    df_liq_in = dfs['Liquido'].copy()
                    df_liq_in['Código'] = df_liq_in['Código'].astype(str).str.strip()
                    df_liq_in['Empresa CNPJ Norm'] = df_liq_in['Empresa CNPJ'].apply(limpar_cnpj)
                    
                    # Merge usando Código E CNPJ
                    df_final = pd.merge(
                        df_final, 
                        df_liq_in[['Código', 'Empresa CNPJ Norm', 'Valor Líquido']], 
                        on=['Código', 'Empresa CNPJ Norm'], 
                        how='left'
                    )
                    df_final.rename(columns={'Valor Líquido': 'Valor Líquido (Relatório)'}, inplace=True)

                # 3. Merge com Extras
                if 'Extras' in dfs and not dfs['Extras'].empty:
                    df_ext = dfs['Extras'].copy()
                    df_ext['Código'] = df_ext['Código'].astype(str).str.strip()
                    df_ext['Empresa CNPJ Norm'] = df_ext['Empresa CNPJ'].apply(limpar_cnpj)
                    
                    # Merge usando Código E CNPJ
                    df_final = pd.merge(
                        df_final, 
                        df_ext[['Código', 'Empresa CNPJ Norm', 'Valor (R$)']], 
                        on=['Código', 'Empresa CNPJ Norm'], 
                        how='left'
                    )
                    df_final.rename(columns={'Valor (R$)': 'Total Extras'}, inplace=True)
                    df_final['Total Extras'] = df_final['Total Extras'].fillna(0.0)

                # Limpeza final (remove coluna de normalização auxiliar)
                if 'Empresa CNPJ Norm' in df_final.columns:
                    df_final.drop(columns=['Empresa CNPJ Norm'], inplace=True)

                st.session_state['df_consolidado_cache'] = df_final
                st.success("🎉 Consolidação realizada com sucesso! (Relacionamento por Código + CNPJ)")

    # --- EXIBIÇÃO PERSISTENTE ---
    if 'df_consolidado_cache' in st.session_state:
        df_final = st.session_state['df_consolidado_cache']

        st.divider()
        st.subheader("🛠️ Personalizar Colunas para Exportação")
        
        todas_colunas = df_final.columns.tolist()
        
        colunas_selecionadas = st.multiselect(
            "Selecione as colunas que deseja no Excel:",
            options=todas_colunas,
            default=todas_colunas
        )

        if not colunas_selecionadas:
            st.error("⚠️ Selecione pelo menos uma coluna.")
        else:
            df_export = df_final[colunas_selecionadas]
            
            st.write("Prévia:")
            st.dataframe(df_export.head())
            
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_export.to_excel(writer, sheet_name='Consolidado', index=False)
                for nome, df_orig in st.session_state.dfs.items():
                    df_orig.to_excel(writer, sheet_name=f"Orig_{nome}", index=False)
            
            st.download_button(
                label="📥 Baixar Excel Personalizado",
                data=buffer.getvalue(),
                file_name="Dados_Consolidados_RH_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
            if st.button("Limpar Consolidação"):
                del st.session_state['df_consolidado_cache']
                st.rerun()

# --- ABA 6: DASHBOARD & ANÁLISE ---
with tab6:
    st.header("📈 Dashboard Gerencial de RH")

    if 'df_consolidado_cache' not in st.session_state:
        st.info("⚠️ Processe a consolidação na **Aba 5** primeiro para visualizar os gráficos.")
    else:
        df_dash = st.session_state['df_consolidado_cache'].copy()
        
        cols_numericas = ['Total Proventos', 'Líquido a Receber', 'Total Extras', 'Total Descontos']
        for col in cols_numericas:
            if col not in df_dash.columns:
                df_dash[col] = 0.0
            else:
                df_dash[col] = df_dash[col].fillna(0).astype(float)

        st.subheader("Visão Geral do Mês")
        col1, col2, col3, col4 = st.columns(4)
        
        total_folha = df_dash['Total Proventos'].sum()
        total_liquido = df_dash['Líquido a Receber'].sum()
        total_extras = df_dash['Total Extras'].sum()
        headcount = df_dash['Código'].nunique()

        col1.metric("💰 Custo Total (Bruto)", f"R$ {total_folha:,.2f}")
        col2.metric("💸 Total Líquido", f"R$ {total_liquido:,.2f}")
        col3.metric("➕ Total Extras/Bonif.", f"R$ {total_extras:,.2f}")
        col4.metric("👥 Headcount", f"{headcount} Func.")
        
        st.divider()

        col_g1, col_g2 = st.columns(2)

        with col_g1:
            st.subheader("🏆 Top 10 Maiores Salários Líquidos")
            df_top10 = df_dash.nlargest(10, 'Líquido a Receber')
            
            fig_bar = px.bar(
                df_top10, 
                x='Líquido a Receber', 
                y='Funcionário', 
                orientation='h',
                text='Líquido a Receber',
                color='Líquido a Receber',
                color_continuous_scale='Blues'
            )
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
            fig_bar.update_traces(texttemplate='R$ %{text:,.2f}', textposition='outside')
            st.plotly_chart(fig_bar, use_container_width=True)

        with col_g2:
            st.subheader("🏢 Custo por Função")
            if 'Função' in df_dash.columns:
                df_func = df_dash.groupby('Função')[['Total Proventos']].sum().reset_index()
                
                fig_pie = px.pie(
                    df_func, 
                    values='Total Proventos', 
                    names='Função',
                    hole=0.4
                )
                fig_pie.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.warning("Coluna 'Função' não encontrada.")

        col_g3, col_g4 = st.columns(2)

        with col_g3:
            st.subheader("📊 Distribuição de Salários (Histograma)")
            fig_hist = px.histogram(
                df_dash, 
                x="Líquido a Receber", 
                nbins=20, 
                color_discrete_sequence=['#3b82f6']
            )
            fig_hist.update_layout(bargap=0.1)
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_g4:
            st.subheader("🔍 Relação: Salário Base vs. Extras")
            fig_scat = px.scatter(
                df_dash, 
                x="Salário Base Contratual", 
                y="Total Extras",
                hover_data=['Funcionário', 'Função'],
                size="Total Proventos", 
                color="Função"
            )
            st.plotly_chart(fig_scat, use_container_width=True)
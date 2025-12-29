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
    return float(str(valor_str).replace('.', '').replace(',', '.'))

def limpar_cnpj(cnpj_str):
    """Remove pontuação do CNPJ"""
    if pd.isna(cnpj_str) or cnpj_str == "Não Encontrado":
        return "N/A"
    return re.sub(r'\D', '', str(cnpj_str))

# --- 1. FUNÇÃO: EXTRAIR LÍQUIDO ---
def processar_liquidos(uploaded_files):
    dados_extraidos = []
    padrao_liquido = re.compile(r'^\s*(\d+)\s+(.+?)\s+(\d{3}\.\d{3}\.\d{3}-\d{2})\s+(\d{2}/\d{2}/\d{4})\s+([\d\.,]+)')
    regex_cnpj_generico = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if not texto: continue
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"
                    for linha in texto.split('\n'):
                        match = padrao_liquido.search(linha)
                        if match:
                            codigo, nome, cpf, data, valor = match.groups()
                            dados_extraidos.append({
                                "Empresa CNPJ": cnpj_encontrado,
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
    regex_linha_nome = re.compile(r'Código:\s*(\d+)\s+Nome\s*:\s*(.+?)\s+Função\s*:\s*(.*)')
    regex_linha_valores = re.compile(r'Admissão\s*:\s*(\d{2}/\d{2}/\d{4})\s*Salário\s*:\s*([,.\d]+)\s*Valor\s*:\s*([,.\d]+)')
    regex_cnpj_generico = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if not texto: continue
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"
                    linhas = texto.split('\n')
                    for i, linha in enumerate(linhas):
                        match_nome = regex_linha_nome.search(linha)
                        if match_nome:
                            if i + 1 < len(linhas):
                                linha_baixo = linhas[i+1]
                                match_valores = regex_linha_valores.search(linha_baixo)
                                if match_valores:
                                    cod, nome, funcao = match_nome.groups()
                                    admissao, salario, valor_desc = match_valores.groups()
                                    dados_assistencial.append({
                                        "Empresa CNPJ": cnpj_encontrado,
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

# --- 3. FUNÇÃO: EXTRAIR EXTRAS (PIVOTADO) ---
def processar_extras(uploaded_files):
    dados_extras = []
    # Regex Padrão
    regex_linha = re.compile(r'^\s*(\d+)\s+(.+?)\s+([\d\.,]+)\s+([\d\.,]+)$')
    # Regex Alternativo (caso o PDF tenha layout levemente diferente, comum em DSR)
    regex_linha_alt = re.compile(r'^\s*(\d+)\s+(.+?)\s+([\d\.,]+)$') 
    
    regex_cnpj_generico = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

    # Lista de colunas esperadas
    lista_eventos_esperados = [
        "Adicional Noturno Horas 20%",
        "Bonificação Extraordinária",
        "D.S.R. Sobre Horas Extras",
        "DSR Adicional Noturno",
        "Hora Extras 100%",
        "Horas Extras 50%"
    ]

    for file in uploaded_files:
        try:
            # Identificar tipo de evento
            nome_arquivo = file.name
            nome_upper = nome_arquivo.upper()
            tipo_evento = "Outros Extras" 
            
            if "1394" in nome_upper or "BONIFICA" in nome_upper: tipo_evento = "Bonificação Extraordinária"
            elif "152" in nome_upper or ("DSR" in nome_upper and "NOTURNO" in nome_upper): tipo_evento = "DSR Adicional Noturno"
            elif "D.S.R." in nome_upper or ("DSR" in nome_upper and "EXTRA" in nome_upper): tipo_evento = "D.S.R. Sobre Horas Extras"
            elif "20%" in nome_upper and "NOTURNO" in nome_upper: tipo_evento = "Adicional Noturno Horas 20%"
            elif "100%" in nome_upper: tipo_evento = "Hora Extras 100%"
            elif "50%" in nome_upper: tipo_evento = "Horas Extras 50%"

            with pdfplumber.open(file) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if not texto: continue
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"

                    for linha in texto.split('\n'):
                        # Tenta o regex padrão primeiro
                        match = regex_linha.search(linha)
                        valor_encontrado = None
                        
                        if match:
                            cod, nome, ref, val = match.groups()
                            valor_encontrado = val
                        else:
                            # Tenta regex alternativo (sem coluna de referência)
                            match_alt = regex_linha_alt.search(linha)
                            if match_alt:
                                cod, nome, val = match_alt.groups()
                                valor_encontrado = val

                        if valor_encontrado:
                            dados_extras.append({
                                "Empresa CNPJ": cnpj_encontrado,
                                "Código": str(int(cod)), 
                                "Funcionário": nome.strip(),
                                "Tipo Evento": tipo_evento,
                                "Valor": limpar_valor(valor_encontrado)
                            })
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    if dados_extras:
        df = pd.DataFrame(dados_extras)
        
        # Pivotar
        df_pivot = df.pivot_table(
            index=['Empresa CNPJ', 'Código', 'Funcionário'], 
            columns='Tipo Evento', 
            values='Valor', 
            aggfunc='sum',
            fill_value=0.0
        ).reset_index()
        
        # Garantir colunas obrigatórias
        for col in lista_eventos_esperados:
            if col not in df_pivot.columns:
                df_pivot[col] = 0.0
        
        # Total
        cols_numericas = [c for c in df_pivot.columns if c not in ['Empresa CNPJ', 'Código', 'Funcionário']]
        df_pivot['Total Extras'] = df_pivot[cols_numericas].sum(axis=1)
        
        return df_pivot
        
    return pd.DataFrame()

# --- 4. FUNÇÃO: EXTRAIR FOLHA COMPLETA ---
def processar_folha(uploaded_files):
    dados_folha = []
    regex_inicio = re.compile(r'Cód:\s*(\d+).*?Nome:\s*(.*?)\s+Função:(.*?)(?:Dep|$)')
    regex_contrato = re.compile(r'Admissão:\s*(\d{2}/\d{2}/\d{4}).*?Salário:\s*([,.\d]+)')
    regex_razao_social = re.compile(r'(?:Apelido:.*?|\s*)Razão Social:\s*(.*?)(?:\s+CNPJ/CEI:|\s+Pág:|\n|$)', re.IGNORECASE)
    regex_cnpj_cei = re.compile(r'CNPJ/CEI:([\d\./\-]+)', re.IGNORECASE)
    
    # Regex Eventos
    regex_item_salario = re.compile(r'\d+Salário\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_dsr_he = re.compile(r'\d+D\.S\.R\. Sobre Horas Extras\s+([\d\.,]+)')
    regex_item_horas_extras_50 = re.compile(r'\d+Horas Extras 50%\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_reembolso_vt = re.compile(r'\d+Reembolso Vale Transporte\s+([\d\.,]+)')
    regex_item_inss_salario = re.compile(r'\d+INSS Sobre Salário\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_irrf_salario = re.compile(r'\d+IRRF Sobre Salário\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_desc_vt = re.compile(r'\d+Desc\. Vale Transporte\s+[\d\.,]+\s+([\d\.,]+)')
    regex_item_contr_assist = re.compile(r'\d+Contribuição Assistencial\s+[\d\.,]+')
    regex_base_inss_empresa = re.compile(r'Base INSS Empresa:\s*([\d\.,]+)')
    regex_base_inss_funcionario = re.compile(r'Base INSS Funcionário:\s*([\d\.,]+)')
    regex_base_fgts = re.compile(r'Base F\.G\.T\.S\.:\s*([\d\.,]+)')
    regex_fgts = re.compile(r'F\.G\.T\.S\.:\s*([\d\.,]+)')
    regex_totais = re.compile(r'Proventos:\s*([\d\.,]+).*?Descontos:\s*([\d\.,]+).*?Liquido:\s*([\d\.,]+)')

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                empresa_nome = "Não Encontrado"
                empresa_cnpj = "Não Encontrado"
                if len(pdf.pages) > 0:
                    first_text = pdf.pages[0].extract_text()
                    match_rz = regex_razao_social.search(first_text)
                    if match_rz: empresa_nome = match_rz.group(1).strip()
                    match_cnpj = regex_cnpj_cei.search(first_text)
                    if match_cnpj: empresa_cnpj = match_cnpj.group(1).strip()

                for pagina in pdf.pages:
                    texto = pagina.extract_text()
                    if not texto: continue
                    match_cnpj_pag = regex_cnpj_cei.search(texto)
                    if match_cnpj_pag: empresa_cnpj = match_cnpj_pag.group(1).strip()
                    
                    func_atual = {}
                    for linha in texto.split('\n'):
                        match_inicio = regex_inicio.search(linha)
                        if match_inicio:
                            cod, nome, funcao = match_inicio.groups()
                            func_atual = {
                                "Empresa": empresa_nome, "Empresa CNPJ": empresa_cnpj, "Código": cod,
                                "Funcionário": nome.strip(), "Função": funcao.strip(), "Arquivo": file.name,
                                "Salário Base Contratual": "0,00", "Salário Provento": "0,00",
                                "D.S.R. Sobre Horas Extras": "0,00", "Horas Extras 50%": "0,00",
                                "Reembolso Vale Transporte": "0,00", "INSS Sobre Salário": "0,00",
                                "IRRF Sobre Salário": "0,00", "Desc. Vale Transporte": "0,00",
                                "Contribuição Assistencial": "0,00", "Base INSS Empresa": "0,00",
                                "Base INSS Funcionário": "0,00", "Base F.G.T.S.": "0,00", "F.G.T.S.": "0,00",
                                "Total Proventos": "0,00", "Total Descontos": "0,00", "Líquido a Receber": "0,00"
                            }
                            continue

                        if func_atual:
                            match_contrato = regex_contrato.search(linha)
                            if match_contrato:
                                func_atual["Admissão"] = match_contrato.group(1)
                                func_atual["Salário Base Contratual"] = match_contrato.group(2)
                            
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
                                func_atual["Total Proventos"] = match_totais.group(1)
                                func_atual["Total Descontos"] = match_totais.group(2)
                                func_atual["Líquido a Receber"] = match_totais.group(3)
                                dados_folha.append(func_atual)
                                func_atual = {}
        except Exception as e:
            st.error(f"Erro ao processar {file.name}: {e}")

    if dados_folha:
        df = pd.DataFrame(dados_folha)
        cols_ignoradas = ["Empresa", "Empresa CNPJ", "Código", "Funcionário", "Função", "Arquivo", "Admissão"]
        cols_valores = [c for c in df.columns if c not in cols_ignoradas]
        
        for col in cols_valores:
            df[col] = df[col].apply(limpar_valor)
            
        df_limpo = df.drop_duplicates(subset=[c for c in df.columns if c != 'Arquivo'])
        df_limpo = df_limpo.loc[~(df_limpo[cols_valores] == 0).all(axis=1)]
        
        chaves = ['Empresa', 'Empresa CNPJ', 'Código', 'Funcionário', 'Função', 'Admissão']
        df_agrupado = df_limpo.groupby(chaves, as_index=False)[cols_valores].sum()
        df_arq = df_limpo[['Empresa CNPJ', 'Código', 'Arquivo']].drop_duplicates(subset=['Empresa CNPJ', 'Código'], keep='first')
        return pd.merge(df_agrupado, df_arq, on=['Empresa CNPJ', 'Código'], how='left')
    return pd.DataFrame()

# --- INTERFACE ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📄 Folha", "🚑 Assistencial", "💰 Líquido", "➕ Extras", "📊 Consolidação", "📈 Dashboard"])

if 'dfs' not in st.session_state: st.session_state.dfs = {}

with tab1:
    st.header("Upload da Folha")
    up_folha = st.file_uploader("PDFs Folha", type="pdf", accept_multiple_files=True, key="u_folha")
    if up_folha:
        df_folha = processar_folha(up_folha)
        st.session_state.dfs['Folha'] = df_folha
        st.success(f"{len(df_folha)} registros.")
        st.dataframe(df_folha.head())

with tab2:
    st.header("Upload Assistencial")
    up_assist = st.file_uploader("PDF Assistencial", type="pdf", accept_multiple_files=True, key="u_assist")
    if up_assist:
        df_assist = processar_assistencial(up_assist)
        st.session_state.dfs['Assistencial'] = df_assist
        st.success(f"{len(df_assist)} registros.")
        st.dataframe(df_assist.head())

with tab3:
    st.header("Upload Líquidos")
    up_liq = st.file_uploader("PDF Líquido", type="pdf", accept_multiple_files=True, key="u_liq")
    if up_liq:
        df_liq = processar_liquidos(up_liq)
        st.session_state.dfs['Liquido'] = df_liq
        st.success(f"{len(df_liq)} registros.")
        st.dataframe(df_liq.head())

with tab4:
    st.header("Upload Extras")
    up_extras = st.file_uploader("PDFs Extras", type="pdf", accept_multiple_files=True, key="u_extras")
    if up_extras:
        df_extras = processar_extras(up_extras)
        st.session_state.dfs['Extras'] = df_extras
        st.success(f"{len(df_extras)} registros.")
        st.dataframe(df_extras, use_container_width=True)


with tab5:
    st.header("Consolidação e Validação de Dados")
    
    if st.button("Processar e Unificar Dados"):
        dfs = st.session_state.dfs
        
        # --- 1. PREPARAÇÃO DOS DADOS (NORMALIZAÇÃO DE CHAVES) ---
        lista_para_consolidar = []
        
        # Função interna para garantir chaves idênticas em todas as tabelas
        def padronizar_dataframe(df_orig, nome_origem):
            df = df_orig.copy()
            # Garante que 'Código' seja um número inteiro (remove zeros à esquerda e espaços)
            # 'errors=coerce' transforma textos não numéricos em NaN, depois preenchemos com 0
            df['KEY_COD'] = pd.to_numeric(df['Código'], errors='coerce').fillna(0).astype(int)
            
            # Garante CNPJ apenas números
            df['KEY_CNPJ'] = df['Empresa CNPJ'].apply(lambda x: re.sub(r'\D', '', str(x)))
            
            # Adiciona sufixo nas colunas de VALOR para saber a origem (exceto Folha que é a base)
            if nome_origem != 'Folha':
                cols_renomear = {c: f"{c}_{nome_origem}" for c in df.columns 
                                 if c not in ['Empresa', 'Funcionário', 'KEY_COD', 'KEY_CNPJ', 'Código', 'Empresa CNPJ']}
                df = df.rename(columns=cols_renomear)
            
            # Retorna apenas as colunas essenciais + chaves
            # Removemos colunas repetidas de texto para não poluir (mantemos só na Folha ou primeira ocorrencia)
            cols_drop = ['Empresa', 'Funcionário', 'Função', 'Arquivo', 'Código', 'Empresa CNPJ']
            if nome_origem != 'Folha':
                df = df.drop(columns=[c for c in cols_drop if c in df.columns], errors='ignore')
                
            return df

        # Processa FOLHA
        if 'Folha' in dfs and not dfs['Folha'].empty:
            df_base = dfs['Folha'].copy()
            df_base['KEY_COD'] = pd.to_numeric(df_base['Código'], errors='coerce').fillna(0).astype(int)
            df_base['KEY_CNPJ'] = df_base['Empresa CNPJ'].apply(lambda x: re.sub(r'\D', '', str(x)))
            lista_para_consolidar.append(df_base)
        
        # Processa OUTRAS TABELAS
        for nome_aba in ['Assistencial', 'Liquido', 'Extras']:
            if nome_aba in dfs and not dfs[nome_aba].empty:
                df_padrao = padronizar_dataframe(dfs[nome_aba], nome_aba)
                lista_para_consolidar.append(df_padrao)

        # --- 2. MOTOR DE CONSOLIDAÇÃO (OUTER JOIN) ---
        if not lista_para_consolidar:
            st.warning("Nenhum dado carregado para consolidar.")
        else:
            df_final = lista_para_consolidar[0]
            
            for df_temp in lista_para_consolidar[1:]:
                # Outer Join: Mantém dados mesmo se não existir na tabela base
                df_final = pd.merge(df_final, df_temp, on=['KEY_COD', 'KEY_CNPJ'], how='outer')

            # --- 3. LIMPEZA FINAL E SOMA INTELIGENTE ---
            
            # Preenche vazios numéricos com 0.00
            cols_num = df_final.select_dtypes(include=['number']).columns
            df_final[cols_num] = df_final[cols_num].fillna(0.0)
            
            # Preenche textos vazios (ex: Funcionário que só existia no Extra e veio NaN no merge)
            cols_text = df_final.select_dtypes(include=['object']).columns
            df_final[cols_text] = df_final[cols_text].fillna("-")

            # --- 4. AGRUPAMENTO FINAL (CORREÇÃO DE DUPLICIDADE) ---
            # Se houver linhas duplicadas por causa do merge, somamos aqui.
            # Agrupamos pelas chaves normalizadas
            
            # Identificamos colunas de identificação (que não devem ser somadas)
            cols_id = ['KEY_COD', 'KEY_CNPJ']
            # Tentamos recuperar nome/empresa se existirem
            if 'Funcionário' in df_final.columns: cols_id.append('Funcionário')
            if 'Empresa' in df_final.columns: cols_id.append('Empresa')

            # Define regra: Números -> SOMA. Textos -> MANTÉM O PRIMEIRO.
            agg_rules = {}
            for col in df_final.columns:
                if col not in cols_id:
                    if col in cols_num:
                        agg_rules[col] = 'sum'
                    else:
                        agg_rules[col] = 'first'
            
            # O Grande GroupBy que corrige os valores
            df_consolidado = df_final.groupby(cols_id, as_index=False).agg(agg_rules)
            
            # Remove as chaves auxiliares para exportação limpa
            df_consolidado['Código'] = df_consolidado['KEY_COD']
            df_consolidado.drop(columns=['KEY_COD', 'KEY_CNPJ'], inplace=True)

            st.session_state['df_consolidado_cache'] = df_consolidado
            st.success("Dados consolidados e somados com sucesso!")

    # --- EXIBIÇÃO ---
    if 'df_consolidado_cache' in st.session_state:
        df_show = st.session_state['df_consolidado_cache']
        st.divider()
        
        # Filtros Automáticos
        cols_numericas = df_show.select_dtypes(include=['number']).columns.tolist()
        cols_texto = df_show.select_dtypes(exclude=['number']).columns.tolist()
        
        # Seleção de colunas inteligente
        st.subheader("Visualização")
        cols_usuario = st.multiselect(
            "Selecione as colunas:", 
            options=df_show.columns,
            default=cols_texto[:3] + cols_numericas[:5] # Padrão: 3 primeiros textos, 5 primeiros números
        )
        
        if cols_usuario:
            df_view = df_show[cols_usuario]
            
            # KPI Rápido
            col_liq = next((c for c in df_view.columns if 'Líquido' in c), None)
            if col_liq:
                total = df_view[col_liq].sum()
                st.metric("Total da Coluna Líquido Selecionada", f"R$ {total:,.2f}")
            
            st.dataframe(df_view.head(50))
            
            # Exportação
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_view.to_excel(writer, sheet_name='Consolidado', index=False)
                # Abas de origem para conferência
                for nome, df in st.session_state.dfs.items():
                    df.to_excel(writer, sheet_name=f"Orig_{nome}", index=False)
                    
            st.download_button("📥 Baixar Planilha Consolidada", buffer, "Relatorio_Final_RH.xlsx")

# --- ABA 6: DASHBOARD & ANÁLISE ---
with tab6:
    st.header("📈 Dashboard Gerencial de RH")

    if 'df_consolidado_cache' not in st.session_state:
        st.info("⚠️ Processe a consolidação na **Aba 5** primeiro para visualizar os gráficos.")
    else:
        df_dash = st.session_state['df_consolidado_cache'].copy()
        
        # 1. GARANTIA DE TIPAGEM E COLUNAS
        # Lista de colunas numéricas que vamos usar nos gráficos
        cols_numericas_esperadas = [
            'Total Proventos', 'Líquido a Receber', 'Total Extras',
            'D.S.R. Sobre Horas Extras', 'Horas Extras 50%', 
            'Adicional Noturno Horas 20%', 'Bonificação Extraordinária', 
            'DSR Adicional Noturno', 'Hora Extras 100%'
        ]
        
        # Garante que as colunas existam e sejam números (float)
        for c in cols_numericas_esperadas:
            if c not in df_dash.columns:
                df_dash[c] = 0.0
            else:
                df_dash[c] = df_dash[c].fillna(0).astype(float)

        # --- 2. KPIs (LINHA SUPERIOR) ---
        st.subheader("Visão Geral do Mês")
        c1, c2, c3, c4 = st.columns(4)
        
        total_bruto = df_dash['Total Proventos'].sum()
        total_liquido = df_dash['Líquido a Receber'].sum()
        total_extras = df_dash['Total Extras'].sum()
        headcount = df_dash['Funcionário'].nunique() # Conta funcionários únicos
        
        c1.metric("👥 Headcount", f"{headcount}")
        c2.metric("💰 Folha Bruta (Total)", f"R$ {total_bruto:,.2f}")
        c3.metric("💸 Líquido a Pagar", f"R$ {total_liquido:,.2f}")
        c4.metric("➕ Total de Extras", f"R$ {total_extras:,.2f}")
        
        st.divider()
        
        # --- 3. GRÁFICOS (LINHA 1) ---
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("🏆 Top 10 Maiores Líquidos")
            # Ordena e pega os 10 maiores
            df_top10 = df_dash.nlargest(10, 'Líquido a Receber')[['Funcionário', 'Líquido a Receber', 'Função']].sort_values('Líquido a Receber', ascending=True)
            
            fig_bar = px.bar(
                df_top10, 
                x='Líquido a Receber', 
                y='Funcionário', 
                orientation='h',
                text_auto='.2s',
                color='Líquido a Receber',
                color_continuous_scale='Blues',
                hover_data=['Função']
            )
            fig_bar.update_layout(xaxis_title="Valor Líquido (R$)", yaxis_title=None)
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_g2:
            st.subheader("🧩 Composição dos Extras (Onde gastamos?)")
            # Cria um dataframe somando as colunas de tipos de extras para ver o peso de cada um
            cols_detalhe_extras = [
                'Horas Extras 50%', 'Hora Extras 100%', 
                'Adicional Noturno Horas 20%', 'DSR Adicional Noturno', 
                'D.S.R. Sobre Horas Extras', 'Bonificação Extraordinária'
            ]
            # Filtra apenas as que existem no dataframe atual
            cols_existentes = [c for c in cols_detalhe_extras if c in df_dash.columns]
            
            if cols_existentes:
                soma_extras = df_dash[cols_existentes].sum().reset_index()
                soma_extras.columns = ['Tipo de Extra', 'Valor Total']
                
                # Gráfico de Rosca
                fig_pie = px.pie(
                    soma_extras, 
                    values='Valor Total', 
                    names='Tipo de Extra', 
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_pie.update_traces(textinfo='percent+label')
                st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("Colunas detalhadas de extras não encontradas ou zeradas.")

        # --- 4. GRÁFICOS (LINHA 2) ---
        col_g3, col_g4 = st.columns(2)
        
        with col_g3:
            st.subheader("📊 Distribuição de Salários")
            # Histograma para ver a concentração de faixas salariais
            fig_hist = px.histogram(
                df_dash, 
                x='Líquido a Receber', 
                nbins=20, 
                color_discrete_sequence=['#3b82f6'],
                title="Faixas de Pagamento Líquido"
            )
            fig_hist.update_layout(xaxis_title="Valor (R$)", yaxis_title="Qtd. Funcionários", bargap=0.1)
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_g4:
            st.subheader("🏢 Top 5 Funções com mais Extras")
            if 'Função' in df_dash.columns:
                # Agrupa por função e soma os extras
                df_funcao = df_dash.groupby('Função')['Total Extras'].sum().reset_index()
                df_funcao = df_funcao.nlargest(5, 'Total Extras').sort_values('Total Extras', ascending=True)
                
                fig_funcao = px.bar(
                    df_funcao,
                    x='Total Extras',
                    y='Função',
                    orientation='h',
                    text_auto='.2s',
                    color='Total Extras',
                    color_continuous_scale='Reds'
                )
                st.plotly_chart(fig_funcao, use_container_width=True)
            else:
                st.warning("Coluna 'Função' não encontrada na base.")
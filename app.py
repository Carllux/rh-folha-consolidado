import streamlit as st
import pandas as pd
import pdfplumber
import re
import os
from datetime import datetime
from io import BytesIO
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Processador de RH Pro", layout="wide")
st.title("📂 Sistema de Consolidação de Documentos de RH (Local + Retenção)")

# --- 0. SETUP DE DIRETÓRIOS E CONFIGURAÇÕES ---
PASTA_CONFIG = "config"
ARQUIVO_REGRAS = os.path.join(PASTA_CONFIG, "regras_processamento.csv")
PASTA_RETENCAO = "retencao"

def setup_inicial():
    """Cria a estrutura de pastas necessária para rodar localmente"""
    if not os.path.exists(PASTA_CONFIG):
        os.makedirs(PASTA_CONFIG)
    if not os.path.exists(PASTA_RETENCAO):
        os.makedirs(PASTA_RETENCAO)

def carregar_regras():
    """Carrega regras do CSV local ou usa padrão se não existir"""
    if os.path.exists(ARQUIVO_REGRAS):
        try:
            return pd.read_csv(ARQUIVO_REGRAS)
        except:
            st.error("Erro ao ler arquivo de configuração. Usando padrão.")
    
    # Dados Iniciais (Padrão)
    return pd.DataFrame([
        # EXTRAS
        {"Texto Identificador": "82 - Hora Extras 100%", "Nome Evento": "Hora Extras 100%", "Categoria": "Extras"},
        {"Texto Identificador": "106 - Adicional Noturno Horas 20%", "Nome Evento": "Adicional Noturno Horas 20%", "Categoria": "Extras"},
        {"Texto Identificador": "17 - Horas Extras 50%", "Nome Evento": "Horas Extras 50%", "Categoria": "Extras"},
        {"Texto Identificador": "5 - D.S.R. Sobre Horas Extras", "Nome Evento": "D.S.R. Sobre Horas Extras", "Categoria": "Extras"},
        {"Texto Identificador": "1025 - PTS", "Nome Evento": "PTS", "Categoria": "Extras"},
        {"Texto Identificador": "152 - DSR Adicional Noturno", "Nome Evento": "DSR Adicional Noturno", "Categoria": "Extras"},
        {"Texto Identificador": "1394 - Bonificação Extraordinária", "Nome Evento": "Bonificação Extraordinária", "Categoria": "Extras"},
        {"Texto Identificador": "1173 - Reembolso Vale Refeição", "Nome Evento": "Reembolso Vale Refeição", "Categoria": "Extras"},
        {"Texto Identificador": "1098 - Reembolso Vale Transporte", "Nome Evento": "Reembolso Vale Transporte", "Categoria": "Extras"},
        # FOLHA
        {"Texto Identificador": "Folha de Pagamento - Adiantamento", "Nome Evento": "Adiantamento", "Categoria": "Folha"},
        {"Texto Identificador": "Folha de Pagamento", "Nome Evento": "Folha Mensal", "Categoria": "Folha"}
    ])

def salvar_regras_localmente(df):
    """Persiste as regras no disco"""
    df.to_csv(ARQUIVO_REGRAS, index=False)

def salvar_arquivos_retencao(arquivos, categoria):
    """Salva cópia dos arquivos de upload na pasta de retenção local"""
    if not arquivos: return
    
    # Cria pasta do dia: retencao/2023-10-27/Folha/
    hoje = datetime.now().strftime("%Y-%m-%d")
    caminho_destino = os.path.join(PASTA_RETENCAO, hoje, categoria)
    
    if not os.path.exists(caminho_destino):
        os.makedirs(caminho_destino)
        
    count = 0
    for arquivo in arquivos:
        try:
            # Reseta o ponteiro do arquivo para ler desde o início
            arquivo.seek(0)
            with open(os.path.join(caminho_destino, arquivo.name), "wb") as f:
                f.write(arquivo.getbuffer())
            count += 1
        except Exception as e:
            st.error(f"Erro na retenção de {arquivo.name}: {e}")
    
    if count > 0:
        st.toast(f"💾 {count} arquivos salvos em '{caminho_destino}'")

# Executa setup ao carregar
setup_inicial()
if 'df_regras' not in st.session_state:
    st.session_state['df_regras'] = carregar_regras()

# --- FUNÇÕES AUXILIARES DE DADOS ---
def limpar_valor(valor_str):
    if pd.isna(valor_str) or valor_str == "": return 0.0
    if isinstance(valor_str, float): return valor_str
    return float(str(valor_str).replace('.', '').replace(',', '.'))

def obter_regras_por_categoria(categoria):
    df = st.session_state['df_regras']
    return df[df['Categoria'] == categoria]

# --- 1. FUNÇÃO: EXTRAIR LÍQUIDO ---
def processar_liquidos(uploaded_files):
    dados_extraidos = []
    padrao_liquido = re.compile(r'^\s*(\d+)\s+(.+?)\s+(\d{3}\.\d{3}\.\d{3}-\d{2})\s+(\d{2}/\d{2}/\d{4})\s+([\d\.,]+)')
    regex_cnpj_generico = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                for pagina in pdf.pages:
                    texto = pagina.extract_text() or ""
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"
                    for linha in texto.split('\n'):
                        match = padrao_liquido.search(linha)
                        if match:
                            codigo, nome, cpf, data, valor = match.groups()
                            dados_extraidos.append({
                                "Empresa CNPJ": cnpj_encontrado, "Código": codigo, "Funcionário": nome.strip(),
                                "CPF": cpf, "Data Pagto": data, "Valor Líquido": limpar_valor(valor), "Arquivo": file.name
                            })
        except Exception as e: st.error(f"Erro {file.name}: {e}")
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
                    texto = pagina.extract_text() or ""
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"
                    linhas = texto.split('\n')
                    for i, linha in enumerate(linhas):
                        if regex_linha_nome.search(linha):
                            match_nome = regex_linha_nome.search(linha)
                            if i + 1 < len(linhas):
                                match_valores = regex_linha_valores.search(linhas[i+1])
                                if match_valores:
                                    cod, nome, funcao = match_nome.groups()
                                    admissao, salario, valor_desc = match_valores.groups()
                                    dados_assistencial.append({
                                        "Empresa CNPJ": cnpj_encontrado, "Código": cod, "Funcionário": nome.strip(),
                                        "Função": funcao.strip(), "Admissão": admissao, "Salário Base": limpar_valor(salario),
                                        "Valor Assistencial": limpar_valor(valor_desc), "Arquivo Original": file.name
                                    })
        except Exception as e: st.error(f"Erro {file.name}: {e}")
    return pd.DataFrame(dados_assistencial)

# --- 3. FUNÇÃO: EXTRAIR EXTRAS ---
def processar_extras(uploaded_files):
    dados_extras = []
    regex_linha = re.compile(r'^\s*(\d+)\s+(.+?)\s+([\d\.,]+)\s+([\d\.,]+)$')
    regex_linha_alt = re.compile(r'^\s*(\d+)\s+(.+?)\s+([\d\.,]+)$') 
    regex_cnpj_generico = re.compile(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}')
    
    df_regras = obter_regras_por_categoria("Extras")

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                texto_completo = "".join([p.extract_text() or "" for p in pdf.pages[:2]])
                
                tipo_evento = "Outros Extras - Não Identificado"
                for _, row in df_regras.iterrows():
                    if str(row['Texto Identificador']).strip() in texto_completo:
                        tipo_evento = row['Nome Evento']
                        break
                
                if tipo_evento == "Outros Extras - Não Identificado":
                    st.warning(f"Extra não identificado em '{file.name}'. Verifique a aba Configurações.")

                for pagina in pdf.pages:
                    texto = pagina.extract_text() or ""
                    match_cnpj = regex_cnpj_generico.search(texto)
                    cnpj_encontrado = match_cnpj.group(0) if match_cnpj else "Não Encontrado"
                    for linha in texto.split('\n'):
                        match = regex_linha.search(linha)
                        val_enc = None
                        if match:
                            cod, nome, _, val = match.groups()
                            val_enc = val
                        elif regex_linha_alt.search(linha):
                            cod, nome, val = regex_linha_alt.search(linha).groups()
                            val_enc = val
                        
                        if val_enc:
                            dados_extras.append({
                                "Empresa CNPJ": cnpj_encontrado, "Código": str(int(cod)), 
                                "Funcionário": nome.strip(), "Tipo Evento": tipo_evento,
                                "Valor": limpar_valor(val_enc)
                            })
        except Exception as e: st.error(f"Erro {file.name}: {e}")

    if dados_extras:
        df = pd.DataFrame(dados_extras)
        df_pivot = df.pivot_table(index=['Empresa CNPJ', 'Código', 'Funcionário'], columns='Tipo Evento', values='Valor', aggfunc='sum', fill_value=0.0).reset_index()
        for col in df_regras['Nome Evento'].unique():
            if col not in df_pivot.columns: df_pivot[col] = 0.0
        
        cols_num = [c for c in df_pivot.columns if c not in ['Empresa CNPJ', 'Código', 'Funcionário']]
        df_pivot['Total Extras'] = df_pivot[cols_num].sum(axis=1)
        return df_pivot
    return pd.DataFrame()

# --- 4. FUNÇÃO: EXTRAIR FOLHA COMPLETA (ATUALIZADA) ---
def processar_folha(uploaded_files):
    dados_folha = []
    
    # Regex de Identificação do Funcionário (Mantido)
    # O (?:Dep|$) no final ajuda a parar a captura antes da coluna de Departamento
    regex_inicio = re.compile(r'Cód:\s*(\d+).*?Nome:\s*(.*?)\s+Função:(.*?)(?:Dep|Depto|$)') 
    
    # Regex de Contrato (Mantido)
    regex_contrato = re.compile(r'Admissão:\s*(\d{2}/\d{2}/\d{4}).*?Salário:\s*([,.\d]+)')
    
    # Regex de Cabeçalho (CNPJ e Razão Social)
    regex_razao_social = re.compile(r'(?:Apelido:.*?|\s*)Razão Social:\s*(.*?)(?:\s+CNPJ/CEI:|\s+Pág:|\n|$)', re.IGNORECASE)
    regex_cnpj_cei = re.compile(r'CNPJ/CEI:([\d\./\-]+)', re.IGNORECASE)
    
    # Regex de Totais (Mantido)
    regex_totais = re.compile(r'Proventos:\s*([\d\.,]+).*?Descontos:\s*([\d\.,]+).*?Liquido:\s*([\d\.,]+)')
    
    # --- MAPEAMENTO DE ITENS (ATUALIZADO PARA ACEITAR ESPAÇOS) ---
    # Adicionamos \s* depois do \d+ para aceitar "1 Salário" ou "1Salário"
    itens_map = {
        # PROVENTOS
        "Salário Provento": re.compile(r'\d+\s*Salário\s+[\d\.,]+\s+([\d\.,]+)'),
        "Adiantamento Crédito": re.compile(r'\d+\s*Adiantamento Crédito\s+[\d\.,]+\s+([\d\.,]+)'), # Adicionado para ler o Adiantamento
        "D.S.R. Sobre Horas Extras": re.compile(r'\d+\s*D\.S\.R\. Sobre Horas Extras\s+([\d\.,]+)'),
        "Horas Extras 50%": re.compile(r'\d+\s*Horas Extras 50%\s+[\d\.,]+\s+([\d\.,]+)'),
        "Horas Extras 100%": re.compile(r'\d+\s*Horas Extras 100%\s+[\d\.,]+\s+([\d\.,]+)'), # Caso exista
        "Reembolso Vale Transporte": re.compile(r'\d+\s*Reembolso Vale Transporte\s+([\d\.,]+)'),
        
        # DESCONTOS
        "INSS Sobre Salário": re.compile(r'\d+\s*INSS Sobre Salário\s+[\d\.,]+\s+([\d\.,]+)'),
        "IRRF Sobre Salário": re.compile(r'\d+\s*IRRF Sobre Salário\s+[\d\.,]+\s+([\d\.,]+)'),
        "Desc. Vale Transporte": re.compile(r'\d+\s*Desc\. Vale Transporte\s+[\d\.,]+\s+([\d\.,]+)'),
        "Contribuição Assistencial": re.compile(r'\d+\s*Contribuição Assistencial\s+[\d\.,]+'),
        "Faltas": re.compile(r'\d+\s*Faltas\s+[\d\.,]+\s+([\d\.,]+)'),
        
        # BASES (Rodapé do funcionário)
        "Base INSS Empresa": re.compile(r'Base INSS Empresa:\s*([\d\.,]+)'),
        "Base INSS Funcionário": re.compile(r'Base INSS Funcionário:\s*([\d\.,]+)'),
        "Base F.G.T.S.": re.compile(r'Base F\.G\.T\.S\.:\s*([\d\.,]+)'),
        "F.G.T.S.": re.compile(r'(?<!Base )F\.G\.T\.S\.:\s*([\d\.,]+)'), # Lookbehind para não pegar a Base
        "Base I.R.R.F.": re.compile(r'Base I\.R\.R\.F\.:\s*([\d\.,]+)')
    }

    df_regras_folha = obter_regras_por_categoria("Folha")

    for file in uploaded_files:
        try:
            with pdfplumber.open(file) as pdf:
                empresa_nome, empresa_cnpj = "Não Encontrado", "Não Encontrado"
                primeira_pag_texto = ""
                
                # Leitura do Cabeçalho Global do Arquivo
                if len(pdf.pages) > 0:
                    primeira_pag_texto = pdf.pages[0].extract_text() or ""
                    match_rz = regex_razao_social.search(primeira_pag_texto)
                    if match_rz: empresa_nome = match_rz.group(1).strip()
                    match_cnpj = regex_cnpj_cei.search(primeira_pag_texto)
                    if match_cnpj: empresa_cnpj = match_cnpj.group(1).strip()

                # Identificação do Tipo de Folha
                tipo_folha = "Folha Geral"
                for _, row in df_regras_folha.iterrows():
                    if str(row['Texto Identificador']).strip() in primeira_pag_texto:
                        tipo_folha = row['Nome Evento']
                        break
                
                # Processamento Página a Página
                for pagina in pdf.pages:
                    texto = pagina.extract_text() or ""
                    # Atualiza CNPJ se mudar na página (comum em arquivos com múltiplas filiais)
                    match_cnpj_pag = regex_cnpj_cei.search(texto)
                    if match_cnpj_pag: empresa_cnpj = match_cnpj_pag.group(1).strip()
                    
                    func_atual = {}
                    
                    for linha in texto.split('\n'):
                        # 1. Tenta identificar Início de Funcionário
                        match_inicio = regex_inicio.search(linha)
                        if match_inicio:
                            # Se já tinha um funcionário aberto não fechado, salva (precaução)
                            if func_atual and "Líquido a Receber" not in func_atual:
                                # Opcional: Log de aviso que fechou forçado
                                pass 
                                
                            cod, nome, funcao = match_inicio.groups()
                            func_atual = {
                                "Empresa": empresa_nome, "Empresa CNPJ": empresa_cnpj, "Código": cod, 
                                "Funcionário": nome.strip(), "Função": funcao.strip(), "Arquivo": file.name, "Tipo Folha": tipo_folha,
                                "Total Proventos": "0,00", "Total Descontos": "0,00", "Líquido a Receber": "0,00"
                            }
                            # Inicializa colunas do map com 0,00
                            for k in itens_map.keys(): func_atual[k] = "0,00"
                            continue

                        # 2. Se estamos dentro de um bloco de funcionário, busca os dados
                        if func_atual:
                            # Dados Contratuais
                            match_ct = regex_contrato.search(linha)
                            if match_ct:
                                func_atual["Admissão"] = match_ct.group(1)
                                func_atual["Salário Base Contratual"] = match_ct.group(2)
                            
                            # Itens Financeiros (Varre todos os regex do mapa contra a linha atual)
                            for k, rgx in itens_map.items():
                                match_item = rgx.search(linha)
                                if match_item:
                                    if k == "Contribuição Assistencial": 
                                        # Se a contribuição não tiver valor explícito na linha, assume fixo (regra de negócio sua)
                                        # Caso tenha grupo de captura no regex, usa ele.
                                        if rgx.groups: func_atual[k] = match_item.group(1)
                                        else: func_atual[k] = "10,00"
                                    else: 
                                        func_atual[k] = match_item.group(1)
                            
                            # Totais / Fechamento
                            match_tot = regex_totais.search(linha)
                            if match_tot:
                                func_atual["Total Proventos"], func_atual["Total Descontos"], func_atual["Líquido a Receber"] = match_tot.groups()
                                dados_folha.append(func_atual)
                                func_atual = {} # Limpa para o próximo
                                
        except Exception as e: st.error(f"Erro ao processar {file.name}: {e}")

    if dados_folha:
        df = pd.DataFrame(dados_folha)
        cols_ignorar = ["Empresa", "Empresa CNPJ", "Código", "Funcionário", "Função", "Arquivo", "Admissão", "Tipo Folha"]
        for c in df.columns:
            if c not in cols_ignorar: df[c] = df[c].apply(limpar_valor)
        return df
        
    return pd.DataFrame()

# --- INTERFACE ---
tab1, tab2, tab3, tab4, tab5, tab6, tab_config = st.tabs(["📄 Folha", "🚑 Assistencial", "💰 Líquido", "➕ Extras", "📊 Consolidação", "📈 Dashboard", "⚙️ Configurações"])

if 'dfs' not in st.session_state: st.session_state.dfs = {}

with tab1:
    st.header("Upload da Folha")
    up_folha = st.file_uploader("PDFs Folha", type="pdf", accept_multiple_files=True, key="u_folha")
    if up_folha:
        # AÇÃO DE RETENÇÃO
        salvar_arquivos_retencao(up_folha, "Folha")
        # PROCESSAMENTO
        df_folha = processar_folha(up_folha)
        st.session_state.dfs['Folha'] = df_folha
        st.success(f"{len(df_folha)} registros.")
        st.dataframe(df_folha.head())

with tab2:
    st.header("Upload Assistencial")
    up_assist = st.file_uploader("PDF Assistencial", type="pdf", accept_multiple_files=True, key="u_assist")
    if up_assist:
        salvar_arquivos_retencao(up_assist, "Assistencial")
        df_assist = processar_assistencial(up_assist)
        st.session_state.dfs['Assistencial'] = df_assist
        st.success(f"{len(df_assist)} registros.")
        st.dataframe(df_assist.head())

with tab3:
    st.header("Upload Líquidos")
    up_liq = st.file_uploader("PDF Líquido", type="pdf", accept_multiple_files=True, key="u_liq")
    if up_liq:
        salvar_arquivos_retencao(up_liq, "Liquido")
        df_liq = processar_liquidos(up_liq)
        st.session_state.dfs['Liquido'] = df_liq
        st.success(f"{len(df_liq)} registros.")
        st.dataframe(df_liq.head())

with tab4:
    st.header("Upload Extras")
    up_extras = st.file_uploader("PDFs Extras", type="pdf", accept_multiple_files=True, key="u_extras")
    if up_extras:
        salvar_arquivos_retencao(up_extras, "Extras")
        df_extras = processar_extras(up_extras)
        st.session_state.dfs['Extras'] = df_extras
        if not df_extras.empty:
            st.success(f"{len(df_extras)} registros.")
            st.dataframe(df_extras, use_container_width=True)

with tab5:
    st.header("Consolidação")
    if st.button("Processar Dados"):
        dfs = st.session_state.dfs
        lista = []
        
        def preparar(df_in, origem):
            df = df_in.copy()
            df['KEY_COD'] = pd.to_numeric(df['Código'], errors='coerce').fillna(0).astype(int)
            df['KEY_CNPJ'] = df['Empresa CNPJ'].apply(lambda x: re.sub(r'\D', '', str(x)))
            if origem == 'Folha':
                if 'Tipo Folha' not in df.columns: df['Tipo Folha'] = 'Mensal'
                df['KEY_TIPO'] = df['Tipo Folha'] + "_" + df['Arquivo']
            else: df['KEY_TIPO'] = 'GERAL'
            
            if origem != 'Folha':
                cols_renomear = {c: f"{c}_{origem}" for c in df.columns if c not in ['Empresa', 'Funcionário', 'KEY_COD', 'KEY_CNPJ', 'KEY_TIPO', 'Código', 'Empresa CNPJ']}
                df = df.rename(columns=cols_renomear)
                df = df.drop(columns=['Empresa', 'Funcionário', 'Função', 'Arquivo', 'Código', 'Empresa CNPJ', 'Tipo Folha'], errors='ignore')
            return df

        if 'Folha' in dfs and not dfs['Folha'].empty:
            lista.append(preparar(dfs['Folha'], 'Folha'))
        
        for aba in ['Assistencial', 'Liquido', 'Extras']:
            if aba in dfs and not dfs[aba].empty:
                df_p = preparar(dfs[aba], aba)
                df_p = df_p.drop(columns=['KEY_TIPO'], errors='ignore')
                lista.append(df_p)

        if not lista: st.warning("Sem dados.")
        else:
            df_final = lista[0]
            for df_t in lista[1:]: df_final = pd.merge(df_final, df_t, on=['KEY_COD', 'KEY_CNPJ'], how='left')

            cols_num = df_final.select_dtypes(include=['number']).columns
            df_final[cols_num] = df_final[cols_num].fillna(0.0)
            df_final = df_final.fillna("-")

            cols_gb = ['KEY_COD', 'KEY_CNPJ', 'KEY_TIPO']
            for c in ['Funcionário', 'Empresa', 'Tipo Folha', 'Arquivo']:
                if c in df_final.columns: cols_gb.append(c)
            
            agg = {c: 'sum' if c in cols_num else 'first' for c in df_final.columns if c not in cols_gb}
            df_cons = df_final.groupby(cols_gb, as_index=False).agg(agg)
            df_cons['Código'] = df_cons['KEY_COD']
            df_cons.drop(columns=['KEY_COD', 'KEY_CNPJ', 'KEY_TIPO'], inplace=True, errors='ignore')

            st.session_state['df_consolidado'] = df_cons
            st.success("Dados Consolidados com Sucesso!")

    if 'df_consolidado' in st.session_state:
        df_show = st.session_state['df_consolidado']
        cols = st.multiselect("Colunas:", df_show.columns, default=list(df_show.columns)[:8])
        if cols:
            st.dataframe(df_show[cols].head(50))
            
            towrite = BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                # df_show[cols].to_excel(writer, sheet_name='Consolidado', index=False)
                for key, df_orig in st.session_state.dfs.items():
                    if not df_orig.empty:
                        sheet_name = f"Orig_{key}"[:31]
                        df_orig.to_excel(writer, sheet_name=sheet_name, index=False)
            
            st.download_button("Baixar Excel (Multi-Abas)", towrite, "Relatorio_RH_Completo.xlsx")

with tab6:
    st.header("Dashboard")
    if 'df_consolidado' in st.session_state:
        df_d = st.session_state['df_consolidado'].copy()
        for c in ['Total Proventos', 'Líquido a Receber', 'Total Extras_Extras']:
             if c not in df_d.columns: df_d[c] = 0.0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Folha Total", f"R$ {df_d['Total Proventos'].sum():,.2f}")
        c2.metric("Líquido Total", f"R$ {df_d['Líquido a Receber'].sum():,.2f}")
        c3.metric("Registros", len(df_d))

with tab_config:
    st.header("⚙️ Configurações e Regras")
    st.info(f"📁 Pasta de Configurações: {ARQUIVO_REGRAS} | 📁 Pasta de Retenção: {PASTA_RETENCAO}")
    
    df_editado = st.data_editor(
        st.session_state['df_regras'],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Categoria": st.column_config.SelectboxColumn("Categoria", options=["Extras", "Folha"], required=True),
            "Texto Identificador": st.column_config.TextColumn("Texto Identificador", required=True),
            "Nome Evento": st.column_config.TextColumn("Nome do Evento", required=True)
        },
        key="editor_regras"
    )
    
    # SALVAMENTO AUTOMÁTICO DAS REGRAS NO DISCO
    if not df_editado.equals(st.session_state['df_regras']):
        st.session_state['df_regras'] = df_editado
        salvar_regras_localmente(df_editado)
        st.toast("✅ Regras salvas no disco com sucesso!")

    st.divider()
    col_d1, col_d2 = st.columns([1, 4])
    with col_d1:
        if st.button("🔄 Resetar Padrões"):
            if os.path.exists(ARQUIVO_REGRAS):
                os.remove(ARQUIVO_REGRAS)
            del st.session_state['df_regras']
            st.rerun()
    with col_d2:
        csv_backup = df_editado.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Baixar Backup", csv_backup, "backup_regras.csv", "text/csv")
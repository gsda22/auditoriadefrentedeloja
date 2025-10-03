import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
import pytz # Biblioteca para manipular fusos horários
from io import BytesIO

# --- Configurações Iniciais ---
DB_NAME = 'auditoria_caixa.db'
# Define o fuso horário de Brasília (America/Sao_Paulo)
BRASILIA_TZ = pytz.timezone('America/Sao_Paulo')
ADMIN_PASSWORD = "123456" # Senha de segurança para exclusão total

# Lista de opções de operadores e fiscais atualizada
PREVENTION_OFFICERS = ["GABRIEL", "EDUARDO", "JULIANA", "KAUÃ", "CARLA"]
SUPERVISORS = ["SIMONE", "JOICE", "SUZANA", "CAMILA", "ARLENE"]

# Operadores de Caixa (obtidos das imagens fornecidas, evitando repetições)
OPERATORS = [
    "ANGELA CAMILA FERREIRA DOS SAN", "ARLENE CRISTIANE RIBEIRO", 
    "CATIA CILENE CERQUEIRA", "Geisa Santos Santana", 
    "JAIANE SANTOS DE SOUZA", "JOSENILDA DE JESUS", 
    "Liliane Barbosa Lima", "MAIARA MACEDO DE ALMEIDA",
    "MARTINHA DE JESUS MACEDO", "MEIRILANE CORREIA MOTA",
    "ROSILENE OLIVEIRA SANTOS", "PATRICIA DE SOUZA",
    "REGIANE DA MOTA DOS SANTOS", "TREINAMENTO 01 - SUSSUCA 16-7"
]

# Lista de PDVs (1 a 20)
PDV_OPTIONS = [str(i) for i in range(1, 21)]

# Variáveis de estado
if 'last_audit_id' not in st.session_state:
    st.session_state.last_audit_id = 0
if 'audit_result' not in st.session_state:
    st.session_state.audit_result = None # Armazena o resultado do último registro para o alerta

# --- Funções do Banco de Dados SQLite ---

def init_db():
    """Inicializa o banco de dados e cria a tabela 'audits' se não existir."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdv_number TEXT NOT NULL,
            audit_datetime TEXT NOT NULL,
            operator_name TEXT,
            supervisor_name TEXT,
            prevention_name TEXT,
            counted_value REAL,
            expected_value REAL,
            difference REAL,
            tef_value REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_audit(pdv, operator, supervisor, prevention, counted, expected, difference, tef):
    """Salva um novo registro de auditoria no banco de dados."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Obtém a data e hora atual no fuso horário de Brasília
    now = datetime.now(BRASILIA_TZ).strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.execute('''
        INSERT INTO audits (pdv_number, audit_datetime, operator_name, supervisor_name, prevention_name, counted_value, expected_value, difference, tef_value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (pdv, now, operator, supervisor, prevention, counted, expected, difference, tef))
    
    last_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return last_id

def load_audits_filtered(start_date=None, end_date=None):
    """Carrega registros de auditoria do banco de dados, com filtros de data opcionais."""
    conn = sqlite3.connect(DB_NAME)
    query = "SELECT * FROM audits"
    conditions = []
    
    if start_date:
        conditions.append(f"audit_datetime >= '{start_date.strftime('%Y-%m-%d 00:00:00')}'")
    if end_date:
        # Garante que inclua o último segundo do dia final
        end_datetime_str = (end_date + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
        conditions.append(f"audit_datetime < '{end_datetime_str}'")
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY audit_datetime DESC"
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def delete_audit_by_id(audit_id):
    """Deleta uma única auditoria pelo seu ID."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM audits WHERE id = ?", (audit_id,))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count

def delete_all_audits():
    """Deleta todos os registros da tabela de auditorias."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM audits")
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count

# Inicializa o banco de dados ao iniciar o aplicativo
init_db()

# Função para converter DataFrame para Excel (XLSX)
@st.cache_data
def convert_df_to_excel(df):
    """Converte um DataFrame em um objeto BytesIO do Excel."""
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Auditorias')
    writer.close()
    processed_data = output.getvalue()
    return processed_data

# Funções para formatar e estilizar a tabela
def format_currency_br(val):
    """Formata um valor float para a moeda brasileira (R$) com 2 decimais."""
    if pd.isna(val):
        return 'R$ 0,00'
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def highlight_difference(s):
    """Destaque para diferença negativa (vermelho) ou positiva (verde)."""
    styles = []
    for val in s:
        # Vermelho (Negativo, Contado < TEF)
        if val < -0.005: 
            styles.append('background-color: #fcebeb; color: #cc0000; font-weight: bold;') 
        # Verde (Positivo, Contado > TEF)
        elif val > 0.005:
            styles.append('background-color: #ecfced; color: #008000; font-weight: bold;') 
        # Neutro (Zero)
        else:
            styles.append('')
    return styles

# --- Aplicação Streamlit ---

def app_main():
    # Configuração básica da página
    st.set_page_config(page_title="Auditoria de Caixa", layout="wide")

    # --- INJEÇÃO DE CSS PARA AUMENTO DE TAMANHO ---
    st.markdown("""
        <style>
        /* Aumenta o tamanho da fonte para todos os textos de input/select e seus labels */
        div[data-testid*="stNumberInput"] label p,
        div[data-testid*="stSelectbox"] label p {
            font-size: 1.25em; /* Aumenta o label */
            font-weight: bold;
        }
        /* Aumenta a altura e fonte dos campos de seleção */
        div[data-testid*="stSelectbox"] div.st-emotion-cache-1cypcdp {
            height: 3.5em; /* Aumenta a altura */
            font-size: 1.25em; /* Aumenta a fonte do texto selecionado */
        }
        /* Aumenta a altura e fonte dos campos de número/texto */
        div[data-testid*="stNumberInput"] input {
            height: 3.5em; /* Aumenta a altura */
            font-size: 1.5em; /* Aumenta a fonte do número */
        }
        /* Aumenta o botão principal de registro */
        div[data-testid="stForm"] button {
            height: 3.5em; /* Aumenta a altura */
            font-size: 1.5em; /* Aumenta a fonte do botão */
            padding: 10px 20px;
        }
        </style>
        """, unsafe_allow_html=True)

    # --- ALERTA NATIVO (Aumento Considerável) ---
    if st.session_state.audit_result is not None:
        result = st.session_state.audit_result
        
        pdv = result['pdv_number']
        difference = result['difference']
        counted_value = result['counted_value']
        tef_value = result['tef_value']
        
        diff_display = f"R$ {difference:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if difference < -0.005:
            title = f"QUEBRA DE CAIXA NO PDV {pdv}"
            # Uso de HTML para garantir o tamanho do texto do alerta
            message = f"""
            <h1 style='font-size: 2.5em;'>❌ {title}</h1>
            <h2 style='font-size: 2em;'>Diferença: <span style='color: #cc0000;'>{diff_display}</span></h2>
            <p style='font-size: 1.5em;'>🛑 O Valor Contado em Dinheiro ({format_currency_br(counted_value)}) é <b>MENOR</b> que o Valor Contado em TEF ({format_currency_br(tef_value)}).</p>
            """
            st.markdown(f'<div style="background-color: #fcebeb; padding: 25px; border-radius: 10px; border: 4px solid #cc0000;">{message}</div>', unsafe_allow_html=True)
            
        elif difference > 0.005:
            title = f"SOBRA DE CAIXA NO PDV {pdv}"
            message = f"""
            <h1 style='font-size: 2.5em;'>✅ {title}</h1>
            <h2 style='font-size: 2em;'>Diferença: <span style='color: #008000;'>{diff_display}</span></h2>
            <p style='font-size: 1.5em;'>⬆️ O Valor Contado em Dinheiro ({format_currency_br(counted_value)}) é <b>MAIOR</b> que o Valor Contado em TEF ({format_currency_br(tef_value)}).</p>
            """
            st.markdown(f'<div style="background-color: #ecfced; padding: 25px; border-radius: 10px; border: 4px solid #008000;">{message}</div>', unsafe_allow_html=True)

        else:
            title = f"CAIXA FECHADO NO PDV {pdv}"
            message = f"""
            <h1 style='font-size: 2.5em;'>👍 {title}</h1>
            <h2 style='font-size: 2em;'>Diferença: <span style='color: #00bfff;'>{diff_display}</span></h2>
            <p style='font-size: 1.5em;'>💰 O Valor Contado em Dinheiro e TEF estão <b>IGUAIS</b> em {format_currency_br(counted_value)}.</p>
            """
            st.markdown(f'<div style="background-color: #e0f7ff; padding: 25px; border-radius: 10px; border: 4px solid #00bfff;">{message}</div>', unsafe_allow_html=True)

        # Limpa o estado para que o alerta suma no próximo rerun
        st.session_state.audit_result = None 

    # --- FIM DO ALERTA NATIVO ---

    # Cabeçalho e Logo 
    logo_path = "logo.png" 
    
    col1, col2 = st.columns([1, 4])
    with col1:
        # Tenta carregar a logo. 
        try:
            st.image(logo_path, width=200) # Aumentando o tamanho da logo
        except FileNotFoundError:
            try:
                st.image("image_e026a7.png", caption="Logo", width=250)
            except:
                st.markdown("<p style='font-size: 60px; text-align: center;'>💵</p>", unsafe_allow_html=True)
            
    with col2:
        # Título principal maior (usando CSS simples injetado)
        st.markdown("<h1 style='font-size: 4em;'>Sistema de Auditoria de Caixa (SAC)</h1>", unsafe_allow_html=True)
        st.markdown("---")

    # Exibe a hora atual de Brasília
    current_time_br = datetime.now(BRASILIA_TZ).strftime('%d/%m/%Y %H:%M:%S')
    st.markdown(f"<div style='font-size: 1.25em;'>**Data e Hora de Brasília (BR):** {current_time_br}</div>", unsafe_allow_html=True)

    st.markdown("<h2 style='font-size: 2.5em;'>1. Iniciar Nova Auditoria</h2>", unsafe_allow_html=True)
    
    # Formulário para o registro da auditoria
    with st.form("audit_form"):
        
        # Detalhes de Identificação
        st.subheader("Identificação")
        colA, colB = st.columns(2)
        
        # Aumentando o tamanho dos elementos de input/select
        with colA:
            pdv_number = st.selectbox("Qual o Número do PDV?", options=PDV_OPTIONS, key='pdv_select')
            operator_name = st.selectbox("Operador(a) de Caixa", options=["Selecione..."] + OPERATORS, key='operator_select')
        
        with colB:
            supervisor_name = st.selectbox("Fiscal de Caixa", options=["Selecione..."] + SUPERVISORS, key='supervisor_select')
            prevention_name = st.selectbox("Prevenção que está realizando a auditoria", options=["Selecione..."] + PREVENTION_OFFICERS, key='prevention_select')

        st.markdown("<hr style='border: 1px solid #ccc;'>", unsafe_allow_html=True)
        
        # Detalhes Financeiros
        st.subheader("Valores Contados")
        
        colD, colE = st.columns(2)
        
        with colD:
            # Valor contado (o que foi fisicamente contado em Dinheiro)
            counted_value = st.number_input("Valor Contado em Dinheiro (R$)", min_value=0.00, format="%.2f", step=0.01, value=0.00, key='counted_input')

        with colE:
            # Valor em TEF/Cartão (para registro, conforme solicitado)
            tef_value = st.number_input("Valor Contado em TEF/Cartão (R$)", min_value=0.00, format="%.2f", step=0.01, value=0.00, key='tef_input')

        # O botão de submissão do formulário pode ser grande por padrão
        submitted = st.form_submit_button("💰 REGISTRAR AUDITORIA", type="primary")

        if submitted:
            # Validação básica
            if operator_name == "Selecione..." or supervisor_name == "Selecione..." or prevention_name == "Selecione...":
                st.error("🚨 Por favor, selecione todos os responsáveis.")
            else:
                # CÁLCULO: Diferença entre Dinheiro Contado e TEF Contado (Contado - TEF)
                difference = counted_value - tef_value
                expected_value = 0.00 

                # 1. Salvar no banco de dados
                try:
                    new_id = save_audit(
                        pdv=pdv_number,
                        operator=operator_name,
                        supervisor=supervisor_name,
                        prevention=prevention_name,
                        counted=counted_value,
                        expected=expected_value,
                        difference=difference, 
                        tef=tef_value
                    )
                    st.session_state.last_audit_id = new_id 
                    st.balloons()
                    
                    # 2. Salva o resultado no estado da sessão para exibição do alerta
                    st.session_state.audit_result = {
                        'pdv_number': pdv_number,
                        'difference': difference,
                        'counted_value': counted_value,
                        'tef_value': tef_value
                    }

                    # 3. Força o Streamlit a rodar novamente para exibir o alerta no topo
                    st.rerun() 
                    
                except Exception as e:
                    st.exception(f"Erro ao salvar no banco de dados: {e}")

    st.markdown("---")
    
    st.markdown("<h2 style='font-size: 2.5em;'>2. Histórico de Auditorias Registradas</h2>", unsafe_allow_html=True)
    
    # --- Filtro de Data ---
    st.subheader("Filtro por Data")
    colFiltro1, colFiltro2 = st.columns(2)
    
    with colFiltro1:
        start_date = st.date_input("Data Inicial", value=date.today() - timedelta(days=30), key='start_date')
        
    with colFiltro2:
        end_date = st.date_input("Data Final", value=date.today(), key='end_date')
        
    # Carrega dados com base nos filtros
    df_audits = load_audits_filtered(start_date, end_date)
    
    if not df_audits.empty:
        # Adiciona a coluna 'ID' para que o usuário possa usá-la na exclusão
        df_display = df_audits[['id', 'pdv_number', 'audit_datetime', 'operator_name', 'supervisor_name', 
                                'prevention_name', 'counted_value', 'tef_value', 'difference', 
                                'expected_value']].copy()
        
        df_display.rename(columns={
            'id': 'ID',
            'pdv_number': 'PDV',
            'audit_datetime': 'Data/Hora (BR)',
            'operator_name': 'Operador(a)',
            'supervisor_name': 'Fiscal',
            'prevention_name': 'Auditor',
            'counted_value': 'Dinheiro Contado (R$)',
            'tef_value': 'TEF Contado (R$)',
            'expected_value': 'Valor Esperado (R$)', 
            'difference': 'Diferença (Dinheiro - TEF)' 
        }, inplace=True)
        
        # Colunas a serem exibidas e reordenadas
        cols_to_display = [
            'ID', 'Data/Hora (BR)', 'PDV', 'Operador(a)', 'Fiscal', 'Auditor', 
            'Dinheiro Contado (R$)', 'TEF Contado (R$)', 'Diferença (Dinheiro - TEF)'
        ]
        df_display_clean = df_display[cols_to_display]
        
        # Aplica a formatação de moeda E o estilo condicional
        styled_df = df_display_clean.style.apply(
            highlight_difference, 
            subset=['Diferença (Dinheiro - TEF)'], 
            axis=0 
        ).format({
            'Dinheiro Contado (R$)': format_currency_br,
            'TEF Contado (R$)': format_currency_br,
            'Diferença (Dinheiro - TEF)': format_currency_br
        })

        st.dataframe(styled_df, use_container_width=True, height=400)
        
        # --- Download XLSX ---
        # Prepara o DataFrame completo (incluindo as colunas zeradas) para download
        excel_data = convert_df_to_excel(df_display)
        
        st.download_button(
            label="Baixar Dados em XLSX",
            data=excel_data,
            file_name=f'auditorias_{start_date.strftime("%Y%m%d")}_{end_date.strftime("%Y%m%d")}.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            key='download_xlsx'
        )
        
    else:
        st.info("Nenhuma auditoria registrada no período selecionado.")

    st.markdown("---")
    
    st.markdown("<h2 style='font-size: 2.5em;'>3. Gerenciamento de Dados de Auditoria</h2>", unsafe_allow_html=True)

    # --- Excluir por ID ---
    st.subheader("Excluir Auditoria por ID")
    colDelId, colDelBtn = st.columns([1, 1])

    with colDelId:
        
        default_id = 1
        if not df_audits.empty:
            max_id = df_audits['id'].max()
            min_id = df_audits['id'].min()
            st.info(f"IDs Atuais no Histórico: de **{min_id}** a **{max_id}**.")
            default_id = max_id

        delete_id = st.number_input(
            "Digite o ID da auditoria a ser excluída:", 
            min_value=1, 
            value=default_id, 
            step=1, 
            key='input_delete_id'
        )

    with colDelBtn:
        st.write(" ")
        st.write(" ")
        # Adiciona um form para isolar o botão de exclusão
        with st.form("form_delete_id"):
            submit_delete_id = st.form_submit_button("🗑️ EXCLUIR ID SELECIONADO", type="primary")

            if submit_delete_id:
                if df_audits.empty:
                    st.warning("Não há dados para excluir.")
                elif int(delete_id) in df_audits['id'].values:
                    deleted_count = delete_audit_by_id(int(delete_id))
                    if deleted_count > 0:
                        st.success(f"✅ Auditoria ID **{delete_id}** excluída com sucesso.")
                        st.rerun() 
                    else:
                        st.warning(f"O ID **{delete_id}** não foi encontrado.")
                else:
                    st.warning(f"O ID **{delete_id}** não foi encontrado no histórico atual.")

    st.markdown("---")

    # --- Excluir Todos os Dados (Protegido por Senha) ---
    st.subheader("Excluir Todos os Dados (Requer Senha)")
    
    with st.expander("🚨 Acesso Administrativo - Exclusão Total"):
        
        with st.form("form_delete_all"):
            password_input = st.text_input("Digite a senha para excluir todos os dados:", type="password", key='admin_password')
            
            submit_delete_all = st.form_submit_button(
                "💣 EXCLUIR TODAS AS AUDITORIAS", 
                type="primary",
                help="ATENÇÃO: A exclusão é irreversível." 
            )
        
            if submit_delete_all:
                if password_input == ADMIN_PASSWORD:
                    deleted_count = delete_all_audits()
                    st.success(f"🔥🔥 {deleted_count} registros foram excluídos com sucesso! 🔥🔥")
                    st.session_state.last_audit_id = 0 
                    st.rerun() 
                else:
                    st.error("Senha incorreta. A exclusão total não foi realizada.")
                    
if __name__ == "__main__":
    app_main()

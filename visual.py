import os
from flask import Flask, render_template, request, jsonify
import pandas as pd
from datetime import datetime
import numpy as np

app = Flask(__name__)

EXCEL_PATH = 'ordens_de_servico.xlsx'
OS_POR_PAGINA = 25

def get_file_modification_time():
    """Retorna o timestamp da última modificação do arquivo Excel"""
    try:
        return os.path.getmtime(EXCEL_PATH)
    except:
        return 0

def ler_ordens():
    return pd.read_excel(EXCEL_PATH)

def salvar_ordens(df):
    df.to_excel(EXCEL_PATH, index=False)

def get_stats(df):
    total = len(df)
    andamento = len(df[df['Status'].astype(str).str.lower().str.contains('andamento', na=False)])
    concluida = len(df[df['Status'].astype(str).str.lower().str.contains('conclu', na=False)])
    cancelada = len(df[df['Status'].astype(str).str.lower().str.contains('cancel', na=False)])
    return dict(total=total, andamento=andamento, concluida=concluida, cancelada=cancelada)

def limpar_valores_nulos(df):
    """Substitui valores NaN, None e 'nan' por strings vazias"""
    for coluna in df.columns:
        df[coluna] = df[coluna].astype(str).replace(['nan', 'None', 'NaN'], '')
    return df

@app.route('/')
def index():
    df = ler_ordens()
    # Filtros
    mes = request.args.get('mes', '')
    ano = request.args.get('ano', '')
    cliente = request.args.get('cliente', '').strip()
    numero_os = request.args.get('numero_os', '').strip()
    responsavel = request.args.get('responsavel', '').strip()
    pagina = int(request.args.get('pagina', 1))

    # Filtro mês/ano
    if mes or ano:
        def match_date(row):
            try:
                data = str(row['Data de início'])
                if '/' in data:
                    partes = data.split('/')
                    if len(partes) >= 3:
                        m, a = partes[1], partes[2][:4]
                        if mes and m != mes: return False
                        if ano and a != ano: return False
                        return True
                elif '-' in data:
                    partes = data.split('-')
                    if len(partes) >= 3:
                        m, a = partes[1], partes[0]
                        if mes and m != mes: return False
                        if ano and a != ano: return False
                        return True
            except: return False
            return not (mes or ano)
        df = df[df.apply(match_date, axis=1)]
    if cliente:
        df = df[df['Cliente'].astype(str).str.contains(cliente, case=False, na=False)]
    if numero_os:
        try:
            numero_os_int = int(float(numero_os))
            df = df[df['Número da OS'].apply(lambda x: int(x) if pd.notnull(x) and str(x).strip() != '' else -1) == numero_os_int]
        except:
            df = df[df['Número da OS'].astype(str) == numero_os]
    if responsavel:
        df = df[df['Responsável'].astype(str).str.contains(responsavel, case=False, na=False)]

    # Converter para float (com NaN) antes de ordenar
    if 'Número da OS' in df.columns:
        df['Número da OS'] = pd.to_numeric(df['Número da OS'], errors='coerce')
        df = df.sort_values(by='Número da OS', ascending=False, na_position='last')
        # Não converte para int/string aqui, só na exibição

    total_os = len(df)
    # Carregamento progressivo: começa com 25, cada clique adiciona mais 25
    os_para_mostrar = min(pagina * OS_POR_PAGINA, total_os)
    ordens = df.iloc[:os_para_mostrar].copy()
    # Converter para int (ou vazio) só na exibição
    if 'Número da OS' in ordens.columns:
        ordens['Número da OS'] = ordens['Número da OS'].apply(lambda x: int(x) if pd.notnull(x) and not pd.isna(x) else '')
    ordens = ordens.to_dict(orient='records')
    # Limpar valores nulos antes de enviar para o template
    for ordem in ordens:
        for key, value in ordem.items():
            if pd.isna(value) or value is None or str(value).lower() in ['nan', 'none']:
                ordem[key] = ''
    stats = get_stats(df)
    anos = sorted({str(row['Data de início']).split('/')[-1][:4] for _, row in ler_ordens().iterrows() if row['Data de início']})
    proxima_pagina = pagina + 1
    # Verificar se ainda há mais OS para mostrar
    tem_mais = os_para_mostrar < total_os
    return render_template('index.html', ordens=ordens, stats=stats, mes=mes, ano=ano, anos=anos, cliente=cliente, numero_os=numero_os, responsavel=responsavel, pagina=pagina, proxima_pagina=proxima_pagina, tem_mais=tem_mais, total_mostrado=os_para_mostrar, total_os=total_os)

@app.route('/deletar_os', methods=['POST'])
def deletar_os():
    dados = request.json
    numero_os = dados.get('numero_os')
    df = ler_ordens()
    try:
        numero_os_int = int(float(numero_os))
        df = df[df['Número da OS'].apply(lambda x: int(float(x)) if pd.notnull(x) and str(x).strip() != '' else -1) != numero_os_int]
    except:
        df = df[df['Número da OS'].astype(str) != str(numero_os)]
    salvar_ordens(df)
    return jsonify({'success': True})

@app.route('/editar_os', methods=['POST'])
def editar_os():
    dados = request.json
    numero_os = dados.get('Número da OS')
    df = ler_ordens()
    try:
        numero_os_int = int(float(numero_os))
        idx = df[df['Número da OS'].apply(lambda x: int(float(x)) if pd.notnull(x) and str(x).strip() != '' else -1) == numero_os_int].index
    except:
        idx = df[df['Número da OS'].astype(str) == str(numero_os)].index
    if len(idx) == 0:
        return jsonify({'success': False, 'msg': 'OS não encontrada'}), 404
    for coluna in dados:
        if coluna in df.columns:
            df.at[idx[0], coluna] = dados[coluna]
    salvar_ordens(df)
    return jsonify({'success': True})

@app.route('/verificar_mudancas')
def verificar_mudancas():
    """Verifica se o arquivo Excel foi modificado desde a última verificação"""
    current_time = get_file_modification_time()
    last_check = request.args.get('last_check', '0')
    try:
        last_check = float(last_check)
    except:
        last_check = 0
    
    mudou = current_time > last_check
    
    return jsonify({
        'mudou': mudou,
        'timestamp': current_time,
        'mensagem': 'Arquivo atualizado!' if mudou else 'Sem mudanças'
    })

@app.route('/buscar_os/<numero_os>')
def buscar_os(numero_os):
    df = ler_ordens()
    try:
        numero_os_int = int(float(numero_os))
        os_data = df[df['Número da OS'].apply(lambda x: int(x) if pd.notnull(x) and str(x).strip() != '' else -1) == numero_os_int]
    except:
        os_data = df[df['Número da OS'].astype(str) == str(numero_os)]
    
    if len(os_data) == 0:
        return jsonify({'error': 'OS não encontrada'}), 404
    
    # Converter para int (ou vazio) para exibição
    if 'Número da OS' in os_data.columns:
        os_data['Número da OS'] = os_data['Número da OS'].apply(lambda x: int(x) if pd.notnull(x) and not pd.isna(x) else '')
    
    # Converter para dicionário e substituir todos os valores nulos por strings vazias
    os_dict = os_data.iloc[0].to_dict()
    for key, value in os_dict.items():
        if pd.isna(value) or value is None or str(value).lower() in ['nan', 'none', 'nat']:
            os_dict[key] = ''
        elif isinstance(value, float) and pd.isna(value):
            os_dict[key] = ''
    
    return jsonify(os_dict)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

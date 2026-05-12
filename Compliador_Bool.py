import sys
import sqlite3
import smtplib
import re
import easyocr
import schedule
import time
import threading
import os
import shutil
from enum import Enum
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Bibliotecas Web (API)
from flask import Flask, request, jsonify
from flask_cors import CORS

# =====================================================================
# 1. ENUM E DICIONÁRIO 
# =====================================================================
class TipoToken(Enum):
    IDENTIFICADOR = 1; STRING = 2; NUMERO_INTEIRO = 3
    ABRE_PARENTESES = 4; FECHA_PARENTESES = 5; VIRGULA = 6; EOF = 7
    BILLS_PROCESS = 8; BILLS_SEARCH = 9; MAILTO = 10; ECHO = 11
    BILLS_ADD = 12; BILLS_PAY = 13; BILLS_CHECK = 14; BILLS_AUTO = 15

NOMES_CUSTOMIZADOS = {
    TipoToken.VIRGULA: "VÍRGULA",
    TipoToken.ABRE_PARENTESES: "(",
    TipoToken.FECHA_PARENTESES: ")",
    TipoToken.BILLS_PROCESS: "bills_process",
    TipoToken.BILLS_SEARCH: "bills_search",
    TipoToken.MAILTO: "mailTo",
    TipoToken.ECHO: "echo",
    TipoToken.BILLS_ADD: "bills_add",
    TipoToken.BILLS_PAY: "bills_pay",
    TipoToken.BILLS_CHECK: "bills_check",
    TipoToken.BILLS_AUTO: "bills_auto_check"
}

# =====================================================================
# 2. ÁRVORE SINTÁTICA (AST Nodes)
# =====================================================================
class Token:
    def __init__(self, tipo, valor=None):
        self.tipo = tipo; self.valor = valor
    def __repr__(self): return f"{self.tipo.name}({self.valor})"

class StringNode:
    def __init__(self, valor): self.valor = valor
class EchoNode:
    def __init__(self, mensagem): self.mensagem = mensagem 
class ProcessNode:
    def __init__(self, caminho_imagem): self.caminho_imagem = caminho_imagem
class MailNode:
    def __init__(self, destinatario, boleto_id):
        self.destinatario = destinatario; self.boleto_id = boleto_id
class AddNode:
    def __init__(self, nome, data_inicio, data_vencimento, valor):
        self.nome = nome; self.data_inicio = data_inicio
        self.data_vencimento = data_vencimento; self.valor = valor
class SearchNode:
    def __init__(self, filtro): self.filtro = filtro
class PayNode:
    def __init__(self, boleto_id): self.boleto_id = boleto_id
class CheckDueNode:
    def __init__(self, email_notificacao): self.email_notificacao = email_notificacao
class AutoCheckNode:
    def __init__(self, horario, email):
        self.horario = horario; self.email = email

# =====================================================================
# 3. PARSER (Analisador Sintático)
# =====================================================================
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens; self.pos = 0; self.erros = []

    def parse(self):
        nodes = []
        while self._current().tipo != TipoToken.EOF:
            node = self._parse_expression()
            if node: nodes.append(node)
        return nodes

    def _current(self):
        if self.pos >= len(self.tokens): return self.tokens[-1] 
        return self.tokens[self.pos]

    def _advance(self):
        if self.pos < len(self.tokens) - 1: self.pos += 1

    def _expect(self, tipo):
        token = self._current()
        if token.tipo != tipo:
            nome_esperado = NOMES_CUSTOMIZADOS.get(tipo, tipo.name)
            nome_encontrado = NOMES_CUSTOMIZADOS.get(token.tipo, token.tipo.name)
            self.erros.append(f"Erro Sintático: Esperado '{nome_esperado}', mas encontrou '{nome_encontrado}'")
            self._sincronizar()
            return None
        self._advance()
        return token

    def _sincronizar(self):
        self._advance()
        while self._current().tipo != TipoToken.EOF:
            if self._current().tipo in (TipoToken.ECHO, TipoToken.MAILTO, TipoToken.BILLS_PROCESS, 
                                        TipoToken.BILLS_ADD, TipoToken.BILLS_SEARCH, 
                                        TipoToken.BILLS_PAY, TipoToken.BILLS_CHECK, TipoToken.BILLS_AUTO):
                return
            self._advance()

    def _parse_argument(self):
        token = self._current()
        if token.tipo == TipoToken.STRING:
            self._advance(); return StringNode(token.valor)
        if token.tipo in (TipoToken.IDENTIFICADOR, TipoToken.NUMERO_INTEIRO):
            val = token.valor; self._advance(); return val
            
        self.erros.append(f"Erro Sintático: Argumento inválido '{token.valor}'")
        self._sincronizar()
        return None

    def _parse_expression(self):
        token = self._current()

        if token.tipo == TipoToken.ECHO:
            self._advance(); self._expect(TipoToken.ABRE_PARENTESES)
            msg = self._parse_argument(); self._expect(TipoToken.FECHA_PARENTESES)
            return EchoNode(msg)

        if token.tipo == TipoToken.MAILTO:
            self._advance(); self._expect(TipoToken.ABRE_PARENTESES)
            email = self._parse_argument(); self._expect(TipoToken.VIRGULA)
            boleto_id = self._parse_argument(); self._expect(TipoToken.FECHA_PARENTESES)
            return MailNode(email, boleto_id)

        if token.tipo == TipoToken.BILLS_PROCESS:
            self._advance(); self._expect(TipoToken.ABRE_PARENTESES)
            caminho_imagem = self._parse_argument(); self._expect(TipoToken.FECHA_PARENTESES)
            return ProcessNode(caminho_imagem)
            
        if token.tipo == TipoToken.BILLS_ADD:
            self._advance(); self._expect(TipoToken.ABRE_PARENTESES)
            nome = self._parse_argument(); self._expect(TipoToken.VIRGULA)
            data_inicio = self._parse_argument(); self._expect(TipoToken.VIRGULA)
            data_vencimento = self._parse_argument(); self._expect(TipoToken.VIRGULA)
            valor = self._parse_argument(); self._expect(TipoToken.FECHA_PARENTESES)
            return AddNode(nome, data_inicio, data_vencimento, valor)

        if token.tipo == TipoToken.BILLS_SEARCH:
            self._advance(); self._expect(TipoToken.ABRE_PARENTESES)
            filtro = self._parse_argument(); self._expect(TipoToken.FECHA_PARENTESES)
            return SearchNode(filtro)

        if token.tipo == TipoToken.BILLS_PAY:
            self._advance(); self._expect(TipoToken.ABRE_PARENTESES)
            id_boleto = self._parse_argument(); self._expect(TipoToken.FECHA_PARENTESES)
            return PayNode(id_boleto)

        if token.tipo == TipoToken.BILLS_CHECK:
            self._advance(); self._expect(TipoToken.ABRE_PARENTESES)
            email = self._parse_argument(); self._expect(TipoToken.FECHA_PARENTESES)
            return CheckDueNode(email)

        if token.tipo == TipoToken.BILLS_AUTO:
            self._advance(); self._expect(TipoToken.ABRE_PARENTESES)
            horario = self._parse_argument(); self._expect(TipoToken.VIRGULA)
            email = self._parse_argument(); self._expect(TipoToken.FECHA_PARENTESES)
            return AutoCheckNode(horario, email)

        self._advance()
        return None 

# =====================================================================
# 4. LEXER (Analisador Léxico)
# =====================================================================
def tokenize(expressao):
    tokens = []
    i = 0
    while i < len(expressao):
        char = expressao[i]
        
        if char.isspace():
            i += 1; continue
            
        elif char == '"':
            i += 1; texto_string = ""
            while i < len(expressao) and expressao[i] != '"':
                texto_string += expressao[i]; i += 1
            if i >= len(expressao): raise Exception("Erro Léxico: Aspas não fechadas!")
            tokens.append(Token(TipoToken.STRING, texto_string))
            i += 1; continue
            
        elif char.isdigit():
            texto_num = ""
            while i < len(expressao) and (expressao[i].isdigit() or expressao[i] == '.'):
                texto_num += expressao[i]; i += 1
            tokens.append(Token(TipoToken.NUMERO_INTEIRO, texto_num))
            continue

        elif char == ',': tokens.append(Token(TipoToken.VIRGULA, ','))
        elif char == '(': tokens.append(Token(TipoToken.ABRE_PARENTESES, '('))
        elif char == ')': tokens.append(Token(TipoToken.FECHA_PARENTESES, ')'))

        elif char.isalpha():
            texto = ""
            while i < len(expressao) and (expressao[i].isalpha() or expressao[i] == '_'):
                texto += expressao[i]; i += 1

            if texto == "bills_process":   tokens.append(Token(TipoToken.BILLS_PROCESS, texto))
            elif texto == "bills_search":  tokens.append(Token(TipoToken.BILLS_SEARCH, texto))
            elif texto == "mailTo":        tokens.append(Token(TipoToken.MAILTO, texto))
            elif texto == "echo":          tokens.append(Token(TipoToken.ECHO, texto))
            elif texto == "bills_add":     tokens.append(Token(TipoToken.BILLS_ADD, texto))
            elif texto == "bills_pay":     tokens.append(Token(TipoToken.BILLS_PAY, texto))
            elif texto == "bills_check":   tokens.append(Token(TipoToken.BILLS_CHECK, texto))
            elif texto == "bills_auto_check": tokens.append(Token(TipoToken.BILLS_AUTO, texto))
            else:                          tokens.append(Token(TipoToken.IDENTIFICADOR, texto))
            continue
        else:
            raise Exception(f"Erro Léxico: Caractere não reconhecido: {char}")
        i += 1
    tokens.append(Token(TipoToken.EOF, ""))
    return tokens

# =====================================================================
# 5. BANCO DE DADOS (SQLite - Estrutura Completa)
# =====================================================================
def inicializar_banco():
    if not os.path.exists('armazenamento'): os.makedirs('armazenamento')
    conexao = sqlite3.connect('boletos.db')
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boletos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT DEFAULT 'Outros',
            data_inicio TEXT,
            data_vencimento TEXT,
            valor REAL,
            linha_digitavel TEXT,
            caminho_imagem TEXT,
            status TEXT DEFAULT 'PENDENTE'
        )
    ''')
    conexao.commit()
    conexao.close()

# =====================================================================
# 6. SISTEMA DE E-MAIL (SMTP)
# =====================================================================
def enviar_email_real(destinatario, assunto, mensagem):
    email_remetente = "lixinhotestes@gmail.com"
    senha_app = "c r a u n e k m f o h f c b a z" # Senha de app configurada

    try:
        msg = MIMEMultipart()
        msg['From'] = email_remetente; msg['To'] = destinatario; msg['Subject'] = assunto
        msg.attach(MIMEText(mensagem, 'plain', 'utf-8'))

        servidor = smtplib.SMTP('smtp.gmail.com', 587)
        servidor.starttls()
        servidor.login(email_remetente, senha_app.replace(" ", ""))
        servidor.send_message(msg)
        servidor.quit()
        return True
    except Exception as e:
        print(f"[ERRO SMTP] Falha ao enviar: {e}")
        return False

# =====================================================================
# 7. VISÃO COMPUTACIONAL (OCR com Lógica Cronológica de Vencimento)
# =====================================================================
def extrair_dados_boleto(caminho_imagem):
    try:
        reader = easyocr.Reader(['pt'], gpu=False, verbose=False) 
        resultados = reader.readtext(caminho_imagem, detail=0)
        texto_completo = " ".join(resultados)
        
        # 1. RASTREIO PRECISO DE DATAS (Extrai todas e pega a maior)
        padrao_data = r'\b(\d{2})[\s/.\-]+(\d{2})[\s/.\-]+(\d{4})\b'
        datas_encontradas = re.findall(padrao_data, texto_completo)
        
        data_venc = None
        datas_validas = []

        for dia, mes, ano in datas_encontradas:
            try:
                dt = datetime.strptime(f"{dia}/{mes}/{ano}", "%d/%m/%Y").date()
                if 2000 <= dt.year <= 2035: # Validação de sanidade do ano
                    datas_validas.append((dt, f"{dia}/{mes}/{ano}"))
            except Exception: pass
        
        if datas_validas:
            # Ordena da mais recente para a mais antiga e pega o topo
            datas_validas.sort(key=lambda x: x[0], reverse=True)
            data_venc = datas_validas[0][1]

        # 2. LINHA DIGITÁVEL E VALOR
        match_linha = re.search(r'\d{5}[\.\s]*\d{5}[\.\s]*\d{5}[\.\s]*\d{6}[\.\s]*\d{5}[\.\s]*\d{6}[\.\s]*\d[\.\s]*\d{14}', texto_completo)
        
        valor = 0.0
        linha_digitavel = "Não identificada"

        if match_linha:
            linha_digitavel = match_linha.group(0)
            linha_limpa = re.sub(r'\D', '', linha_digitavel)
            if len(linha_limpa) == 47:
                valor = float(linha_limpa[-10:]) / 100.0
        
        if valor == 0.0:
            regex_dinheiro = r'(\d{1,3}(?:[\.\s]?\d{3})*[.,]\d{2})'
            todos_valores = re.findall(regex_dinheiro, texto_completo)
            if todos_valores:
                valor_str = todos_valores[-1].replace(' ', '').replace('.', '').replace(',', '.')
                valor = float(valor_str)

        return data_venc, valor, linha_digitavel
    except Exception as e:
        print(f"[ERRO IA] Falha de leitura: {e}")
        return None, 0.0, "Erro de Leitura"

# =====================================================================
# 8. AVALIADOR (Motor Central)
# =====================================================================
def evaluate(node):
    if isinstance(node, list):
        for statement in node: evaluate(statement)
        return
    if isinstance(node, StringNode): return node.valor

    if isinstance(node, EchoNode):
        msg = node.mensagem.valor if isinstance(node.mensagem, StringNode) else node.mensagem
        print(f"[SISTEMA] -> {msg}")
        return
    
    if isinstance(node, ProcessNode):
        img_path_original = node.caminho_imagem.valor if isinstance(node.caminho_imagem, StringNode) else node.caminho_imagem
        data_venc, valor, linha_digitavel = extrair_dados_boleto(img_path_original)

        if data_venc and valor > 0:
            try:
                conexao = sqlite3.connect('boletos.db')
                cursor = conexao.cursor()
                hoje_str = datetime.now().strftime("%d/%m/%Y")
                
                if not os.path.exists('armazenamento'): os.makedirs('armazenamento')
                extensao = os.path.splitext(img_path_original)[1]
                nome_arquivo_novo = f"boleto_{int(time.time())}{extensao}"
                caminho_destino = os.path.join('armazenamento', nome_arquivo_novo)
                shutil.copy(img_path_original, caminho_destino) 
                
                cursor.execute('''
                    INSERT INTO boletos (nome, categoria, data_inicio, data_vencimento, valor, linha_digitavel, caminho_imagem)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ("Boleto Escaneado", "Outros", hoje_str, data_venc, valor, linha_digitavel, caminho_destino))
                
                conexao.commit(); conexao.close()
                print(f"Imagem salva em: {caminho_destino}")
            except Exception as e: print(f"Erro ao salvar: {e}")
        return

    if isinstance(node, MailNode):
        email = node.destinatario.valor if isinstance(node.destinatario, StringNode) else node.destinatario
        print(f"[SMTP] Disparando para {email}...")
        return

    if isinstance(node, AddNode):
        n = node.nome.valor if isinstance(node.nome, StringNode) else node.nome
        inicio = node.data_inicio.valor if isinstance(node.data_inicio, StringNode) else node.data_inicio
        venc = node.data_vencimento.valor if isinstance(node.data_vencimento, StringNode) else node.data_vencimento
        valor_numero = float(node.valor.valor if hasattr(node.valor, 'valor') else node.valor)
        
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute('INSERT INTO boletos (nome, data_inicio, data_vencimento, valor) VALUES (?, ?, ?, ?)', (n, inicio, venc, valor_numero))
        conexao.commit(); conexao.close()
        return

    if isinstance(node, SearchNode):
        filtro_str = node.filtro.valor if isinstance(node.filtro, StringNode) else node.filtro
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        if str(filtro_str).upper() == "TODOS": cursor.execute("SELECT id, nome, data_vencimento, valor, status FROM boletos")
        else: cursor.execute("SELECT id, nome, data_vencimento, valor, status FROM boletos WHERE status = ? OR nome LIKE ?", (str(filtro_str).upper(), f"%{filtro_str}%"))
        resultados = cursor.fetchall()
        conexao.close()
        print(f"\n--- BUSCA: {filtro_str} ---")
        for r in resultados: print(f"[{r[0]}] {r[1]} | Vence: {r[2]} | R${r[3]:.2f} | Status: {r[4]}")
        return

    if isinstance(node, PayNode):
        id_alvo = node.boleto_id.valor if hasattr(node.boleto_id, 'valor') else node.boleto_id
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute("UPDATE boletos SET status = 'PAGO' WHERE id = ?", (id_alvo,))
        conexao.commit(); conexao.close()
        print(f"Boleto {id_alvo} pago!")
        return

    if isinstance(node, CheckDueNode):
        email_alvo = node.email_notificacao.valor if hasattr(node.email_notificacao, 'valor') else node.email_notificacao
        hoje = datetime.now().date()
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute("SELECT id, nome, data_vencimento, valor FROM boletos WHERE status != 'PAGO'")
        pendentes = cursor.fetchall()
        conexao.close()
        
        for boleto in pendentes:
            id_bol, nome, dt_venc_str, valor = boleto
            try:
                data_vencimento = datetime.strptime(dt_venc_str, "%d/%m/%Y").date()
                diferenca_dias = (data_vencimento - hoje).days
                if 0 <= diferenca_dias <= 3:
                    enviar_email_real(email_alvo, f"Aviso de Vencimento: {nome}", f"O boleto '{nome}' vence em {diferenca_dias} dias.\nValor: R${valor:.2f}")
                elif diferenca_dias < 0:
                    enviar_email_real(email_alvo, f"URGENTE: Boleto Atrasado - {nome}", f"O boleto '{nome}' está ATRASADO há {abs(diferenca_dias)} dias!\nValor: R${valor:.2f}")
            except Exception: pass
        return

    if isinstance(node, AutoCheckNode):
        horario = node.horario.valor if isinstance(node.horario, StringNode) else node.horario
        email_alvo = node.email.valor if isinstance(node.email, StringNode) else node.email
        def tarefa_diaria(): evaluate(CheckDueNode(StringNode(email_alvo)))
        schedule.every().day.at(horario).do(tarefa_diaria)
        def rodar_agendador():
            while True:
                schedule.run_pending(); time.sleep(60)
        threading.Thread(target=rodar_agendador, daemon=True).start()
        print(f"Automação ativada para as {horario}!")
        return

# =====================================================================
# 9. API FLASK (A Ponte Definitiva com o React)
# =====================================================================
from flask import send_from_directory

app = Flask(__name__)
CORS(app) 

@app.route('/imagens/<path:filename>')
def servir_imagem(filename):
    return send_from_directory('armazenamento', filename)


@app.route('/boletos', methods=['GET'])
def api_listar_boletos():
    try:
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute("SELECT id, nome, categoria, data_vencimento, valor, status, linha_digitavel, caminho_imagem FROM boletos ORDER BY id DESC")
        resultados = cursor.fetchall()
        conexao.close()

        lista_react = []
        hoje = datetime.now().date()

        for linha in resultados:
            id_bol, nome, categoria, dt_venc_str, valor, status_db, linha_dig, caminho_img = linha
            
            # Status dinâmico
            status_react = "Pendente"
            if status_db == "PAGO": 
                status_react = "Pago"
            else:
                if dt_venc_str:
                    try:
                        dt_venc = datetime.strptime(dt_venc_str, "%d/%m/%Y").date()
                        if dt_venc < hoje: status_react = "Atrasado"
                    except Exception: pass

            url_img = f"http://localhost:5000/imagens/{os.path.basename(caminho_img)}" if caminho_img else None

            venc_iso = dt_venc_str
            if dt_venc_str:
                try: venc_iso = datetime.strptime(dt_venc_str, "%d/%m/%Y").strftime("%Y-%m-%d")
                except Exception: pass

            lista_react.append({
                "id": id_bol,
                "beneficiario": nome,
                "categoria": categoria if categoria else "Outros",
                "vencimento": venc_iso if venc_iso else "",
                "valor": float(valor) if valor else 0.0,
                "status": status_react,
                "linhaDigitavel": linha_dig if linha_dig else "Não identificada",
                "url_imagem": url_img
            })

        return jsonify(lista_react), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/boletos/<int:id>', methods=['PATCH'])
def api_atualizar_boleto(id):
    """Salva instantaneamente a edição de Nome e Categoria no banco"""
    try:
        dados = request.json
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute("UPDATE boletos SET nome = ?, categoria = ? WHERE id = ?", (dados.get('nome'), dados.get('categoria'), id))
        conexao.commit(); conexao.close()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/boletos/process', methods=['POST'])
def api_processar_imagem():
    """Recebe do Drop, aciona OCR, avalia Vencimento Real e devolve Status correto"""
    if 'file' not in request.files: return jsonify({"error": "Nenhuma imagem recebida"}), 400
    arquivo = request.files['file']
    if arquivo.filename == '': return jsonify({"error": "Arquivo vazio"}), 400

    if not os.path.exists('armazenamento'): os.makedirs('armazenamento')
    nome_persistente = f"boleto_{int(time.time())}{os.path.splitext(arquivo.filename)[1]}"
    caminho_destino = os.path.join('armazenamento', nome_persistente)
    arquivo.save(caminho_destino)

    try:
        data_venc, valor, linha_digitavel = extrair_dados_boleto(caminho_destino)
        
        nome_inicial = "Novo Boleto (Clique para editar)"
        categoria_inicial = "Outros"

        # --- VERIFICAÇÃO DINÂMICA DE ATRASO IMEDIATA ---
        status_react = "Pendente"
        hoje = datetime.now().date()
        if data_venc:
            try:
                dt_venc = datetime.strptime(data_venc, "%d/%m/%Y").date()
                if dt_venc < hoje: 
                    status_react = "Atrasado"
            except Exception: pass

        # Inserção completa com a coluna de categoria
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        hoje_str = hoje.strftime("%d/%m/%Y")
        cursor.execute(
            'INSERT INTO boletos (nome, categoria, data_inicio, data_vencimento, valor, linha_digitavel, caminho_imagem) VALUES (?, ?, ?, ?, ?, ?, ?)', 
            (nome_inicial, categoria_inicial, hoje_str, data_venc, valor, linha_digitavel, caminho_destino)
        )
        conexao.commit()
        bol_id = cursor.lastrowid
        conexao.close()

        venc_iso = data_venc
        if data_venc:
            try: venc_iso = datetime.strptime(data_venc, "%d/%m/%Y").strftime("%Y-%m-%d")
            except Exception: pass

        # Retorna o objeto integral para a linha nascer limpa, formatada e com a cor certa!
        return jsonify({
            "id": bol_id,
            "beneficiario": nome_inicial,
            "categoria": categoria_inicial,
            "vencimento": venc_iso if venc_iso else "",
            "valor": float(valor) if valor else 0.0,
            "status": status_react,
            "linhaDigitavel": linha_digitavel if linha_digitavel else "Não identificada",
            "url_imagem": f"http://localhost:5000/imagens/{nome_persistente}"
        }), 201

    except Exception as e:
        if os.path.exists(caminho_destino): os.remove(caminho_destino)
        return jsonify({"error": str(e)}), 500


@app.route('/boletos/pay/<int:id>', methods=['POST'])
def api_confirmar_pagamento(id):
    try:
        evaluate(PayNode(StringNode(str(id))))
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route('/boletos/check', methods=['POST'])
def api_disparar_notificacoes():
    try:
        evaluate(CheckDueNode(StringNode("lixinhotestes@gmail.com")))
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# =====================================================================
# 10. EXECUTOR GERAL
# =====================================================================
def ler_arquivo(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as f: return f.read()
    except Exception: return None

def rodar_codigo(codigo_fonte):
    tokens = tokenize(codigo_fonte)
    meu_parser = Parser(tokens)
    arvore = meu_parser.parse()
    if len(meu_parser.erros) > 0:
        for erro in meu_parser.erros: print("  ->", erro)
    else: evaluate(arvore)

if __name__ == "__main__":
    inicializar_banco()

    if len(sys.argv) > 1:
        caminho_arquivo = sys.argv[1]
        if not caminho_arquivo.endswith(".bool"):
            print("Erro: O arquivo deve ter a extensão .bool")
        else:
            codigo = ler_arquivo(caminho_arquivo)
            if codigo:
                print(f"--- Executando script: {caminho_arquivo} ---\n")
                rodar_codigo(codigo)
                print("\n--- Fim da execução ---")
    else:
        print("\n=======================================================")
        print("     🚀 SERVIDOR WEB ATIVADO (API FLASK)       ")
        print(" O Back-End do compilador está online na porta 5000.   ")
        print(" Pode iniciar e testar a sua aplicação visual em React! ")
        print("=======================================================\n")
        app.run(host="0.0.0.0", port=5000, debug=False)
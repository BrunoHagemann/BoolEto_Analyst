import sys
import sqlite3
import smtplib
import re
import easyocr
import schedule
import time
import threading
import os
from enum import Enum
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import shutil

# Bibliotecas Web (API)
from flask import Flask, request, jsonify
from flask_cors import CORS

# =====================================================================
# 1. ENUM E DICIONÁRIO 
# =====================================================================
class TipoToken(Enum):
    IDENTIFICADOR = 1
    STRING = 2
    NUMERO_INTEIRO = 3
    ABRE_PARENTESES = 4
    FECHA_PARENTESES = 5
    VIRGULA = 6
    EOF = 7

    BILLS_PROCESS = 8
    BILLS_SEARCH = 9
    MAILTO = 10
    ECHO = 11
    BILLS_ADD = 12
    BILLS_PAY = 13
    BILLS_CHECK = 14
    BILLS_AUTO = 15

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
        self.tipo = tipo
        self.valor = valor
    def __repr__(self): return f"{self.tipo.name}({self.valor})"

class StringNode:
    def __init__(self, valor): self.valor = valor
    def __repr__(self): return f"String('{self.valor}')"

class EchoNode:
    def __init__(self, mensagem): self.mensagem = mensagem 
    def __repr__(self): return f"EchoNode(msg={self.mensagem})"

class ProcessNode:
    def __init__(self, caminho_imagem): self.caminho_imagem = caminho_imagem
    def __repr__(self): return f"ProcessNode(img={self.caminho_imagem})"

class MailNode:
    def __init__(self, destinatario, boleto_id):
        self.destinatario = destinatario
        self.boleto_id = boleto_id
    def __repr__(self): return f"MailNode(to={self.destinatario}, id={self.boleto_id})"

class AddNode:
    def __init__(self, nome, data_inicio, data_vencimento, valor):
        self.nome = nome
        self.data_inicio = data_inicio
        self.data_vencimento = data_vencimento
        self.valor = valor
    def __repr__(self): return f"AddNode(nome={self.nome}, valor={self.valor})"

class SearchNode:
    def __init__(self, filtro): self.filtro = filtro
    def __repr__(self): return f"SearchNode(filtro={self.filtro})"

class PayNode:
    def __init__(self, boleto_id): self.boleto_id = boleto_id
    def __repr__(self): return f"PayNode(id={self.boleto_id})"

class CheckDueNode:
    def __init__(self, email_notificacao): self.email_notificacao = email_notificacao
    def __repr__(self): return f"CheckDueNode(email={self.email_notificacao})"

class AutoCheckNode:
    def __init__(self, horario, email):
        self.horario = horario
        self.email = email
    def __repr__(self): return f"AutoCheckNode(hora={self.horario}, email={self.email})"

# =====================================================================
# 3. PARSER (Analisador Sintático)
# =====================================================================
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.erros = []

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
            self._advance()
            return StringNode(token.valor)
        if token.tipo == TipoToken.IDENTIFICADOR:
            self._advance()
            return token.valor 
        if token.tipo == TipoToken.NUMERO_INTEIRO:
            self._advance()
            return token.valor 
            
        self.erros.append(f"Erro Sintático: Argumento inválido '{token.valor}'")
        self._sincronizar()
        return None

    def _parse_expression(self):
        token = self._current()

        if token.tipo == TipoToken.ECHO:
            self._advance()
            self._expect(TipoToken.ABRE_PARENTESES) # Corrigido para exigir parênteses
            msg = self._parse_argument()
            self._expect(TipoToken.FECHA_PARENTESES)
            return EchoNode(msg)

        if token.tipo == TipoToken.MAILTO:
            self._advance()
            self._expect(TipoToken.ABRE_PARENTESES)
            email = self._parse_argument()
            self._expect(TipoToken.VIRGULA)
            boleto_id = self._parse_argument()
            self._expect(TipoToken.FECHA_PARENTESES)
            return MailNode(email, boleto_id)

        if token.tipo == TipoToken.BILLS_PROCESS:
            self._advance()
            self._expect(TipoToken.ABRE_PARENTESES)
            caminho_imagem = self._parse_argument()
            self._expect(TipoToken.FECHA_PARENTESES)
            return ProcessNode(caminho_imagem)
            
        if token.tipo == TipoToken.BILLS_ADD:
            self._advance()
            self._expect(TipoToken.ABRE_PARENTESES)
            nome = self._parse_argument()
            self._expect(TipoToken.VIRGULA)
            data_inicio = self._parse_argument()
            self._expect(TipoToken.VIRGULA)
            data_vencimento = self._parse_argument()
            self._expect(TipoToken.VIRGULA)
            valor = self._parse_argument()
            self._expect(TipoToken.FECHA_PARENTESES)
            return AddNode(nome, data_inicio, data_vencimento, valor)

        if token.tipo == TipoToken.BILLS_SEARCH:
            self._advance()
            self._expect(TipoToken.ABRE_PARENTESES)
            filtro = self._parse_argument()
            self._expect(TipoToken.FECHA_PARENTESES)
            return SearchNode(filtro)

        if token.tipo == TipoToken.BILLS_PAY:
            self._advance()
            self._expect(TipoToken.ABRE_PARENTESES)
            id_boleto = self._parse_argument()
            self._expect(TipoToken.FECHA_PARENTESES)
            return PayNode(id_boleto)

        if token.tipo == TipoToken.BILLS_CHECK:
            self._advance()
            self._expect(TipoToken.ABRE_PARENTESES)
            email = self._parse_argument()
            self._expect(TipoToken.FECHA_PARENTESES)
            return CheckDueNode(email)

        if token.tipo == TipoToken.BILLS_AUTO:
            self._advance()
            self._expect(TipoToken.ABRE_PARENTESES)
            horario = self._parse_argument()
            self._expect(TipoToken.VIRGULA)
            email = self._parse_argument()
            self._expect(TipoToken.FECHA_PARENTESES)
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
            i += 1
            continue
            
        elif char == '"':
            i += 1 
            texto_string = ""
            while i < len(expressao) and expressao[i] != '"':
                texto_string += expressao[i]
                i += 1
            if i >= len(expressao): raise Exception("Erro Léxico: Aspas não fechadas!")
            tokens.append(Token(TipoToken.STRING, texto_string))
            i += 1 
            continue
            
        # Corrigido para aceitar ponto decimal perfeitamente
        elif char.isdigit():
            texto_num = ""
            while i < len(expressao) and (expressao[i].isdigit() or expressao[i] == '.'):
                texto_num += expressao[i]
                i += 1
            tokens.append(Token(TipoToken.NUMERO_INTEIRO, texto_num))
            continue

        elif char == ',': tokens.append(Token(TipoToken.VIRGULA, ','))
        elif char == '(': tokens.append(Token(TipoToken.ABRE_PARENTESES, '('))
        elif char == ')': tokens.append(Token(TipoToken.FECHA_PARENTESES, ')'))

        elif char.isalpha():
            texto = ""
            while i < len(expressao) and (expressao[i].isalpha() or expressao[i] == '_'):
                texto += expressao[i]
                i += 1

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
# 5. BANCO DE DADOS (SQLite)
# =====================================================================
def inicializar_banco():
    if not os.path.exists('armazenamento'): os.makedirs('armazenamento')
    conexao = sqlite3.connect('boletos.db')
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boletos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT DEFAULT 'Outros', -- NOVA COLUNA FIXA
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
    senha_app = "c r a u n e k m f o h f c b a z" # <-- Lembre-se de colocar sua senha de 16 letras aqui!

    if senha_app == "COLE_SUA_SENHA_DE_APP_AQUI":
        print("[ERRO SMTP] Senha de App do Gmail não configurada no código!")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = email_remetente
        msg['To'] = destinatario
        msg['Subject'] = assunto
        msg.attach(MIMEText(mensagem, 'plain', 'utf-8'))

        servidor = smtplib.SMTP('smtp.gmail.com', 587)
        servidor.starttls()
        servidor.login(email_remetente, senha_app)
        servidor.send_message(msg)
        servidor.quit()
        return True
    except Exception as e:
        print(f"[ERRO SMTP] Falha ao enviar: {e}")
        return False

# =====================================================================
# 7. VISÃO COMPUTACIONAL (OCR)
# =====================================================================
def extrair_dados_boleto(caminho_imagem):
    try:
        # Lendo SEM detail=0 para receber as coordenadas espaciais (eixos X e Y)
        reader = easyocr.Reader(['pt'], gpu=False, verbose=False) 
        resultados = reader.readtext(caminho_imagem) 
        
        # Recria o texto completo juntando apenas as strings para os buscadores de Regex
        texto_completo = " ".join([item[1] for item in resultados])
        
        # 1. DATA DE VENCIMENTO
        match_data = re.search(r'\d{2}/\d{2}/\d{4}', texto_completo)
        data_venc = match_data.group(0) if match_data else None

        # 2. LINHA DIGITÁVEL E VALOR
        match_linha = re.search(r'\d{5}[\.\s]*\d{5}[\.\s]*\d{5}[\.\s]*\d{6}[\.\s]*\d{5}[\.\s]*\d{6}[\.\s]*\d[\.\s]*\d{14}', texto_completo)
        
        valor = 0.0
        linha_digitavel = "Não identificada"

        if match_linha:
            linha_digitavel = match_linha.group(0)
            linha_limpa = re.sub(r'\D', '', linha_digitavel)
            if len(linha_limpa) == 47:
                valor_centavos = linha_limpa[-10:]
                valor = float(valor_centavos) / 100.0
        
        if valor == 0.0:
            regex_dinheiro = r'(\d{1,3}(?:[\.\s]?\d{3})*[.,]\d{2})'
            todos_valores = re.findall(regex_dinheiro, texto_completo)
            if todos_valores:
                valor_str = todos_valores[-1].replace(' ', '').replace('.', '').replace(',', '.')
                valor = float(valor_str)

        # 3. DETETIVE ESPACIAL: RASTREAMENTO DO BENEFICIÁRIO
        beneficiario = None
        coordenada_ancora = None
        
        # Passo A: Encontra as coordenadas da palavra "Beneficiário" ou "Cedente"
        for bbox, texto, conf in resultados:
            if any(c in texto.lower() for c in ["beneficiario", "beneficiário", "cedente"]):
                # bbox traz os 4 cantos da caixa. Pegamos o Y da parte de baixo da palavra
                y_inferior = bbox[2][1] 
                x_esquerdo = bbox[0][0]
                coordenada_ancora = (x_esquerdo, y_inferior)
                
                # Se por acaso o OCR leu o nome grudado na mesma caixa
                limpo = re.sub(r'(?i)benefici[aá]rio|cedente|[:\-]', '', texto).strip()
                if len(limpo) > 3:
                    beneficiario = limpo
                break
        
        # Passo B: Rastreia qual texto está posicionado fisicamente LOGO ABAIXO da âncora
        if coordenada_ancora and not beneficiario:
            x_ancora, y_ancora = coordenada_ancora
            textos_abaixo = []
            
            for bbox, texto, conf in resultados:
                y_topo_item = bbox[0][1]
                x_esq_item = bbox[0][0]
                
                # Calcula a distância física entre a palavra Beneficiário e este texto
                distancia_y = y_topo_item - y_ancora
                distancia_x = abs(x_esq_item - x_ancora)
                
                # Se o texto estiver abaixo (Y positivo até 85 pixels) e alinhado à esquerda
                if 0 < distancia_y < 85 and distancia_x < 120:
                    # Ignora rótulos perdidos de outras colunas da direita
                    if len(texto.strip()) > 2 and not any(r in texto.lower() for r in ["agência", "código", "data", "documento"]):
                        textos_abaixo.append((distancia_y, texto))
            
            # Se encontrou textos na zona alvo, escolhe o que está geograficamente mais próximo
            if textos_abaixo:
                textos_abaixo.sort(key=lambda item: item[0])
                beneficiario = textos_abaixo[0][1]

        # Fallback de Segurança: Busca qualquer linha com CNPJ que não seja o Pagador/Sacador
        if not beneficiario:
            for bbox, texto, conf in resultados:
                if "/" in texto and "-" in texto and any(char.isdigit() for char in texto):
                    if not any(p in texto.lower() for p in ["pagador", "sacador", "avalista"]):
                        beneficiario = texto
                        break

        # --- FILTRO DE LIMPEZA DO NOME ---
        if beneficiario:
            # Se a IA capturou o CNPJ na mesma string, passamos a tesoura nele
            beneficiario = re.sub(r'\(?\d{2,3}\.\d{3}\.\d{3}/.+|\(?\d{2,3}\.\d{3}\.\d{3}\-.+', '', beneficiario)
            # Limpa sujeiras, traços e a própria palavra âncora se sobrou
            beneficiario = re.sub(r'(?i)benefici[aá]rio|cedente', '', beneficiario)
            beneficiario = beneficiario.strip('() -:')
            
        if not beneficiario or len(beneficiario) < 3:
            beneficiario = "Boleto Digitalizado (IA)"

        # 4. CATEGORIA AUTOMÁTICA
        categoria = "Outros"
        b_lower = beneficiario.lower()
        t_lower = texto_completo.lower()
        
        if any(p in b_lower or p in t_lower for p in ["luz", "energia", "enel", "cpfl"]): categoria = "Serviços"
        elif any(p in b_lower or p in t_lower for p in ["água", "sabesp", "saneamento"]): categoria = "Serviços"
        elif any(p in b_lower or p in t_lower for p in ["vivo", "claro", "tim", "internet"]): categoria = "Assinaturas"
        elif any(p in b_lower or p in t_lower for p in ["condomínio", "aluguel"]): categoria = "Moradia"
        elif any(p in b_lower or p in t_lower for p in ["escola", "faculdade", "mensalidade"]): categoria = "Educação"
        elif "teste" in b_lower: categoria = "Testes do Sistema"

        return data_venc, valor, linha_digitavel, beneficiario, categoria
    except Exception as e:
        print(f"[ERRO IA] Falha de leitura espacial: {e}")
        return None, 0.0, "Erro de Leitura", "Erro no OCR", "Outros"

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
        
        # Recebe os 5 parâmetros da nova inteligência visual
        data_venc, valor, linha_digitavel, beneficiario, categoria = extrair_dados_boleto(img_path_original)
        
        if not data_venc: data_venc = input("Data não identificada. Digite (DD/MM/AAAA): ")
        if valor == 0.0: valor = float(input("Valor não identificado. Digite: ").replace(',', '.'))

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
                    INSERT INTO boletos (nome, data_inicio, data_vencimento, valor, linha_digitavel, caminho_imagem)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (beneficiario, hoje_str, data_venc, valor, linha_digitavel, caminho_destino))
                
                conexao.commit()
                conexao.close()
                print(f"Boleto '{beneficiario}' salvo via OCR com sucesso!")
            except Exception as e:
                print(f"Erro ao salvar imagem/dados: {e}")
        return

    if isinstance(node, MailNode):
        email = node.destinatario.valor if isinstance(node.destinatario, StringNode) else node.destinatario
        print(f"[SMTP] Disparando notificação manual para {email}...")
        return

    if isinstance(node, AddNode):
        n = node.nome.valor if isinstance(node.nome, StringNode) else node.nome
        inicio = node.data_inicio.valor if isinstance(node.data_inicio, StringNode) else node.data_inicio
        venc = node.data_vencimento.valor if isinstance(node.data_vencimento, StringNode) else node.data_vencimento
        valor_numero = float(node.valor.valor if hasattr(node.valor, 'valor') else node.valor)
        
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute('INSERT INTO boletos (nome, data_inicio, data_vencimento, valor) VALUES (?, ?, ?, ?)', (n, inicio, venc, valor_numero))
        conexao.commit()
        conexao.close()
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
        for linha in resultados: print(f"[{linha[0]}] {linha[1]} | Vence: {linha[2]} | R${linha[3]:.2f} | Status: {linha[4]}")
        return

    if isinstance(node, PayNode):
        id_alvo = node.boleto_id.valor if hasattr(node.boleto_id, 'valor') else node.boleto_id
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute("UPDATE boletos SET status = 'PAGO' WHERE id = ?", (id_alvo,))
        conexao.commit()
        conexao.close()
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
                if diferenca_dias <= 3 and diferenca_dias >= 0:
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
                schedule.run_pending()
                time.sleep(60)
        threading.Thread(target=rodar_agendador, daemon=True).start()
        print(f"Automação diária ativada para as {horario}!")
        return

# =====================================================================
# 9. API FLASK (A Ponte com o React)
# =====================================================================
app = Flask(__name__)
CORS(app) 

from flask import send_from_directory

# ROTA 1: Entrega a imagem para o navegador quando o usuário clicar no botão de visualização
@app.route('/imagens/<path:filename>')
def servir_imagem(filename):
    return send_from_directory('armazenamento', filename)


# ROTA 2: Busca a lista de boletos (Agora trazendo o nome editado e a categoria do Banco)
@app.route('/boletos', methods=['GET'])
def api_listar_boletos():
    try:
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        # Note que agora buscamos a coluna 'categoria' e 'caminho_imagem'
        cursor.execute("SELECT id, nome, categoria, data_vencimento, valor, status, linha_digitavel, caminho_imagem FROM boletos ORDER BY id DESC")
        resultados = cursor.fetchall()
        conexao.close()

        lista_react = []
        hoje = datetime.now().date()

        for linha in resultados:
            id_bol, nome, categoria, dt_venc_str, valor, status_db, linha_dig, caminho_img = linha
            
            # Lógica de Status
            status_react = "Pendente"
            if status_db == "PAGO": 
                status_react = "Pago"
            else:
                try:
                    dt_venc = datetime.strptime(dt_venc_str, "%d/%m/%Y").date()
                    if dt_venc < hoje: status_react = "Atrasado"
                except: pass

            # URL da Imagem para o botão de visualização
            url_img = None
            if caminho_img:
                url_img = f"http://localhost:5000/imagens/{os.path.basename(caminho_img)}"

            # Data em formato ISO para o React
            venc_iso = dt_venc_str
            try: venc_iso = datetime.strptime(dt_venc_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except: pass

            lista_react.append({
                "id": id_bol,
                "beneficiario": nome,
                "categoria": categoria, # Categoria agora vem do Banco!
                "vencimento": venc_iso,
                "valor": float(valor) if valor else 0.0,
                "status": status_react,
                "linhaDigitavel": linha_dig,
                "url_imagem": url_img
            })
        return jsonify(lista_react), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ROTA 3: NOVA! Salva as edições que você fizer diretamente na tabela do site
@app.route('/boletos/<int:id>', methods=['PATCH'])
def api_atualizar_boleto(id):
    try:
        dados = request.json
        novo_nome = dados.get('nome')
        nova_cat = dados.get('categoria')
        
        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute("UPDATE boletos SET nome = ?, categoria = ? WHERE id = ?", (novo_nome, nova_cat, id))
        conexao.commit()
        conexao.close()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ROTA 4: Processa a Imagem (IA)
@app.route('/boletos/process', methods=['POST'])
def api_processar_imagem():
    if 'file' not in request.files: return jsonify({"error": "No file"}), 400
    arquivo = request.files['file']
    
    if not os.path.exists('armazenamento'): os.makedirs('armazenamento')
    nome_persistente = f"boleto_{int(time.time())}{os.path.splitext(arquivo.filename)[1]}"
    caminho_destino = os.path.join('armazenamento', nome_persistente)
    arquivo.save(caminho_destino)

    try:
        # Extrai apenas os dados "brutos" (Data, Valor, Linha)
        data_venc, valor, linha_digitavel, _, _ = extrair_dados_boleto(caminho_destino)
        
        # Padrões iniciais para você editar depois no site
        nome_inicial = "Novo Boleto (Clique para editar)"
        categoria_inicial = "Outros"

        conexao = sqlite3.connect('boletos.db')
        cursor = conexao.cursor()
        cursor.execute(
            'INSERT INTO boletos (nome, categoria, data_inicio, data_vencimento, valor, linha_digitavel, caminho_imagem) VALUES (?, ?, ?, ?, ?, ?, ?)', 
            (nome_inicial, categoria_inicial, datetime.now().strftime("%d/%m/%Y"), data_venc, valor, linha_digitavel, caminho_destino)
        )
        conexao.commit()
        bol_id = cursor.lastrowid
        conexao.close()

        return jsonify({"id": bol_id, "status": "Pendente", "url_imagem": f"http://localhost:5000/imagens/{nome_persistente}"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ROTA 5: Pagar
@app.route('/boletos/pay/<int:id>', methods=['POST'])
def api_confirmar_pagamento(id):
    try:
        evaluate(PayNode(StringNode(str(id))))
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ROTA 6: Notificar
@app.route('/boletos/check', methods=['POST'])
def api_disparar_notificacoes():
    try:
        evaluate(CheckDueNode(StringNode("lixinhotestes@gmail.com")))
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# =====================================================================
# 10. EXECUTOR GERAL
# =====================================================================
def ler_arquivo(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as f: return f.read()
    except: return None

def rodar_codigo(codigo_fonte):
    tokens = tokenize(codigo_fonte)
    meu_parser = Parser(tokens)
    arvore = meu_parser.parse()
    if len(meu_parser.erros) > 0:
        for erro in meu_parser.erros: print("  ->", erro)
    else: evaluate(arvore)

if __name__ == "__main__":
    inicializar_banco()

    # MODO 1: Roda arquivos soltos arrastados para cima do .bat
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
    
    # MODO 2: Abre a porta da internet para renderizar o painel React
    else:
        print("\n=======================================================")
        print("     🚀 SERVIDOR WEB ATIVADO (API FLASK)       ")
        print(" O Back-End do compilador está online na porta 5000.   ")
        print(" Pode iniciar e testar a sua aplicação visual em React! ")
        print("=======================================================\n")
        app.run(host="0.0.0.0", port=5000, debug=False)
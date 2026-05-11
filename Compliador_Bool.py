import sys
import sqlite3
import smtplib
import re
import easyocr
from enum import Enum
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import schedule       
import time           
import threading

# ==============================
# 1. ENUM E DICIONÁRIO (A Nova Linguagem)
# ==============================
class TipoToken(Enum):
    IDENTIFICADOR = 1
    STRING = 2
    NUMERO_INTEIRO = 3
    ABRE_PARENTESES = 4
    FECHA_PARENTESES = 5
    VIRGULA = 6
    EOF = 7

    # Comandos do Sistema de Boletos
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

# ==============================
# 2. ÁRVORE SINTÁTICA (AST Nodes)
# ==============================
class Token:
    def __init__(self, tipo, valor=None):
        self.tipo = tipo
        self.valor = valor
    def __repr__(self):
        return f"{self.tipo.name}({self.valor})"

class StringNode:
    def __init__(self, valor):
        self.valor = valor
    def __repr__(self): 
        return f"String('{self.valor}')"

class EchoNode:
    def __init__(self, mensagem):
        self.mensagem = mensagem 
    def __repr__(self): 
        return f"EchoNode(msg={self.mensagem})"

class ProcessNode:
    def __init__(self, caminho_imagem):
        self.caminho_imagem = caminho_imagem
    def __repr__(self): 
        return f"ProcessNode(img={self.caminho_imagem})"

class MailNode:
    def __init__(self, destinatario, boleto_id):
        self.destinatario = destinatario
        self.boleto_id = boleto_id
    def __repr__(self): 
        return f"MailNode(to={self.destinatario}, id={self.boleto_id})"

class AddNode:
    def __init__(self, nome, data_inicio, data_vencimento, valor):
        self.nome = nome
        self.data_inicio = data_inicio
        self.data_vencimento = data_vencimento
        self.valor = valor
    def __repr__(self): 
        return f"AddNode(nome={self.nome}, inicio={self.data_inicio}, venc={self.data_vencimento}, valor={self.valor})"

class SearchNode:
    def __init__(self, filtro):
        self.filtro = filtro
    def __repr__(self): 
        return f"SearchNode(filtro={self.filtro})"

class PayNode:
    def __init__(self, boleto_id):
        self.boleto_id = boleto_id
    def __repr__(self): 
        return f"PayNode(id={self.boleto_id})"

class CheckDueNode:
    def __init__(self, email_notificacao):
        self.email_notificacao = email_notificacao
    def __repr__(self): 
        return f"CheckDueNode(email={self.email_notificacao})"
    
class AutoCheckNode:
    def __init__(self, horario, email):
        self.horario = horario
        self.email = email
    def __repr__(self): 
        return f"AutoCheckNode(hora={self.horario}, email={self.email})"
    

# ==============================
# 3. PARSER (Analisador Sintático)
# ==============================
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
        self.erros = []

    def parse(self):
        nodes = []
        while self._current().tipo != TipoToken.EOF:
            node = self._parse_expression()
            if node:
                nodes.append(node)
        return nodes

    def _current(self):
        if self.pos >= len(self.tokens):
            return self.tokens[-1] 
        return self.tokens[self.pos]

    def _advance(self):
        if self.pos < len(self.tokens) - 1:
            self.pos += 1

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
                                        TipoToken.BILLS_PAY, TipoToken.BILLS_CHECK):
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
            self._expect(TipoToken.ABRE_PARENTESES)
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

# ==============================
# 4. LEXER (Analisador Léxico)
# ==============================
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
            if i >= len(expressao):
                raise Exception("Erro Léxico: Aspas não fechadas!")
            tokens.append(Token(TipoToken.STRING, texto_string))
            i += 1 
            continue
            
        elif char.isdigit():
            texto_num = ""
            while i < len(expressao) and (expressao[i].isdigit() or expressao[i] == '.'):
                texto_num += expressao[i]
                i += 1
            tokens.append(Token(TipoToken.NUMERO_INTEIRO, texto_num))
            continue

        elif char == ',':
            tokens.append(Token(TipoToken.VIRGULA, ','))
        elif char == '(':
            tokens.append(Token(TipoToken.ABRE_PARENTESES, '('))
        elif char == ')':
            tokens.append(Token(TipoToken.FECHA_PARENTESES, ')'))

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

# ==============================
# 5. BANCO DE DADOS (SQLite)
# ==============================
def inicializar_banco():
    conexao = sqlite3.connect('boletos.db')
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS boletos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            data_inicio TEXT,
            data_vencimento TEXT,
            valor REAL,
            linha_digitavel TEXT,
            status TEXT DEFAULT 'PENDENTE'
        )
    ''')
    conexao.commit()
    conexao.close()
    print("[SISTEMA] Banco de dados 'boletos.db' inicializado e pronto!")

# ==============================
# 6. SISTEMA DE E-MAIL (SMTP)
# ==============================
def enviar_email_real(destinatario, assunto, mensagem):
    email_remetente = "lixinhotestes@gmail.com"
    senha_app = "c r a u n e k m f o h f c b a z" # <-- Lembre-se de colar sua senha de 16 letras aqui!

    if senha_app == "COLE_SUA_SENHA_DE_APP_AQUI":
        print("[ERRO SMTP] Você esqueceu de configurar a senha de App no código!")
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
        print(f"[ERRO SMTP] Falha ao enviar e-mail: {e}")
        return False

# ==============================
# 7. VISÃO COMPUTACIONAL (OCR + Lógica de Linha Digitável)
# ==============================
def extrair_dados_boleto(caminho_imagem):
    print("[IA_VISION] Analisando imagem...")
    try:
        reader = easyocr.Reader(['pt'], gpu=False, verbose=False) 
        resultados = reader.readtext(caminho_imagem, detail=0)
        texto_completo = " ".join(resultados)
        
        # 1. Busca Data
        match_data = re.search(r'\d{2}/\d{2}/\d{4}', texto_completo)
        data_venc = match_data.group(0) if match_data else None

        # 2. Busca Linha Digitável (47 dígitos)
        match_linha = re.search(r'\d{5}[\.\s]*\d{5}[\.\s]*\d{5}[\.\s]*\d{6}[\.\s]*\d{5}[\.\s]*\d{6}[\.\s]*\d[\.\s]*\d{14}', texto_completo)
        
        valor = 0.0
        linha_digitavel = "Não identificada"

        if match_linha:
            linha_digitavel = match_linha.group(0)
            # Limpa a linha para ter apenas números
            linha_limpa = re.sub(r'\D', '', linha_digitavel)
            
            if len(linha_limpa) == 47:
                # A MÁGICA: Os últimos 10 dígitos são o valor em centavos
                valor_centavos = linha_limpa[-10:]
                valor = float(valor_centavos) / 100.0
                print(f"  -> [INFO] Valor extraído via Linha Digitável: R${valor:.2f}")
        
        # 3. Se não achou valor pela linha, tenta pela regex de dinheiro (Fallback)
        if valor == 0.0:
            regex_dinheiro = r'(\d{1,3}(?:[\.\s]?\d{3})*[.,]\d{2})'
            todos_valores = re.findall(regex_dinheiro, texto_completo)
            if todos_valores:
                valor_str = todos_valores[-1].replace(' ', '').replace('.', '').replace(',', '.')
                valor = float(valor_str)

        return data_venc, valor, linha_digitavel
    except Exception as e:
        print(f"[ERRO IA] Falha ao processar imagem: {e}")
        return None, 0.0, "Erro"

# ==============================
# 8. AVALIADOR 
# ==============================
def evaluate(node):
    if isinstance(node, list):
        for statement in node:
            evaluate(statement)
        return

    if isinstance(node, StringNode):
        return node.valor

    if isinstance(node, EchoNode):
        msg = node.mensagem.valor if isinstance(node.mensagem, StringNode) else node.mensagem
        print(f"[SISTEMA_AVISO] -> {msg}")
        return

    if isinstance(node, MailNode):
        email = node.destinatario.valor if isinstance(node.destinatario, StringNode) else node.destinatario
        print(f"[SMTP_GMAIL] Enviando e-mail para '{email}' sobre o boleto ID: {node.boleto_id}...")
        return

    if isinstance(node, ProcessNode):
        img_path = node.caminho_imagem.valor if isinstance(node.caminho_imagem, StringNode) else node.caminho_imagem
        print(f"\n[YOLO_OCR_IA] Analisando: {img_path}")
        
        data_venc, valor, linha_digitavel = extrair_dados_boleto(img_path)
        
        # --- INTERVENÇÃO MANUAL ---
        nome_boleto = "Boleto Escaneado"
        
        if not data_venc:
            print("  ⚠️ [IA_ALERTA] Não consegui ler a DATA DE VENCIMENTO.")
            data_venc = input("     Por favor, digite a data (DD/MM/AAAA): ")
            nome_boleto = input("     Dê um nome para este boleto (ex: Luz, Internet): ")
            
        if valor == 0.0:
            print("  ⚠️ [IA_ALERTA] Não consegui identificar o VALOR.")
            valor = float(input("     Por favor, digite o valor (ex: 150.50): ").replace(',', '.'))    

        # --- SALVAMENTO FINAL ---
        if data_venc and valor > 0:
            try:
                conexao = sqlite3.connect('boletos.db')
                cursor = conexao.cursor()
                hoje_str = datetime.now().strftime("%d/%m/%Y")
                
                cursor.execute('''
                    INSERT INTO boletos (nome, data_inicio, data_vencimento, valor, linha_digitavel)
                    VALUES (?, ?, ?, ?, ?)
                ''', (nome_boleto, hoje_str, data_venc, valor, linha_digitavel))
                
                conexao.commit()
                print(f"  -> [SQLITE_DB] Boleto '{nome_boleto}' salvo com sucesso! (ID: {cursor.lastrowid})")
                conexao.close()
            except Exception as e:
                print(f"  -> [ERRO SQLITE] Falha ao salvar: {e}")
        return
    
    if isinstance(node, AutoCheckNode):
        horario = node.horario.valor if isinstance(node.horario, StringNode) else node.horario
        email_alvo = node.email.valor if isinstance(node.email, StringNode) else node.email

        # Função que será ativada no horário marcado
        def tarefa_diaria():
            print(f"\n[ROBÔ DIÁRIO] Acordando às {horario}! Executando varredura...")
            # Reutilizamos o CheckDueNode que você já tem pronto!
            evaluate(CheckDueNode(StringNode(email_alvo)))

        # Agenda a tarefa
        schedule.every().day.at(horario).do(tarefa_diaria)

        # Cria o motor invisível (Thread) para não travar o seu terminal
        def rodar_agendador():
            while True:
                schedule.run_pending()
                time.sleep(60) # Verifica o relógio a cada 1 minuto

        motor_invisivel = threading.Thread(target=rodar_agendador, daemon=True)
        motor_invisivel.start()

        print(f"✅ [SISTEMA_AUTO] Automação ativada com sucesso!")
        print(f"   -> Todos os dias, às {horario}, o sistema verificará boletos para '{email_alvo}'.")
        print(f"   -> (Mantenha este terminal aberto para o robô funcionar).")
        return

    if isinstance(node, AddNode):
        n = node.nome.valor if isinstance(node.nome, StringNode) else node.nome
        inicio = node.data_inicio.valor if isinstance(node.data_inicio, StringNode) else node.data_inicio
        venc = node.data_vencimento.valor if isinstance(node.data_vencimento, StringNode) else node.data_vencimento
        valor_numero = float(node.valor.valor if hasattr(node.valor, 'valor') else node.valor)
        
        try:
            conexao = sqlite3.connect('boletos.db')
            cursor = conexao.cursor()
            # A inserção manual não tem linha digitável, então o banco vai salvar como NULL automaticamente
            cursor.execute('''
                INSERT INTO boletos (nome, data_inicio, data_vencimento, valor)
                VALUES (?, ?, ?, ?)
            ''', (n, inicio, venc, valor_numero))
            conexao.commit()
            boleto_id = cursor.lastrowid
            conexao.close()
            print(f"[SQLITE_DB] Sucesso! Boleto manual '{n}' salvo. (ID: {boleto_id})")
        except Exception as e:
            print(f"[SQLITE_DB] Erro ao salvar no banco: {e}")
        return

    if isinstance(node, SearchNode):
        filtro_str = node.filtro.valor if isinstance(node.filtro, StringNode) else node.filtro
        
        try:
            conexao = sqlite3.connect('boletos.db')
            cursor = conexao.cursor()
            
            if str(filtro_str).upper() == "TODOS":
                cursor.execute("SELECT id, nome, data_vencimento, valor, status FROM boletos")
            else:
                cursor.execute("SELECT id, nome, data_vencimento, valor, status FROM boletos WHERE status = ? OR nome LIKE ?", (str(filtro_str).upper(), f"%{filtro_str}%"))
                
            resultados = cursor.fetchall()
            conexao.close()
            
            print(f"\n--- 📋 RESULTADO DA BUSCA: '{filtro_str}' ---")
            if len(resultados) == 0:
                print("Nenhum boleto encontrado com esse filtro.")
            else:
                for linha in resultados:
                    id_bol, nome, dt_venc, valor, status = linha
                    print(f"[{id_bol}] {nome} | Vence: {dt_venc} | R${valor:.2f} | Status: {status}")
            print("----------------------------------------\n")
            
        except Exception as e:
            print(f"[SQLITE_DB] Erro na busca: {e}")
        return

    if isinstance(node, PayNode):
        id_alvo = node.boleto_id.valor if hasattr(node.boleto_id, 'valor') else node.boleto_id
        try:
            conexao = sqlite3.connect('boletos.db')
            cursor = conexao.cursor()
            cursor.execute("UPDATE boletos SET status = 'PAGO' WHERE id = ?", (id_alvo,))
            if cursor.rowcount > 0:
                print(f"[SQLITE_DB] Boleto ID {id_alvo} atualizado para PAGO! Notificações desativadas.")
            else:
                print(f"[SQLITE_DB] Nenhum boleto encontrado com o ID {id_alvo}.")
            conexao.commit()
            conexao.close()
        except Exception as e:
            print(f"[SQLITE_DB] Erro ao atualizar pagamento: {e}")
        return

    if isinstance(node, CheckDueNode):
        email_alvo = node.email_notificacao.valor if hasattr(node.email_notificacao, 'valor') else node.email_notificacao
        hoje = datetime.now().date()
        
        try:
            conexao = sqlite3.connect('boletos.db')
            cursor = conexao.cursor()
            cursor.execute("SELECT id, nome, data_vencimento, valor FROM boletos WHERE status != 'PAGO'")
            pendentes = cursor.fetchall()
            conexao.close()
            
            print(f"\n[SISTEMA] Verificando vencimentos para notificar '{email_alvo}'...")
            avisos_enviados = 0
            
            for boleto in pendentes:
                id_bol, nome, dt_venc_str, valor = boleto
                try:
                    data_vencimento = datetime.strptime(dt_venc_str, "%d/%m/%Y").date()
                    diferenca_dias = (data_vencimento - hoje).days
                    
                    if diferenca_dias <= 3 and diferenca_dias >= 0:
                        print(f" ⚠️ [EMAIL] Preparando aviso de {diferenca_dias} dias para '{nome}'...")
                        assunto = f"Aviso de Vencimento: {nome}"
                        corpo = f"Olá!\n\nO boleto '{nome}' (ID: {id_bol}) vence em {diferenca_dias} dias ({dt_venc_str}).\nValor: R${valor:.2f}\n\nPor favor, não esqueça de realizar o pagamento."
                        
                        if enviar_email_real(email_alvo, assunto, corpo):
                            print("    -> E-mail ENVIADO de verdade com sucesso!")
                        avisos_enviados += 1
                        
                    elif diferenca_dias < 0:
                        print(f" 🚨 [EMAIL] Preparando alerta de ATRASO para '{nome}'...")
                        assunto = f"URGENTE: Boleto Atrasado - {nome}"
                        corpo = f"ALERTA!\n\nO boleto '{nome}' (ID: {id_bol}) está ATRASADO há {abs(diferenca_dias)} dias!\nVencimento original: {dt_venc_str}\nValor: R${valor:.2f}\n\nRegularize a situação o mais rápido possível."
                        
                        if enviar_email_real(email_alvo, assunto, corpo):
                            print("    -> E-mail de cobrança ENVIADO de verdade com sucesso!")
                        avisos_enviados += 1
                        
                except ValueError:
                    print(f" [ERRO] O boleto ID {id_bol} possui uma data em formato inválido ({dt_venc_str}). Use DD/MM/YYYY.")
                    
            if avisos_enviados == 0:
                print(" -> Nenhum boleto próximo do vencimento hoje. Ufa!")
                
        except Exception as e:
            print(f"[SISTEMA] Erro ao verificar datas: {e}")
        return

# ==============================
# 9. TERMINAL INTERATIVO
# ==============================
def rodar_codigo(codigo_fonte):
    try:
        tokens = tokenize(codigo_fonte)
        meu_parser = Parser(tokens)
        arvore = meu_parser.parse()

        if len(meu_parser.erros) > 0:
            print("\nErros Encontrados:")
            for erro in meu_parser.erros:
                print("  ->", erro)
        else:
            evaluate(arvore)
                
    except Exception as e:
        print(f"\n[ERRO CRÍTICO] Ocorreu um problema na execução:\n -> {e}")

def modo_interativo():
    print("=======================================")
    print("   Sistema de Gestão de Boletos (IA)   ")
    print("   Digite 'sair' para fechar.          ")
    print("=======================================\n")
    
    while True:
        try:
            entrada = input("boletos> ")
            if entrada.strip().lower() == 'sair':
                print("Encerrando sistema...")
                break
            if not entrada.strip():
                continue
            rodar_codigo(entrada)
            
        except KeyboardInterrupt:
            print("\nSaindo...")
            break

def ler_arquivo(caminho):
    """Lê o conteúdo de um arquivo de texto"""
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Erro ao ler o arquivo: {e}")
        return None

if __name__ == "__main__":
    inicializar_banco()

    # Verifica se o usuário passou um arquivo ao abrir o programa
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
        # Se não passou arquivo nenhum, abre o terminal interativo normal
        modo_interativo()
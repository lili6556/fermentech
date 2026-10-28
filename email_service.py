
import os
import smtplib
import ssl

from pathlib import Path
from email.message import EmailMessage
from dotenv import load_dotenv


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# Carrega as variáveis do arquivo .env
load_dotenv(BASE_DIR / ".env")


# ============================================================
# ENVIO DE E-MAIL
# ============================================================

def enviar_senha_por_email(email, nome, senha):

    """
    Envia ao funcionário um e-mail com sua senha temporária.

    Parâmetros:
        email: e-mail pessoal do funcionário.
        nome: nome do funcionário.
        senha: senha temporária gerada pelo app.py.

    Retorna:
        True  -> envio aceito pelo servidor SMTP.
        False -> ocorreu um erro durante o envio.
    """

    # --------------------------------------------------------
    # Recupera as configurações do .env
    # --------------------------------------------------------

    remetente = os.getenv(
        "SMTP_USER",
        ""
    ).strip()

    senha_app = os.getenv(
        "SMTP_PASSWORD",
        ""
    ).strip()

    nome_sistema = os.getenv(
        "SMTP_FROM_NAME",
        "FERMENTECH"
    ).strip()

    servidor_smtp = os.getenv(
        "SMTP_HOST",
        "smtp.gmail.com"
    ).strip()

    try:
        porta_smtp = int(
            os.getenv("SMTP_PORT", "587")
        )
    except ValueError:
        print("ERRO: SMTP_PORT precisa ser um número.")
        return False

    # --------------------------------------------------------
    # Valida as configurações
    # --------------------------------------------------------

    if not remetente or not senha_app:
        print(
            "ERRO: configure SMTP_USER e SMTP_PASSWORD "
            "no arquivo .env."
        )
        return False

    if not email or not nome or not senha:
        print(
            "ERRO: e-mail, nome e senha são obrigatórios."
        )
        return False

    # --------------------------------------------------------
    # Monta a mensagem
    # --------------------------------------------------------

    mensagem = EmailMessage()

    mensagem["Subject"] = "Seu acesso ao FERMENTECH"

    mensagem["From"] = f"{nome_sistema} <{remetente}>"

    mensagem["To"] = email

    mensagem.set_content(
        f"""Olá, {nome}!

Seu acesso ao FERMENTECH foi criado.

E-mail de acesso: {email}
Senha temporária: {senha}

Por segurança, altere sua senha após o primeiro acesso.

Se você não esperava receber esta mensagem, entre em contato
com a administração do FERMENTECH.

Atenciosamente,
Equipe FERMENTECH
"""
    )

    # --------------------------------------------------------
    # Conecta ao Gmail e envia a mensagem
    # --------------------------------------------------------

    try:
        print("=" * 55)
        print("FERMENTECH - ENVIO DE E-MAIL")
        print(f"Destinatário: {email}")
        print(f"Remetente: {remetente}")
        print(f"Servidor: {servidor_smtp}")
        print(f"Porta: {porta_smtp}")
        print("Iniciando conexão SMTP...")

        contexto_ssl = ssl.create_default_context()

        with smtplib.SMTP(
    servidor_smtp,
    porta_smtp,
    timeout=15
) as servidor:

            # Identifica o cliente SMTP
            servidor.ehlo()

            # Ativa a conexão criptografada
            servidor.starttls(
                context=contexto_ssl
            )

            # Identifica novamente após ativar TLS
            servidor.ehlo()

            # Autentica a conta remetente
            print("Autenticando no Gmail...")

            servidor.login(
                remetente,
                senha_app
            )

            # Envia a mensagem
            print("Enviando mensagem...")

            servidor.send_message(
                mensagem
            )

        print("E-mail enviado com sucesso!")
        print("=" * 55)

        return True

    except smtplib.SMTPAuthenticationError as erro:
        print("ERRO: falha na autenticação do Gmail.")
        print("Confira o e-mail remetente e a senha de aplicativo.")
        print(f"Detalhes SMTP: {erro}")
        return False

    except smtplib.SMTPRecipientsRefused as erro:
        print("ERRO: o servidor recusou o destinatário.")
        print(f"Detalhes SMTP: {erro}")
        return False

    except smtplib.SMTPException as erro:
        print("ERRO SMTP durante o envio.")
        print(f"Tipo: {type(erro).__name__}")
        print(f"Detalhes: {erro}")
        return False

    except (TimeoutError, OSError) as erro:
        print("ERRO: não foi possível conectar ao servidor SMTP.")
        print(f"Tipo: {type(erro).__name__}")
        print(f"Detalhes: {erro}")
        print(
            "Confira a conectividade com o servidor, "
            "a porta SMTP e possíveis bloqueios de rede."
        )
        return False

    except Exception as erro:
        print("ERRO inesperado ao enviar o e-mail.")
        print(f"Tipo: {type(erro).__name__}")
        print(f"Detalhes: {erro}")
        return False

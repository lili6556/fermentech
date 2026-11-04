
import os
import json
import urllib.request
import urllib.error

from pathlib import Path
from dotenv import load_dotenv


# ============================================================
# CONFIGURAÇÃO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

# Carrega as variáveis do arquivo .env
load_dotenv(BASE_DIR / ".env")


# ============================================================
# ENVIO DE E-MAIL PELA API BREVO
# ============================================================

def enviar_senha_por_email(email, nome, senha):

    """
    Envia ao funcionário um e-mail com sua senha temporária
    utilizando a API HTTPS da Brevo.

    Parâmetros:
        email: e-mail pessoal do funcionário.
        nome: nome do funcionário.
        senha: senha temporária gerada pelo app.py.

    Retorna:
        True  -> solicitação de envio aceita pela API.
        False -> ocorreu algum erro durante o envio.
    """

    # --------------------------------------------------------
    # Recupera as configurações do ambiente
    # --------------------------------------------------------

    api_key = os.getenv(
        "BREVO_API_KEY",
        ""
    ).strip()

    remetente = os.getenv(
        "BREVO_SENDER_EMAIL",
        ""
    ).strip()

    nome_sistema = os.getenv(
        "BREVO_SENDER_NAME",
        "FERMENTECH"
    ).strip()

    # --------------------------------------------------------
    # Valida as configurações
    # --------------------------------------------------------

    if not api_key:
        print("ERRO: configure BREVO_API_KEY no ambiente.")
        return False

    if not remetente:
        print("ERRO: configure BREVO_SENDER_EMAIL no ambiente.")
        return False

    if not email or not nome or not senha:
        print("ERRO: e-mail, nome e senha são obrigatórios.")
        return False

    # --------------------------------------------------------
    # Monta a mensagem
    # --------------------------------------------------------

    assunto = "Seu acesso ao FERMENTECH"

    conteudo = f"""Olá, {nome}!

Seu acesso ao FERMENTECH foi criado.

E-mail de acesso: {email}
Senha temporária: {senha}

Por segurança, altere sua senha após o primeiro acesso.

Se você não esperava receber esta mensagem, entre em contato
com a administração do FERMENTECH.

Atenciosamente,
Equipe FERMENTECH
"""

    dados = {
        "sender": {
            "name": nome_sistema,
            "email": remetente
        },
        "to": [
            {
                "email": email,
                "name": nome
            }
        ],
        "subject": assunto,
        "textContent": conteudo
    }

    # Converte os dados para JSON
    corpo = json.dumps(dados).encode("utf-8")

    # --------------------------------------------------------
    # Prepara a requisição HTTPS
    # --------------------------------------------------------

    requisicao = urllib.request.Request(
        url="https://api.brevo.com/v3/smtp/email",
        data=corpo,
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        },
        method="POST"
    )

    # --------------------------------------------------------
    # Conecta à API e envia o e-mail
    # --------------------------------------------------------

    try:
        print("=" * 55)
        print("FERMENTECH - ENVIO DE E-MAIL PELA BREVO")
        print(f"Destinatário: {email}")
        print(f"Remetente: {remetente}")
        print("Iniciando conexão HTTPS...")

        with urllib.request.urlopen(
            requisicao,
            timeout=20
        ) as resposta:

            resultado = resposta.read().decode("utf-8")
            codigo = resposta.status

        if codigo == 201:
            try:
                resposta_json = json.loads(resultado)
                message_id = resposta_json.get("messageId")
            except json.JSONDecodeError:
                message_id = None

            print("Solicitação de envio aceita pela Brevo!")

            if message_id:
                print(f"ID da mensagem: {message_id}")

            print("=" * 55)

            return True

        print(f"ERRO: resposta inesperada da API: {codigo}")
        print(resultado)

        return False

    # --------------------------------------------------------
    # Tratamento de erros HTTP
    # --------------------------------------------------------

    except urllib.error.HTTPError as erro:

        detalhes = erro.read().decode(
            "utf-8",
            errors="replace"
        )

        print("ERRO: a API recusou a solicitação.")
        print(f"Código HTTP: {erro.code}")
        print(f"Detalhes: {detalhes}")

        return False

    # --------------------------------------------------------
    # Tratamento de erros de conexão
    # --------------------------------------------------------

    except urllib.error.URLError as erro:

        print("ERRO: não foi possível conectar à API.")
        print(f"Detalhes: {erro.reason}")

        return False

    except TimeoutError:

        print("ERRO: tempo limite de conexão excedido.")

        return False

    # --------------------------------------------------------
    # Outros erros
    # --------------------------------------------------------

    except Exception as erro:

        print("ERRO inesperado ao enviar o e-mail.")
        print(f"Tipo: {type(erro).__name__}")
        print(f"Detalhes: {erro}")

        return False


import os
import secrets
import string
import sqlite3
import re

from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)

from email_service import enviar_senha_por_email


# ============================================================
# CONFIGURAÇÃO DO PROJETO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

# Caminho configurável do banco.
# Localmente utiliza fermentech.db.
# No Render, configure DATABASE_PATH para o caminho
# do disco persistente realmente montado no serviço.

BANCO_DADOS = Path(
    os.getenv(
        "DATABASE_PATH",
        str(BASE_DIR / "fermentech.db")
    )
)


# ============================================================
# CRIAÇÃO DO FLASK
# ============================================================

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv(
    "FERMENTECH_SECRET_KEY"
)

if not app.config["SECRET_KEY"]:
    raise RuntimeError(
        "FERMENTECH_SECRET_KEY não foi encontrada no arquivo .env"
    )

app.config["SESSION_COOKIE_HTTPONLY"] = True

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("COOKIE_SECURE", "false").lower() == "true"
)

app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024


# ============================================================
# USUÁRIOS DE TESTE
# ============================================================

USUARIOS_TESTE = {
    "aliciaadmin3@gmail.com": {
        "nome": "Administradora FERMENTECH",
        "senha": os.getenv("ADMIN_TEST_PASSWORD", ""),
        "tipo": "admin",
    },

    "aliciafuncionaria3@gmail.com": {
        "nome": "Funcionária FERMENTECH",
        "senha": os.getenv("FUNCIONARIO_TEST_PASSWORD", ""),
        "tipo": "funcionario",
    },
}


# ============================================================
# BANCO DE DADOS SQLITE
# ============================================================

def conectar_banco():
    """
    Abre uma conexão com o banco SQLite.

    O caminho pode ser configurado pela variável
    DATABASE_PATH.
    """

    BANCO_DADOS.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    conexao = sqlite3.connect(
        str(BANCO_DADOS),
        timeout=30
    )

    conexao.row_factory = sqlite3.Row

    conexao.execute(
        "PRAGMA busy_timeout = 30000"
    )

    return conexao


# ============================================================
# INICIALIZAR BANCO
# ============================================================

def inicializar_banco():
    """
    Cria as tabelas necessárias.

    CREATE TABLE IF NOT EXISTS não apaga
    os registros de tabelas existentes.
    """

    with conectar_banco() as conexao:

        # ----------------------------------------------------
        # USUÁRIOS
        # ----------------------------------------------------

        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                nome TEXT NOT NULL,

                email TEXT NOT NULL COLLATE NOCASE UNIQUE,

                senha_hash TEXT NOT NULL,

                tipo TEXT NOT NULL
                    CHECK (tipo IN ('admin', 'funcionario')),

                status TEXT NOT NULL DEFAULT 'Ativo',

                criado_em TEXT NOT NULL
            )
            """
        )

        # ----------------------------------------------------
        # RESPONSABILIDADES DO COCHO
        # ----------------------------------------------------

        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS responsabilidades_cocho (
                cocho_codigo TEXT PRIMARY KEY,

                usuario_id INTEGER,

                usuario_nome TEXT NOT NULL,

                usuario_email TEXT NOT NULL,

                inicio TEXT NOT NULL,

                fim TEXT NOT NULL,

                dias INTEGER NOT NULL,

                tipo TEXT NOT NULL
            )
            """
        )

        # ----------------------------------------------------
        # HISTÓRICO DA FERMENTAÇÃO
        # ----------------------------------------------------

        conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_fermentacao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                cocho_codigo TEXT NOT NULL,

                temperatura REAL NOT NULL,

                status TEXT NOT NULL,

                data_hora TEXT NOT NULL
            )
            """
        )

        # ----------------------------------------------------
        # ÍNDICE DO HISTÓRICO
        # ----------------------------------------------------

        conexao.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_historico_cocho_data
            ON historico_fermentacao (
                cocho_codigo,
                data_hora
            )
            """
        )

        # ----------------------------------------------------
        # CONTAS DE TESTE
        # ----------------------------------------------------

        for email_teste, dados_teste in USUARIOS_TESTE.items():

            senha_teste = dados_teste.get("senha", "")

            if not senha_teste:
                continue

            existente = conexao.execute(
                """
                SELECT id
                FROM usuarios
                WHERE email = ? COLLATE NOCASE
                """,
                (email_teste,),
            ).fetchone()

            if existente is None:

                conexao.execute(
                    """
                    INSERT INTO usuarios (
                        nome,
                        email,
                        senha_hash,
                        tipo,
                        status,
                        criado_em
                    )
                    VALUES (?, ?, ?, ?, 'Ativo', ?)
                    """,
                    (
                        dados_teste["nome"],
                        email_teste,
                        generate_password_hash(senha_teste),
                        dados_teste["tipo"],
                        datetime.now().isoformat(
                            timespec="seconds"
                        ),
                    ),
                )


# Inicializa o banco antes de iniciar o Flask.
inicializar_banco()


# ============================================================
# BUSCAR USUÁRIO POR E-MAIL
# ============================================================

def buscar_usuario_por_email(email):

    email = email.strip().lower()

    with conectar_banco() as conexao:

        return conexao.execute(
            """
            SELECT *
            FROM usuarios
            WHERE email = ? COLLATE NOCASE
            """,
            (email,),
        ).fetchone()


# ============================================================
# LISTAR FUNCIONÁRIOS
# ============================================================

def listar_funcionarios():

    with conectar_banco() as conexao:

        linhas = conexao.execute(
            """
            SELECT id, nome, email, status
            FROM usuarios
            WHERE tipo = 'funcionario'
            ORDER BY nome COLLATE NOCASE
            """
        ).fetchall()

        return [
            dict(linha)
            for linha in linhas
        ]


# ============================================================
# CRIAR FUNCIONÁRIO
# ============================================================

def criar_funcionario(nome, email, senha_temporaria):

    senha_hash = generate_password_hash(
        senha_temporaria
    )

    with conectar_banco() as conexao:

        conexao.execute(
            """
            INSERT INTO usuarios (
                nome,
                email,
                senha_hash,
                tipo,
                status,
                criado_em
            )
            VALUES (
                ?, ?, ?, 'funcionario', 'Ativo', ?
            )
            """,
            (
                nome,
                email.strip().lower(),
                senha_hash,
                datetime.now().isoformat(
                    timespec="seconds"
                ),
            ),
        )


# ============================================================
# GERAÇÃO DE SENHA TEMPORÁRIA
# ============================================================

def gerar_senha_aleatoria(tamanho=12):

    caracteres = (
        string.ascii_letters
        + string.digits
        + "!@#$%&*"
    )

    return "".join(
        secrets.choice(caracteres)
        for _ in range(tamanho)
    )


# ============================================================
# VERIFICAÇÃO DE SESSÃO DO FUNCIONÁRIO
# ============================================================

@app.before_request
def verificar_sessao_funcionario():

    if (
        not session.get("autenticado")
        or session.get("tipo") != "funcionario"
    ):
        return None

    usuario_id = session.get("usuario_id")

    # Contas de teste antigas podem não ter ID.
    if usuario_id is None:
        return None

    with conectar_banco() as conexao:

        usuario = conexao.execute(
            """
            SELECT id, nome, email, status
            FROM usuarios
            WHERE id = ?
              AND tipo = 'funcionario'
            """,
            (usuario_id,),
        ).fetchone()

    if not usuario or usuario["status"] != "Ativo":

        session.clear()

        flash(
            "Sua conta está bloqueada ou não está mais disponível. "
            "Entre em contato com a administradora.",
            "erro",
        )

        return redirect(
            url_for("login")
        )

    session["nome"] = usuario["nome"]

    session["email"] = usuario["email"]

    return None


# ============================================================
# PÁGINA INICIAL
# ============================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ============================================================
# API DE SESSÃO
# ============================================================

@app.route("/api/sessao")
def api_sessao():

    return jsonify({
        "autenticado": bool(
            session.get("autenticado")
        ),

        "tipo": session.get("tipo"),

        "nome": session.get("nome"),

        "email": session.get("email"),
    })


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get("autenticado"):

        if session.get("tipo") == "admin":

            return redirect(
                url_for("painel_admin")
            )

        if session.get("tipo") == "funcionario":

            return redirect(
                url_for("painel_funcionario")
            )

    if request.method == "POST":

        email = request.form.get(
            "email", ""
        ).strip().lower()

        senha = request.form.get(
            "senha", ""
        )

        usuario = buscar_usuario_por_email(
            email
        )

        # ----------------------------------------------------
        # LOGIN PELO BANCO
        # ----------------------------------------------------

        if usuario is not None:

            if (
                usuario["status"].strip().lower() == "ativo"
                and check_password_hash(
                    usuario["senha_hash"],
                    senha
                )
            ):

                session.clear()

                session["autenticado"] = True

                session["usuario_id"] = usuario["id"]

                session["email"] = usuario["email"]

                session["nome"] = usuario["nome"]

                session["tipo"] = usuario["tipo"]

                if usuario["tipo"] == "admin":

                    return redirect(
                        url_for("painel_admin")
                    )

                return redirect(
                    url_for("painel_funcionario")
                )

        # ----------------------------------------------------
        # CONTAS DE TESTE
        # ----------------------------------------------------

        else:

            usuario_teste = USUARIOS_TESTE.get(
                email
            )

            if (
                usuario_teste
                and usuario_teste["senha"]
                and secrets.compare_digest(
                    usuario_teste["senha"],
                    senha
                )
            ):

                session.clear()

                session["autenticado"] = True

                session["email"] = email

                session["nome"] = usuario_teste["nome"]

                session["tipo"] = usuario_teste["tipo"]

                if usuario_teste["tipo"] == "admin":

                    return redirect(
                        url_for("painel_admin")
                    )

                return redirect(
                    url_for("painel_funcionario")
                )

        flash(
            "E-mail ou senha incorretos.",
            "erro",
        )

    return render_template(
        "login.html"
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("index")
    )


# ============================================================
# PAINEL ADMINISTRADOR
# ============================================================

@app.route("/painel/admin")
def painel_admin():

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    if session.get("tipo") != "admin":

        return redirect(
            url_for("login")
        )

    return render_template(
        "menuadmin.html",
        nome=session.get("nome"),
        email=session.get("email"),
    )


# ============================================================
# PAINEL FUNCIONÁRIO
# ============================================================

@app.route("/painel/funcionario")
def painel_funcionario():

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    if session.get("tipo") != "funcionario":

        return redirect(
            url_for("login")
        )

    return render_template(
        "menufuncionario.html",
        nome=session.get("nome"),
        email=session.get("email"),
    )


# ============================================================
# PERFIL
# ============================================================

@app.route("/perfil", methods=["GET", "POST"])
def perfil():

    if not session.get("autenticado"):

        flash(
            "Faça login para acessar seu perfil.",
            "error",
        )

        return redirect(
            url_for("login")
        )

    email_sessao = session.get("email")

    usuario_id = session.get("usuario_id")

    if not email_sessao:

        session.clear()

        flash(
            "Sua sessão está incompleta. Entre novamente.",
            "error",
        )

        return redirect(
            url_for("login")
        )

    try:

        with conectar_banco() as conexao:

            if usuario_id is not None:

                usuario = conexao.execute(
                    """
                    SELECT id, nome, email, senha_hash, tipo, status
                    FROM usuarios
                    WHERE id = ?
                    """,
                    (usuario_id,),
                ).fetchone()

            else:

                usuario = conexao.execute(
                    """
                    SELECT id, nome, email, senha_hash, tipo, status
                    FROM usuarios
                    WHERE email = ? COLLATE NOCASE
                    """,
                    (
                        email_sessao.strip().lower(),
                    ),
                ).fetchone()

            if usuario is None:

                flash(
                    "Não foi possível localizar sua conta no banco. "
                    "Entre novamente e confira a configuração do banco.",
                    "error",
                )

                return redirect(
                    url_for("login")
                )

            if usuario["status"].strip().lower() != "ativo":

                session.clear()

                flash(
                    "Sua conta está bloqueada.",
                    "error",
                )

                return redirect(
                    url_for("login")
                )

            # ------------------------------------------------
            # ALTERAÇÕES DO PERFIL
            # ------------------------------------------------

            if request.method == "POST":

                acao = request.form.get(
                    "acao", ""
                ).strip()

                # --------------------------------------------
                # ALTERAR NOME
                # --------------------------------------------

                if acao == "alterar_nome":

                    nome = request.form.get(
                        "nome", ""
                    ).strip()

                    if len(nome) < 2 or len(nome) > 100:

                        flash(
                            "O nome deve ter entre 2 e 100 caracteres.",
                            "error",
                        )

                    else:

                        conexao.execute(
                            """
                            UPDATE usuarios
                            SET nome = ?
                            WHERE id = ?
                            """,
                            (
                                nome,
                                usuario["id"],
                            ),
                        )

                        conexao.commit()

                        session["usuario_id"] = usuario["id"]

                        session["nome"] = nome

                        session["email"] = usuario["email"]

                        session["tipo"] = usuario["tipo"]

                        flash(
                            "Nome atualizado com sucesso!",
                            "success",
                        )

                        return redirect(
                            url_for("perfil")
                        )

                # --------------------------------------------
                # ALTERAR SENHA
                # --------------------------------------------

                elif acao == "alterar_senha":

                    senha_atual = request.form.get(
                        "senha_atual", ""
                    )

                    nova_senha = request.form.get(
                        "nova_senha", ""
                    )

                    confirmar_senha = request.form.get(
                        "confirmar_senha", ""
                    )

                    if not check_password_hash(
                        usuario["senha_hash"],
                        senha_atual,
                    ):

                        flash(
                            "A senha atual está incorreta.",
                            "error",
                        )

                    elif len(nova_senha) < 8:

                        flash(
                            "A nova senha deve ter pelo menos 8 caracteres.",
                            "error",
                        )

                    elif len(nova_senha) > 128:

                        flash(
                            "A nova senha não pode ultrapassar 128 caracteres.",
                            "error",
                        )

                    elif nova_senha != confirmar_senha:

                        flash(
                            "As novas senhas não coincidem.",
                            "error",
                        )

                    elif check_password_hash(
                        usuario["senha_hash"],
                        nova_senha,
                    ):

                        flash(
                            "Escolha uma senha diferente da atual.",
                            "error",
                        )

                    else:

                        novo_hash = generate_password_hash(
                            nova_senha
                        )

                        conexao.execute(
                            """
                            UPDATE usuarios
                            SET senha_hash = ?
                            WHERE id = ?
                            """,
                            (
                                novo_hash,
                                usuario["id"],
                            ),
                        )

                        conexao.commit()

                        flash(
                            "Senha alterada com sucesso!",
                            "success",
                        )

                        return redirect(
                            url_for("perfil")
                        )

                else:

                    flash(
                        "Ação inválida. Tente novamente.",
                        "error",
                    )

            # ------------------------------------------------
            # SINCRONIZAR SESSÃO
            # ------------------------------------------------

            session["usuario_id"] = usuario["id"]

            session["nome"] = usuario["nome"]

            session["email"] = usuario["email"]

            session["tipo"] = usuario["tipo"]

            tipo_conta = (
                "Administradora"
                if usuario["tipo"] == "admin"
                else "Funcionário"
            )

            return render_template(
                "perfil.html",
                nome=usuario["nome"],
                email=usuario["email"],
                tipo_conta=tipo_conta,
                status_conta=usuario["status"],
            )

    except sqlite3.Error:

        app.logger.exception(
            "Erro ao acessar ou atualizar o perfil."
        )

        flash(
            "Não foi possível atualizar seu perfil agora.",
            "error",
        )

        if session.get("tipo") == "admin":

            return redirect(
                url_for("painel_admin")
            )

        return redirect(
            url_for("painel_funcionario")
        )


# ============================================================
# VOLTAR AO PERFIL
# ============================================================

@app.route("/voltar-perfil")
def voltar_perfil():

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    if session.get("tipo") == "admin":

        return redirect(
            url_for("painel_admin")
        )

    if session.get("tipo") == "funcionario":

        return redirect(
            url_for("painel_funcionario")
        )

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# ESCANEAR QR CODE
# ============================================================

@app.route("/scanear-qr")
def scanear_qr():

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    return render_template(
        "scanear_qr.html"
    )


# ============================================================
# COCHO FT-001
# ============================================================

@app.route("/cocho/<codigo>", methods=["GET", "POST"])
def cocho(codigo):

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    if codigo != "FT-001":

        return "Cocho não encontrado.", 404

    agora = datetime.now()

    try:

        with conectar_banco() as conexao:

            conexao.execute(
                "BEGIN IMMEDIATE"
            )

            atual = conexao.execute(
                """
                SELECT *
                FROM responsabilidades_cocho
                WHERE cocho_codigo = ?
                """,
                (codigo,),
            ).fetchone()

            # ----------------------------------------------
            # VERIFICAR RESPONSABILIDADE ATUAL
            # ----------------------------------------------

            if atual:

                try:

                    fim_atual = datetime.fromisoformat(
                        atual["fim"]
                    )

                except (TypeError, ValueError):

                    conexao.execute(
                        """
                        DELETE FROM responsabilidades_cocho
                        WHERE cocho_codigo = ?
                        """,
                        (codigo,),
                    )

                    atual = None

                else:

                    if agora >= fim_atual:

                        conexao.execute(
                            """
                            DELETE FROM responsabilidades_cocho
                            WHERE cocho_codigo = ?
                            """,
                            (codigo,),
                        )

                        atual = None

            # ----------------------------------------------
            # GET
            # ----------------------------------------------

            if request.method == "GET" and atual:

                email_atual = (
                    session.get("email") or ""
                ).strip().lower()

                email_dono = (
                    atual["usuario_email"] or ""
                ).strip().lower()

                if (
                    email_atual
                    and email_atual == email_dono
                ):

                    conexao.commit()

                    return redirect(
                        url_for("minha_fermentacao")
                    )

                fim_formatado = datetime.fromisoformat(
                    atual["fim"]
                ).strftime(
                    "%d/%m/%Y às %H:%M"
                )

                conexao.commit()

                return render_template(
                    "confirmar_responsabilidade.html",
                    codigo=codigo,
                    nome=session.get("nome"),
                    email=session.get("email"),
                    cocho_ocupado=True,
                    responsavel_nome=atual["usuario_nome"],
                    responsavel_fim=fim_formatado,
                    mensagem_cocho=(
                        "Este cocho já possui um responsável. "
                        "Tente novamente no dia "
                        f"{fim_formatado}, quando a responsabilidade "
                        "atual termina."
                    ),
                )

            # ----------------------------------------------
            # POST
            # ----------------------------------------------

            if request.method == "POST":

                tipo = request.form.get(
                    "tipo_responsabilidade", ""
                ).strip()

                dias_form = request.form.get(
                    "dias"
                )

                if tipo not in [
                    "periodo",
                    "fermentacao"
                ]:

                    conexao.commit()

                    flash(
                        "Selecione como deseja se responsabilizar pelo cocho.",
                        "erro",
                    )

                    return redirect(
                        url_for("cocho", codigo=codigo)
                    )

                if tipo == "periodo":

                    try:

                        dias = int(
                            dias_form
                        )

                    except (TypeError, ValueError):

                        conexao.commit()

                        flash(
                            "Selecione uma quantidade de dias válida.",
                            "erro",
                        )

                        return redirect(
                            url_for("cocho", codigo=codigo)
                        )

                    if not 1 <= dias <= 7:

                        conexao.commit()

                        flash(
                            "A responsabilidade deve ser de 1 a 7 dias.",
                            "erro",
                        )

                        return redirect(
                            url_for("cocho", codigo=codigo)
                        )

                else:

                    dias = 7

                # ------------------------------------------
                # VERIFICAR NOVAMENTE
                # ------------------------------------------

                atual = conexao.execute(
                    """
                    SELECT *
                    FROM responsabilidades_cocho
                    WHERE cocho_codigo = ?
                    """,
                    (codigo,),
                ).fetchone()

                if atual:

                    try:

                        fim_atual = datetime.fromisoformat(
                            atual["fim"]
                        )

                    except (TypeError, ValueError):

                        fim_atual = agora

                    if agora < fim_atual:

                        fim_formatado = fim_atual.strftime(
                            "%d/%m/%Y às %H:%M"
                        )

                        conexao.commit()

                        return render_template(
                            "confirmar_responsabilidade.html",
                            codigo=codigo,
                            nome=session.get("nome"),
                            email=session.get("email"),
                            cocho_ocupado=True,
                            responsavel_nome=atual["usuario_nome"],
                            responsavel_fim=fim_formatado,
                            mensagem_cocho=(
                                "Este cocho já possui um responsável. "
                                "Tente novamente no dia "
                                f"{fim_formatado}, quando a responsabilidade "
                                "atual termina."
                            ),
                        )

                    conexao.execute(
                        """
                        DELETE FROM responsabilidades_cocho
                        WHERE cocho_codigo = ?
                        """,
                        (codigo,),
                    )

                # ------------------------------------------
                # CRIAR NOVA RESPONSABILIDADE
                # ------------------------------------------

                inicio = datetime.now()

                fim = inicio + timedelta(
                    days=dias
                )

                conexao.execute(
                    """
                    INSERT INTO responsabilidades_cocho (
                        cocho_codigo,
                        usuario_id,
                        usuario_nome,
                        usuario_email,
                        inicio,
                        fim,
                        dias,
                        tipo
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        codigo,
                        session.get("usuario_id"),
                        session.get("nome") or "Usuário FERMENTECH",
                        (
                            session.get("email") or ""
                        ).strip().lower(),
                        inicio.isoformat(
                            timespec="seconds"
                        ),
                        fim.isoformat(
                            timespec="seconds"
                        ),
                        dias,
                        tipo,
                    ),
                )

                conexao.commit()

                session["responsabilidade_cocho"] = {
                    "cocho": codigo,
                    "usuario_nome": session.get("nome"),
                    "usuario_email": session.get("email"),
                    "inicio": inicio.strftime(
                        "%d/%m/%Y %H:%M"
                    ),
                    "fim": fim.strftime(
                        "%d/%m/%Y %H:%M"
                    ),
                    "dias": dias,
                    "tipo": tipo,
                }

                return redirect(
                    url_for("minha_fermentacao")
                )

            conexao.commit()

    except sqlite3.Error:

        app.logger.exception(
            "Erro ao consultar ou salvar responsabilidade do cocho."
        )

        flash(
            "Não foi possível verificar a disponibilidade do cocho.",
            "erro",
        )

        return redirect(
            url_for("scanear_qr")
        )

    return render_template(
        "confirmar_responsabilidade.html",
        codigo=codigo,
        nome=session.get("nome"),
        email=session.get("email"),
        cocho_ocupado=False,
    )


# ============================================================
# MINHA FERMENTAÇÃO
# ============================================================

@app.route("/minha-fermentacao")
def minha_fermentacao():

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    email_sessao = (
        session.get("email") or ""
    ).strip().lower()

    if not email_sessao:

        session.pop(
            "responsabilidade_cocho",
            None,
        )

        flash(
            "Sua sessão está incompleta. Entre novamente.",
            "erro",
        )

        return redirect(
            url_for("login")
        )

    try:

        with conectar_banco() as conexao:

            responsabilidade = conexao.execute(
                """
                SELECT *
                FROM responsabilidades_cocho
                WHERE cocho_codigo = ?
                """,
                ("FT-001",),
            ).fetchone()

            if responsabilidade is None:

                session.pop(
                    "responsabilidade_cocho",
                    None,
                )

                flash(
                    "Você ainda não assumiu a responsabilidade por um cocho.",
                    "erro",
                )

                return redirect(
                    url_for("scanear_qr")
                )

            email_dono = (
                responsabilidade["usuario_email"] or ""
            ).strip().lower()

            if email_sessao != email_dono:

                session.pop(
                    "responsabilidade_cocho",
                    None,
                )

                fim = datetime.fromisoformat(
                    responsabilidade["fim"]
                )

                flash(
                    "Este cocho está sob responsabilidade de outra pessoa até "
                    f"{fim.strftime('%d/%m/%Y às %H:%M')}.",
                    "erro",
                )

                return redirect(
                    url_for("scanear_qr")
                )

            # ----------------------------------------------
            # VALIDAR DATAS
            # ----------------------------------------------

            try:

                inicio = datetime.fromisoformat(
                    responsabilidade["inicio"]
                )

                fim = datetime.fromisoformat(
                    responsabilidade["fim"]
                )

            except (TypeError, ValueError):

                conexao.execute(
                    """
                    DELETE FROM responsabilidades_cocho
                    WHERE cocho_codigo = ?
                    """,
                    ("FT-001",),
                )

                session.pop(
                    "responsabilidade_cocho",
                    None,
                )

                flash(
                    "Não foi possível validar o prazo da responsabilidade.",
                    "erro",
                )

                return redirect(
                    url_for("scanear_qr")
                )

            # ----------------------------------------------
            # PRAZO ENCERRADO
            # ----------------------------------------------

            if datetime.now() >= fim:

                conexao.execute(
                    """
                    DELETE FROM responsabilidades_cocho
                    WHERE cocho_codigo = ?
                    """,
                    ("FT-001",),
                )

                session.pop(
                    "responsabilidade_cocho",
                    None,
                )

                flash(
                    "Seu período de responsabilidade terminou. "
                    "Leia o QR Code para assumir o cocho novamente.",
                    "sucesso",
                )

                return redirect(
                    url_for("scanear_qr")
                )

            # ----------------------------------------------
            # FORMATAR DADOS
            # ----------------------------------------------

            dados = dict(
                responsabilidade
            )

            dados["inicio"] = inicio.strftime(
                "%d/%m/%Y %H:%M"
            )

            dados["fim"] = fim.strftime(
                "%d/%m/%Y %H:%M"
            )

            session["responsabilidade_cocho"] = {
                "cocho": dados["cocho_codigo"],
                "usuario_nome": dados["usuario_nome"],
                "usuario_email": dados["usuario_email"],
                "inicio": dados["inicio"],
                "fim": dados["fim"],
                "dias": dados["dias"],
                "tipo": dados["tipo"],
            }

    except sqlite3.Error:

        app.logger.exception(
            "Erro ao consultar responsabilidade do cocho."
        )

        flash(
            "Não foi possível consultar sua responsabilidade agora.",
            "erro",
        )

        return redirect(
            url_for("scanear_qr")
        )

    return render_template(
        "minha_fermentacao.html",
        responsabilidade=dados,
    )


# ============================================================
# HISTÓRICO - PÁGINA
# ============================================================

@app.route("/historico")
def historico():

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    return render_template(
        "historico.html",
        nome=session.get("nome"),
        email=session.get("email"),
    )


# ============================================================
# HISTÓRICO - API
# ============================================================

@app.route("/api/cocho/<codigo>/history")
def api_historico_fermentacao(codigo):

    if not session.get("autenticado"):

        return jsonify({
            "erro": "Autenticação necessária."
        }), 401

    if codigo != "FT-001":

        return jsonify({
            "erro": "Cocho não encontrado."
        }), 404

    try:

        limite = int(
            request.args.get("limit", 1000)
        )

    except (TypeError, ValueError):

        return jsonify({
            "erro": "O limite informado é inválido."
        }), 400

    limite = max(
        1,
        min(limite, 5000)
    )

    try:

        with conectar_banco() as conexao:

            linhas = conexao.execute(
                """
                SELECT
                    id,
                    cocho_codigo,
                    temperatura,
                    status,
                    data_hora
                FROM historico_fermentacao
                WHERE cocho_codigo = ?
                ORDER BY data_hora DESC, id DESC
                LIMIT ?
                """,
                (
                    codigo,
                    limite,
                ),
            ).fetchall()

        return jsonify({
            "history": [
                dict(linha)
                for linha in linhas
            ]
        })

    except sqlite3.Error:

        app.logger.exception(
            "Erro ao consultar histórico."
        )

        return jsonify({
            "erro": "Não foi possível consultar o histórico."
        }), 500


# ============================================================
# REGISTRAR LEITURA DE TEMPERATURA
# ============================================================

def registrar_leitura_fermentacao(
    temperatura,
    status,
    cocho_codigo="FT-001",
):

    """
    Registra uma leitura recebida do sistema de sensores.

    Esta função não simula temperaturas.
    Ela somente salva os valores recebidos.
    """

    if cocho_codigo != "FT-001":

        raise ValueError(
            "Cocho não encontrado."
        )

    try:

        temperatura = float(
            temperatura
        )

    except (TypeError, ValueError):

        raise ValueError(
            "Temperatura inválida."
        )

    if not -50 <= temperatura <= 150:

        raise ValueError(
            "Temperatura fora do intervalo permitido."
        )

    if (
        not isinstance(status, str)
        or not status.strip()
    ):

        raise ValueError(
            "Informe o status da leitura."
        )

    data_hora = datetime.now().isoformat(
        timespec="seconds"
    )

    with conectar_banco() as conexao:

        cursor = conexao.execute(
            """
            INSERT INTO historico_fermentacao (
                cocho_codigo,
                temperatura,
                status,
                data_hora
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                cocho_codigo,
                temperatura,
                status.strip(),
                data_hora,
            ),
        )

        return cursor.lastrowid


# ============================================================
# FUNCIONÁRIOS
# ============================================================

@app.route("/funcionarios")
def funcionarios():

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    if session.get("tipo") != "admin":

        return redirect(
            url_for("login")
        )

    return render_template(
        "funcionarios.html",
        funcionarios=listar_funcionarios(),
        nome=session.get("nome"),
        email=session.get("email"),
    )



# ============================================================
# CADASTRAR FUNCIONÁRIO
# ============================================================

@app.route(
    "/funcionarios/cadastrar",
    methods=["POST"],
)
def cadastrar_funcionario():

    if not session.get("autenticado"):
        return redirect(url_for("login"))

    if session.get("tipo") != "admin":
        return redirect(url_for("login"))

    nome = request.form.get("nome", "").strip()

    email = request.form.get("email", "").strip().lower()

    if not nome or not email:
        flash(
            "Preencha o nome e o e-mail.",
            "erro",
        )
        return redirect(url_for("funcionarios"))

    if len(nome) > 120 or len(email) > 254:
        flash(
            "O nome ou o e-mail ultrapassa o limite permitido.",
            "erro",
        )
        return redirect(url_for("funcionarios"))

    if not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+",
        email,
    ):
        flash(
            "Digite um endereço de e-mail válido.",
            "erro",
        )
        return redirect(url_for("funcionarios"))

    if buscar_usuario_por_email(email):
        flash(
            "Este e-mail já está cadastrado.",
            "erro",
        )
        return redirect(url_for("funcionarios"))

    senha_temporaria = gerar_senha_aleatoria()

    # --------------------------------------------------------
    # SALVAR FUNCIONÁRIO PRIMEIRO
    # --------------------------------------------------------

    try:

        criar_funcionario(
            nome,
            email,
            senha_temporaria,
        )

    except sqlite3.IntegrityError:

        flash(
            "Este e-mail já está cadastrado.",
            "erro",
        )

        return redirect(url_for("funcionarios"))

    except sqlite3.Error:

        app.logger.exception(
            "Erro ao salvar funcionário no banco."
        )

        flash(
            "Não foi possível cadastrar o funcionário. "
            "Confira o banco de dados.",
            "erro",
        )

        return redirect(url_for("funcionarios"))

    # --------------------------------------------------------
    # TENTAR ENVIAR A SENHA POR E-MAIL
    # --------------------------------------------------------

    try:

        email_enviado = enviar_senha_por_email(
            email=email,
            nome=nome,
            senha=senha_temporaria,
        )

    except Exception:

        app.logger.exception(
            "Erro inesperado ao enviar senha por e-mail."
        )

        email_enviado = False

    # --------------------------------------------------------
    # RESULTADO DO CADASTRO
    # --------------------------------------------------------

    if email_enviado:

        flash(
            f"Funcionário {nome} cadastrado com sucesso! "
            f"A senha temporária foi enviada para {email}.",
            "sucesso",
        )

    else:

        app.logger.warning(
            "Funcionário cadastrado, mas o e-mail não foi enviado: %s",
            email,
        )

        flash(
            f"Funcionário {nome} foi cadastrado, mas não foi "
            "possível enviar a senha por e-mail. "
            "O cadastro está salvo. Será necessário configurar "
            "o envio de e-mail e disponibilizar uma nova senha "
            "temporária para o funcionário.",
            "erro",
        )

    return redirect(
        url_for("funcionarios")
    )



# ============================================================
# EDITAR FUNCIONÁRIO
# ============================================================

@app.route(
    "/funcionarios/editar/<int:usuario_id>",
    methods=["POST"],
)
def editar_funcionario(usuario_id):

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    if session.get("tipo") != "admin":

        return redirect(
            url_for("login")
        )

    nome = request.form.get(
        "nome", ""
    ).strip()

    email = request.form.get(
        "email", ""
    ).strip().lower()

    if not nome or not email:

        flash(
            "Preencha o nome e o e-mail.",
            "erro",
        )

        return redirect(
            url_for("funcionarios")
        )

    if len(nome) > 120 or len(email) > 254:

        flash(
            "O nome ou o e-mail ultrapassa o limite permitido.",
            "erro",
        )

        return redirect(
            url_for("funcionarios")
        )

    if not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+",
        email,
    ):

        flash(
            "Digite um endereço de e-mail válido.",
            "erro",
        )

        return redirect(
            url_for("funcionarios")
        )

    try:

        with conectar_banco() as conexao:

            funcionario = conexao.execute(
                """
                SELECT id
                FROM usuarios
                WHERE id = ?
                  AND tipo = 'funcionario'
                """,
                (usuario_id,),
            ).fetchone()

            if not funcionario:

                flash(
                    "Funcionário não encontrado.",
                    "erro",
                )

                return redirect(
                    url_for("funcionarios")
                )

            email_existente = conexao.execute(
                """
                SELECT id
                FROM usuarios
                WHERE email = ? COLLATE NOCASE
                  AND id != ?
                """,
                (
                    email,
                    usuario_id,
                ),
            ).fetchone()

            if email_existente:

                flash(
                    "Este e-mail já está sendo utilizado.",
                    "erro",
                )

                return redirect(
                    url_for("funcionarios")
                )

            conexao.execute(
                """
                UPDATE usuarios
                SET nome = ?, email = ?
                WHERE id = ?
                  AND tipo = 'funcionario'
                """,
                (
                    nome,
                    email,
                    usuario_id,
                ),
            )

    except sqlite3.Error:

        app.logger.exception(
            "Erro ao editar funcionário."
        )

        flash(
            "Não foi possível atualizar o funcionário.",
            "erro",
        )

        return redirect(
            url_for("funcionarios")
        )

    flash(
        "Dados do funcionário atualizados com sucesso!",
        "sucesso",
    )

    return redirect(
        url_for("funcionarios")
    )


# ============================================================
# BLOQUEAR / REATIVAR FUNCIONÁRIO
# ============================================================

@app.route(
    "/funcionarios/bloquear/<int:usuario_id>",
    methods=["POST"],
)
def bloquear_funcionario(usuario_id):

    if not session.get("autenticado"):

        return redirect(
            url_for("login")
        )

    if session.get("tipo") != "admin":

        return redirect(
            url_for("login")
        )

    try:

        with conectar_banco() as conexao:

            funcionario = conexao.execute(
                """
                SELECT id, status
                FROM usuarios
                WHERE id = ?
                  AND tipo = 'funcionario'
                """,
                (usuario_id,),
            ).fetchone()

            if not funcionario:

                flash(
                    "Funcionário não encontrado.",
                    "erro",
                )

                return redirect(
                    url_for("funcionarios")
                )

            if funcionario["status"] == "Ativo":

                novo_status = "Bloqueado"

            else:

                novo_status = "Ativo"

            conexao.execute(
                """
                UPDATE usuarios
                SET status = ?
                WHERE id = ?
                  AND tipo = 'funcionario'
                """,
                (
                    novo_status,
                    usuario_id,
                ),
            )

    except sqlite3.Error:

        app.logger.exception(
            "Erro ao alterar status do funcionário."
        )

        flash(
            "Não foi possível alterar o status do funcionário.",
            "erro",
        )

        return redirect(
            url_for("funcionarios")
        )

    if novo_status == "Bloqueado":

        flash(
            "Funcionário bloqueado com sucesso.",
            "sucesso",
        )

    else:

        flash(
            "Funcionário reativado com sucesso.",
            "sucesso",
        )

    return redirect(
        url_for("funcionarios")
    )


# ============================================================
# TESTE DE ENVIO DE E-MAIL
# ============================================================

@app.route("/teste/senha")
def teste_senha():

    if (
        not session.get("autenticado")
        or session.get("tipo") != "admin"
    ):

        return redirect(
            url_for("login")
        )

    senha = gerar_senha_aleatoria()

    email_teste = (
        "aliciapereiradasilva3@gmail.com"
    )

    email_enviado = enviar_senha_por_email(
        email=email_teste,
        nome="Usuário Teste",
        senha=senha,
    )

    if email_enviado:

        return """
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <title>Teste FERMENTECH</title>
        </head>
        <body>
            <h1>Teste realizado com sucesso!</h1>
            <p>O serviço de e-mail informou que a mensagem foi enviada.</p>
            <p>Verifique a caixa de entrada e a pasta de spam.</p>
            <a href="/">Voltar</a>
        </body>
        </html>
        """

    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Teste FERMENTECH</title>
    </head>
    <body>
        <h1>Erro no envio.</h1>
        <p>O e-mail não pôde ser enviado.</p>
        <p>Consulte o terminal do VS Code para ver o erro.</p>
        <a href="/">Voltar</a>
    </body>
    </html>
    """, 500


# ============================================================
# GEMINI
# ============================================================

def obter_cliente_gemini():

    chave = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if not chave:

        return None, "chave"

    try:

        from google import genai

        return genai.Client(
            api_key=chave
        ), None

    except ImportError:

        app.logger.exception(
            "O pacote google-genai não está instalado."
        )

        return None, "pacote"


def modelo_gemini():

    return os.getenv(
        "GEMINI_MODEL",
        "gemini-2.5-flash",
    ).strip()


# ============================================================
# IA - RECOMENDAÇÃO
# ============================================================

@app.route(
    "/api/ia/recomendacao",
    methods=["POST"],
)
def api_ia_recomendacao():

    if not session.get("autenticado"):

        return jsonify({
            "erro": "Faça login para utilizar a inteligência artificial."
        }), 401

    cliente, problema_configuracao = obter_cliente_gemini()

    if cliente is None:

        if problema_configuracao == "chave":

            mensagem = (
                "Configure GEMINI_API_KEY no arquivo .env "
                "para ativar a IA."
            )

        else:

            mensagem = (
                "A biblioteca google-genai não está instalada. "
                "Execute python -m pip install google-genai."
            )

        return jsonify({
            "erro": mensagem
        }), 503

    try:

        with conectar_banco() as conexao:

            linhas = conexao.execute(
                """
                SELECT temperatura, status, data_hora
                FROM historico_fermentacao
                WHERE cocho_codigo = ?
                ORDER BY data_hora DESC, id DESC
                LIMIT 30
                """,
                ("FT-001",),
            ).fetchall()

        leituras = [
            dict(linha)
            for linha in linhas
            if "SIMULADO" not in str(
                linha["status"]
            ).upper()
        ][:20]

        if leituras:

            resumo = (
                "Leituras reais registradas no banco "
                "(mais recentes primeiro):\n"
            )

            resumo += "\n".join(
                (
                    f"- Data/hora: {item['data_hora']}; "
                    f"temperatura: {item['temperatura']} °C; "
                    f"status registrado: {item['status']}"
                )
                for item in leituras
            )

        else:

            resumo = (
                "Não há leituras reais disponíveis no banco. "
                "Não invente temperaturas, tendências ou alertas. "
                "Forneça somente orientações gerais e diga claramente "
                "que a análise baseada em dados reais depende da "
                "conexão e do recebimento das leituras dos sensores."
            )

        prompt = f"""
Você é o assistente de apoio do FERMENTECH,
sistema de acompanhamento da fermentação de cacau.

Responda em português brasileiro,
de maneira clara e prática.

Use somente os dados fornecidos.
Nunca invente medições.

Não declare que a fermentação está boa ou ruim
de forma definitiva apenas com base em dados limitados.

As condições adequadas podem variar conforme
o método, o ambiente e o processo utilizado.

Não substitua a avaliação da equipe responsável.

DADOS DISPONÍVEIS:

{resumo}

Organize a resposta em:

1. Situação dos dados
2. Observações
3. Próximos passos sugeridos
"""

        resposta = cliente.models.generate_content(
            model=modelo_gemini(),
            contents=prompt,
        )

        texto = getattr(
            resposta,
            "text",
            None,
        )

        if not texto:

            return jsonify({
                "erro": "A IA não retornou uma resposta. Tente novamente."
            }), 502

        return jsonify({
            "resposta": texto,
            "leituras_reais_analisadas": len(leituras),
            "aviso": (
                "As recomendações são informativas. "
                "Confirme as decisões com a equipe responsável."
            ),
        })

    except Exception:

        app.logger.exception(
            "Erro ao gerar recomendação com a IA."
        )

        return jsonify({
            "erro": (
                "Não foi possível consultar a IA. "
                "Confira a configuração e o terminal do Flask."
            )
        }), 502


# ============================================================
# IA - ANALISAR FOTO
# ============================================================

@app.route(
    "/api/ia/analisar-foto",
    methods=["POST"],
)
def api_ia_analisar_foto():

    if not session.get("autenticado"):

        return jsonify({
            "erro": "Faça login para utilizar a inteligência artificial."
        }), 401

    arquivo = request.files.get(
        "foto"
    )

    if not arquivo or not arquivo.filename:

        return jsonify({
            "erro": "Selecione uma fotografia antes de solicitar a análise."
        }), 400

    mime = (
        arquivo.mimetype or ""
    ).lower()

    tipos_permitidos = {
        "image/jpeg",
        "image/png",
        "image/webp",
    }

    if mime not in tipos_permitidos:

        return jsonify({
            "erro": (
                "Formato não permitido. "
                "Envie uma imagem JPG, PNG ou WEBP."
            )
        }), 400

    imagem = arquivo.read()

    if not imagem:

        return jsonify({
            "erro": "O arquivo enviado está vazio."
        }), 400

    if len(imagem) > 5 * 1024 * 1024:

        return jsonify({
            "erro": "A imagem deve ter no máximo 5 MB."
        }), 413

    cliente, problema_configuracao = obter_cliente_gemini()

    if cliente is None:

        if problema_configuracao == "chave":

            mensagem = (
                "Configure GEMINI_API_KEY no arquivo .env "
                "para ativar a IA."
            )

        else:

            mensagem = (
                "A biblioteca google-genai não está instalada. "
                "Execute python -m pip install google-genai."
            )

        return jsonify({
            "erro": mensagem
        }), 503

    try:

        from google.genai import types

        prompt = """
Você auxilia na inspeção visual de amêndoas de cacau
no sistema FERMENTECH.

Descreva somente características visíveis
na fotografia, como:

- Cor aparente
- Uniformidade
- Possíveis alterações visíveis

Não confirme fermentação, segurança alimentar,
sabor ou qualidade final apenas pela imagem.

Iluminação, câmera e forma de corte podem
alterar a aparência.

Se não for possível identificar claramente
as amêndoas, informe essa limitação.

Responda em português brasileiro com as seções:

1. O que é possível observar
2. Limitações da imagem
3. Próximos passos sugeridos

Não invente características que não estejam visíveis.
"""

        parte_imagem = types.Part.from_bytes(
            data=imagem,
            mime_type=mime,
        )

        resposta = cliente.models.generate_content(
            model=modelo_gemini(),
            contents=[
                prompt,
                parte_imagem,
            ],
        )

        texto = getattr(
            resposta,
            "text",
            None,
        )

        if not texto:

            return jsonify({
                "erro": "A IA não retornou uma análise. Tente novamente."
            }), 502

        return jsonify({
            "resposta": texto,
            "aviso": (
                "A análise visual é preliminar e não confirma, "
                "sozinha, a qualidade ou a segurança do cacau."
            ),
        })

    except Exception:

        app.logger.exception(
            "Erro durante a análise da fotografia."
        )

        return jsonify({
            "erro": (
                "Não foi possível analisar a fotografia. "
                "Confira a configuração da IA e o terminal do Flask."
            )
        }), 502


# ============================================================
# ERRO DE ARQUIVO GRANDE
# ============================================================

@app.errorhandler(413)
def arquivo_muito_grande(_erro):

    return jsonify({
        "erro": (
            "O arquivo é muito grande. "
            "Envie uma imagem de até 5 MB."
        )
    }), 413


# ============================================================
# TESTE DO SERVIDOR
# ============================================================

@app.route("/api/health")
def health():

    return jsonify({
        "application": "FERMENTECH",
        "status": "online",
        "sensor": "não conectado",
    })


# ============================================================
# EXECUÇÃO DO SERVIDOR
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.getenv(
            "FLASK_DEBUG",
            "true"
        ).lower() == "true",
    )

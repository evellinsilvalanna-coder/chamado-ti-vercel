from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone
import pytz

db = SQLAlchemy()

def get_sao_paulo_time():
    tz = pytz.timezone('America/Sao_Paulo')
    return datetime.now(tz)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    profile = db.Column(db.String(20), nullable=False, default='solicitante')  # solicitante, tecnico, admin
    is_active = db.Column(db.Boolean, default=True)
    avatar = db.Column(db.String(200))
    reset_token = db.Column(db.String(100))
    reset_token_expiry = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)
    last_login = db.Column(db.DateTime)

    department = db.relationship('Department', backref='users')
    chamados = db.relationship('Chamado', foreign_keys='Chamado.user_id', backref='solicitante', lazy='dynamic')
    assigned = db.relationship('Chamado', foreign_keys='Chamado.tecnico_id', backref='tecnico', lazy='dynamic')

    def get_role_display(self):
        return {'solicitante': 'Solicitante', 'tecnico': 'Técnico', 'admin': 'Administrador'}.get(self.profile, self.profile)

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(300))
    icon = db.Column(db.String(50), default='bi bi-folder')
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

class SLA(db.Model):
    __tablename__ = 'slas'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    priority = db.Column(db.String(20), nullable=False)  # baixa, media, alta, critica
    first_response_hours = db.Column(db.Integer, nullable=False, default=24)
    resolution_hours = db.Column(db.Integer, nullable=False, default=72)
    warning_hours = db.Column(db.Integer, default=2)
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

    category = db.relationship('Category', backref='slas')

class Chamado(db.Model):
    __tablename__ = 'chamados'
    id = db.Column(db.Integer, primary_key=True)
    protocolo = db.Column(db.String(20), unique=True, nullable=False)
    titulo = db.Column(db.String(200), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    prioridade = db.Column(db.String(20), nullable=False, default='media')
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    localizacao = db.Column(db.String(200))
    equipamento = db.Column(db.String(100))
    patrimonio = db.Column(db.String(50))
    telefone = db.Column(db.String(20))
    descricao = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='novo')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    tecnico_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    sla_id = db.Column(db.Integer, db.ForeignKey('slas.id'), nullable=True)
    first_response_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    sla_first_response_deadline = db.Column(db.DateTime)
    sla_resolution_deadline = db.Column(db.DateTime)
    sla_breached = db.Column(db.Boolean, default=False)
    tempo_gasto_minutos = db.Column(db.Integer, default=0)
    avaliacao_nota = db.Column(db.Integer)
    avaliacao_comentario = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)
    updated_at = db.Column(db.DateTime, default=get_sao_paulo_time, onupdate=get_sao_paulo_time)

    category = db.relationship('Category', backref='chamados')
    department = db.relationship('Department', backref='chamados')
    messages = db.relationship('Message', backref='chamado', lazy='dynamic', order_by='Message.created_at')
    history = db.relationship('History', backref='chamado', lazy='dynamic', order_by='History.created_at')
    attachments = db.relationship('Attachment', backref='chamado', lazy='dynamic')

    STATUS_COLORS = {
        'novo': '#3498db',
        'em_analise': '#f39c12',
        'em_atendimento': '#2ecc71',
        'aguardando_usuario': '#e67e22',
        'aguardando_fornecedor': '#9b59b6',
        'aguardando_peca': '#e74c3c',
        'pendente': '#6f42c1',
        'resolvido': '#1abc9c',
        'finalizado': '#7f8c8d',
        'cancelado': '#95a5a6'
    }

    STATUS_DISPLAY = {
        'novo': 'Novo',
        'em_analise': 'Em análise',
        'em_atendimento': 'Em atendimento',
        'aguardando_usuario': 'Aguardando usuário',
        'aguardando_fornecedor': 'Aguardando fornecedor',
        'aguardando_peca': 'Aguardando peça',
        'pendente': 'Pendente',
        'resolvido': 'Resolvido',
        'finalizado': 'Finalizado',
        'cancelado': 'Cancelado'
    }

    def get_status_color(self):
        return self.STATUS_COLORS.get(self.status, '#3498db')

    def get_status_display(self):
        return self.STATUS_DISPLAY.get(self.status, self.status)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    message = db.Column(db.Text, nullable=False)
    is_internal = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

    user = db.relationship('User', backref='messages')
    attachments = db.relationship('Attachment', backref='message_obj', lazy='dynamic')

class Attachment(db.Model):
    __tablename__ = 'attachments'
    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'))
    message_id = db.Column(db.Integer, db.ForeignKey('messages.id'), nullable=True)
    filename = db.Column(db.String(300), nullable=False)
    original_name = db.Column(db.String(300), nullable=False)
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(50))
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

    uploader = db.relationship('User', backref='uploads')

class History(db.Model):
    __tablename__ = 'history'
    id = db.Column(db.Integer, primary_key=True)
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(200), nullable=False)
    status_anterior = db.Column(db.String(30))
    novo_status = db.Column(db.String(30))
    detalhes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

    user = db.relationship('User', backref='history_entries')

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    chamado_id = db.Column(db.Integer, db.ForeignKey('chamados.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(30), default='info')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

    user = db.relationship('User', backref='notifications')

class QuickSolution(db.Model):
    __tablename__ = 'quick_solutions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50), default='bi bi-tools')
    script_file = db.Column(db.String(300))
    script_type = db.Column(db.String(10))  # bat, cmd, ps1, exe
    version = db.Column(db.String(20), default='1.0')
    is_active = db.Column(db.Boolean, default=True)
    needs_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)
    updated_at = db.Column(db.DateTime, default=get_sao_paulo_time, onupdate=get_sao_paulo_time)

    departments = db.relationship('SolutionDepartment', backref='solution', lazy='dynamic')
    allowed_users = db.relationship('SolutionUser', backref='solution', lazy='dynamic')

class SolutionDepartment(db.Model):
    __tablename__ = 'solution_departments'
    id = db.Column(db.Integer, primary_key=True)
    solution_id = db.Column(db.Integer, db.ForeignKey('quick_solutions.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))

class SolutionUser(db.Model):
    __tablename__ = 'solution_users'
    id = db.Column(db.Integer, primary_key=True)
    solution_id = db.Column(db.Integer, db.ForeignKey('quick_solutions.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

class SolutionExecution(db.Model):
    __tablename__ = 'solution_executions'
    id = db.Column(db.Integer, primary_key=True)
    solution_id = db.Column(db.Integer, db.ForeignKey('quick_solutions.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    computer_name = db.Column(db.String(100))
    ip_address = db.Column(db.String(45))
    result = db.Column(db.String(20))  # success, error
    error_message = db.Column(db.Text)
    executed_at = db.Column(db.DateTime, default=get_sao_paulo_time)

    solution = db.relationship('QuickSolution', backref='executions')
    user = db.relationship('User', backref='solution_executions')

class KnowledgeBase(db.Model):
    __tablename__ = 'knowledge_base'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))
    tags = db.Column(db.String(500))
    file_path = db.Column(db.String(300))
    file_type = db.Column(db.String(20))
    is_published = db.Column(db.Boolean, default=True)
    visibility = db.Column(db.String(20), default='all')  # all, tecnico, solicitante
    views = db.Column(db.Integer, default=0)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)
    updated_at = db.Column(db.DateTime, default=get_sao_paulo_time, onupdate=get_sao_paulo_time)

    author = db.relationship('User', backref='kb_articles')
    attachments = db.relationship('KnowledgeAttachment', backref='article', lazy='dynamic', cascade='all, delete-orphan')


class KnowledgeAttachment(db.Model):
    __tablename__ = 'knowledge_attachments'
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('knowledge_base.id'))
    filename = db.Column(db.String(300), nullable=False)
    original_name = db.Column(db.String(300))
    file_type = db.Column(db.String(50))  # image, pdf, document
    is_image = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

class SystemLog(db.Model):
    __tablename__ = 'system_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=get_sao_paulo_time)

    user = db.relationship('User', backref='logs')
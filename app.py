import os
import uuid
import hashlib
import pytz
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_from_directory, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import bcrypt

from config import Config
from models import db, User, Department, Category, SLA, Chamado, Message, Attachment, History, Notification, QuickSolution, SolutionDepartment, SolutionUser, SolutionExecution, KnowledgeBase, SystemLog

app = Flask(__name__)
app.config.from_object(Config)

# Necessário para o Vercel
app_handler = app

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')

def now_sp():
    return datetime.now(SAO_PAULO_TZ)

# ─── Helpers ────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def generate_protocolo():
    year = now_sp().year
    last = Chamado.query.filter(Chamado.protocolo.like(f'TI-{year}-%')).order_by(Chamado.id.desc()).first()
    if last:
        num = int(last.protocolo.split('-')[-1]) + 1
    else:
        num = 1
    return f'TI-{year}-{num:06d}'

def has_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.profile not in roles:
                flash('Acesso não autorizado.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_system(user_id, action, details=None):
    log = SystemLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=request.remote_addr,
        created_at=now_sp()
    )
    db.session.add(log)
    db.session.commit()

def create_notification(user_id, title, message, chamado_id=None, type='info'):
    notif = Notification(
        user_id=user_id,
        chamado_id=chamado_id,
        title=title,
        message=message,
        type=type,
        created_at=now_sp()
    )
    db.session.add(notif)
    db.session.commit()

def add_history(chamado_id, user_id, action, status_anterior=None, novo_status=None, detalhes=None):
    h = History(
        chamado_id=chamado_id,
        user_id=user_id,
        action=action,
        status_anterior=status_anterior,
        novo_status=novo_status,
        detalhes=detalhes,
        created_at=now_sp()
    )
    db.session.add(h)
    db.session.commit()

def calculate_sla(chamado):
    """Calcula e retorna informações de SLA para um chamado."""
    sla = SLA.query.filter_by(category_id=chamado.categoria_id, priority=chamado.prioridade).first()
    if not sla:
        # SLA padrão
        sla_defaults = {
            'baixa': (48, 168, 12),
            'media': (24, 72, 6),
            'alta': (8, 24, 2),
            'critica': (1, 4, 1)
        }
        first_resp, resolution, warning = sla_defaults.get(chamado.prioridade, (24, 72, 6))
    else:
        first_resp = sla.first_response_hours
        resolution = sla.resolution_hours
        warning = sla.warning_hours

    chamado.sla_first_response_deadline = now_sp() + timedelta(hours=first_resp)
    chamado.sla_resolution_deadline = now_sp() + timedelta(hours=resolution)
    db.session.commit()

def get_sla_status(chamado):
    """Retorna status do SLA: ok, warning, breached"""
    now = now_sp()
    if chamado.status in ['finalizado', 'cancelado']:
        return 'ok'
    
    if chamado.sla_resolution_deadline and now > chamado.sla_resolution_deadline:
        return 'breached'
    if chamado.sla_resolution_deadline:
        diff = chamado.sla_resolution_deadline - now
        total_hours = (chamado.sla_resolution_deadline - (chamado.created_at or now)).total_seconds() / 3600
        remaining_hours = diff.total_seconds() / 3600
        if remaining_hours < total_hours * 0.1:  # menos de 10% do tempo
            return 'warning'
    return 'ok'

# ─── Login Manager ──────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── Auth Routes ────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        profile = request.form.get('profile', 'solicitante')
        
        user = User.query.filter_by(email=email, profile=profile).first()
        
        if user and user.is_active and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            user.last_login = now_sp()
            db.session.commit()
            log_system(user.id, 'login', f'Usuário {user.email} fez login como {user.get_role_display()}')
            return redirect(url_for('dashboard'))
        
        flash('E-mail, senha ou perfil inválidos.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    log_system(current_user.id, 'logout', f'Usuário {current_user.email} fez logout')
    logout_user()
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        phone = request.form.get('phone', '')
        department_id = request.form.get('department_id', type=int)
        
        if not name or not email or not password:
            flash('Todos os campos obrigatórios devem ser preenchidos.', 'danger')
            return render_template('register.html', departments=Department.query.all())
        
        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return render_template('register.html', departments=Department.query.all())
        
        if User.query.filter_by(email=email).first():
            flash('Este e-mail já está cadastrado.', 'danger')
            return render_template('register.html', departments=Department.query.all())
        
        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            phone=phone,
            department_id=department_id,
            profile='solicitante',
            created_at=now_sp()
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Cadastro realizado com sucesso! Faça login para continuar.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html', departments=Department.query.all())

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            # Gera token de reset
            token = str(uuid.uuid4())
            user.reset_token = token
            user.reset_token_expiry = now_sp() + timedelta(hours=1)
            db.session.commit()
            
            # Mostra o link de reset direto na tela (sem e-mail)
            reset_url = url_for('reset_password', token=token, _external=True)
            flash(f'Link de redefinição gerado! Acesse: {reset_url}', 'success')
        else:
            flash('Se o e-mail existir em nosso sistema, você receberá instruções para redefinir sua senha.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expiry or now_sp() > user.reset_token_expiry:
        flash('Link inválido ou expirado. Solicite uma nova recuperação de senha.', 'danger')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or len(new_password) < 4:
            flash('A senha deve ter pelo menos 4 caracteres.', 'danger')
            return render_template('reset_password.html', token=token)
        
        if new_password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return render_template('reset_password.html', token=token)
        
        user.password_hash = generate_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        
        flash('Senha redefinida com sucesso! Faça login com sua nova senha.', 'success')
        return redirect(url_for('login'))
    
    return render_template('reset_password.html', token=token)

@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    
    if not check_password_hash(current_user.password_hash, current_password):
        flash('Senha atual incorreta.', 'danger')
        return redirect(url_for('profile'))
    
    if new_password != confirm_password:
        flash('As novas senhas não coincidem.', 'danger')
        return redirect(url_for('profile'))
    
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash('Senha alterada com sucesso!', 'success')
    return redirect(url_for('profile'))

# ─── Dashboard ──────────────────────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.profile == 'solicitante':
        return redirect(url_for('dashboard_solicitante'))
    elif current_user.profile == 'tecnico':
        return redirect(url_for('dashboard_tecnico'))
    return redirect(url_for('dashboard_admin'))

@app.route('/dashboard/solicitante')
@login_required
@has_role('solicitante')
def dashboard_solicitante():
    chamados = Chamado.query.filter_by(user_id=current_user.id).order_by(Chamado.created_at.desc()).limit(10).all()
    
    stats = {
        'abertos': Chamado.query.filter_by(user_id=current_user.id, status='novo').count(),
        'atendimento': Chamado.query.filter_by(user_id=current_user.id).filter(
            Chamado.status.in_(['em_analise', 'em_atendimento'])
        ).count(),
        'aguardando': Chamado.query.filter_by(user_id=current_user.id).filter(
            Chamado.status.in_(['aguardando_usuario', 'aguardando_fornecedor', 'aguardando_peca'])
        ).count(),
        'finalizados': Chamado.query.filter_by(user_id=current_user.id).filter(
            Chamado.status.in_(['finalizado', 'cancelado'])
        ).count()
    }
    
    return render_template('dashboard_solicitante.html', chamados=chamados, stats=stats)

@app.route('/dashboard/tecnico')
@login_required
@has_role('tecnico', 'admin')
def dashboard_tecnico():
    now = now_sp()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Estatísticas do técnico
    stats = {
        'novos': Chamado.query.filter_by(status='novo').count(),
        'atendimento': Chamado.query.filter_by(tecnico_id=current_user.id, status='em_atendimento').count(),
        'pendentes': Chamado.query.filter_by(tecnico_id=current_user.id).filter(
            Chamado.status.in_(['aguardando_usuario', 'aguardando_fornecedor', 'aguardando_peca'])
        ).count(),
        'resolvidos_hoje': Chamado.query.filter(
            Chamado.tecnico_id == current_user.id,
            Chamado.resolved_at >= today_start
        ).count()
    }
    
    # Dados para gráficos
    chamados_por_categoria = db.session.query(
        Category.name, db.func.count(Chamado.id)
    ).join(Category, Chamado.categoria_id == Category.id).group_by(Category.name).all()
    
    chamados_por_prioridade = db.session.query(
        Chamado.prioridade, db.func.count(Chamado.id)
    ).group_by(Chamado.prioridade).all()
    
    chamados_por_departamento = db.session.query(
        Department.name, db.func.count(Chamado.id)
    ).join(Department, Chamado.department_id == Department.id).group_by(Department.name).all()
    
    chamados_por_mes = db.session.query(
        db.func.strftime('%m/%Y', Chamado.created_at).label('mes'),
        db.func.count(Chamado.id)
    ).group_by('mes').order_by(Chamado.created_at.asc()).limit(12).all()
    
    return render_template('dashboard_tecnico.html', stats=stats,
                          chamados_por_categoria=chamados_por_categoria,
                          chamados_por_prioridade=chamados_por_prioridade,
                          chamados_por_departamento=chamados_por_departamento,
                          chamados_por_mes=chamados_por_mes)

@app.route('/dashboard/admin')
@login_required
@has_role('admin')
def dashboard_admin():
    now = now_sp()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    total = Chamado.query.count()
    abertos = Chamado.query.filter(Chamado.status.in_(['novo', 'em_analise'])).count()
    atendimento = Chamado.query.filter_by(status='em_atendimento').count()
    finalizados = Chamado.query.filter(Chamado.status.in_(['finalizado', 'cancelado'])).count()
    
    # SLA
    sla_cumprido = Chamado.query.filter_by(sla_breached=False).filter(
        Chamado.status.in_(['resolvido', 'finalizado'])
    ).count()
    sla_vencido = Chamado.query.filter_by(sla_breached=True).filter(
        Chamado.status.in_(['resolvido', 'finalizado'])
    ).count()
    
    return render_template('dashboard_admin.html', 
                          total=total, abertos=abertos, atendimento=atendimento, finalizados=finalizados,
                          sla_cumprido=sla_cumprido, sla_vencido=sla_vencido)

# ─── Chamados ───────────────────────────────────────────────────────

@app.route('/chamados')
@login_required
def list_chamados():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = Chamado.query
    if current_user.profile == 'solicitante':
        query = query.filter_by(user_id=current_user.id)
    
    # Filtros
    status = request.args.get('status')
    categoria = request.args.get('categoria', type=int)
    prioridade = request.args.get('prioridade')
    search = request.args.get('search')
    
    if status:
        query = query.filter_by(status=status)
    if categoria:
        query = query.filter_by(categoria_id=categoria)
    if prioridade:
        query = query.filter_by(prioridade=prioridade)
    if search:
        query = query.filter(
            db.or_(
                Chamado.protocolo.ilike(f'%{search}%'),
                Chamado.titulo.ilike(f'%{search}%'),
                Chamado.equipamento.ilike(f'%{search}%')
            )
        )
    
    chamados = query.order_by(Chamado.created_at.desc()).paginate(page=page, per_page=per_page)
    categorias = Category.query.all()
    
    return render_template('list_chamados.html', chamados=chamados, categorias=categorias)

@app.route('/chamados/novo', methods=['GET', 'POST'])
@login_required
@has_role('solicitante')
def novo_chamado():
    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        categoria_id = request.form.get('categoria_id', type=int)
        prioridade = request.form.get('prioridade', 'media')
        department_id = request.form.get('department_id', type=int)
        localizacao = request.form.get('localizacao', '')
        equipamento = request.form.get('equipamento', '')
        patrimonio = request.form.get('patrimonio', '')
        telefone = request.form.get('telefone', '')
        descricao = request.form.get('descricao', '').strip()
        
        if not titulo or not descricao:
            flash('Título e descrição são obrigatórios.', 'danger')
            return redirect(url_for('novo_chamado'))
        
        chamado = Chamado(
            protocolo=generate_protocolo(),
            titulo=titulo,
            categoria_id=categoria_id,
            prioridade=prioridade,
            department_id=department_id or current_user.department_id,
            localizacao=localizacao,
            equipamento=equipamento,
            patrimonio=patrimonio,
            telefone=telefone,
            descricao=descricao,
            status='novo',
            user_id=current_user.id,
            created_at=now_sp()
        )
        db.session.add(chamado)
        db.session.flush()
        
        # Calcular SLA
        calculate_sla(chamado)
        
        # Anexos
        if 'attachments' in request.files:
            files = request.files.getlist('attachments')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    attachment = Attachment(
                        chamado_id=chamado.id,
                        filename=filename,
                        original_name=file.filename,
                        file_size=os.path.getsize(filepath),
                        file_type=file.content_type,
                        uploaded_by=current_user.id,
                        created_at=now_sp()
                    )
                    db.session.add(attachment)
        
        db.session.commit()
        
        # Histórico e notificação
        add_history(chamado.id, current_user.id, 'Chamado criado', novo_status='novo', detalhes=f'Protocolo {chamado.protocolo}')
        log_system(current_user.id, 'novo_chamado', f'Chamado {chamado.protocolo} criado')
        
        # Notificar técnicos
        tecnicos = User.query.filter(User.profile.in_(['tecnico', 'admin']), User.is_active == True).all()
        for tec in tecnicos:
            create_notification(tec.id, 'Novo Chamado', 
                              f'Novo chamado {chamado.protocolo}: {chamado.titulo}',
                              chamado.id, 'info')
        
        flash(f'Chamado {chamado.protocolo} aberto com sucesso!', 'success')
        return redirect(url_for('view_chamado', id=chamado.id))
    
    return render_template('novo_chamado.html',
                          categorias=Category.query.all(),
                          departments=Department.query.all())

@app.route('/chamados/<int:id>')
@login_required
def view_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    
    # Verificar permissão
    if current_user.profile == 'solicitante' and chamado.user_id != current_user.id:
        abort(403)
    
    messages = Message.query.filter_by(chamado_id=id).order_by(Message.created_at.asc()).all()
    historico = History.query.filter_by(chamado_id=id).order_by(History.created_at.asc()).all()
    tecnicos = User.query.filter(User.profile.in_(['tecnico', 'admin']), User.is_active == True).all()
    
    sla_status = get_sla_status(chamado)
    
    # Marcar notificações como lidas
    Notification.query.filter_by(user_id=current_user.id, chamado_id=id, is_read=False).update({'is_read': True})
    db.session.commit()
    
    return render_template('view_chamado.html', chamado=chamado, messages=messages,
                          historico=historico, tecnicos=tecnicos, sla_status=sla_status)

@app.route('/chamados/<int:id>/assumir', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def assumir_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    chamado.tecnico_id = current_user.id
    chamado.status = 'em_atendimento'
    chamado.first_response_at = now_sp()
    db.session.commit()
    add_history(id, current_user.id, 'Chamado assumido', detalhes=f'Técnico: {current_user.name}')
    create_notification(chamado.user_id, 'Chamado em atendimento',
                       f'Seu chamado {chamado.protocolo} foi assumido por {current_user.name}', id, 'info')
    flash('Chamado assumido com sucesso!', 'success')
    return redirect(url_for('view_chamado', id=id))

@app.route('/chamados/<int:id>/prioridade', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def update_priority(id):
    chamado = Chamado.query.get_or_404(id)
    prioridade = request.form.get('prioridade', 'media')
    prioridade_anterior = chamado.prioridade
    chamado.prioridade = prioridade
    db.session.commit()
    add_history(id, current_user.id, 'Prioridade alterada', detalhes=f'De {prioridade_anterior} para {prioridade}')
    flash('Prioridade atualizada!', 'success')
    return redirect(url_for('view_chamado', id=id))

@app.route('/chamados/<int:id>/transferir', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def transferir_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    tecnico_id = request.form.get('tecnico_id', type=int)
    if tecnico_id:
        novo_tecnico = User.query.get(tecnico_id)
        tecnico_anterior = chamado.tecnico.name if chamado.tecnico else 'Nenhum'
        chamado.tecnico_id = tecnico_id
        db.session.commit()
        add_history(id, current_user.id, 'Chamado transferido',
                   detalhes=f'De {tecnico_anterior} para {novo_tecnico.name}')
        flash(f'Chamado transferido para {novo_tecnico.name}!', 'success')
    return redirect(url_for('view_chamado', id=id))

@app.route('/chamados/<int:id>/avaliar', methods=['POST'])
@login_required
@has_role('solicitante')
def avaliar_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    if chamado.user_id != current_user.id:
        abort(403)
    nota = request.form.get('nota', type=int, default=5)
    comentario = request.form.get('comentario', '')
    chamado.avaliacao_nota = nota
    chamado.avaliacao_comentario = comentario
    db.session.commit()
    add_history(id, current_user.id, 'Avaliação registrada', detalhes=f'Nota: {nota}/5')
    flash('Avaliação registrada! Obrigado pelo feedback.', 'success')
    return redirect(url_for('view_chamado', id=id))

@app.route('/chamados/<int:id>/reabrir', methods=['POST'])
@login_required
@has_role('solicitante')
def reabrir_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    if chamado.user_id != current_user.id:
        abort(403)
    chamado.status = 'em_atendimento'
    db.session.commit()
    add_history(id, current_user.id, 'Chamado reaberto pelo solicitante')
    flash('Chamado reaberto com sucesso!', 'success')
    return redirect(url_for('view_chamado', id=id))

@app.route('/api/chamados/<int:id>/messages', methods=['GET'])
@login_required
def get_messages(id):
    chamado = Chamado.query.get_or_404(id)
    messages = Message.query.filter_by(chamado_id=id).order_by(Message.created_at.asc()).all()
    result = []
    for msg in messages:
        if msg.is_internal and current_user.profile == 'solicitante':
            continue
        result.append({
            'id': msg.id,
            'user': msg.user.name,
            'user_profile': msg.user.profile,
            'message': msg.message,
            'is_internal': msg.is_internal,
            'created_at': msg.created_at.strftime('%d/%m/%Y %H:%M')
        })
    return jsonify(result)

@app.route('/api/chamados/<int:id>/message', methods=['POST'])
@login_required
def send_message(id):
    chamado = Chamado.query.get_or_404(id)
    data = request.get_json()
    message_text = data.get('message', '').strip()
    is_internal = data.get('is_internal', False)
    
    if not message_text:
        return jsonify({'error': 'Mensagem vazia'}), 400
    
    # Solicitante não pode enviar mensagens internas
    if is_internal and current_user.profile == 'solicitante':
        return jsonify({'error': 'Acesso não autorizado'}), 403
    
    msg = Message(
        chamado_id=id,
        user_id=current_user.id,
        message=message_text,
        is_internal=is_internal,
        created_at=now_sp()
    )
    db.session.add(msg)
    db.session.commit()
    
    add_history(id, current_user.id, 'Mensagem enviada', detalhes=message_text[:100])
    
    # Notificar envolvidos
    if current_user.id == chamado.user_id and chamado.tecnico_id:
        create_notification(chamado.tecnico_id, 'Nova mensagem',
                          f'{current_user.name} respondeu no chamado {chamado.protocolo}',
                          id, 'info')
    elif current_user.profile in ['tecnico', 'admin']:
        create_notification(chamado.user_id, 'Nova resposta',
                          f'Técnico respondeu no chamado {chamado.protocolo}',
                          id, 'info')
    
    return jsonify({'success': True, 'message': {
        'id': msg.id,
        'user': msg.user.name,
        'user_profile': msg.user.profile,
        'message': msg.message,
        'is_internal': msg.is_internal,
        'created_at': msg.created_at.strftime('%d/%m/%Y %H:%M')
    }})

@app.route('/api/chamados/<int:id>/status', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def update_status(id):
    chamado = Chamado.query.get_or_404(id)
    is_json = request.is_json
    
    if is_json:
        data = request.get_json()
        novo_status = data.get('status')
    else:
        novo_status = request.form.get('status')
    
    if not novo_status or novo_status not in Chamado.STATUS_DISPLAY:
        if is_json:
            return jsonify({'error': 'Status inválido'}), 400
        flash('Status inválido.', 'danger')
        return redirect(url_for('view_chamado', id=id))
    
    status_anterior = chamado.status
    chamado.status = novo_status
    
    if novo_status == 'em_atendimento' and not chamado.first_response_at:
        chamado.first_response_at = now_sp()
    
    if novo_status == 'resolvido' and not chamado.resolved_at:
        chamado.resolved_at = now_sp()
    
    if novo_status == 'finalizado':
        chamado.closed_at = now_sp()
    
    db.session.commit()
    
    add_history(id, current_user.id, 'Status alterado', status_anterior, novo_status)
    
    # Notificar solicitante
    create_notification(chamado.user_id, 'Status atualizado',
                       f'Chamado {chamado.protocolo} alterado para {Chamado.STATUS_DISPLAY[novo_status]}',
                       id, 'info')
    
    if is_json:
        return jsonify({'success': True, 'status': novo_status, 'status_display': Chamado.STATUS_DISPLAY[novo_status]})
    
    flash(f'Status alterado para {Chamado.STATUS_DISPLAY[novo_status]}!', 'success')
    return redirect(url_for('view_chamado', id=id))

@app.route('/api/chamados/<int:id>/assume', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def api_assume_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    
    if chamado.tecnico_id and chamado.tecnico_id != current_user.id:
        return jsonify({'error': 'Chamado já está com outro técnico'}), 400
    
    status_anterior = chamado.status
    chamado.tecnico_id = current_user.id
    if chamado.status == 'novo':
        chamado.status = 'em_analise'
        chamado.first_response_at = now_sp()
    
    db.session.commit()
    
    add_history(id, current_user.id, 'Chamado assumido', status_anterior, chamado.status, 
               f'Técnico: {current_user.name}')
    
    create_notification(chamado.user_id, 'Chamado atribuído',
                       f'{current_user.name} está analisando seu chamado {chamado.protocolo}',
                       id, 'info')
    
    return jsonify({'success': True, 'tecnico': current_user.name})

@app.route('/api/chamados/<int:id>/transfer', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def transfer_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    data = request.get_json()
    tecnico_id = data.get('tecnico_id')
    
    if not tecnico_id:
        return jsonify({'error': 'Selecione um técnico'}), 400
    
    novo_tecnico = User.query.get(tecnico_id)
    if not novo_tecnico or novo_tecnico.profile not in ['tecnico', 'admin']:
        return jsonify({'error': 'Técnico inválido'}), 400
    
    old_tecnico = chamado.tecnico
    chamado.tecnico_id = tecnico_id
    db.session.commit()
    
    add_history(id, current_user.id, 'Chamado transferido',
               detalhes=f'De {old_tecnico.name if old_tecnico else "Nenhum"} para {novo_tecnico.name}')
    
    create_notification(tecnico_id, 'Chamado transferido',
                       f'Chamado {chamado.protocolo} foi transferido para você',
                       id, 'warning')
    
    return jsonify({'success': True})

@app.route('/api/chamados/<int:id>/priority', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def change_priority(id):
    chamado = Chamado.query.get_or_404(id)
    data = request.get_json()
    nova_prioridade = data.get('prioridade')
    
    if nova_prioridade not in ['baixa', 'media', 'alta', 'critica']:
        return jsonify({'error': 'Prioridade inválida'}), 400
    
    old_priority = chamado.prioridade
    chamado.prioridade = nova_prioridade
    calculate_sla(chamado)
    db.session.commit()
    
    add_history(id, current_user.id, 'Prioridade alterada',
               detalhes=f'De {old_priority} para {nova_prioridade}')
    
    return jsonify({'success': True})

@app.route('/api/chamados/<int:id>/category', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def change_category(id):
    chamado = Chamado.query.get_or_404(id)
    data = request.get_json()
    categoria_id = data.get('categoria_id')
    
    if not categoria_id:
        return jsonify({'error': 'Selecione uma categoria'}), 400
    
    old_cat = chamado.category
    chamado.categoria_id = categoria_id
    calculate_sla(chamado)
    db.session.commit()
    
    add_history(id, current_user.id, 'Categoria alterada',
               detalhes=f'De {old_cat.name if old_cat else "N/A"} para {chamado.category.name}')
    
    return jsonify({'success': True})

@app.route('/api/chamados/<int:id>/time', methods=['POST'])
@login_required
@has_role('tecnico', 'admin')
def register_time(id):
    chamado = Chamado.query.get_or_404(id)
    data = request.get_json()
    minutes = data.get('minutes', 0)
    
    if minutes <= 0:
        return jsonify({'error': 'Tempo inválido'}), 400
    
    chamado.tempo_gasto_minutos = (chamado.tempo_gasto_minutos or 0) + minutes
    db.session.commit()
    
    add_history(id, current_user.id, 'Tempo registrado',
               detalhes=f'{minutes} minutos adicionados. Total: {chamado.tempo_gasto_minutos} minutos')
    
    return jsonify({'success': True, 'total_minutes': chamado.tempo_gasto_minutos})

@app.route('/api/chamados/<int:id>/reopen', methods=['POST'])
@login_required
def reopen_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    
    if current_user.profile == 'solicitante' and chamado.user_id != current_user.id:
        abort(403)
    
    if chamado.status not in ['finalizado', 'cancelado', 'resolvido']:
        return jsonify({'error': 'Chamado não pode ser reaberto'}), 400
    
    status_anterior = chamado.status
    chamado.status = 'em_analise'
    db.session.commit()
    
    add_history(id, current_user.id, 'Chamado reaberto', status_anterior, 'em_analise')
    
    tecnicos = User.query.filter(User.profile.in_(['tecnico', 'admin']), User.is_active == True).all()
    for tec in tecnicos:
        create_notification(tec.id, 'Chamado reaberto',
                          f'Chamado {chamado.protocolo} foi reaberto por {current_user.name}',
                          id, 'warning')
    
    return jsonify({'success': True})

@app.route('/api/chamados/<int:id>/rate', methods=['POST'])
@login_required
def rate_chamado(id):
    chamado = Chamado.query.get_or_404(id)
    
    if chamado.user_id != current_user.id:
        abort(403)
    
    if chamado.status != 'finalizado':
        return jsonify({'error': 'Chamado precisa estar finalizado para avaliação'}), 400
    
    data = request.get_json()
    nota = data.get('nota', 0)
    comentario = data.get('comentario', '')
    
    if nota < 1 or nota > 5:
        return jsonify({'error': 'Nota deve ser entre 1 e 5'}), 400
    
    chamado.avaliacao_nota = nota
    chamado.avaliacao_comentario = comentario
    db.session.commit()
    
    add_history(id, current_user.id, 'Avaliação registrada', detalhes=f'Nota: {nota}/5')
    
    return jsonify({'success': True})

@app.route('/api/chamados/<int:id>/attachments', methods=['POST'])
@login_required
def upload_attachment(id):
    chamado = Chamado.query.get_or_404(id)
    
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Arquivo inválido'}), 400
    
    filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    attachment = Attachment(
        chamado_id=id,
        filename=filename,
        original_name=file.filename,
        file_size=os.path.getsize(filepath),
        file_type=file.content_type,
        uploaded_by=current_user.id,
        created_at=now_sp()
    )
    db.session.add(attachment)
    db.session.commit()
    
    return jsonify({'success': True, 'attachment': {
        'id': attachment.id,
        'name': attachment.original_name,
        'size': attachment.file_size,
        'url': url_for('download_attachment', id=attachment.id)
    }})

@app.route('/uploads/<path:filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/attachments/<int:id>/download')
@login_required
def download_attachment(id):
    attachment = Attachment.query.get_or_404(id)
    return send_from_directory(app.config['UPLOAD_FOLDER'], attachment.filename, 
                              download_name=attachment.original_name)

# ─── Autoatendimento / Soluções Rápidas ────────────────────────────

@app.route('/autoatendimento')
@login_required
@has_role('solicitante')
def autoatendimento():
    solutions = QuickSolution.query.filter_by(is_active=True).all()
    categories = [s.category for s in solutions if s.category]
    categories = sorted(set(categories))
    grouped = {}
    for s in solutions:
        grouped.setdefault(s.category, []).append(s)
    return render_template('autoatendimento.html', solutions=solutions,
                          categories=categories, grouped_solutions=grouped)

@app.route('/api/autoatendimento/execute/<int:id>', methods=['POST'])
@login_required
@has_role('solicitante')
def execute_solution(id):
    solution = QuickSolution.query.get_or_404(id)
    
    if not solution.is_active:
        return jsonify({'error': 'Solução não está disponível'}), 400
    
    # Verificar permissões
    if solution.departments.count() > 0:
        dept_ids = [sd.department_id for sd in solution.departments]
        if current_user.department_id not in dept_ids:
            return jsonify({'error': 'Você não tem permissão para executar esta solução'}), 403
    
    if solution.allowed_users.count() > 0:
        user_ids = [su.user_id for su in solution.allowed_users]
        if current_user.id not in user_ids:
            return jsonify({'error': 'Você não tem permissão para executar esta solução'}), 403
    
    # Registrar execução
    execution = SolutionExecution(
        solution_id=id,
        user_id=current_user.id,
        computer_name=request.headers.get('User-Agent', 'Unknown')[:100],
        ip_address=request.remote_addr,
        result='success',
        executed_at=now_sp()
    )
    db.session.add(execution)
    db.session.commit()
    
    log_system(current_user.id, 'solucao_executada', 
              f'Solução "{solution.name}" executada por {current_user.name}')
    
    return jsonify({
        'success': True,
        'solution': {
            'name': solution.name,
            'description': solution.description,
            'needs_admin': solution.needs_admin,
            'script_file': solution.script_file,
            'script_type': solution.script_type
        }
    })

# ─── Notificações ───────────────────────────────────────────────────

@app.route('/api/notificacoes')
@login_required
def get_notifications():
    notificacoes = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(20).all()
    return jsonify([{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'type': n.type,
        'chamado_id': n.chamado_id,
        'created_at': n.created_at.strftime('%d/%m/%Y %H:%M') if n.created_at else '',
        'is_read': n.is_read
    } for n in notificacoes])

@app.route('/api/notificacoes/read/<int:id>', methods=['POST'])
@login_required
def read_notification(id):
    n = Notification.query.get_or_404(id)
    if n.user_id == current_user.id:
        n.is_read = True
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/notificacoes/read-all', methods=['POST'])
@login_required
def read_all_notifications():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

# ─── Perfil ─────────────────────────────────────────────────────────

@app.route('/perfil', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name', current_user.name)
        current_user.phone = request.form.get('phone', current_user.phone)
        
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                filename = secure_filename(f"avatar_{current_user.id}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                current_user.avatar = filename
        
        db.session.commit()
        flash('Perfil atualizado com sucesso!', 'success')
        return redirect(url_for('profile'))
    
    return render_template('profile.html')

# ─── Administração ─────────────────────────────────────────────────

@app.route('/admin/usuarios')
@login_required
@has_role('admin')
def admin_users():
    users = User.query.all()
    departments = Department.query.all()
    return render_template('admin_usuarios.html', users=users, departments=departments)

@app.route('/admin/usuarios/novo', methods=['POST'])
@login_required
@has_role('admin')
def admin_new_user():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '123456')
    profile = request.form.get('profile', 'solicitante')
    department_id = request.form.get('department_id', type=int)
    
    if not name or not email:
        flash('Nome e e-mail são obrigatórios.', 'danger')
        return redirect(url_for('admin_users'))
    
    if User.query.filter_by(email=email).first():
        flash('E-mail já cadastrado.', 'danger')
        return redirect(url_for('admin_users'))
    
    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        profile=profile,
        department_id=department_id,
        created_at=now_sp()
    )
    db.session.add(user)
    db.session.commit()
    
    log_system(current_user.id, 'usuario_criado', f'Usuário {email} ({profile}) criado')
    flash(f'Usuário {name} criado com sucesso!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/usuarios/<int:id>/edit', methods=['POST'])
@login_required
@has_role('admin')
def admin_edit_user(id):
    user = User.query.get_or_404(id)
    user.name = request.form.get('name', user.name)
    user.email = request.form.get('email', user.email)
    user.profile = request.form.get('profile', user.profile)
    user.department_id = request.form.get('department_id', type=int)
    user.is_active = request.form.get('is_active') == 'on'
    db.session.commit()
    
    log_system(current_user.id, 'usuario_editado', f'Usuário {user.email} editado')
    flash('Usuário atualizado com sucesso!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/usuarios/<int:id>/reset-password', methods=['POST'])
@login_required
@has_role('admin')
def admin_reset_password(id):
    user = User.query.get_or_404(id)
    new_password = request.form.get('new_password', '123456')
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    flash(f'Senha do usuário {user.name} redefinida para: {new_password}', 'info')
    return redirect(url_for('admin_users'))

@app.route('/admin/usuarios/<int:id>/delete', methods=['POST'])
@login_required
@has_role('admin')
def admin_delete_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Você não pode excluir seu próprio usuário.', 'danger')
        return redirect(url_for('admin_users'))
    
    log_system(current_user.id, 'usuario_excluido', f'Usuário {user.email} excluído')
    user.is_active = False
    db.session.commit()
    flash(f'Usuário {user.name} desativado com sucesso!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/usuarios/<int:id>/block', methods=['GET'])
@login_required
@has_role('admin')
def block_user(id):
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Você não pode bloquear seu próprio usuário.', 'danger')
    else:
        user.is_active = False
        db.session.commit()
        log_system(current_user.id, 'usuario_bloqueado', f'Usuário {user.email} bloqueado')
        flash(f'Usuário {user.name} bloqueado!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/usuarios/<int:id>/unblock', methods=['GET'])
@login_required
@has_role('admin')
def unblock_user(id):
    user = User.query.get_or_404(id)
    user.is_active = True
    db.session.commit()
    log_system(current_user.id, 'usuario_desbloqueado', f'Usuário {user.email} desbloqueado')
    flash(f'Usuário {user.name} desbloqueado!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/departamentos')
@login_required
@has_role('admin')
def admin_departments():
    departments = Department.query.all()
    return render_template('admin_departamentos.html', departments=departments)

@app.route('/admin/departamentos/novo', methods=['POST'])
@login_required
@has_role('admin')
def admin_new_department():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '')
    
    if not name:
        flash('Nome do departamento é obrigatório.', 'danger')
        return redirect(url_for('admin_departments'))
    
    if Department.query.filter_by(name=name).first():
        flash('Departamento já existe.', 'danger')
        return redirect(url_for('admin_departments'))
    
    dept = Department(name=name, description=description, created_at=now_sp())
    db.session.add(dept)
    db.session.commit()
    flash(f'Departamento {name} criado!', 'success')
    return redirect(url_for('admin_departments'))

@app.route('/admin/departamentos/<int:id>/edit', methods=['POST'])
@login_required
@has_role('admin')
def admin_edit_department(id):
    dept = Department.query.get_or_404(id)
    dept.name = request.form.get('name', dept.name)
    dept.description = request.form.get('description', dept.description)
    db.session.commit()
    flash('Departamento atualizado!', 'success')
    return redirect(url_for('admin_departments'))

@app.route('/admin/categorias')
@login_required
@has_role('admin')
def admin_categorias():
    categorias = Category.query.all()
    return render_template('admin_categorias.html', categorias=categorias)

@app.route('/admin/categorias/novo', methods=['POST'])
@login_required
@has_role('admin')
def admin_new_category():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '')
    
    if not name:
        flash('Nome da categoria é obrigatório.', 'danger')
        return redirect(url_for('admin_categorias'))
    
    cat = Category(name=name, description=description, created_at=now_sp())
    db.session.add(cat)
    db.session.commit()
    flash(f'Categoria {name} criada!', 'success')
    return redirect(url_for('admin_categorias'))

@app.route('/admin/categorias/<int:id>/edit', methods=['POST'])
@login_required
@has_role('admin')
def admin_edit_category(id):
    cat = Category.query.get_or_404(id)
    cat.name = request.form.get('name', cat.name)
    cat.description = request.form.get('description', cat.description)
    db.session.commit()
    flash('Categoria atualizada!', 'success')
    return redirect(url_for('admin_categorias'))

@app.route('/admin/sla', methods=['GET', 'POST'])
@login_required
@has_role('admin')
def admin_sla():
    if request.method == 'POST':
        sla = SLA.query.first()
        if not sla:
            sla = SLA(created_at=now_sp())
            db.session.add(sla)
        sla.first_response_hours = request.form.get('first_response_time', type=int, default=4)
        sla.resolution_hours = request.form.get('resolution_time', type=int, default=24)
        sla.warning_hours = request.form.get('alert_before', type=int, default=60)
        sla.auto_escalate = request.form.get('auto_escalate') == 'on'
        db.session.commit()
        flash('Configurações de SLA salvas!', 'success')
        return redirect(url_for('admin_sla'))
    sla = SLA.query.first()
    categorias = Category.query.all()
    return render_template('admin_sla.html', sla=sla, categorias=categorias)

@app.route('/admin/sla/novo', methods=['POST'])
@login_required
@has_role('admin')
def admin_new_sla():
    category_id = request.form.get('category_id', type=int)
    priority = request.form.get('priority')
    first_response = request.form.get('first_response', type=int, default=24)
    resolution = request.form.get('resolution', type=int, default=72)
    warning = request.form.get('warning', type=int, default=2)
    
    existing = SLA.query.filter_by(category_id=category_id, priority=priority).first()
    if existing:
        flash('SLA já existe para esta categoria e prioridade.', 'danger')
        return redirect(url_for('admin_sla'))
    
    sla = SLA(
        category_id=category_id,
        priority=priority,
        first_response_hours=first_response,
        resolution_hours=resolution,
        warning_hours=warning,
        created_at=now_sp()
    )
    db.session.add(sla)
    db.session.commit()
    flash('SLA configurado!', 'success')
    return redirect(url_for('admin_sla'))

@app.route('/admin/sla/<int:id>/edit', methods=['POST'])
@login_required
@has_role('admin')
def admin_edit_sla(id):
    sla = SLA.query.get_or_404(id)
    sla.priority = request.form.get('priority', sla.priority)
    sla.first_response_hours = request.form.get('first_response', type=int, default=sla.first_response_hours)
    sla.resolution_hours = request.form.get('resolution', type=int, default=sla.resolution_hours)
    sla.warning_hours = request.form.get('warning', type=int, default=sla.warning_hours)
    sla.category_id = request.form.get('category_id', type=int) or sla.category_id
    db.session.commit()
    flash('SLA atualizado!', 'success')
    return redirect(url_for('admin_sla'))

@app.route('/admin/solucoes')
@login_required
@has_role('admin')
def admin_solutions():
    solutions = QuickSolution.query.all()
    departments = Department.query.all()
    return render_template('admin_solucoes.html', solutions=solutions, departments=departments)

@app.route('/admin/solucoes/novo', methods=['POST'])
@login_required
@has_role('admin')
def admin_new_solution():
    name = request.form.get('name', '').strip()
    category = request.form.get('category', '')
    description = request.form.get('description', '')
    icon = request.form.get('icon', 'bi bi-tools')
    needs_admin = request.form.get('needs_admin') == 'on'
    
    if not name or not category:
        flash('Nome e categoria são obrigatórios.', 'danger')
        return redirect(url_for('admin_solutions'))
    
    script_file = None
    script_type = None
    
    if 'script_file' in request.files:
        file = request.files['script_file']
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
            if ext in ['bat', 'cmd', 'ps1', 'exe']:
                filename = secure_filename(f"sol_{uuid.uuid4()}.{ext}")
                filepath = os.path.join(app.config['SOLUTIONS_FOLDER'], filename)
                file.save(filepath)
                script_file = filename
                script_type = ext
    
    solution = QuickSolution(
        name=name,
        category=category,
        description=description,
        icon=icon,
        script_file=script_file,
        script_type=script_type,
        needs_admin=needs_admin,
        created_at=now_sp()
    )
    db.session.add(solution)
    db.session.flush()
    
    # Permissões por departamento
    dept_ids = request.form.getlist('department_ids')
    for dept_id in dept_ids:
        sd = SolutionDepartment(solution_id=solution.id, department_id=int(dept_id))
        db.session.add(sd)
    
    db.session.commit()
    log_system(current_user.id, 'solucao_criada', f'Solução "{name}" criada')
    flash(f'Solução "{name}" criada!', 'success')
    return redirect(url_for('admin_solutions'))

@app.route('/admin/solucoes/<int:id>/toggle', methods=['POST'])
@login_required
@has_role('admin')
def admin_toggle_solution(id):
    solution = QuickSolution.query.get_or_404(id)
    solution.is_active = not solution.is_active
    db.session.commit()
    return jsonify({'success': True, 'is_active': solution.is_active})

@app.route('/admin/solucoes/<int:id>/delete', methods=['POST'])
@login_required
@has_role('admin')
def admin_delete_solution(id):
    solution = QuickSolution.query.get_or_404(id)
    db.session.delete(solution)
    db.session.commit()
    flash('Solução excluída!', 'success')
    return redirect(url_for('admin_solutions'))

# ─── Base de Conhecimento ──────────────────────────────────────────

@app.route('/knowledge-base')
@login_required
def knowledge_base():
    articles = KnowledgeBase.query.filter_by(is_published=True).order_by(KnowledgeBase.views.desc()).all()
    return render_template('knowledge_base.html', artigos=articles)

@app.route('/knowledge-base/<int:id>')
@login_required
def knowledge_view(id):
    article = KnowledgeBase.query.get_or_404(id)
    article.views = (article.views or 0) + 1
    db.session.commit()
    return render_template('knowledge_view.html', article=article)

@app.route('/admin/knowledge-base')
@login_required
@has_role('admin')
def admin_knowledge_base():
    articles = KnowledgeBase.query.all()
    return render_template('admin_knowledge_base.html', articles=articles)

@app.route('/admin/knowledge-base/novo', methods=['POST'])
@login_required
@has_role('admin')
def admin_new_article():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    category = request.form.get('category', '')
    tags = request.form.get('tags', '')
    
    if not title or not content:
        flash('Título e conteúdo são obrigatórios.', 'danger')
        return redirect(url_for('admin_knowledge_base'))
    
    article = KnowledgeBase(
        title=title,
        content=content,
        category=category,
        tags=tags,
        author_id=current_user.id,
        created_at=now_sp()
    )
    db.session.add(article)
    db.session.commit()
    flash('Artigo publicado!', 'success')
    return redirect(url_for('admin_knowledge_base'))

# ─── Delete Routes ─────────────────────────────────────────────────

@app.route('/admin/departamentos/<int:id>/delete', methods=['POST'])
@login_required
@has_role('admin')
def delete_department(id):
    dept = Department.query.get_or_404(id)
    name = dept.name
    db.session.delete(dept)
    db.session.commit()
    flash(f'Departamento {name} excluído!', 'success')
    return redirect(url_for('admin_departments'))

@app.route('/admin/categorias/<int:id>/delete', methods=['GET', 'POST'])
@login_required
@has_role('admin')
def delete_category(id):
    cat = Category.query.get_or_404(id)
    name = cat.name
    db.session.delete(cat)
    db.session.commit()
    flash(f'Categoria {name} excluída!', 'success')
    return redirect(url_for('admin_categorias'))

@app.route('/admin/knowledge/<int:id>/delete', methods=['POST'])
@login_required
@has_role('admin')
def delete_article(id):
    article = KnowledgeBase.query.get_or_404(id)
    db.session.delete(article)
    db.session.commit()
    flash('Artigo excluído!', 'success')
    return redirect(url_for('admin_knowledge_base'))

@app.route('/admin/knowledge/<int:id>/toggle', methods=['GET', 'POST'])
@login_required
@has_role('admin')
def toggle_article(id):
    article = KnowledgeBase.query.get_or_404(id)
    article.is_published = not article.is_published
    db.session.commit()
    flash(f'Artigo {"publicado" if article.is_published else "despublicado"}!', 'success')
    return redirect(url_for('admin_knowledge_base'))

@app.route('/knowledge-base/add', methods=['POST'])
@login_required
@has_role('admin')
def add_knowledge():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    category = request.form.get('category', '')
    tags = request.form.get('tags', '')
    
    if not title or not content:
        flash('Título e conteúdo são obrigatórios.', 'danger')
        return redirect(url_for('knowledge_base'))
    
    article = KnowledgeBase(
        title=title,
        content=content,
        category=category,
        tags=tags,
        author_id=current_user.id,
        is_published=True,
        created_at=now_sp()
    )
    db.session.add(article)
    db.session.commit()
    flash('Artigo publicado na base de conhecimento!', 'success')
    return redirect(url_for('knowledge_base'))

# ─── Upload solução ────────────────────────────────────────────────

@app.route('/upload/solution/<int:id>', methods=['POST'])
@login_required
@has_role('admin')
def upload_solution_file(id):
    solution = QuickSolution.query.get_or_404(id)
    if 'file' not in request.files:
        flash('Nenhum arquivo enviado.', 'danger')
        return redirect(url_for('admin_solutions'))
    file = request.files['file']
    if file and file.filename:
        filename = secure_filename(f"sol_{id}_{file.filename}")
        filepath = os.path.join(app.config['SOLUTIONS_FOLDER'], filename)
        file.save(filepath)
        solution.file_path = filename
        db.session.commit()
        flash('Arquivo enviado com sucesso!', 'success')
    return redirect(url_for('admin_solutions'))

@app.route('/solutions/<int:id>/download')
@login_required
@has_role('admin')
def download_solution_file(id):
    solution = QuickSolution.query.get_or_404(id)
    if not solution.file_path:
        flash('Nenhum arquivo vinculado a esta solução.', 'danger')
        return redirect(url_for('admin_solutions'))
    return send_from_directory(app.config['SOLUTIONS_FOLDER'], solution.file_path, 
                              as_attachment=True)

# ─── Relatórios ────────────────────────────────────────────────────

@app.route('/admin/relatorios')
@login_required
@has_role('admin')
def admin_reports():
    from datetime import date, timedelta
    
    period = request.args.get('period', 'month')
    today = date.today()
    
    if period == 'week':
        start_date = today - timedelta(days=7)
    elif period == 'month':
        start_date = today - timedelta(days=30)
    elif period == 'quarter':
        start_date = today - timedelta(days=90)
    elif period == 'year':
        start_date = today - timedelta(days=365)
    else:
        start_date = today - timedelta(days=30)
    
    # Dados do relatório
    total_chamados = Chamado.query.count()
    total_periodo = Chamado.query.filter(Chamado.created_at >= start_date).count()
    
    # SLA
    sla_cumprido = Chamado.query.filter(Chamado.sla_breached == False, 
                                       Chamado.status.in_(['resolvido', 'finalizado'])).count()
    sla_vencido = Chamado.query.filter(Chamado.sla_breached == True,
                                      Chamado.status.in_(['resolvido', 'finalizado'])).count()
    total_sla = sla_cumprido + sla_vencido
    
    # Tempo médio
    from sqlalchemy import func
    tempo_medio = db.session.query(func.avg(Chamado.tempo_gasto_minutos)).filter(
        Chamado.status == 'finalizado'
    ).scalar() or 0
    
    # Satisfação
    avaliacoes = db.session.query(func.avg(Chamado.avaliacao_nota)).filter(
        Chamado.avaliacao_nota.isnot(None)
    ).scalar() or 0
    
    return render_template('admin_relatorios.html',
                          total_chamados=total_chamados,
                          total_periodo=total_periodo,
                          sla_cumprido=sla_cumprido,
                          sla_vencido=sla_vencido,
                          total_sla=total_sla,
                          tempo_medio=round(tempo_medio, 0),
                          avaliacoes=round(avaliacoes, 1),
                          period=period)

# ─── Logs do Sistema ───────────────────────────────────────────────

@app.route('/admin/logs')
@login_required
@has_role('admin')
def admin_logs():
    page = request.args.get('page', 1, type=int)
    logs = SystemLog.query.order_by(SystemLog.created_at.desc()).paginate(page=page, per_page=50)
    return render_template('admin_logs.html', logs=logs)

# ─── Inicialização ─────────────────────────────────────────────────

@app.before_request
def create_tables():
    """Garante que as tabelas existam antes do primeiro request."""
    if not hasattr(app, '_tables_created'):
        db.create_all()
        # Seed data
        seed_data()
        app._tables_created = True

def seed_data():
    """Popula dados iniciais se estiver vazio."""
    if Department.query.count() > 0:
        return
    
    # Departamentos
    depts = ['Administrativo', 'Financeiro', 'RH', 'Comercial', 'Marketing', 'TI', 'Produção', 'Logística']
    for d in depts:
        db.session.add(Department(name=d, description=f'Departamento {d}'))
    
    # Categorias
    cats = [
        ('Computador', 'bi bi-pc-display'),
        ('Notebook', 'bi bi-laptop'),
        ('Impressora', 'bi bi-printer'),
        ('Internet', 'bi bi-globe2'),
        ('Rede', 'bi bi-diagram-3'),
        ('Sistema', 'bi bi-gear'),
        ('Office', 'bi bi-file-earmark-text'),
        ('E-mail', 'bi bi-envelope'),
        ('Telefonia', 'bi bi-telephone'),
        ('Hardware', 'bi bi-motherboard'),
        ('Software', 'bi bi-code-slash'),
        ('Acesso', 'bi bi-key'),
        ('Equipamentos', 'bi bi-tools'),
        ('Outros', 'bi bi-other')
    ]
    for c_name, c_icon in cats:
        db.session.add(Category(name=c_name, icon=c_icon, description=f'Problemas com {c_name}'))
    
    db.session.commit()
    
    # Admin padrão
    admin = User(
        name='Administrador',
        email='admin@chamadoti.com',
        password_hash=generate_password_hash('admin123'),
        profile='admin',
        department_id=1,
        created_at=now_sp()
    )
    db.session.add(admin)
    
    # Técnico padrão
    tecnico = User(
        name='Técnico TI',
        email='tecnico@chamadoti.com',
        password_hash=generate_password_hash('tecnico123'),
        profile='tecnico',
        department_id=6,
        created_at=now_sp()
    )
    db.session.add(tecnico)
    
    # Solicitante padrão
    solicitante = User(
        name='Usuário Teste',
        email='usuario@chamadoti.com',
        password_hash=generate_password_hash('usuario123'),
        profile='solicitante',
        department_id=2,
        created_at=now_sp()
    )
    db.session.add(solicitante)
    
    db.session.commit()
    
    # Soluções rápidas padrão
    solucoes = [
        # Rede
        ('Renovar IP', 'rede', 'Libera e renova o endereço IP do computador', 'bi bi-wifi', False),
        ('Limpar Cache DNS', 'rede', 'Limpa o cache de resolução DNS do sistema', 'bi bi-arrow-repeat', False),
        ('Resetar Winsock', 'rede', 'Restaura a configuração de sockets do Windows', 'bi bi-arrow-counterclockwise', True),
        ('Resetar TCP/IP', 'rede', 'Reinicia a pilha de protocolo TCP/IP', 'bi bi-arrow-clockwise', True),
        ('Diagnóstico de Rede', 'rede', 'Executa diagnóstico completo de rede', 'bi bi-search', False),
        ('Reiniciar Adaptador', 'rede', 'Desabilita e reabilita o adaptador de rede', 'bi bi-ethernet', False),
        # Impressoras
        ('Reiniciar Spooler', 'impressoras', 'Reinicia o serviço de spooler de impressão', 'bi bi-printer', True),
        ('Limpar Fila de Impressão', 'impressoras', 'Limpa todos os documentos da fila de impressão', 'bi bi-trash', False),
        ('Reinstalar Impressora', 'impressoras', 'Remove e reinstala a impressora padrão', 'bi bi-printer-fill', True),
        ('Testar Impressão', 'impressoras', 'Envia uma página de teste para a impressora', 'bi bi-filetype-doc', False),
        # Windows
        ('Limpar Temporários', 'windows', 'Remove arquivos temporários do sistema', 'bi bi-broom', False),
        ('Executar SFC', 'windows', 'Verifica e repara arquivos do sistema', 'bi bi-shield-check', True),
        ('Executar DISM', 'windows', 'Repara a imagem do Windows', 'bi bi-hdd-network', True),
        ('Atualizar GPUpdate', 'windows', 'Força atualização de políticas de grupo', 'bi bi-arrow-repeat', True),
        ('Abrir Serviços', 'windows', 'Abre o console de gerenciamento de serviços', 'bi bi-gear-wide-connected', False),
        ('Abrir Gerenciador de Dispositivos', 'windows', 'Abre o gerenciador de dispositivos', 'bi bi-devices', False),
        # Office
        ('Reparar Office', 'office', 'Executa reparo rápido do Microsoft Office', 'bi bi-file-earmark', True),
        ('Corrigir Outlook', 'office', 'Repara problemas comuns do Outlook', 'bi bi-envelope', False),
        ('Limpar Credenciais', 'office', 'Limpa credenciais salvas do Office', 'bi bi-key', False),
        ('Reativar Office', 'office', 'Reativa a licença do Microsoft Office', 'bi bi-lock', True),
        # Navegadores
        ('Limpar Cache Navegador', 'navegadores', 'Limpa o cache dos navegadores', 'bi bi-globe', False),
        ('Limpar Cookies', 'navegadores', 'Remove cookies dos navegadores', 'bi bi-cookie', False),
        ('Restaurar Navegador', 'navegadores', 'Restaura configurações do navegador', 'bi bi-arrow-counterclockwise', False),
        # Utilidades
        ('Reiniciar Explorer', 'utilidades', 'Reinicia o Windows Explorer', 'bi bi-folder2-open', False),
        ('Reiniciar Computador', 'utilidades', 'Reinicia o computador', 'bi bi-arrow-clockwise', False),
        ('Abrir CMD', 'utilidades', 'Abre o prompt de comando como administrador', 'bi bi-terminal', True),
        ('Abrir PowerShell', 'utilidades', 'Abre o PowerShell', 'bi bi-terminal-plus', False),
        ('Abrir Painel de Controle', 'utilidades', 'Abre o painel de controle do Windows', 'bi bi-sliders', False),
    ]
    
    for name, category, description, icon, needs_admin in solucoes:
        sol = QuickSolution(
            name=name,
            category=category,
            description=description,
            icon=icon,
            needs_admin=needs_admin,
            is_active=True,
            created_at=now_sp()
        )
        db.session.add(sol)
    
    db.session.commit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
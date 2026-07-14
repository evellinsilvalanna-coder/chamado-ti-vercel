// Chamado TI - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initSidebar();
    initDarkMode();
    initNotifications();
    initTooltips();
    initFileUpload();
    initChamadoForm();
    animateCards();
});

// ========== SIDEBAR ==========
function initSidebar() {
    const toggleBtn = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const main = document.getElementById('mainContent');

    if (!toggleBtn || !sidebar || !main) return;

    // Estado salvo
    const collapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (collapsed) {
        sidebar.classList.add('collapsed');
        main.classList.add('expanded');
    }

    toggleBtn.addEventListener('click', function() {
        if (window.innerWidth <= 768) {
            sidebar.classList.toggle('mobile-open');
        } else {
            sidebar.classList.toggle('collapsed');
            main.classList.toggle('expanded');
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
        }
    });

    // Fechar sidebar mobile ao clicar fora
    document.addEventListener('click', function(e) {
        if (window.innerWidth <= 768) {
            if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target)) {
                sidebar.classList.remove('mobile-open');
            }
        }
    });
}

// ========== DARK MODE ==========
function initDarkMode() {
    const darkToggle = document.getElementById('darkModeToggle');
    if (!darkToggle) return;

    // Estado salvo
    const isDark = localStorage.getItem('theme') === 'dark';
    if (isDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
        const icon = darkToggle.querySelector('i');
        if (icon) {
            icon.className = 'bi bi-sun-fill';
        }
    }

    darkToggle.addEventListener('click', function() {
        const html = document.documentElement;
        const current = html.getAttribute('data-theme');
        const newTheme = current === 'dark' ? 'light' : 'dark';
        
        html.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        const icon = this.querySelector('i');
        if (icon) {
            icon.className = newTheme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
        }
    });
}

// ========== NOTIFICATIONS ==========
function initNotifications() {
    const notifBtn = document.getElementById('notificationBtn');
    const notifDropdown = document.getElementById('notificationDropdown');

    if (!notifBtn || !notifDropdown) return;

    notifBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        notifDropdown.classList.toggle('show');
    });

    document.addEventListener('click', function(e) {
        if (!notifDropdown.contains(e.target) && !notifBtn.contains(e.target)) {
            notifDropdown.classList.remove('show');
        }
    });
}

function loadNotifications() {
    fetch('/api/notifications')
        .then(res => res.json())
        .then(data => {
            const badge = document.getElementById('notifBadge');
            const list = document.getElementById('notifList');
            
            if (badge) {
                if (data.count > 0) {
                    badge.textContent = data.count;
                    badge.style.display = 'flex';
                } else {
                    badge.style.display = 'none';
                }
            }
            
            if (list) {
                list.innerHTML = data.html;
            }
        })
        .catch(() => {});
}

function markNotifRead(id) {
    fetch('/api/notifications/' + id + '/read', { method: 'POST' })
        .then(() => loadNotifications());
}

// ========== TOOLTIPS ==========
function initTooltips() {
    const tooltipTriggers = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    if (tooltipTriggers.length && typeof bootstrap !== 'undefined') {
        tooltipTriggers.forEach(el => new bootstrap.Tooltip(el));
    }
}

// ========== FILE UPLOAD ==========
function initFileUpload() {
    const fileInputs = document.querySelectorAll('.file-upload-input');
    
    fileInputs.forEach(input => {
        const area = input.closest('.file-upload-area');
        const preview = document.getElementById('filePreview');
        
        if (!area) return;
        
        area.addEventListener('click', () => input.click());
        area.addEventListener('dragover', (e) => {
            e.preventDefault();
            area.style.borderColor = '#2563eb';
            area.style.background = 'rgba(37,99,235,0.08)';
        });
        area.addEventListener('dragleave', () => {
            area.style.borderColor = '';
            area.style.background = '';
        });
        area.addEventListener('drop', (e) => {
            e.preventDefault();
            area.style.borderColor = '';
            area.style.background = '';
            if (e.dataTransfer.files.length) {
                input.files = e.dataTransfer.files;
                updateFilePreview(input, preview);
            }
        });
        
        input.addEventListener('change', function() {
            updateFilePreview(this, preview);
        });
    });
}

function updateFilePreview(input, preview) {
    if (!preview || !input.files.length) return;
    
    const files = Array.from(input.files);
    preview.innerHTML = files.map(f => {
        const size = (f.size / 1024).toFixed(1);
        const icon = getFileIcon(f.name);
        return `<div class="d-inline-flex align-items-center gap-2 p-2 m-1 border rounded">
            <i class="bi ${icon}"></i>
            <small>${f.name} (${size}KB)</small>
        </div>`;
    }).join('');
}

function getFileIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        pdf: 'bi-filetype-pdf text-danger',
        doc: 'bi-filetype-doc text-primary',
        docx: 'bi-filetype-docx text-primary',
        xls: 'bi-filetype-xls text-success',
        xlsx: 'bi-filetype-xlsx text-success',
        png: 'bi-filetype-png',
        jpg: 'bi-filetype-jpg',
        jpeg: 'bi-filetype-jpg',
        gif: 'bi-filetype-gif',
        zip: 'bi-filetype-zip',
        rar: 'bi-filetype-zip',
        bat: 'bi-filetype-bat text-warning',
        cmd: 'bi-terminal',
        ps1: 'bi-terminal-fill',
        exe: 'bi-gear'
    };
    return icons[ext] || 'bi-paperclip';
}

// ========== CHAMADO FORM ==========
function initChamadoForm() {
    const form = document.getElementById('chamadoForm');
    if (!form) return;
    
    form.addEventListener('submit', function(e) {
        const btn = this.querySelector('button[type="submit"]');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Salvando...';
        }
    });
}

// ========== ANIMATIONS ==========
function animateCards() {
    const cards = document.querySelectorAll('.stat-card, .card.shadow-sm');
    cards.forEach((card, i) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        setTimeout(() => {
            card.style.transition = 'all 0.4s ease-out';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, i * 80);
    });
}

// ========== QUICK SOLUTION EXECUTION ==========
function executeSolution(solutionId, solutionName) {
    const overlay = document.getElementById('confirmOverlay');
    const confirmMsg = document.getElementById('confirmMessage');
    const confirmBtn = document.getElementById('confirmBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    
    if (!overlay || !confirmMsg) return;
    
    confirmMsg.innerHTML = `
        <div class="text-center mb-3">
            <i class="bi bi-shield-check text-warning" style="font-size: 48px;"></i>
            <h5 class="mt-2">Executar: ${solutionName}</h5>
            <p class="text-muted small">Esta ação executará um script no seu computador. Deseja continuar?</p>
        </div>
    `;
    
    overlay.classList.add('show');
    
    confirmBtn.onclick = function() {
        overlay.classList.remove('show');
        showSolutionProgress(solutionName);
        
        fetch('/api/solutions/' + solutionId + '/execute', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                updateSolutionProgress(data);
            })
            .catch(err => {
                updateSolutionProgress({ success: false, message: 'Erro ao executar solução: ' + err });
            });
    };
    
    cancelBtn.onclick = function() {
        overlay.classList.remove('show');
    };
    
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) overlay.classList.remove('show');
    });
}

function showSolutionProgress(name) {
    const container = document.getElementById('solutionProgress');
    if (!container) return;
    
    container.innerHTML = `
        <div class="card mt-3">
            <div class="card-body">
                <h6><i class="bi bi-gear spinning me-2"></i>Executando: ${name}</h6>
                <div class="progress progress-thin mt-2">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                         style="width: 100%; background: linear-gradient(90deg, #2563eb, #3b82f6);"></div>
                </div>
                <p class="text-muted small mt-2" id="progressStatus">Iniciando execução...</p>
            </div>
        </div>
    `;
    
    container.scrollIntoView({ behavior: 'smooth' });
}

function updateSolutionProgress(data) {
    const status = document.getElementById('progressStatus');
    const progress = document.querySelector('#solutionProgress .progress-bar');
    
    if (data.success) {
        if (progress) {
            progress.className = 'progress-bar bg-success';
            progress.style.width = '100%';
        }
        if (status) {
            status.innerHTML = `<i class="bi bi-check-circle-fill text-success me-1"></i> ${data.message || 'Executado com sucesso!'}`;
            status.className = 'text-success small mt-2';
        }
    } else {
        if (progress) {
            progress.className = 'progress-bar bg-danger';
            progress.style.width = '100%';
        }
        if (status) {
            status.innerHTML = `<i class="bi bi-x-circle-fill text-danger me-1"></i> ${data.message || 'Erro na execução'}`;
            status.className = 'text-danger small mt-2';
        }
    }
}

// ========== SEARCH ==========
function globalSearch() {
    const q = document.getElementById('globalSearchInput')?.value;
    if (q && q.trim()) {
        window.location.href = '/chamados?q=' + encodeURIComponent(q.trim());
    }
}

document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.key === '/') {
        e.preventDefault();
        const input = document.getElementById('globalSearchInput');
        if (input) input.focus();
    }
});

// ========== CHART COLOR HELPERS ==========
const chartColors = [
    '#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#06b6d4', '#f43f5e', '#14b8a6', '#f97316', '#6366f1'
];

// ========== ESTRELAS AVALIAÇÃO ==========
function setRating(stars) {
    const starInput = document.getElementById('ratingValue');
    const starElements = document.querySelectorAll('.star-rating i');
    
    if (starInput) starInput.value = stars;
    
    starElements.forEach((star, i) => {
        if (i < stars) {
            star.className = 'bi bi-star-fill active';
        } else {
            star.className = 'bi bi-star';
        }
    });
}

// ========== MASKS ==========
function maskPhone(input) {
    let value = input.value.replace(/\D/g, '');
    if (value.length > 11) value = value.slice(0, 11);
    
    if (value.length > 6) {
        value = `(${value.slice(0,2)}) ${value.slice(2,7)}-${value.slice(7)}`;
    } else if (value.length > 2) {
        value = `(${value.slice(0,2)}) ${value.slice(2)}`;
    } else if (value.length > 0) {
        value = `(${value}`;
    }
    
    input.value = value;
}

function maskDocument(input) {
    let value = input.value.replace(/\D/g, '');
    if (value.length > 11) value = value.slice(0, 11);
    
    if (value.length > 9) {
        value = `${value.slice(0,3)}.${value.slice(3,6)}.${value.slice(6,9)}-${value.slice(9)}`;
    } else if (value.length > 6) {
        value = `${value.slice(0,3)}.${value.slice(3,6)}.${value.slice(6)}`;
    } else if (value.length > 3) {
        value = `${value.slice(0,3)}.${value.slice(3)}`;
    }
    
    input.value = value;
}

// ========== INIT ==========
console.log('Chamado TI - Sistema de Service Desk carregado');
console.log('© 2026 - Todos os direitos reservados');
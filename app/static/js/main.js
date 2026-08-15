// ============================================================
// Script principal — Ferretería Adrialga, C.A.
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');

    // Crear overlay dinámicamente si no existe
    let overlay = document.querySelector('.sidebar-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);
    }

    function openSidebar() {
        if (sidebar) sidebar.classList.add('open');
        overlay.classList.add('active');
        document.body.classList.add('sidebar-open');
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove('open');
        overlay.classList.remove('active');
        document.body.classList.remove('sidebar-open');
    }

    function toggleSidebar() {
        if (sidebar && sidebar.classList.contains('open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    }

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', toggleSidebar);
    }

    // Cerrar sidebar al hacer clic en el overlay
    overlay.addEventListener('click', closeSidebar);

    // Cerrar sidebar con tecla Escape
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && sidebar && sidebar.classList.contains('open')) {
            closeSidebar();
        }
    });

    // Cerrar sidebar al hacer clic fuera (en móvil)
    document.addEventListener('click', function (event) {
        if (window.innerWidth <= 768 && sidebar && document.body.classList.contains('sidebar-open')) {
            if (!sidebar.contains(event.target) && !event.target.closest('#sidebarToggle')) {
                closeSidebar();
            }
        } else if (window.innerWidth <= 768 && sidebar && !document.body.classList.contains('sidebar-open')) {
            if (!sidebar.contains(event.target) && !event.target.closest('#sidebarToggle')) {
                openSidebar();
            }
        }
    });

    // Cerrar sidebar al navegar (clic en un enlace del sidebar en móvil)
    if (sidebar) {
        sidebar.querySelectorAll('.nav-link').forEach(function (link) {
            link.addEventListener('click', function () {
                if (window.innerWidth <= 768) {
                    closeSidebar();
                }
            });
        });
    }

    // Tooltips de Bootstrap
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    if (tooltipTriggerList.length > 0 && typeof bootstrap !== 'undefined') {
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
});

// Marcar el enlace del sidebar activo según la ruta actual
document.addEventListener('htmx:afterSwap', function () {
    const links = document.querySelectorAll('.sidebar .nav-link');
    links.forEach(function (link) {
        link.classList.remove('active');
        if (link.getAttribute('href') === window.location.pathname) {
            link.classList.add('active');
        }
    });
});
// ============================================================
// Script principal — Ferretería Adrialga, C.A.
// ============================================================

document.addEventListener('DOMContentLoaded', function () {
    // Toggle del sidebar en móvil
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', function () {
            sidebar.classList.toggle('open');
            document.body.classList.toggle('sidebar-open');
        });
    }

    // Cerrar sidebar al hacer clic fuera (en móvil)
    document.addEventListener('click', function (event) {
        if (window.innerWidth <= 991.98 && sidebar && document.body.classList.contains('sidebar-open')) {
            if (!sidebar.contains(event.target) && !event.target.closest('#sidebarToggle')) {
                sidebar.classList.remove('open');
                document.body.classList.remove('sidebar-open');
            }
        }
    });

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
/**
 * Natural Wood Theme Controller for PicoChess
 * Aplica automáticamente el tema de madera natural a la interfaz
 */

(function() {
    'use strict';
    
    // Configuración del tema
    const THEME_CONFIG = {
        name: 'natural-wood',
        displayName: 'Madera Natural',
        version: '1.0',
        author: 'PicoChess Enhanced'
    };
    
    // Función para aplicar el tema de madera natural
    function applyNaturalWoodTheme() {
        console.log('Aplicando tema de madera natural...');
        
        // Cambiar la clase del tablero
        const boardSection = document.getElementById('xboardsection');
        if (boardSection) {
            // Remover clases existentes de tema
            boardSection.classList.remove('blue', 'green', 'brown');
            // Aplicar el tema de madera natural
            boardSection.classList.add('natural-wood', 'merida');
            console.log('Tema de tablero aplicado: natural-wood');
        }
        
        // Aplicar estilos al body
        document.body.classList.add('natural-wood-theme');
        
        // Aplicar estilos a los controles
        const boardControl = document.getElementById('boardcontrol');
        if (boardControl) {
            boardControl.classList.add('natural-wood-controls');
        }
        
        // Aplicar estilos a las pestañas
        const tabContainer = document.querySelector('#pills-tab');
        if (tabContainer) {
            tabContainer.closest('.card').classList.add('natural-wood-tabs');
        }
        
        // Aplicar estilos a las cartas
        const cards = document.querySelectorAll('.card');
        cards.forEach(card => {
            card.classList.add('natural-wood-cards');
        });
        
        // Aplicar estilos al texto
        const textElements = document.querySelectorAll('h1, h2, h3, h4, h5, h6, p, span, label');
        textElements.forEach(element => {
            if (!element.closest('.btn')) { // No aplicar a botones
                element.classList.add('natural-wood-text');
            }
        });
        
        // Aplicar estilos a las tablas
        const tables = document.querySelectorAll('.table');
        tables.forEach(table => {
            table.closest('.card-body').classList.add('natural-wood-tables');
        });
        
        // Aplicar efectos especiales
        const specialElements = document.querySelectorAll('.card, .btn-group, #evaluation-bar-container');
        specialElements.forEach(element => {
            element.classList.add('natural-wood-glow');
        });
        
        // Animación de entrada
        const animatedElements = document.querySelectorAll('.card, .btn-group');
        animatedElements.forEach((element, index) => {
            setTimeout(() => {
                element.classList.add('natural-wood-animate');
            }, index * 100);
        });
        
        console.log('Tema de madera natural aplicado completamente');
    }
    
    // Función para personalizar colores específicos
    function customizeColors() {
        // Crear estilos dinámicos
        const style = document.createElement('style');
        style.textContent = `
            /* Personalización dinámica de colores */
            .natural-wood .cg-board square.selected {
                animation: golden-pulse 2s ease-in-out infinite alternate;
            }
            
            @keyframes golden-pulse {
                0% { box-shadow: inset 0 0 15px rgba(255, 215, 0, 0.4), 0 0 20px rgba(255, 215, 0, 0.6); }
                100% { box-shadow: inset 0 0 25px rgba(255, 215, 0, 0.6), 0 0 30px rgba(255, 215, 0, 0.8); }
            }
            
            /* Mejoras para dispositivos táctiles */
            @media (hover: none) and (pointer: coarse) {
                .natural-wood .cg-board piece {
                    filter: drop-shadow(2px 2px 4px rgba(0, 0, 0, 0.3));
                }
                
                .natural-wood-controls .btn {
                    padding: 0.75rem 1rem;
                    font-size: 1rem;
                }
            }
            
            /* Modo de alto contraste */
            @media (prefers-contrast: high) {
                .natural-wood .cg-board square.light {
                    background: #F5F5DC;
                }
                
                .natural-wood .cg-board square.dark {
                    background: #654321;
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    // Función para manejar cambios de tema dinámicos
    function setupThemeToggle() {
        // Crear botón de toggle si no existe
        const existingToggle = document.getElementById('theme-toggle');
        if (!existingToggle) {
            const toggleButton = document.createElement('button');
            toggleButton.id = 'theme-toggle';
            toggleButton.className = 'btn btn-wood btn-sm';
            toggleButton.innerHTML = '<i class="fa fa-palette"></i> Tema Madera';
            toggleButton.style.position = 'fixed';
            toggleButton.style.top = '10px';
            toggleButton.style.right = '10px';
            toggleButton.style.zIndex = '9999';
            
            toggleButton.addEventListener('click', function() {
                const isActive = document.body.classList.contains('natural-wood-theme');
                if (isActive) {
                    removeNaturalWoodTheme();
                    this.innerHTML = '<i class="fa fa-palette"></i> Activar Madera';
                } else {
                    applyNaturalWoodTheme();
                    this.innerHTML = '<i class="fa fa-palette"></i> Tema Activo';
                }
            });
            
            document.body.appendChild(toggleButton);
        }
    }
    
    // Función para remover el tema
    function removeNaturalWoodTheme() {
        console.log('Removiendo tema de madera natural...');
        
        // Remover clases del tablero
        const boardSection = document.getElementById('xboardsection');
        if (boardSection) {
            boardSection.classList.remove('natural-wood');
            boardSection.classList.add('blue'); // Volver al tema por defecto
        }
        
        // Remover clases del body y otros elementos
        const elementsToClean = [
            document.body,
            document.getElementById('boardcontrol'),
            ...document.querySelectorAll('.card, .table, h1, h2, h3, h4, h5, h6, p, span, label')
        ];
        
        elementsToClean.forEach(element => {
            if (element) {
                element.classList.remove(
                    'natural-wood-theme',
                    'natural-wood-controls',
                    'natural-wood-tabs',
                    'natural-wood-cards',
                    'natural-wood-text',
                    'natural-wood-tables',
                    'natural-wood-glow',
                    'natural-wood-animate'
                );
            }
        });
        
        console.log('Tema de madera natural removido');
    }
    
    // Función para detectar preferencias del usuario
    function detectUserPreferences() {
        // Verificar si el usuario prefiere temas oscuros
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        
        // Verificar si el usuario prefiere movimiento reducido
        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        
        if (prefersReducedMotion) {
            // Desactivar animaciones si el usuario prefiere movimiento reducido
            const style = document.createElement('style');
            style.textContent = `
                .natural-wood-animate,
                .natural-wood .cg-board piece,
                .natural-wood .cg-board square.selected {
                    animation: none !important;
                    transition: none !important;
                }
            `;
            document.head.appendChild(style);
        }
        
        return { prefersDark, prefersReducedMotion };
    }
    
    // Función de inicialización
    function initializeNaturalWoodTheme() {
        console.log(`Inicializando ${THEME_CONFIG.displayName} v${THEME_CONFIG.version}`);
        
        // Detectar preferencias del usuario
        const preferences = detectUserPreferences();
        console.log('Preferencias del usuario:', preferences);
        
        // Aplicar el tema
        applyNaturalWoodTheme();
        
        // Personalizar colores
        customizeColors();
        
        // Configurar toggle de tema
        setupThemeToggle();
        
        // Manejar redimensionamiento de ventana
        window.addEventListener('resize', function() {
            // Reajustar elementos si es necesario
            const boardSection = document.getElementById('xboardsection');
            if (boardSection && window.chessground1) {
                setTimeout(() => {
                    window.chessground1.redrawAll();
                }, 100);
            }
        });
        
        // Manejar cambios de orientación en dispositivos móviles
        window.addEventListener('orientationchange', function() {
            setTimeout(() => {
                if (window.chessground1) {
                    window.chessground1.redrawAll();
                }
            }, 500);
        });
        
        console.log('Tema de madera natural inicializado correctamente');
    }
    
    // Exponer funciones globalmente para uso externo
    window.NaturalWoodTheme = {
        apply: applyNaturalWoodTheme,
        remove: removeNaturalWoodTheme,
        toggle: function() {
            const isActive = document.body.classList.contains('natural-wood-theme');
            if (isActive) {
                removeNaturalWoodTheme();
            } else {
                applyNaturalWoodTheme();
            }
            return !isActive;
        },
        config: THEME_CONFIG
    };
    
    // Auto-inicializar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeNaturalWoodTheme);
    } else {
        initializeNaturalWoodTheme();
    }
    
})();
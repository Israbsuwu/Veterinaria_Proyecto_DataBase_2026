/* ==========================================================================
   Panel de gestión — interacción, filtros y animaciones (anime.js v4)
   ========================================================================== */

(function () {
  'use strict';

  const $ = (selector, scope) => (scope || document).querySelector(selector);
  const $$ = (selector, scope) => Array.from((scope || document).querySelectorAll(selector));

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hasAnime = typeof window.anime !== 'undefined';

  const VISTAS = ['resumen', 'inventario', 'vencimientos', 'citas', 'proveedores', 'facturas', 'clientes', 'equipo'];

  /* ------------------------------------------------------------------------
     Utilidades
     ------------------------------------------------------------------------ */

  function animar(targets, params) {
    if (!hasAnime || reduceMotion || !targets) return null;
    try {
      return window.anime.animate(targets, params);
    } catch (error) {
      return null;
    }
  }

  function escalonar(valor) {
    if (!hasAnime) return 0;
    return window.anime.stagger(valor);
  }

  function dinero(valor) {
    const numero = Number(valor) || 0;
    return 'C$ ' + numero.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function entero(valor) {
    return (Number(valor) || 0).toLocaleString('en-US');
  }

  function escapar(texto) {
    return String(texto == null ? '' : texto)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function sinAcentos(texto) {
    return String(texto || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  function fechaHora(valor) {
    if (!valor) return '—';
    const partes = String(valor).match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (!partes) return String(valor);

    let hora = Number(partes[4]);
    const sufijo = hora >= 12 ? 'PM' : 'AM';
    hora = hora % 12 || 12;
    return `${partes[3]}/${partes[2]}/${partes[1]} · ${String(hora).padStart(2, '0')}:${partes[5]} ${sufijo}`;
  }

  let temporizadorToast = null;

  function mostrarToast(mensaje, tipo) {
    const toast = $('#toast');
    if (!toast) return;
    toast.textContent = mensaje;
    toast.classList.toggle('is-error', tipo === 'error');
    toast.hidden = false;

    if (hasAnime && !reduceMotion) {
      window.anime.animate(toast, {
        opacity: [0, 1],
        translateY: [12, 0],
        duration: 260,
        ease: 'outCubic',
      });
    }

    window.clearTimeout(temporizadorToast);
    temporizadorToast = window.setTimeout(() => {
      if (hasAnime && !reduceMotion) {
        window.anime.animate(toast, {
          opacity: [1, 0],
          translateY: [0, 10],
          duration: 220,
          ease: 'inCubic',
          onComplete: () => { toast.hidden = true; },
        });
      } else {
        toast.hidden = true;
      }
    }, 4200);
  }

  /* ------------------------------------------------------------------------
     Navegación entre vistas
     ------------------------------------------------------------------------ */

  const vistas = {};
  $$('.view[data-view]').forEach((seccion) => {
    vistas[seccion.dataset.view] = seccion;
  });

  const navItems = $$('.nav-item[data-view]');
  const crumb = $('#crumbVista');
  let vistaActual = null;

  function animarVista(seccion) {
    if (!hasAnime || reduceMotion) return;

    const head = $('.view-head', seccion);
    if (head) {
      window.anime.animate(head, {
        opacity: [0, 1],
        translateY: [14, 0],
        duration: 380,
        ease: 'outCubic',
      });
    }

    const bloques = $$('.kpi, .panel, .stat, .cat-card, .provider-card', seccion);
    if (bloques.length) {
      window.anime.animate(bloques, {
        opacity: [0, 1],
        translateY: [16, 0],
        duration: 420,
        delay: escalonar(28),
        ease: 'outCubic',
      });
    }
  }

  function activarVista(nombre, actualizarHash) {
    if (!vistas[nombre]) nombre = 'resumen';
    if (vistaActual === nombre) {
      if (actualizarHash && window.location.hash !== '#' + nombre) {
        window.history.replaceState(null, '', '#' + nombre);
      }
      return;
    }

    vistaActual = nombre;

    Object.keys(vistas).forEach((clave) => {
      const seccion = vistas[clave];
      const activa = clave === nombre;
      seccion.classList.toggle('active', activa);
      seccion.setAttribute('aria-hidden', activa ? 'false' : 'true');
    });

    navItems.forEach((item) => {
      item.classList.toggle('active', item.dataset.view === nombre);
    });

    const seccion = vistas[nombre];
    if (crumb) crumb.textContent = seccion.dataset.title || nombre;

    if (actualizarHash && window.location.hash !== '#' + nombre) {
      window.history.replaceState(null, '', '#' + nombre);
    }

    cerrarSidebar();
    animarVista(seccion);
    animarIndicadores(seccion);
    window.scrollTo({ top: 0, behavior: reduceMotion ? 'auto' : 'smooth' });
  }

  navItems.forEach((item) => {
    item.addEventListener('click', () => activarVista(item.dataset.view, true));
  });

  $$('[data-go]').forEach((boton) => {
    boton.addEventListener('click', () => activarVista(boton.dataset.go, true));
  });

  window.addEventListener('hashchange', () => {
    const nombre = window.location.hash.replace('#', '');
    if (VISTAS.indexOf(nombre) !== -1) activarVista(nombre, false);
  });

  /* ------------------------------------------------------------------------
     Indicadores animados
     ------------------------------------------------------------------------ */

  function animarContador(elemento) {
    const objetivo = Number(elemento.dataset.count) || 0;
    const esDinero = elemento.dataset.money === '1';
    const formatear = (valor) => (esDinero ? dinero(valor) : entero(Math.round(valor)));

    if (!hasAnime || reduceMotion) {
      elemento.textContent = formatear(objetivo);
      return;
    }

    if (elemento.dataset.animado === '1') return;
    elemento.dataset.animado = '1';

    const proxy = { valor: 0 };
    window.anime.animate(proxy, {
      valor: objetivo,
      duration: 1100,
      ease: 'outExpo',
      onUpdate: () => { elemento.textContent = formatear(proxy.valor); },
      onComplete: () => { elemento.textContent = formatear(objetivo); },
    });
  }

  function animarBarras(scope) {
    $$('[data-pct]', scope || document).forEach((barra) => {
      const pct = Math.max(0, Math.min(100, Number(barra.dataset.pct) || 0));
      const esAltura = barra.classList.contains('sales-bar');
      const propiedad = esAltura ? 'height' : 'width';

      if (!hasAnime || reduceMotion) {
        barra.style[propiedad] = pct + '%';
        return;
      }

      if (barra.dataset.animado === '1') return;
      barra.dataset.animado = '1';

      barra.style[propiedad] = '0%';
      window.anime.animate(barra, {
        [propiedad]: [0, pct + '%'],
        duration: 900,
        delay: 120 + Math.random() * 180,
        ease: 'outCubic',
      });
    });
  }

  function animarIndicadores(scope) {
    $$('[data-count]', scope || document).forEach(animarContador);
    animarBarras(scope || document);
  }

  /* ------------------------------------------------------------------------
     Barra lateral móvil
     ------------------------------------------------------------------------ */

  const shell = $('#dashShell');

  function abrirSidebar() {
    if (shell) shell.classList.add('sidebar-open');
  }

  function cerrarSidebar() {
    if (shell) shell.classList.remove('sidebar-open');
  }

  const menuBtn = $('#menuBtn');
  if (menuBtn) {
    menuBtn.addEventListener('click', () => {
      if (shell && shell.classList.contains('sidebar-open')) cerrarSidebar();
      else abrirSidebar();
    });
  }

  const backdrop = $('#sidebarBackdrop');
  if (backdrop) backdrop.addEventListener('click', cerrarSidebar);

  /* ------------------------------------------------------------------------
     Modales
     ------------------------------------------------------------------------ */

  let modalAbierto = null;
  let focoAnterior = null;

  function abrirModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;

    focoAnterior = document.activeElement;
    modalAbierto = modal;
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('no-scroll');

    if (hasAnime && !reduceMotion) {
      const card = $('.modal-card', modal);
      if (card) {
        window.anime.animate(modal, { opacity: [0, 1], duration: 200, ease: 'outQuad' });
        window.anime.animate(card, {
          opacity: [0, 1],
          translateY: [18, 0],
          scale: [0.985, 1],
          duration: 320,
          ease: 'outCubic',
        });
      }
    }

    const enfocable = $('input:not([type="hidden"]), select, textarea, button', modal);
    if (enfocable) window.setTimeout(() => enfocable.focus(), 90);
  }

  function cerrarModal() {
    if (!modalAbierto) return;
    const modal = modalAbierto;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('no-scroll');
    modalAbierto = null;

    if (focoAnterior && typeof focoAnterior.focus === 'function') {
      focoAnterior.focus();
    }
  }

  $$('[data-open]').forEach((boton) => {
    boton.addEventListener('click', () => abrirModal(boton.dataset.open));
  });

  $$('[data-close]').forEach((boton) => {
    boton.addEventListener('click', cerrarModal);
  });

  $$('.modal-layer').forEach((capa) => {
    capa.addEventListener('mousedown', (evento) => {
      if (evento.target === capa) cerrarModal();
    });
  });

  /* ------------------------------------------------------------------------
     Filtros y búsquedas
     ------------------------------------------------------------------------ */

  function normalizar(valor) {
    return sinAcentos(valor);
  }

  function configurarFiltro(opciones) {
    const tabla = $(opciones.tabla);
    if (!tabla) return;

    const cuerpo = tabla.tBodies[0];
    if (!cuerpo) return;

    const filas = Array.from(cuerpo.rows);
    const buscador = opciones.buscar ? $(opciones.buscar) : null;
    const contador = opciones.contador ? $(opciones.contador) : null;
    const vacio = opciones.vacio ? $(opciones.vacio) : null;
    const chips = opciones.chips ? $$(opciones.chips + ' .chip') : [];

    const estado = { filtro: opciones.filtroInicial || 'todos', texto: '' };

    function coincideEstado(fila) {
      if (!opciones.estadoDe) return true;
      return opciones.estadoDe(fila, estado.filtro);
    }

    function aplicar() {
      let visibles = 0;

      filas.forEach((fila) => {
        const texto = normalizar(fila.dataset.buscar || fila.textContent);
        const coincideTexto = !estado.texto || texto.indexOf(estado.texto) !== -1;
        const visible = coincideTexto && coincideEstado(fila);
        fila.hidden = !visible;
        if (visible) visibles += 1;
      });

      if (contador) {
        contador.textContent = opciones.etiqueta
          ? opciones.etiqueta(visibles)
          : visibles + (visibles === 1 ? ' resultado' : ' resultados');
      }

      if (vacio) vacio.hidden = visibles !== 0;
    }

    if (buscador) {
      buscador.addEventListener('input', () => {
        estado.texto = normalizar(buscador.value.trim());
        aplicar();
      });
    }

    chips.forEach((chip) => {
      chip.addEventListener('click', () => {
        chips.forEach((otro) => otro.classList.remove('active'));
        chip.classList.add('active');
        estado.filtro = chip.dataset.filtro;
        aplicar();
      });
    });

    aplicar();
  }

  configurarFiltro({
    tabla: '#tablaInventario',
    buscar: '#buscarInventario',
    chips: '[data-filtro-inventario]',
    contador: '#contadorInventario',
    vacio: '#vacioInventario',
    filtroInicial: 'todos',
    etiqueta: (n) => n + (n === 1 ? ' producto' : ' productos'),
    estadoDe: (fila, filtro) => filtro === 'todos' || fila.dataset.estado === filtro,
  });

  configurarFiltro({
    tabla: '#tablaVencimientos',
    buscar: '#buscarVencimientos',
    chips: '[data-filtro-vencimientos]',
    contador: '#contadorVencimientos',
    vacio: '#vacioVencimientos',
    filtroInicial: 'todos',
    etiqueta: (n) => n + (n === 1 ? ' lote' : ' lotes'),
    estadoDe: (fila, filtro) => {
      if (filtro === 'todos') return true;
      const dias = Number(fila.dataset.dias);
      if (filtro === 'vencido') return dias < 0;
      if (filtro === '30') return dias >= 0 && dias <= 30;
      if (filtro === '90') return dias > 30 && dias <= 90;
      if (filtro === '180') return dias > 90 && dias <= 180;
      if (filtro === '365') return dias > 180 && dias <= 365;
      if (filtro === 'lejano') return dias > 365;
      return true;
    },
  });

  configurarFiltro({
    tabla: '#tablaCitas',
    buscar: '#buscarCitas',
    chips: '[data-filtro-citas]',
    contador: '#contadorCitas',
    vacio: '#vacioCitas',
    filtroInicial: 'PROGRAMADA',
    etiqueta: (n) => n + (n === 1 ? ' cita' : ' citas'),
    estadoDe: (fila, filtro) => filtro === 'TODAS' || fila.dataset.estado === filtro,
  });

  configurarFiltro({
    tabla: '#tablaFacturas',
    buscar: '#buscarFacturas',
    chips: '[data-filtro-facturas]',
    contador: '#contadorFacturas',
    vacio: '#vacioFacturas',
    filtroInicial: 'TODAS',
    etiqueta: (n) => n + (n === 1 ? ' factura' : ' facturas'),
    estadoDe: (fila, filtro) => {
      if (filtro === 'TODAS') return true;
      const valor = fila.dataset.estado;
      if (filtro === 'PENDIENTE') return valor !== 'PAGADA' && valor !== 'ANULADA';
      return valor === filtro;
    },
  });

  configurarFiltro({
    tabla: '#tablaClientes',
    buscar: '#buscarClientes',
    contador: '#contadorClientes',
    vacio: '#vacioClientes',
    etiqueta: (n) => n + (n === 1 ? ' cliente' : ' clientes'),
  });

  configurarFiltro({
    tabla: '#tablaEquipo',
    buscar: '#buscarEquipo',
    contador: '#contadorEquipo',
    vacio: '#vacioEquipo',
    etiqueta: (n) => n + (n === 1 ? ' cuenta' : ' cuentas'),
  });

  /* Proveedores: tarjetas, no tabla */
  const grillaProveedores = $('#grillaProveedores');
  const buscarProveedores = $('#buscarProveedores');
  if (grillaProveedores && buscarProveedores) {
    const tarjetas = $$('.provider-card', grillaProveedores);
    const contador = $('#contadorProveedores');
    const vacio = $('#vacioProveedores');

    buscarProveedores.addEventListener('input', () => {
      const texto = normalizar(buscarProveedores.value.trim());
      let visibles = 0;
      tarjetas.forEach((tarjeta) => {
        const coincide = !texto || normalizar(tarjeta.dataset.buscar).indexOf(texto) !== -1;
        tarjeta.hidden = !coincide;
        if (coincide) visibles += 1;
      });
      if (contador) contador.textContent = visibles + (visibles === 1 ? ' proveedor' : ' proveedores');
      if (vacio) vacio.hidden = visibles !== 0;
    });
  }

  /* ------------------------------------------------------------------------
     Movimiento de stock
     ------------------------------------------------------------------------ */

  $$('[data-movimiento]').forEach((boton) => {
    boton.addEventListener('click', () => {
      const idLote = $('#movLoteId');
      const codigo = $('#movLoteCodigo');
      const producto = $('#movProducto');
      const stock = $('#movStock');

      if (idLote) idLote.value = boton.dataset.lote || '';
      if (codigo) codigo.textContent = boton.dataset.codigo || '—';
      if (producto) producto.textContent = boton.dataset.producto || '—';
      if (stock) stock.textContent = boton.dataset.stock || '0';

      const cantidad = $('input[name="cantidad"]', $('#modalMovimiento'));
      if (cantidad) cantidad.value = '1';

      abrirModal('modalMovimiento');
    });
  });

  /* ------------------------------------------------------------------------
     Citas: cambiar estado
     ------------------------------------------------------------------------ */

  const etiquetaEstado = { PROGRAMADA: 'Programada', ATENDIDA: 'Atendida', CANCELADA: 'Cancelada' };
  const claseEstado = { PROGRAMADA: 'warn', ATENDIDA: 'ok', CANCELADA: 'danger' };

  function refrescarStatsCitas(anterior, nuevo) {
    const programadas = $('#statCitasProgramadas');
    const atendidas = $('#statCitasAtendidas');
    const canceladas = $('#statCitasCanceladas');

    const ajustar = (elemento, delta) => {
      if (!elemento) return;
      const valor = Math.max(0, (parseInt(elemento.textContent, 10) || 0) + delta);
      elemento.textContent = valor;
      if (hasAnime && !reduceMotion) {
        window.anime.animate(elemento, {
          scale: [1.16, 1],
          duration: 330,
          ease: 'outBack',
        });
      }
    };

    if (anterior === 'PROGRAMADA') ajustar(programadas, -1);
    if (anterior === 'ATENDIDA') ajustar(atendidas, -1);
    if (anterior === 'CANCELADA') ajustar(canceladas, -1);
    if (nuevo === 'PROGRAMADA') ajustar(programadas, 1);
    if (nuevo === 'ATENDIDA') ajustar(atendidas, 1);
    if (nuevo === 'CANCELADA') ajustar(canceladas, 1);
  }

  function actualizarContadorCitas() {
    const contador = $('#contadorCitas');
    if (!contador) return;
    const visibles = $$('#tablaCitas tbody tr').filter((fila) => !fila.hidden).length;
    contador.textContent = visibles + (visibles === 1 ? ' cita' : ' citas');
    const vacio = $('#vacioCitas');
    if (vacio) vacio.hidden = visibles !== 0;
  }

  $$('[data-cita-estado]').forEach((boton) => {
    boton.addEventListener('click', async () => {
      const fila = boton.closest('tr');
      if (!fila || boton.disabled) return;

      const anterior = fila.dataset.estado;
      const nuevo = boton.dataset.estado;
      const acciones = $$('[data-cita-estado]', fila);
      acciones.forEach((b) => { b.disabled = true; });

      try {
        const respuesta = await fetch(boton.dataset.url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ estado: nuevo }),
        });
        const datos = await respuesta.json().catch(() => ({}));

        if (!respuesta.ok || datos.error) {
          throw new Error(datos.error || 'No se pudo actualizar la cita.');
        }

        fila.dataset.estado = nuevo;

        const pill = $('.pill', fila);
        if (pill) {
          pill.className = 'pill pill--' + (claseEstado[nuevo] || 'info');
          pill.textContent = etiquetaEstado[nuevo] || nuevo;
        }

        const celdaAcciones = boton.closest('td');
        if (celdaAcciones) {
          celdaAcciones.innerHTML = '<span class="muted">—</span>';
        }

        refrescarStatsCitas(anterior, nuevo);
        mostrarToast('Cita #' + fila.dataset.id + ' marcada como ' + (etiquetaEstado[nuevo] || nuevo) + '.', 'success');

        const filtroActivo = $('[data-filtro-citas] .chip.active');
        if (filtroActivo && filtroActivo.dataset.filtro !== 'TODAS' && filtroActivo.dataset.filtro !== nuevo) {
          const ocultar = () => {
            fila.hidden = true;
            actualizarContadorCitas();
          };
          if (hasAnime && !reduceMotion) {
            window.anime.animate(fila, {
              opacity: [1, 0],
              translateX: [0, 18],
              duration: 240,
              ease: 'inCubic',
              onComplete: ocultar,
            });
          } else {
            ocultar();
          }
        }
      } catch (error) {
        acciones.forEach((b) => { b.disabled = false; });
        mostrarToast(error.message || 'No se pudo actualizar la cita.', 'error');
      }
    });
  });

  /* ------------------------------------------------------------------------
     Detalle de factura
     ------------------------------------------------------------------------ */

  function pintarFactura(factura) {
    const lineas = (factura.lineas || []).map((linea) => `
      <tr>
        <td>${escapar(linea.concepto)}<br><small class="muted">${escapar(linea.tipo)}</small></td>
        <td class="num">${entero(linea.cantidad)}</td>
        <td class="num">${dinero(linea.precio)}</td>
        <td class="num">${dinero(linea.subtotal)}</td>
      </tr>
    `).join('');

    const pagos = (factura.pagos || []).map((pago) => `
      <li>
        <span class="mono">${escapar(fechaHora(pago.fecha))}</span>
        <span>${escapar(pago.metodo)}${pago.referencia ? ' · ' + escapar(pago.referencia) : ''}</span>
        <span class="mono">${dinero(pago.monto)}</span>
      </li>
    `).join('');

    const cliente = factura.cliente || {};

    return `
      <div class="invoice-head">
        <div>
          <p class="invoice-number">${escapar(factura.numero)}</p>
          <div class="invoice-meta">
            <span>${escapar(fechaHora(factura.fecha))}</span>
            <span>Vendedor: ${escapar(factura.vendedor)}</span>
          </div>
        </div>
        <span class="pill pill--${factura.estado === 'PAGADA' ? 'ok' : factura.estado === 'ANULADA' ? 'danger' : 'warn'}">${escapar(factura.estado)}</span>
      </div>

      <div class="invoice-client">
        <span><strong>Cliente:</strong> ${escapar(cliente.nombre)}</span>
        <span><strong>Cédula:</strong> ${escapar(cliente.cedula || '—')}</span>
        <span><strong>Correo:</strong> ${escapar(cliente.correo || '—')}</span>
        <span><strong>Teléfono:</strong> ${escapar(cliente.telefono || '—')}</span>
        <span style="grid-column: 1 / -1;"><strong>Dirección:</strong> ${escapar(cliente.direccion || '—')}</span>
      </div>

      <table class="invoice-table">
        <thead>
          <tr><th>Concepto</th><th class="num">Cant.</th><th class="num">Precio</th><th class="num">Subtotal</th></tr>
        </thead>
        <tbody>${lineas || '<tr><td colspan="4" class="muted">Sin líneas registradas.</td></tr>'}</tbody>
      </table>

      <div class="invoice-totals">
        <div><span>Total facturado</span><strong>${dinero(factura.total)}</strong></div>
        <div><span>Pagado</span><strong>${dinero(factura.pagado)}</strong></div>
        <div class="grand"><span>Saldo</span><strong>${dinero(factura.saldo)}</strong></div>
      </div>

      <div class="payment-list">
        <h4>Pagos recibidos</h4>
        ${pagos ? '<ul>' + pagos + '</ul>' : '<p class="muted" style="font-size:0.7rem;">Sin pagos registrados.</p>'}
      </div>
    `;
  }

  $$('[data-factura]').forEach((boton) => {
    boton.addEventListener('click', async () => {
      const cuerpo = $('#facturaCuerpo');
      if (!cuerpo) return;

      cuerpo.innerHTML = '<p class="invoice-loading">Cargando el detalle de la factura…</p>';
      abrirModal('modalFactura');

      try {
        const respuesta = await fetch(boton.dataset.url, { headers: { Accept: 'application/json' } });
        const datos = await respuesta.json().catch(() => ({}));

        if (!respuesta.ok || datos.error) {
          throw new Error(datos.error || 'No se pudo cargar la factura.');
        }

        cuerpo.innerHTML = pintarFactura(datos);

        if (hasAnime && !reduceMotion) {
          window.anime.animate($$('tr, .invoice-client, .invoice-totals, .payment-list', cuerpo), {
            opacity: [0, 1],
            translateY: [8, 0],
            duration: 300,
            delay: escalonar(26),
            ease: 'outCubic',
          });
        }
      } catch (error) {
        cuerpo.innerHTML = '<p class="empty-state">' + escapar(error.message || 'No se pudo cargar la factura.') + '</p>';
      }
    });
  });

  /* ------------------------------------------------------------------------
     Avisos y teclado
     ------------------------------------------------------------------------ */

  $$('[data-dismiss-flash]').forEach((boton) => {
    boton.addEventListener('click', () => {
      const aviso = boton.closest('.flash');
      if (!aviso) return;
      if (hasAnime && !reduceMotion) {
        window.anime.animate(aviso, {
          opacity: [1, 0],
          translateX: [0, 14],
          duration: 200,
          ease: 'inQuad',
          onComplete: () => { aviso.remove(); },
        });
      } else {
        aviso.remove();
      }
    });
  });

  document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape') {
      if (modalAbierto) {
        cerrarModal();
      } else {
        cerrarSidebar();
      }
    }

    if (evento.key === 'Tab' && modalAbierto) {
      const enfocables = $$('a[href], button:not([disabled]), input:not([type="hidden"]), select, textarea', modalAbierto)
        .filter((elemento) => elemento.offsetParent !== null);

      if (!enfocables.length) return;

      const primero = enfocables[0];
      const ultimo = enfocables[enfocables.length - 1];

      if (evento.shiftKey && document.activeElement === primero) {
        evento.preventDefault();
        ultimo.focus();
      } else if (!evento.shiftKey && document.activeElement === ultimo) {
        evento.preventDefault();
        primero.focus();
      }
    }
  });

  /* ------------------------------------------------------------------------
     Arranque
     ------------------------------------------------------------------------ */

  function iniciar() {
    const inicial = window.location.hash.replace('#', '');
    vistaActual = null;
    activarVista(VISTAS.indexOf(inicial) !== -1 ? inicial : 'resumen', false);

    animarIndicadores(document);

    if (hasAnime && !reduceMotion) {
      const cabecera = $('.topbar');
      if (cabecera) {
        window.anime.animate(cabecera, {
          opacity: [0, 1],
          translateY: [-10, 0],
          duration: 380,
          ease: 'outCubic',
        });
      }

      const nav = $$('.nav-item');
      if (nav.length) {
        window.anime.animate(nav, {
          opacity: [0, 1],
          translateX: [-12, 0],
          duration: 360,
          delay: escalonar(32),
          ease: 'outCubic',
        });
      }
    }

    if (window.location.hash) {
      const destino = document.getElementById(window.location.hash.replace('#', ''));
      if (destino && !destino.classList.contains('view')) {
        window.setTimeout(() => destino.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' }), 220);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
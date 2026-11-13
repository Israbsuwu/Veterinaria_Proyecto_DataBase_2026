/* ==========================================================================
   Tienda y portal clínico — Pepe & Pepito
   El cliente ve la tienda; el personal ve además el portal clínico.
   ========================================================================== */

(function () {
  'use strict';

  /* ------------------------------------------------------------------------
     Datos inyectados por Flask
     ------------------------------------------------------------------------ */

  const serverData = document.getElementById('server-data');
  let propietarios = [];
  let mascotas = [];

  if (serverData) {
    try {
      propietarios = JSON.parse(serverData.dataset.clientes || '[]');
    } catch (error) {
      propietarios = [];
    }
    try {
      mascotas = JSON.parse(serverData.dataset.mascotas || '[]');
    } catch (error) {
      mascotas = [];
    }
  }

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hasAnime = typeof window.anime !== 'undefined';

  function animar(targets, params) {
    if (!hasAnime || reduceMotion || !targets) return null;
    try {
      return window.anime.animate(targets, params);
    } catch (error) {
      return null;
    }
  }

  function escapar(texto) {
    return String(texto == null ? '' : texto)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function dinero(valor) {
    const numero = Number(valor) || 0;
    return 'C$' + numero.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  /* ------------------------------------------------------------------------
     Aviso flotante
     ------------------------------------------------------------------------ */

  let temporizadorAviso = null;

  function avisar(mensaje, tipo) {
    let aviso = document.getElementById('avisoTienda');
    if (!aviso) {
      aviso = document.createElement('div');
      aviso.id = 'avisoTienda';
      aviso.setAttribute('role', 'status');
      aviso.setAttribute('aria-live', 'polite');
      aviso.style.cssText = [
        'position:fixed', 'right:1rem', 'bottom:1rem', 'z-index:220',
        'max-width:min(360px, calc(100vw - 2rem))',
        'padding:0.75rem 0.95rem', 'border-radius:9px',
        'font-family:Open Sans, sans-serif', 'font-size:0.82rem',
        'line-height:1.45', 'box-shadow:0 18px 40px -18px rgba(20,32,8,0.55)',
        'border:1px solid #c7dba6', 'background:#f1f7e6', 'color:#3f641f',
        'transition:opacity 0.2s ease, transform 0.2s ease',
      ].join(';');
      document.body.appendChild(aviso);
    }

    aviso.textContent = mensaje;
    if (tipo === 'error') {
      aviso.style.borderColor = '#e8bdb1';
      aviso.style.background = '#fbeae5';
      aviso.style.color = '#8c3525';
    } else {
      aviso.style.borderColor = '#c7dba6';
      aviso.style.background = '#f1f7e6';
      aviso.style.color = '#3f641f';
    }

    aviso.style.opacity = '1';
    aviso.style.transform = 'translateY(0)';

    if (hasAnime && !reduceMotion) {
      window.anime.animate(aviso, {
        opacity: [0, 1],
        translateY: [12, 0],
        duration: 240,
        ease: 'outCubic',
      });
    }

    window.clearTimeout(temporizadorAviso);
    temporizadorAviso = window.setTimeout(() => {
      aviso.style.opacity = '0';
      aviso.style.transform = 'translateY(10px)';
    }, 3600);
  }

  /* ------------------------------------------------------------------------
     Portal clínico (solo personal)
     ------------------------------------------------------------------------ */

  window.togglePortalClinico = function () {
    const portal = document.getElementById('portalClinicoWrap');
    if (!portal) {
      avisar('El portal clínico está disponible para el personal de la veterinaria.', 'error');
      return;
    }

    const oculto = portal.style.display === 'none' || portal.style.display === '';
    portal.style.display = oculto ? 'block' : 'none';

    if (oculto) {
      portal.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
      if (hasAnime && !reduceMotion) {
        const bloques = portal.querySelectorAll('.portal-tab-btn, .portal-view-panel.active, form');
        if (bloques.length) {
          window.anime.animate(bloques, {
            opacity: [0, 1],
            translateY: [12, 0],
            duration: 380,
            delay: window.anime.stagger(35),
            ease: 'outCubic',
          });
        }
      }
    }
  };

  window.cambiarPortalTab = function (panelId, btnElement) {
    document.querySelectorAll('.portal-tab-btn').forEach((btn) => btn.classList.remove('active'));
    if (btnElement) btnElement.classList.add('active');

    document.querySelectorAll('.portal-view-panel').forEach((panel) => panel.classList.remove('active'));
    const panel = document.getElementById('pview-' + panelId);
    if (panel) {
      panel.classList.add('active');
      animar(panel, {
        opacity: [0, 1],
        translateY: [10, 0],
        duration: 320,
        ease: 'outCubic',
      });
    }
  };

  window.abrirPortalEnTab = function (tabName) {
    const portal = document.getElementById('portalClinicoWrap');
    if (!portal) {
      const productos = document.querySelector('.products-grid');
      if (productos) productos.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
      avisar('El portal clínico está disponible para el personal de la veterinaria.', 'error');
      return;
    }

    portal.style.display = 'block';
    portal.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });

    const tabBtns = document.querySelectorAll('.portal-tab-btn');
    if (tabName === 'pacientes') {
      if (tabBtns[0]) cambiarPortalTab('registro', tabBtns[0]);
    } else if (tabBtns[1]) {
      cambiarPortalTab('expediente', tabBtns[1]);
    }
  };

  /* ------------------------------------------------------------------------
     Desplegables y expediente clínico
     ------------------------------------------------------------------------ */

  function actualizarSelectores() {
    const selDueno = document.getElementById('selectDuenoAsignado');
    const selExpediente = document.getElementById('selectExpediente');
    const selPacienteConsulta = document.getElementById('selectPacienteConsulta');

    if (!selDueno || !selExpediente || !selPacienteConsulta) return;

    selDueno.innerHTML = '';
    propietarios.forEach((p) => {
      selDueno.innerHTML += `<option value="${escapar(p.id)}">${escapar(p.nombre)} ${escapar(p.apellido)} (${escapar(p.cedula)})</option>`;
    });

    selExpediente.innerHTML = '';
    selPacienteConsulta.innerHTML = '';
    mascotas.forEach((m) => {
      const dueno = propietarios.find((p) => p.id === m.duenoId);
      const duenoTxt = dueno ? `${dueno.nombre} ${dueno.apellido}` : 'Sin dueño';
      const opt = `<option value="${escapar(m.id)}">${escapar(m.nombre)} (${escapar(m.especie)}) — Propietario: ${escapar(duenoTxt)}</option>`;
      selExpediente.innerHTML += opt;
      selPacienteConsulta.innerHTML += opt;
    });

    if (mascotas.length > 0) {
      selExpediente.value = mascotas[0].id;
      window.renderExpedienteSeleccionado(mascotas[0].id);
    }
  }

  window.renderExpedienteSeleccionado = function (mascotaId) {
    mascotaId = parseInt(mascotaId, 10);
    const mascota = mascotas.find((m) => m.id === mascotaId);
    if (!mascota) return;

    const nombreEl = document.getElementById('expNombreMascota');
    const detallesEl = document.getElementById('expDetallesMascota');
    const duenoEl = document.getElementById('expDuenoMascota');
    const badgeAlergia = document.getElementById('expAlergiaMascota');
    const timeline = document.getElementById('timelineConsultas');

    if (!nombreEl || !detallesEl || !duenoEl || !badgeAlergia) return;

    const dueno = propietarios.find((p) => p.id === mascota.duenoId);

    nombreEl.textContent = mascota.nombre;
    detallesEl.textContent = `${mascota.especie} • Raza: ${mascota.raza} • Sexo: ${mascota.sexo}`;

    if (dueno) {
      duenoEl.textContent = `Dueño: ${dueno.nombre} ${dueno.apellido} (Tel: ${dueno.tel})`;

      if (mascota.alergias && mascota.alergias.trim() !== '') {
        badgeAlergia.textContent = `⚠️ Alergia: ${mascota.alergias}`;
        badgeAlergia.style.backgroundColor = '#fee2e2';
        badgeAlergia.style.color = '#b91c1c';
        badgeAlergia.style.borderColor = '#f87171';
      } else {
        badgeAlergia.textContent = '✓ Sin alergias registradas';
        badgeAlergia.style.backgroundColor = '#dcfce7';
        badgeAlergia.style.color = '#15803d';
        badgeAlergia.style.borderColor = '#86efac';
      }
    }

    if (timeline) {
      timeline.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem 0;">(En la Fase 5 conectaremos las consultas y recetas desde la base de datos).</p>';
    }
  };

  /* ------------------------------------------------------------------------
     Formularios clínicos (solo existen para el personal)
     ------------------------------------------------------------------------ */

  const formPropietario = document.getElementById('formPropietario');
  if (formPropietario) {
    formPropietario.addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const data = {
        cedula: document.getElementById('propCedula').value.trim(),
        nombre: document.getElementById('propNombre').value.trim(),
        apellido: document.getElementById('propApellido').value.trim(),
        tel: document.getElementById('propTel').value.trim(),
      };

      try {
        const res = await fetch('/api/cliente', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        const result = await res.json();

        if (result.success) {
          data.id = result.id;
          propietarios.push(data);
          actualizarSelectores();
          avisar(`Propietario ${data.nombre} guardado correctamente.`);
          evento.target.reset();
        } else {
          avisar(`No se pudo guardar (cédula duplicada u otro dato): ${result.error}`, 'error');
        }
      } catch (error) {
        avisar('No se pudo conectar con el servidor.', 'error');
      }
    });
  }

  const formMascota = document.getElementById('formMascota');
  if (formMascota) {
    formMascota.addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const data = {
        duenoId: parseInt(document.getElementById('selectDuenoAsignado').value, 10),
        nombre: document.getElementById('mascotaNombre').value.trim(),
        especie: document.getElementById('mascotaEspecie').value,
        raza: document.getElementById('mascotaRaza').value.trim() || 'Criollo',
        sexo: document.getElementById('mascotaSexo').value,
        alergias: document.getElementById('mascotaAlergias').value.trim(),
      };

      try {
        const res = await fetch('/api/mascota', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        const result = await res.json();

        if (result.success) {
          data.id = result.id;
          mascotas.push(data);
          actualizarSelectores();
          avisar(`Mascota "${data.nombre}" guardada y expediente creado.`);
          evento.target.reset();

          const tabBtns = document.querySelectorAll('.portal-tab-btn');
          if (tabBtns[1]) cambiarPortalTab('expediente', tabBtns[1]);
        } else {
          avisar(`Error al guardar mascota: ${result.error}`, 'error');
        }
      } catch (error) {
        avisar('No se pudo conectar con el servidor.', 'error');
      }
    });
  }

  const formNuevaConsulta = document.getElementById('formNuevaConsulta');
  if (formNuevaConsulta) {
    formNuevaConsulta.addEventListener('submit', (evento) => {
      evento.preventDefault();
      avisar('En el próximo paso conectaremos la consulta médica, el descuento de vacuna y la notificación por correo.');
    });
  }

  /* ------------------------------------------------------------------------
     Modales clínicos (stubs seguros)
     ------------------------------------------------------------------------ */

  function mostrarModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('hidden');
  }

  function ocultarModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add('hidden');
  }

  window.abrirModalEditarPaciente = () => mostrarModal('modalEditarPaciente');
  window.cerrarModalEditarPaciente = () => ocultarModal('modalEditarPaciente');
  window.cerrarModalReceta = () => ocultarModal('modalReceta');
  window.cerrarModalConfirmacion = () => ocultarModal('modalConfirmacion');

  /* ------------------------------------------------------------------------
     Carrito de compras
     ------------------------------------------------------------------------ */

  const CLAVE_CARRITO = 'vetpepe_carrito_v1';
  const IVA = 0.15;
  let carrito = leerCarrito();

  function leerCarrito() {
    try {
      const crudo = window.localStorage.getItem(CLAVE_CARRITO);
      const lista = crudo ? JSON.parse(crudo) : [];
      if (!Array.isArray(lista)) return [];
      return lista
        .filter((item) => item && item.nombre)
        .map((item) => ({
          nombre: String(item.nombre),
          precio: Number(item.precio) || 0,
          imagen: item.imagen ? String(item.imagen) : '',
          cantidad: Math.max(1, parseInt(item.cantidad, 10) || 1),
        }));
    } catch (error) {
      return [];
    }
  }

  function guardarCarrito() {
    try {
      window.localStorage.setItem(CLAVE_CARRITO, JSON.stringify(carrito));
    } catch (error) {
      /* Sin almacenamiento: el carrito funciona solo en esta página. */
    }
  }

  function totales() {
    const subtotal = carrito.reduce((suma, item) => suma + item.precio * item.cantidad, 0);
    const iva = subtotal * IVA;
    return { subtotal, iva, total: subtotal + iva };
  }

  function actualizarContador() {
    const contador = document.getElementById('cartCount');
    if (contador) {
      const unidades = carrito.reduce((suma, item) => suma + item.cantidad, 0);
      contador.textContent = unidades;
      if (hasAnime && !reduceMotion && unidades > 0) {
        window.anime.animate(contador, {
          scale: [1.35, 1],
          duration: 320,
          ease: 'outBack',
        });
      }
    }
  }

  function renderCarrito() {
    const lista = document.getElementById('cartItemsList');
    if (!lista) return;

    if (carrito.length === 0) {
      lista.innerHTML = `
        <div class="cart-empty-state">
          <div style="font-size: 2.4rem; margin-bottom: 0.4rem;">🐾</div>
          <p style="font-weight: 700; color: var(--vet-green-dark);">Tu carrito está vacío</p>
          <p style="font-size: 0.8rem;">Agrega productos desde la tienda.</p>
        </div>`;
    } else {
      lista.innerHTML = carrito.map((item, indice) => {
        const imagen = item.imagen
          ? `<img src="static/img/${escapar(item.imagen)}" alt="${escapar(item.nombre)}">`
          : '<span style="font-size:1.4rem;">🐾</span>';
        return `
          <div class="cart-item-card" data-indice="${indice}">
            <div class="cart-item-img">${imagen}</div>
            <div class="cart-item-info">
              <div class="cart-item-title">${escapar(item.nombre)}</div>
              <div class="cart-item-price-unit">${dinero(item.precio)} c/u</div>
              <div class="cart-qty-controls">
                <button type="button" class="btn-qty" onclick="cambiarCantidad(${indice}, -1)" aria-label="Quitar una unidad">−</button>
                <span class="qty-display-number">${item.cantidad}</span>
                <button type="button" class="btn-qty" onclick="cambiarCantidad(${indice}, 1)" aria-label="Agregar una unidad">+</button>
              </div>
              <div class="cart-item-subtotal">${dinero(item.precio * item.cantidad)}</div>
            </div>
            <button type="button" class="btn-remove-item" onclick="quitarDelCarrito(${indice})" aria-label="Quitar producto">🗑️</button>
          </div>`;
      }).join('');
    }

    const { subtotal, iva, total } = totales();
    const subtotalEl = document.getElementById('cartSubtotalText');
    const ivaEl = document.getElementById('cartIvaText');
    const totalEl = document.getElementById('cartTotalText');

    if (subtotalEl) subtotalEl.textContent = dinero(subtotal);
    if (ivaEl) ivaEl.textContent = dinero(iva);
    if (totalEl) totalEl.textContent = dinero(total);

    actualizarContador();

    if (hasAnime && !reduceMotion && carrito.length) {
      const tarjetas = lista.querySelectorAll('.cart-item-card');
      if (tarjetas.length) {
        window.anime.animate(tarjetas, {
          opacity: [0, 1],
          translateX: [14, 0],
          duration: 300,
          delay: window.anime.stagger(30),
          ease: 'outCubic',
        });
      }
    }
  }

  window.agregarAlCarrito = function (nombre, precio, imagen) {
    const existente = carrito.find((item) => item.nombre === nombre);
    if (existente) {
      existente.cantidad += 1;
    } else {
      carrito.push({
        nombre: String(nombre),
        precio: Number(precio) || 0,
        imagen: imagen ? String(imagen) : '',
        cantidad: 1,
      });
    }

    guardarCarrito();
    renderCarrito();
    avisar(`"${nombre}" se agregó al carrito.`);
    actualizarContador();
  };

  window.cambiarCantidad = function (indice, delta) {
    const item = carrito[indice];
    if (!item) return;

    item.cantidad += delta;
    if (item.cantidad <= 0) {
      carrito.splice(indice, 1);
    }

    guardarCarrito();
    renderCarrito();
  };

  window.quitarDelCarrito = function (indice) {
    if (!carrito[indice]) return;
    const nombre = carrito[indice].nombre;
    carrito.splice(indice, 1);
    guardarCarrito();
    renderCarrito();
    avisar(`"${nombre}" se quitó del carrito.`);
  };

  window.vaciarCarrito = function () {
    if (!carrito.length) {
      avisar('El carrito ya está vacío.');
      return;
    }
    carrito = [];
    guardarCarrito();
    renderCarrito();
    avisar('Carrito vaciado.');
  };

  window.abrirCarrito = function () {
    const cajon = document.getElementById('cartDrawer');
    const fondo = document.getElementById('cartBackdrop');
    if (!cajon || !fondo) return;

    cajon.classList.add('active');
    fondo.classList.add('active');
    document.body.style.overflow = 'hidden';

    if (hasAnime && !reduceMotion) {
      window.anime.animate(cajon, {
        translateX: [24, 0],
        opacity: [0.4, 1],
        duration: 320,
        ease: 'outCubic',
      });
    }
  };

  window.cerrarCarrito = function () {
    const cajon = document.getElementById('cartDrawer');
    const fondo = document.getElementById('cartBackdrop');
    if (!cajon || !fondo) return;

    cajon.classList.remove('active');
    fondo.classList.remove('active');
    document.body.style.overflow = '';
  };

  window.abrirModalConfirmarCompra = function () {
    if (!carrito.length) {
      avisar('Agrega al menos un producto antes de confirmar el pedido.', 'error');
      return;
    }

    const resumen = document.getElementById('checkoutSummaryList');
    const totalEl = document.getElementById('checkoutModalTotal');

    if (resumen) {
      resumen.innerHTML = carrito.map((item) => `
        <div style="display:flex; justify-content:space-between; gap:0.6rem; font-size:0.8rem; padding:0.28rem 0; border-bottom:1px dashed #e2e8f0;">
          <span>${escapar(item.nombre)} <strong>×${item.cantidad}</strong></span>
          <strong style="white-space:nowrap;">${dinero(item.precio * item.cantidad)}</strong>
        </div>`).join('');
    }

    if (totalEl) totalEl.textContent = dinero(totales().total);

    mostrarModal('modalConfirmarCompra');
    if (hasAnime && !reduceMotion) {
      const tarjeta = document.querySelector('#modalConfirmarCompra .modal-white-card');
      if (tarjeta) {
        window.anime.animate(tarjeta, {
          opacity: [0, 1],
          translateY: [16, 0],
          scale: [0.98, 1],
          duration: 300,
          ease: 'outCubic',
        });
      }
    }
  };

  window.cerrarModalConfirmarCompra = function () {
    ocultarModal('modalConfirmarCompra');
  };

  window.finalizarPedidoConfirmado = function () {
    const total = dinero(totales().total);
    ocultarModal('modalConfirmarCompra');
    carrito = [];
    guardarCarrito();
    renderCarrito();
    window.setTimeout(() => {
      window.cerrarCarrito();
      avisar(`¡Pedido confirmado por ${total}! Te contactaremos para coordinar la entrega.`);
    }, 180);
  };

  /* Cerrar el carrito con Escape */
  document.addEventListener('keydown', (evento) => {
    if (evento.key === 'Escape') {
      window.cerrarCarrito();
      ocultarModal('modalConfirmarCompra');
    }
  });

  /* ------------------------------------------------------------------------
     Arranque
     ------------------------------------------------------------------------ */

  document.addEventListener('DOMContentLoaded', () => {
    actualizarSelectores();
    renderCarrito();

    if (hasAnime && !reduceMotion) {
      const tarjetas = document.querySelectorAll('.product-card');
      if (tarjetas.length) {
        window.anime.animate(tarjetas, {
          opacity: [0, 1],
          translateY: [18, 0],
          duration: 460,
          delay: window.anime.stagger(55),
          ease: 'outCubic',
        });
      }
    }
  });
})();
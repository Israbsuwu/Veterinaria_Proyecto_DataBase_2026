/* ==========================================================================
   Tienda — Veterinaria Pepe & Pepito
   Catálogo, filtros, detalle de producto y carrito. Solo compra.
   ========================================================================== */

(function () {
  'use strict';

  /* ------------------------------------------------------------------------
     Utilidades
     ------------------------------------------------------------------------ */

  const $ = (selector, scope) => (scope || document).querySelector(selector);
  const $$ = (selector, scope) => Array.from((scope || document).querySelectorAll(selector));

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

  function sinAcentos(texto) {
    return String(texto || '')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  function dinero(valor) {
    const numero = Number(valor) || 0;
    return 'C$ ' + numero.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  /* ------------------------------------------------------------------------
     Catálogo entregado por Flask
     ------------------------------------------------------------------------ */

  let productos = [];

  const datosCatalogo = $('#datos-catalogo');
  if (datosCatalogo) {
    try {
      productos = JSON.parse(datosCatalogo.textContent || '[]');
    } catch (error) {
      productos = [];
    }
  }

  const porId = new Map();
  productos.forEach((producto) => porId.set(String(producto.id), producto));

  const estado = {
    categoria: 'todas',
    texto: '',
    orden: 'relevancia',
    visibles: 12,
  };

  const TAMANO_PAGINA = 12;

  function estadoStock(producto) {
    const stock = Number(producto.stock) || 0;
    const minimo = Number(producto.minimo) || 0;
    if (stock <= 0) return { clase: 'agotado', texto: 'Agotado' };
    if (stock <= minimo) return { clase: 'low', texto: 'Stock bajo' };
    return { clase: 'ok', texto: 'Disponible' };
  }

  function imagenDe(producto) {
    return producto.imagen || producto.arte || '';
  }

  function coincide(producto) {
    if (estado.categoria !== 'todas' && producto.categoria !== estado.categoria) return false;
    if (!estado.texto) return true;
    const texto = sinAcentos([
      producto.nombre,
      producto.categoria,
      producto.descripcion,
      producto.unidad,
    ].join(' '));
    return texto.indexOf(estado.texto) !== -1;
  }

  function ordenar(lista) {
    const copia = lista.slice();
    switch (estado.orden) {
      case 'precio-asc':
        copia.sort((a, b) => (Number(a.precio) || 0) - (Number(b.precio) || 0));
        break;
      case 'precio-desc':
        copia.sort((a, b) => (Number(b.precio) || 0) - (Number(a.precio) || 0));
        break;
      case 'nombre':
        copia.sort((a, b) => String(a.nombre).localeCompare(String(b.nombre), 'es'));
        break;
      case 'stock':
        copia.sort((a, b) => (Number(b.stock) || 0) - (Number(a.stock) || 0));
        break;
      default:
        copia.sort((a, b) => String(a.nombre).localeCompare(String(b.nombre), 'es'));
    }
    return copia;
  }

  function tarjetaProducto(producto) {
    const stock = estadoStock(producto);
    const agotado = stock.clase === 'agotado';
    const imagen = imagenDe(producto);
    const descripcion = producto.descripcion && producto.descripcion.trim()
      ? producto.descripcion
      : 'Producto veterinario seleccionado por nuestro equipo.';

    return `
      <article class="shop-card" data-id="${producto.id}">
        <button type="button" class="card-add" data-agregar="${producto.id}" ${agotado ? 'disabled' : ''}
                title="${agotado ? 'Producto agotado' : 'Agregar al carrito'}"
                aria-label="${agotado ? 'Producto agotado' : 'Agregar ' + escapar(producto.nombre) + ' al carrito'}">+</button>
        <div class="shop-card-img">
          <img src="${escapar(imagen)}" alt="${escapar(producto.nombre)}" loading="lazy">
          <span class="stock-badge ${stock.clase}">${stock.texto}</span>
        </div>
        <div class="shop-card-body">
          <span class="card-cat">${escapar(producto.categoria)}</span>
          <h3>${escapar(producto.nombre)}</h3>
          <p class="card-desc">${escapar(descripcion)}</p>
          <div class="card-foot">
            <span class="card-price">${dinero(producto.precio)}<br><small>más IVA</small></span>
            <button type="button" class="btn-detail" data-detalle="${producto.id}">Ver detalle</button>
          </div>
        </div>
      </article>`;
  }

  function renderCatalogo() {
    const grilla = $('#productGrid');
    if (!grilla) return;

    const filtrados = ordenar(productos.filter(coincide));
    const recorte = filtrados.slice(0, estado.visibles);

    grilla.innerHTML = recorte.map(tarjetaProducto).join('');

    const contador = $('#contadorProductos');
    if (contador) {
      contador.textContent = filtrados.length + (filtrados.length === 1 ? ' producto' : ' productos');
    }

    const vacio = $('#vacioCatalogo');
    if (vacio) vacio.hidden = filtrados.length !== 0;

    const verMas = $('#btnVerMas');
    if (verMas) verMas.hidden = filtrados.length <= estado.visibles;

    animar($$('.shop-card', grilla), {
      opacity: [0, 1],
      translateY: [16, 0],
      duration: 380,
      delay: hasAnime ? window.anime.stagger(28) : 0,
      ease: 'outCubic',
    });
  }

  function aplicarFiltroCategoria(categoria) {
    estado.categoria = categoria || 'todas';
    estado.visibles = TAMANO_PAGINA;

    $$('.cat-chip').forEach((chip) => {
      chip.classList.toggle('active', chip.dataset.categoria === estado.categoria);
    });

    renderCatalogo();
  }

  /* ------------------------------------------------------------------------
     Aviso flotante
     ------------------------------------------------------------------------ */

  let temporizadorAviso = null;

  function avisar(mensaje, tipo) {
    const aviso = $('#avisoTienda');
    if (!aviso) return;

    aviso.textContent = mensaje;
    aviso.classList.toggle('is-error', tipo === 'error');
    aviso.hidden = false;

    animar(aviso, {
      opacity: [0, 1],
      translateY: [12, 0],
      duration: 240,
      ease: 'outCubic',
    });

    window.clearTimeout(temporizadorAviso);
    temporizadorAviso = window.setTimeout(() => {
      aviso.hidden = true;
    }, 3800);
  }

  /* ------------------------------------------------------------------------
     Carrito
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
        .filter((item) => item && (item.nombre || item.id))
        .map((item) => {
          const producto = item.id != null ? porId.get(String(item.id)) : null;
          return {
            id: item.id != null ? item.id : null,
            nombre: String(item.nombre || (producto ? producto.nombre : 'Producto')),
            precio: Number(item.precio != null ? item.precio : producto ? producto.precio : 0) || 0,
            imagen: String(item.imagen || (producto ? imagenDe(producto) : '')),
            cantidad: Math.max(1, parseInt(item.cantidad, 10) || 1),
          };
        });
    } catch (error) {
      return [];
    }
  }

  function guardarCarrito() {
    try {
      window.localStorage.setItem(CLAVE_CARRITO, JSON.stringify(carrito));
    } catch (error) {
      /* Sin almacenamiento: el carrito vive solo en esta página. */
    }
  }

  function totales() {
    const subtotal = carrito.reduce((suma, item) => suma + item.precio * item.cantidad, 0);
    const iva = subtotal * IVA;
    return { subtotal, iva, total: subtotal + iva };
  }

  function actualizarContador() {
    const contador = $('#cartCount');
    const resumen = $('#cartResumen');
    const unidades = carrito.reduce((suma, item) => suma + item.cantidad, 0);

    if (contador) {
      contador.textContent = unidades;
      if (unidades > 0) {
        animar(contador, { scale: [1.35, 1], duration: 320, ease: 'outBack' });
      }
    }

    if (resumen) {
      resumen.textContent = unidades === 1 ? '1 producto' : unidades + ' productos';
    }
  }

  function renderCarrito() {
    const lista = $('#cartItemsList');
    if (!lista) return;

    if (carrito.length === 0) {
      lista.innerHTML = `
        <div class="cart-empty">
          <span>🐾</span>
          <strong>Tu carrito está vacío</strong>
          <p>Agrega productos desde el catálogo de la tienda.</p>
        </div>`;
    } else {
      lista.innerHTML = carrito.map((item, indice) => {
        const imagen = item.imagen
          ? `<img src="${escapar(item.imagen)}" alt="${escapar(item.nombre)}">`
          : '<span style="font-size:1.5rem">🐾</span>';
        return `
          <div class="cart-item" data-indice="${indice}">
            <div class="cart-item-img">${imagen}</div>
            <div class="cart-item-info">
              <strong>${escapar(item.nombre)}</strong>
              <small>${dinero(item.precio)} c/u</small>
              <div class="qty-controls">
                <button type="button" class="qty-btn" data-cantidad="${indice}" data-delta="-1" aria-label="Quitar una unidad">−</button>
                <span class="qty-value">${item.cantidad}</span>
                <button type="button" class="qty-btn" data-cantidad="${indice}" data-delta="1" aria-label="Agregar una unidad">+</button>
              </div>
              <div class="cart-item-subtotal">${dinero(item.precio * item.cantidad)}</div>
            </div>
            <button type="button" class="cart-remove" data-quitar="${indice}" aria-label="Quitar ${escapar(item.nombre)}">✕</button>
          </div>`;
      }).join('');
    }

    const { subtotal, iva, total } = totales();
    const subtotalEl = $('#cartSubtotalText');
    const ivaEl = $('#cartIvaText');
    const totalEl = $('#cartTotalText');

    if (subtotalEl) subtotalEl.textContent = dinero(subtotal);
    if (ivaEl) ivaEl.textContent = dinero(iva);
    if (totalEl) totalEl.textContent = dinero(total);

    actualizarContador();

    animar($$('.cart-item', lista), {
      opacity: [0, 1],
      translateX: [14, 0],
      duration: 300,
      delay: hasAnime ? window.anime.stagger(30) : 0,
      ease: 'outCubic',
    });
  }

  function agregarProducto(id, cantidad) {
    const producto = porId.get(String(id));
    if (!producto) return;

    const stock = Number(producto.stock) || 0;
    if (stock <= 0) {
      avisar('Ese producto está agotado por el momento.', 'error');
      return;
    }

    const existente = carrito.find((item) => String(item.id) === String(id));
    if (existente) {
      existente.cantidad += cantidad || 1;
    } else {
      carrito.push({
        id: producto.id,
        nombre: producto.nombre,
        precio: Number(producto.precio) || 0,
        imagen: imagenDe(producto),
        cantidad: cantidad || 1,
      });
    }

    guardarCarrito();
    renderCarrito();
    avisar(`“${producto.nombre}” se agregó al carrito.`);
  }

  /* ------------------------------------------------------------------------
     Detalle de producto
     ------------------------------------------------------------------------ */

  function abrirDetalleProducto(id) {
    const producto = porId.get(String(id));
    const modal = $('#modalProducto');
    const cuerpo = $('#detalleProducto');
    const titulo = $('#tituloProducto');
    if (!producto || !modal || !cuerpo) return;

    const stock = estadoStock(producto);
    const agotado = stock.clase === 'agotado';
    const descripcion = producto.descripcion && producto.descripcion.trim()
      ? producto.descripcion
      : 'Producto veterinario seleccionado por nuestro equipo. Consulta disponibilidad y recomendaciones con el personal de la clínica.';

    if (titulo) titulo.textContent = producto.nombre;

    cuerpo.innerHTML = `
      <div class="detail-grid">
        <div class="detail-img">
          <img src="${escapar(imagenDe(producto))}" alt="${escapar(producto.nombre)}">
        </div>
        <div>
          <span class="detail-cat">${escapar(producto.categoria)}</span>
          <h3 class="detail-name">${escapar(producto.nombre)}</h3>
          <p class="detail-desc">${escapar(descripcion)}</p>
          <div class="detail-meta">
            <span>${escapar(producto.unidad)}</span>
            <span>${stock.texto}</span>
            <span>${producto.controla_vencimiento ? 'Controla vencimiento' : 'Sin vencimiento'}</span>
            <span>Mínimo: ${Number(producto.minimo) || 0}</span>
          </div>
          <div class="detail-price">${dinero(producto.precio)} <small>+ IVA</small></div>
          <button type="button" class="btn-primary detail-add" data-agregar="${producto.id}" ${agotado ? 'disabled' : ''}>
            ${agotado ? 'Producto agotado' : 'Agregar al carrito'}
          </button>
        </div>
      </div>`;

    modal.hidden = false;
    document.body.classList.add('no-scroll');
    animar($('.shop-modal-card', modal), {
      opacity: [0, 1],
      translateY: [18, 0],
      scale: [0.98, 1],
      duration: 300,
      ease: 'outCubic',
    });
  }

  function cerrarDetalleProducto() {
    const modal = $('#modalProducto');
    if (modal) modal.hidden = true;
    if (!modalAbierto()) document.body.classList.remove('no-scroll');
  }

  /* ------------------------------------------------------------------------
     Carrito visual y confirmación
     ------------------------------------------------------------------------ */

  function abrirCarrito() {
    const cajon = $('#cartDrawer');
    const fondo = $('#cartBackdrop');
    if (!cajon || !fondo) return;

    cajon.classList.add('active');
    cajon.setAttribute('aria-hidden', 'false');
    fondo.classList.add('active');
    document.body.classList.add('no-scroll');

    animar(cajon, { translateX: [24, 0], opacity: [0.4, 1], duration: 320, ease: 'outCubic' });
  }

  function cerrarCarrito() {
    const cajon = $('#cartDrawer');
    const fondo = $('#cartBackdrop');
    if (!cajon || !fondo) return;

    cajon.classList.remove('active');
    cajon.setAttribute('aria-hidden', 'true');
    fondo.classList.remove('active');
    if (!modalAbierto()) document.body.classList.remove('no-scroll');
  }

  function modalAbierto() {
    return $$('.shop-modal').some((modal) => !modal.hidden);
  }

  function abrirModalConfirmarCompra() {
    if (!carrito.length) {
      avisar('Agrega al menos un producto antes de confirmar el pedido.', 'error');
      return;
    }

    const resumen = $('#checkoutSummaryList');
    const totalEl = $('#checkoutModalTotal');

    if (resumen) {
      resumen.innerHTML = carrito.map((item) => `
        <div class="checkout-item">
          <span>${escapar(item.nombre)} <strong>×${item.cantidad}</strong></span>
          <strong>${dinero(item.precio * item.cantidad)}</strong>
        </div>`).join('');
    }

    if (totalEl) totalEl.textContent = dinero(totales().total);

    const modal = $('#modalConfirmarCompra');
    if (modal) modal.hidden = false;
    document.body.classList.add('no-scroll');

    animar($('#modalConfirmarCompra .shop-modal-card'), {
      opacity: [0, 1],
      translateY: [16, 0],
      scale: [0.98, 1],
      duration: 300,
      ease: 'outCubic',
    });
  }

  function cerrarModalConfirmarCompra() {
    const modal = $('#modalConfirmarCompra');
    if (modal) modal.hidden = true;
    if (!modalAbierto()) document.body.classList.remove('no-scroll');
  }

  function finalizarPedidoConfirmado() {
    if (!carrito.length) return;
    const payload = {
      auto_print: true,
      items: carrito.map((item) => ({
        nombre: item.nombre,
        cantidad: item.cantidad,
        precio: item.precio,
      })),
    };

    cerrarModalConfirmarCompra();

    // Generar comprobante imprimible/PDF en una nueva pestaña.
    try {
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/tienda/comprobante';
      form.target = '_blank';

      const campo = document.createElement('input');
      campo.type = 'hidden';
      campo.name = 'datos';
      campo.value = JSON.stringify(payload);
      form.appendChild(campo);
      document.body.appendChild(form);
      form.submit();
      form.remove();
    } catch (error) {
      /* Si falla la apertura, se continúa con la confirmación. */
    }

    carrito = [];
    guardarCarrito();
    renderCarrito();
    window.setTimeout(() => {
      cerrarCarrito();
      avisar('Pedido confirmado. Se generó tu comprobante para imprimir o guardar en PDF.');
    }, 180);
  }

  function cambiarCantidad(indice, delta) {
    const item = carrito[indice];
    if (!item) return;

    item.cantidad += delta;
    if (item.cantidad <= 0) carrito.splice(indice, 1);

    guardarCarrito();
    renderCarrito();
  }

  function quitarDelCarrito(indice) {
    const item = carrito[indice];
    if (!item) return;
    carrito.splice(indice, 1);
    guardarCarrito();
    renderCarrito();
    avisar(`“${item.nombre}” se quitó del carrito.`);
  }

  function vaciarCarrito() {
    if (!carrito.length) {
      avisar('El carrito ya está vacío.');
      return;
    }
    carrito = [];
    guardarCarrito();
    renderCarrito();
    avisar('Carrito vaciado.');
  }

  /* ------------------------------------------------------------------------
     Eventos
     ------------------------------------------------------------------------ */

  // Delegación de clics del catálogo, carrito y detalle.
  document.addEventListener('click', (evento) => {
    const agregar = evento.target.closest('[data-agregar]');
    if (agregar) {
      evento.preventDefault();
      agregarProducto(agregar.dataset.agregar, 1);
      return;
    }

    const detalle = evento.target.closest('[data-detalle]');
    if (detalle) {
      evento.preventDefault();
      abrirDetalleProducto(detalle.dataset.detalle);
      return;
    }

    const cantidad = evento.target.closest('[data-cantidad]');
    if (cantidad) {
      cambiarCantidad(Number(cantidad.dataset.cantidad), Number(cantidad.dataset.delta));
      return;
    }

    const quitar = evento.target.closest('[data-quitar]');
    if (quitar) {
      quitarDelCarrito(Number(quitar.dataset.quitar));
      return;
    }

    const chip = evento.target.closest('.cat-chip');
    if (chip) {
      aplicarFiltroCategoria(chip.dataset.categoria);
      return;
    }

    const filtrar = evento.target.closest('[data-filtrar]');
    if (filtrar) {
      evento.preventDefault();
      const categoria = filtrar.dataset.filtrar;
      aplicarFiltroCategoria(categoria);
      const destino = $('#catalogo');
      if (destino) destino.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
      return;
    }

    // Cerrar modales al hacer clic en el fondo oscuro.
    if (evento.target.classList.contains('shop-modal')) {
      evento.target.hidden = true;
      if (!modalAbierto()) document.body.classList.remove('no-scroll');
    }
  });

  const buscador = $('#buscarProducto');
  if (buscador) {
    buscador.addEventListener('input', () => {
      estado.texto = sinAcentos(buscador.value.trim());
      estado.visibles = TAMANO_PAGINA;
      renderCatalogo();
    });
  }

  const orden = $('#ordenProducto');
  if (orden) {
    orden.addEventListener('change', () => {
      estado.orden = orden.value;
      estado.visibles = TAMANO_PAGINA;
      renderCatalogo();
    });
  }

  const verMas = $('#btnVerMas');
  if (verMas) {
    verMas.addEventListener('click', () => {
      estado.visibles += TAMANO_PAGINA;
      renderCatalogo();
    });
  }

  document.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Escape') return;
    cerrarCarrito();
    cerrarModalConfirmarCompra();
    cerrarDetalleProducto();
  });

  /* API usada por los botones del HTML */
  window.abrirCarrito = abrirCarrito;
  window.cerrarCarrito = cerrarCarrito;
  window.abrirModalConfirmarCompra = abrirModalConfirmarCompra;
  window.cerrarModalConfirmarCompra = cerrarModalConfirmarCompra;
  window.finalizarPedidoConfirmado = finalizarPedidoConfirmado;
  window.vaciarCarrito = vaciarCarrito;
  window.cerrarDetalleProducto = cerrarDetalleProducto;

  /* ------------------------------------------------------------------------
     Arranque
     ------------------------------------------------------------------------ */

  function iniciar() {
    renderCatalogo();
    renderCarrito();

    animar($$('.hero-copy > *'), {
      opacity: [0, 1],
      translateY: [18, 0],
      duration: 520,
      delay: hasAnime ? window.anime.stagger(70) : 0,
      ease: 'outCubic',
    });

    animar($$('.hero-photo'), {
      opacity: [0, 1],
      scale: [0.94, 1],
      duration: 620,
      delay: hasAnime ? window.anime.stagger(80, { start: 180 }) : 0,
      ease: 'outCubic',
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
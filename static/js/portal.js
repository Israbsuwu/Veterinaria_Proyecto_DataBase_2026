/* ==========================================================================
   Portal clínico — Veterinaria Pepe & Pepito
   Registro de propietarios y mascotas, expediente y consultas.
   ========================================================================== */

(function () {
  'use strict';

  const $ = (selector, scope) => (scope || document).querySelector(selector);
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

  /* ------------------------------------------------------------------------
     Datos inyectados por Flask
     ------------------------------------------------------------------------ */

  const serverData = $('#server-data');
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

  /* ------------------------------------------------------------------------
     Aviso flotante
     ------------------------------------------------------------------------ */

  let temporizador = null;

  function avisar(mensaje, tipo) {
    const aviso = $('#avisoClinico');
    if (!aviso) return;

    aviso.textContent = mensaje;
    aviso.classList.toggle('is-error', tipo === 'error');
    aviso.hidden = false;

    animar(aviso, { opacity: [0, 1], translateY: [12, 0], duration: 240, ease: 'outCubic' });

    window.clearTimeout(temporizador);
    temporizador = window.setTimeout(() => { aviso.hidden = true; }, 4000);
  }

  /* ------------------------------------------------------------------------
     Pestañas
     ------------------------------------------------------------------------ */

  window.cambiarPortalTab = function (panelId, btnElement) {
    document.querySelectorAll('.portal-tab-btn').forEach((btn) => btn.classList.remove('active'));
    if (btnElement) btnElement.classList.add('active');

    document.querySelectorAll('.portal-view-panel').forEach((panel) => panel.classList.remove('active'));
    const panel = document.getElementById('pview-' + panelId);
    if (panel) {
      panel.classList.add('active');
      animar(panel, { opacity: [0, 1], translateY: [10, 0], duration: 320, ease: 'outCubic' });
    }
  };

  /* ------------------------------------------------------------------------
     Selectores y expediente
     ------------------------------------------------------------------------ */

  function actualizarSelectores() {
    const selDueno = $('#selectDuenoAsignado');
    const selExpediente = $('#selectExpediente');
    const selPacienteConsulta = $('#selectPacienteConsulta');

    if (!selDueno || !selExpediente || !selPacienteConsulta) return;

    selDueno.innerHTML = '';
    propietarios.forEach((p) => {
      selDueno.innerHTML += `<option value="${escapar(p.id)}">${escapar(p.nombre)} ${escapar(p.apellido)} (${escapar(p.cedula)})</option>`;
    });

    selExpediente.innerHTML = '';
    selPacienteConsulta.innerHTML = '';
    mascotas.forEach((m) => {
      const dueno = propietarios.find((p) => String(p.id) === String(m.duenoId));
      const duenoTxt = dueno ? `${dueno.nombre} ${dueno.apellido}` : 'Sin dueño';
      const opcion = `<option value="${escapar(m.id)}">${escapar(m.nombre)} (${escapar(m.especie)}) — Propietario: ${escapar(duenoTxt)}</option>`;
      selExpediente.innerHTML += opcion;
      selPacienteConsulta.innerHTML += opcion;
    });

    if (mascotas.length > 0) {
      selExpediente.value = mascotas[0].id;
      window.renderExpedienteSeleccionado(mascotas[0].id);
    } else {
      renderSinPacientes();
    }
  }

  function renderSinPacientes() {
    const nombreEl = $('#expNombreMascota');
    const detallesEl = $('#expDetallesMascota');
    const duenoEl = $('#expDuenoMascota');
    const badge = $('#expEstadoAlergia');
    const timeline = $('#timelineConsultas');
    const animal = $('#alergiaAnimal');

    if (nombreEl) nombreEl.textContent = 'Sin pacientes registrados';
    if (detallesEl) detallesEl.textContent = 'Registra un propietario y una mascota para comenzar.';
    if (duenoEl) duenoEl.textContent = '';
    if (animal) animal.value = '';
    if (badge) {
      badge.textContent = 'Análisis de alergia pendiente';
      badge.style.background = '#fdf3dc';
      badge.style.color = '#875810';
      badge.style.borderColor = '#e8cc93';
    }
    if (timeline) {
      timeline.innerHTML = '<p style="color: var(--muted); font-size: 0.82rem;">Todavía no hay atenciones registradas.</p>';
    }
  }

  window.renderExpedienteSeleccionado = function (mascotaId) {
    const mascota = mascotas.find((m) => String(m.id) === String(mascotaId));
    if (!mascota) {
      renderSinPacientes();
      return;
    }

    const nombreEl = $('#expNombreMascota');
    const detallesEl = $('#expDetallesMascota');
    const duenoEl = $('#expDuenoMascota');
    const badge = $('#expEstadoAlergia');
    const timeline = $('#timelineConsultas');
    const animal = $('#alergiaAnimal');

    if (nombreEl) nombreEl.textContent = mascota.nombre;
    if (detallesEl) {
      const partes = [mascota.especie || '—', `Raza: ${mascota.raza || '—'}`, `Sexo: ${mascota.sexo || '—'}`];
      if (mascota.color) partes.push(`Color: ${mascota.color}`);
      if (mascota.fecha_nacimiento) partes.push(`Nacimiento: ${mascota.fecha_nacimiento}`);
      detallesEl.textContent = partes.join(' • ');
    }
    if (animal) animal.value = `${mascota.nombre || ''} (${mascota.especie || 'Animal'})`.trim();

    const dueno = propietarios.find((p) => String(p.id) === String(mascota.duenoId));
    if (duenoEl) {
      duenoEl.textContent = dueno
        ? `Dueño: ${dueno.nombre} ${dueno.apellido} (Tel: ${dueno.tel || '—'})`
        : 'Dueño: sin registrar';
    }

    if (badge) {
      const analisis = mascota.analisis_alergia || '';
      if (analisis && analisis.trim() !== '') {
        badge.textContent = 'Análisis de alergia registrado';
        badge.style.background = '#edf6df';
        badge.style.color = '#41681c';
        badge.style.borderColor = '#c7dba6';
      } else {
        badge.textContent = 'Análisis de alergia pendiente';
        badge.style.background = '#fdf3dc';
        badge.style.color = '#875810';
        badge.style.borderColor = '#e8cc93';
      }
    }

    if (timeline) {
      timeline.innerHTML = '<p style="color: var(--muted); font-size: 0.82rem;">El detalle de consultas y recetas se conectará en la siguiente fase del sistema.</p>';
    }
  };

  /* ------------------------------------------------------------------------
     Formularios clínicos
     ------------------------------------------------------------------------ */

  const formPropietario = $('#formPropietario');
  if (formPropietario) {
    formPropietario.addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const datos = {
        cedula: $('#propCedula').value.trim(),
        nombre: $('#propNombre').value.trim(),
        apellido: $('#propApellido').value.trim(),
        tel: $('#propTel').value.trim(),
        correo: ($('#propCorreo') ? $('#propCorreo').value.trim() : ''),
        direccion: ($('#propDireccion') ? $('#propDireccion').value.trim() : ''),
      };

      try {
        const respuesta = await fetch('/api/cliente', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(datos),
        });
        const resultado = await respuesta.json();

        if (resultado.success) {
          datos.id = resultado.id;
          propietarios.push(datos);
          actualizarSelectores();
          avisar(`Propietario ${datos.nombre} guardado correctamente.`);
          evento.target.reset();
        } else {
          avisar(`No se pudo guardar: ${resultado.error || 'revisa los datos.'}`, 'error');
        }
      } catch (error) {
        avisar('No se pudo conectar con el servidor.', 'error');
      }
    });
  }

  const formMascota = $('#formMascota');
  if (formMascota) {
    formMascota.addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const datos = {
        duenoId: parseInt($('#selectDuenoAsignado').value, 10),
        nombre: $('#mascotaNombre').value.trim(),
        especie: $('#mascotaEspecie').value,
        raza: $('#mascotaRaza').value.trim() || 'Criollo',
        sexo: $('#mascotaSexo').value,
        color: ($('#mascotaColor') ? $('#mascotaColor').value.trim() : ''),
        fecha_nacimiento: ($('#mascotaNacimiento') ? $('#mascotaNacimiento').value : ''),
        senas: ($('#mascotaSenas') ? $('#mascotaSenas').value.trim() : ''),
      };

      try {
        const respuesta = await fetch('/api/mascota', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(datos),
        });
        const resultado = await respuesta.json();

        if (resultado.success) {
          datos.id = resultado.id;
          mascotas.push(datos);
          actualizarSelectores();
          avisar(`Mascota “${datos.nombre}” guardada y expediente creado.`);
          evento.target.reset();

          const botones = document.querySelectorAll('.portal-tab-btn');
          if (botones[1]) window.cambiarPortalTab('expediente', botones[1]);
        } else {
          avisar(`Error al guardar mascota: ${resultado.error || 'revisa los datos.'}`, 'error');
        }
      } catch (error) {
        avisar('No se pudo conectar con el servidor.', 'error');
      }
    });
  }

  const formNuevaConsulta = $('#formNuevaConsulta');
  if (formNuevaConsulta) {
    formNuevaConsulta.addEventListener('submit', (evento) => {
      evento.preventDefault();
      avisar('La consulta médica y el descuento de vacuna se conectarán en la siguiente fase.');
    });
  }

  const formAnalisisAlergia = $('#formAnalisisAlergia');
  if (formAnalisisAlergia) {
    formAnalisisAlergia.addEventListener('submit', async (evento) => {
      evento.preventDefault();
      const sel = $('#selectExpediente');
      const idMascota = sel ? sel.value : '';
      const mascota = mascotas.find((m) => String(m.id) === String(idMascota));
      if (!mascota) {
        avisar('Selecciona un paciente para registrar el análisis de alergia.', 'error');
        return;
      }
      const datos = {
        id_mascota: Number(idMascota),
        tipo_examen: ($('#alergiaExamen') ? $('#alergiaExamen').value : ''),
        tipo_alergia: ($('#alergiaTipo') ? $('#alergiaTipo').value : ''),
        animal: ($('#alergiaAnimal') ? $('#alergiaAnimal').value : ''),
        observaciones: ($('#alergiaObservaciones') ? $('#alergiaObservaciones').value.trim() : ''),
      };
      try {
        const respuesta = await fetch('/api/expediente/alergia', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(datos),
        });
        const resultado = await respuesta.json();
        if (resultado.success) {
          mascota.analisis_alergia = resultado.resumen || 'registrado';
          mascota.condiciones = resultado.condiciones || '';
          avisar('Análisis de alergia guardado en el expediente.');
          window.renderExpedienteSeleccionado(idMascota);
        } else {
          avisar(resultado.error || 'No se pudo guardar el análisis.', 'error');
        }
      } catch (error) {
        avisar('No se pudo conectar con el servidor.', 'error');
      }
    });
  }

  /* ------------------------------------------------------------------------
     Modales
     ------------------------------------------------------------------------ */

  function mostrarModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.classList.remove('hidden');
      document.body.classList.add('no-scroll');
    }
  }

  function ocultarModal(id) {
    const modal = document.getElementById(id);
    if (modal) {
      modal.classList.add('hidden');
      if (!document.querySelector('.modal-backdrop:not(.hidden)')) {
        document.body.classList.remove('no-scroll');
      }
    }
  }

  window.abrirModalEditarPaciente = function () {
    const select = $('#selectExpediente');
    const mascota = mascotas.find((m) => String(m.id) === String(select ? select.value : ''));
    if (!mascota) {
      avisar('Selecciona un paciente registrado para editar sus datos.', 'error');
      return;
    }

    const dueno = propietarios.find((p) => String(p.id) === String(mascota.duenoId)) || {};

    $('#editMascotaId').value = mascota.id;
    $('#editDuenoId').value = mascota.duenoId || '';
    $('#editDuenoNombre').value = dueno.nombre || '';
    $('#editDuenoApellido').value = dueno.apellido || '';
    $('#editDuenoCedula').value = dueno.cedula || '';
    $('#editDuenoTel').value = dueno.tel || '';
    $('#editMascotaNombre').value = mascota.nombre || '';
    $('#editMascotaEspecie').value = mascota.especie || 'Canino';
    const senas = $('#editMascotaSenas');
    if (senas) senas.value = mascota.senas || mascota.condiciones || '';

    mostrarModal('modalEditarPaciente');
  };

  window.cerrarModalEditarPaciente = function () { ocultarModal('modalEditarPaciente'); };
  window.cerrarModalReceta = function () { ocultarModal('modalReceta'); };
  window.cerrarModalConfirmacion = function () { ocultarModal('modalConfirmacion'); };

  window.solicitarEliminarPaciente = function () {
    const titulo = $('#confirmTitle');
    const mensaje = $('#confirmMessage');
    if (titulo) titulo.textContent = 'Eliminar paciente';
    if (mensaje) mensaje.textContent = 'La eliminación de expedientes se habilitará cuando se conecte la operación en la base de datos.';
    mostrarModal('modalConfirmacion');
  };

  const formEditar = $('#formModalEditarPaciente');
  if (formEditar) {
    formEditar.addEventListener('submit', (evento) => {
      evento.preventDefault();
      window.cerrarModalEditarPaciente();
      avisar('La edición de pacientes se conectará en la siguiente fase.');
    });
  }

  document.addEventListener('keydown', (evento) => {
    if (evento.key !== 'Escape') return;
    ['modalEditarPaciente', 'modalReceta', 'modalConfirmacion'].forEach(ocultarModal);
  });

  /* ------------------------------------------------------------------------
     Arranque
     ------------------------------------------------------------------------ */

  function iniciar() {
    actualizarSelectores();

    animar(document.querySelectorAll('.portal-tab-btn, .portal-view-panel.active'), {
      opacity: [0, 1],
      translateY: [10, 0],
      duration: 380,
      delay: hasAnime ? window.anime.stagger(40) : 0,
      ease: 'outCubic',
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', iniciar);
  } else {
    iniciar();
  }
})();
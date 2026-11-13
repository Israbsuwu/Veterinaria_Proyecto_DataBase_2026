// Leer los datos inyectados de forma segura desde el HTML
const serverData = document.getElementById('server-data');
let propietarios = [];
let mascotas = [];

if (serverData) {
    propietarios = JSON.parse(serverData.dataset.clientes || '[]');
    mascotas = JSON.parse(serverData.dataset.mascotas || '[]');
}

// CONTROL DE NAVEGACIÓN Y TABS
window.togglePortalClinico = function() {
    const portal = document.getElementById('portalClinicoWrap');
    if (portal.style.display === 'none' || portal.style.display === '') {
        portal.style.display = 'block';
        portal.scrollIntoView({ behavior: 'smooth' });
    } else {
        portal.style.display = 'none';
    }
};

window.cambiarPortalTab = function(panelId, btnElement) {
    document.querySelectorAll('.portal-tab-btn').forEach(btn => btn.classList.remove('active'));
    btnElement.classList.add('active');

    document.querySelectorAll('.portal-view-panel').forEach(panel => panel.classList.remove('active'));
    document.getElementById(`pview-${panelId}`).classList.add('active');
};

window.abrirPortalEnTab = function(tabName) {
    document.getElementById('portalClinicoWrap').style.display = 'block';
    document.getElementById('portalClinicoWrap').scrollIntoView({ behavior: 'smooth' });
    
    const tabBtns = document.querySelectorAll('.portal-tab-btn');
    if (tabName === 'pacientes') {
        cambiarPortalTab('registro', tabBtns[0]);
    } else {
        cambiarPortalTab('expediente', tabBtns[1]);
    }
};

// ==========================================
// FUNCIONES PARA LLENAR LOS DESPLEGABLES CON SQL
// ==========================================
function actualizarSelectores() {
    const selDueno = document.getElementById('selectDuenoAsignado');
    const selExpediente = document.getElementById('selectExpediente');
    const selPacienteConsulta = document.getElementById('selectPacienteConsulta');

    selDueno.innerHTML = '';
    propietarios.forEach(p => {
        selDueno.innerHTML += `<option value="${p.id}">${p.nombre} ${p.apellido} (${p.cedula})</option>`;
    });

    selExpediente.innerHTML = '';
    selPacienteConsulta.innerHTML = '';
    mascotas.forEach(m => {
        const dueno = propietarios.find(p => p.id === m.duenoId);
        const duenoTxt = dueno ? `${dueno.nombre} ${dueno.apellido}` : 'Sin dueño';
        const opt = `<option value="${m.id}">${m.nombre} (${m.especie}) — Propietario: ${duenoTxt}</option>`;
        selExpediente.innerHTML += opt;
        selPacienteConsulta.innerHTML += opt;
    });

    if (mascotas.length > 0) {
        selExpediente.value = mascotas[0].id;
        renderExpedienteSeleccionado(mascotas[0].id);
    }
}

window.renderExpedienteSeleccionado = function(mascotaId) {
    mascotaId = parseInt(mascotaId); // Castear a número porque el ID viene de SQL (INT)
    const mascota = mascotas.find(m => m.id === mascotaId);
    if (!mascota) return;

    const dueno = propietarios.find(p => p.id === mascota.duenoId);
    document.getElementById('expNombreMascota').textContent = mascota.nombre;
    document.getElementById('expDetallesMascota').textContent = `${mascota.especie} • Raza: ${mascota.raza} • Sexo: ${mascota.sexo}`;
    
    if (dueno) {
        document.getElementById('expDuenoMascota').textContent = `Dueño: ${dueno.nombre} ${dueno.apellido} (Tel: ${dueno.tel})`;
        // Actualizar el letrero de Alergias dinámicamente
      const badgeAlergia = document.getElementById('expAlergiaMascota');
      if (mascota.alergias && mascota.alergias.trim() !== '') {
          badgeAlergia.textContent = `⚠️ Alergia: ${mascota.alergias}`;
          badgeAlergia.style.backgroundColor = '#fee2e2'; // Fondo rojo claro
          badgeAlergia.style.color = '#b91c1c'; // Letra roja oscura
          badgeAlergia.style.borderColor = '#f87171';
      } else {
          badgeAlergia.textContent = '✓ Sin alergias registradas';
          badgeAlergia.style.backgroundColor = '#dcfce7'; // Fondo verde claro
          badgeAlergia.style.color = '#15803d'; // Letra verde oscura
          badgeAlergia.style.borderColor = '#86efac';
      }
    }

    // Por ahora mostramos un mensaje, en la próxima fase inyectaremos las consultas de SQL
    document.getElementById('timelineConsultas').innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem 0;">(En la Fase 5 conectaremos las consultas y recetas desde la base de datos).</p>';
};

// ==========================================
// FORMULARIOS CONECTADOS A FLASK (SQL SERVER)
// ==========================================
document.getElementById('formPropietario').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
        cedula: document.getElementById('propCedula').value.trim(),
        nombre: document.getElementById('propNombre').value.trim(),
        apellido: document.getElementById('propApellido').value.trim(),
        tel: document.getElementById('propTel').value.trim()
    };

    const res = await fetch('/api/cliente', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    const result = await res.json();
    
    if (result.success) {
        data.id = result.id; // Asignamos el ID real de SQL Server
        propietarios.push(data); // Actualizamos la vista local
        actualizarSelectores();
        alert(`✅ Propietario ${data.nombre} guardado correctamente en la Base de Datos.`);
        e.target.reset();
    } else {
        alert(`❌ Ocurrió un error (Ej. Cédula duplicada): ${result.error}`);
    }
});

document.getElementById('formMascota').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
        duenoId: parseInt(document.getElementById('selectDuenoAsignado').value),
        nombre: document.getElementById('mascotaNombre').value.trim(),
        especie: document.getElementById('mascotaEspecie').value,
        raza: document.getElementById('mascotaRaza').value.trim() || 'Criollo',
        sexo: document.getElementById('mascotaSexo').value,
        alergias: document.getElementById('mascotaAlergias').value.trim()
    };

    const res = await fetch('/api/mascota', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    const result = await res.json();
    
    if (result.success) {
        data.id = result.id; // Asignamos el ID de la mascota y del expediente
        mascotas.push(data);
        actualizarSelectores();
        alert(`🐾 Mascota "${data.nombre}" guardada y Expediente Clínico inicializado en SQL.`);
        e.target.reset();
        
        // Mover a la pestaña del expediente
        const tabBtns = document.querySelectorAll('.portal-tab-btn');
        cambiarPortalTab('expediente', tabBtns[1]);
    } else {
        alert(`❌ Error al guardar mascota: ${result.error}`);
    }
});

// Desactivar temporalmente la consulta para el siguiente paso
document.getElementById('formNuevaConsulta').addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = {
        mascotaId: parseInt(document.getElementById('selectPacienteConsulta').value),
        peso: document.getElementById('consultaPeso').value,
        motivo: document.getElementById('consultaMotivo').value.trim(),
        diagnostico: document.getElementById('consultaDiagnostico').value.trim(),
        farmaco: document.getElementById('recetaFarmaco').value.trim(),
        dosis: document.getElementById('recetaDosis').value.trim(),
        duracion: document.getElementById('recetaDuracion').value.trim()
    };

    const res = await fetch('/api/consulta', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    const result = await res.json();
    
    if (result.success) {
        alert('🩺 Consulta guardada exitosamente.\n💉 Vacuna registrada en inventario.\n📧 Recordatorio de refuerzo programado (n8n).');
        
        // Inyectamos visualmente la tarjeta de la consulta en el expediente (Línea de tiempo)
        const timeline = document.getElementById('timelineConsultas');
        
        // Si estaba el mensaje de advertencia ("En la Fase 5..."), lo borramos
        if(timeline.innerHTML.includes('Fase 5')) { timeline.innerHTML = ''; }
        
        const nuevaCard = document.createElement('div');
        nuevaCard.className = 'history-card-item';
        nuevaCard.innerHTML = `
        <div class="history-top-row">
            <strong>${data.motivo}</strong>
            <small style="color: #64748b;">Hoy</small>
        </div>
        <p style="font-size: 0.85rem; margin-bottom: 4px;"><strong>Peso:</strong> ${data.peso} kg</p>
        <p style="font-size: 0.85rem; margin-bottom: 4px;"><strong>Diagnóstico:</strong> ${data.diagnostico}</p>
        <p style="font-size: 0.85rem; color: #475569;"><strong>Prescripción:</strong> ${data.farmaco} (${data.dosis}) por ${data.duracion} días.</p>
        <p style="font-size: 0.85rem; color: var(--vet-green-dark); margin-top: 8px;"><strong>💉 Vacuna Aplicada y Recordatorio de refuerzo programado para 30 días</strong></p>
        `;
        timeline.prepend(nuevaCard);
        
        e.target.reset();
        
        // Nos pasamos a la pestaña de Expediente para ver la tarjeta agregada
        const tabBtns = document.querySelectorAll('.portal-tab-btn');
        cambiarPortalTab('expediente', tabBtns[1]);
    } else {
        alert(`❌ Error al guardar la consulta: ${result.error}`);
    }
});

// Arrancar funciones de inicio
document.addEventListener("DOMContentLoaded", () => {
    actualizarSelectores();
});
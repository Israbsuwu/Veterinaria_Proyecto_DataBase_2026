document.addEventListener("DOMContentLoaded", () => {
  // Manejo de Navegación por Pestañas
  const navButtons = document.querySelectorAll(".nav-btn");
  const tabPanels = document.querySelectorAll(".tab-panel");

  navButtons.forEach(button => {
    button.addEventListener("click", () => {
      const targetTab = button.dataset.tab;

      // Actualizar estado de botones
      navButtons.forEach(btn => btn.classList.remove("active"));
      button.classList.add("active");

      // Mostrar el panel seleccionado
      tabPanels.forEach(panel => {
        panel.classList.remove("active");
        if (panel.id === `tab-${targetTab}`) {
          panel.classList.add("active");
        }
      });
    });
  });

  // Notificación Toast
  function showToast(message) {
    const toast = document.getElementById("toastNotification");
    toast.textContent = message;
    toast.classList.remove("hidden");
    setTimeout(() => {
      toast.classList.add("hidden");
    }, 3000);
  }

  // Eventos de Formulario (Simulación inicial antes de conectar con n8n)
  document.getElementById("formCliente").addEventListener("submit", (e) => {
    e.preventDefault();
    showToast("✅ Propietario registrado con éxito (Simulado)");
    e.target.reset();
  });

  document.getElementById("formMascota").addEventListener("submit", (e) => {
    e.preventDefault();
    showToast("🐾 Mascota vinculada y expediente abierto (Simulado)");
    e.target.reset();
  });

  document.getElementById("formConsulta").addEventListener("submit", (e) => {
    e.preventDefault();
    const peso = document.getElementById("pesoMascota").value;
    showToast(`🩺 Consulta guardada. Peso registrado: ${peso} kg`);
    e.target.reset();
  });

  document.getElementById("btnCobrar").addEventListener("click", () => {
    showToast("💳 Venta procesada y comprobante emitido");
  });
});
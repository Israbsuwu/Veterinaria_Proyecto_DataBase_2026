/* Comportamientos generales del panel administrativo. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    // Reloj en la barra superior
    const clock = document.getElementById("topbar-clock");
    if (clock) {
      const render = () => {
        const now = new Date();
        clock.textContent = now.toLocaleDateString("es-NI", {
          weekday: "short",
          day: "2-digit",
          month: "short",
          year: "numeric",
        });
      };
      render();
    }

    // Confirmación de acciones destructivas
    document.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-confirm]");
      if (btn && !window.confirm(btn.dataset.confirm)) {
        event.preventDefault();
        event.stopPropagation();
      }
    });
  });
})();

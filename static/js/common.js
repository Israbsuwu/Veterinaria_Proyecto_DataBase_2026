/* Utilidades compartidas por el panel y la tienda. */
(function () {
  "use strict";

  const CURRENCY = "C$";

  function money(value) {
    const number = Number(value || 0);
    return (
      CURRENCY +
      " " +
      number.toLocaleString("es-NI", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  }

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async function api(url, options = {}) {
    const config = {
      method: options.method || "GET",
      headers: { Accept: "application/json", ...(options.headers || {}) },
      credentials: "same-origin",
    };
    if (options.body !== undefined) {
      config.headers["Content-Type"] = "application/json";
      config.body = JSON.stringify(options.body);
    }
    let response;
    try {
      response = await fetch(url, config);
    } catch (error) {
      throw new Error("No se pudo conectar con el servidor.");
    }
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = { success: false, error: "Respuesta inválida del servidor." };
    }
    if (response.status === 401) {
      toast("Tu sesión expiró. Inicia sesión nuevamente.", "error");
      setTimeout(() => {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href =
          window.location.pathname.indexOf("/tienda") === 0
            ? "/tienda/login?next=" + next
            : "/login?next=" + next;
      }, 900);
      throw new Error(data.error || "Sesión expirada.");
    }
    if (!response.ok || data.success === false) {
      throw new Error(data.error || "Ocurrió un error inesperado.");
    }
    return data.data !== undefined ? data.data : data;
  }

  let toastTimer = null;
  function toast(message, type = "success", duration = 3600) {
    let element = document.getElementById("app-toast");
    if (!element) {
      element = document.createElement("div");
      element.id = "app-toast";
      element.className = "toast hidden";
      document.body.appendChild(element);
    }
    element.className = "toast " + (type === "error" ? "toast-error" : type === "info" ? "toast-info" : "");
    element.textContent = message;
    element.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => element.classList.add("hidden"), duration);
  }

  function formData(form) {
    const data = {};
    new FormData(form).forEach((value, key) => {
      if (value !== "") data[key] = value;
    });
    return data;
  }

  function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add("open");
  }

  function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove("open");
  }

  function setLoading(button, loading, text) {
    if (!button) return;
    if (loading) {
      button.dataset.originalText = button.innerHTML;
      button.disabled = true;
      button.innerHTML = text || "Procesando…";
    } else {
      button.disabled = false;
      if (button.dataset.originalText) button.innerHTML = button.dataset.originalText;
    }
  }

  function confirmAction(message) {
    return window.confirm(message);
  }

  function todayISO() {
    const now = new Date();
    const offset = now.getTimezoneOffset();
    return new Date(now.getTime() - offset * 60000).toISOString().slice(0, 10);
  }

  function initModals() {
    document.addEventListener("click", (event) => {
      const opener = event.target.closest("[data-modal-open]");
      if (opener) {
        event.preventDefault();
        openModal(opener.dataset.modalOpen);
      }
      const closer = event.target.closest("[data-modal-close]");
      if (closer) {
        event.preventDefault();
        closeModal(closer.dataset.modalClose);
      }
      const backdrop = event.target.classList && event.target.classList.contains("modal-backdrop");
      if (backdrop) backdrop.classList.remove("open");
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        document.querySelectorAll(".modal-backdrop.open").forEach((modal) => modal.classList.remove("open"));
      }
    });
  }

  function initTabs() {
    document.querySelectorAll("[data-tabs]").forEach((group) => {
      group.querySelectorAll("[data-tab]").forEach((button) => {
        button.addEventListener("click", () => {
          const target = button.dataset.tab;
          group.querySelectorAll("[data-tab]").forEach((b) => b.classList.remove("active"));
          button.classList.add("active");
          const scope = document.querySelector(group.dataset.tabs);
          if (!scope) return;
          scope.querySelectorAll("[data-panel]").forEach((panel) => {
            panel.classList.toggle("active", panel.dataset.panel === target);
          });
        });
      });
    });
  }

  window.App = {
    api,
    money,
    escapeHtml,
    toast,
    formData,
    openModal,
    closeModal,
    setLoading,
    confirmAction,
    todayISO,
  };

  document.addEventListener("DOMContentLoaded", () => {
    initModals();
    initTabs();
    // Cierra automáticamente los mensajes flash después de 6 segundos
    document.querySelectorAll(".flash[data-auto-hide]").forEach((flash) => {
      setTimeout(() => {
        flash.style.transition = "opacity .4s";
        flash.style.opacity = "0";
        setTimeout(() => flash.remove(), 450);
      }, 6000);
    });
  });
})();

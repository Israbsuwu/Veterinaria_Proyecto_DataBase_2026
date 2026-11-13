/* Tienda en línea: carrito, checkout, cuenta y reservas. */
(function () {
  "use strict";

  const App = window.App;

  function setCartCount(count) {
    const value = Number(count || 0);
    document.querySelectorAll("[data-cart-count]").forEach((element) => {
      element.textContent = value;
      element.dataset.count = value;
    });
  }

  function currentCartCount() {
    const badge = document.querySelector("[data-cart-count]");
    return badge ? Number(badge.dataset.count || badge.textContent || 0) : 0;
  }

  // ------------------------------------------------------------------
  // Agregar al carrito
  // ------------------------------------------------------------------
  async function addToCart(button) {
    const id = button.dataset.addConcept;
    if (!id) return;
    const quantityField = document.querySelector('[data-qty-for="' + id + '"]');
    const cantidad = quantityField
      ? Math.max(1, Number(quantityField.value || 1))
      : Math.max(1, Number(button.dataset.cantidad || 1));

    App.setLoading(button, true, "Agregando…");
    try {
      const data = await App.api("/api/tienda/carrito", {
        method: "POST",
        body: { id_concepto: Number(id), cantidad: cantidad },
      });
      setCartCount(data.carrito_count);
      App.toast("Producto agregado al carrito.");
    } catch (error) {
      App.toast(error.message, "error");
    } finally {
      App.setLoading(button, false);
    }
  }

  // ------------------------------------------------------------------
  // Página del carrito
  // ------------------------------------------------------------------
  function refreshTotalFromRows() {
    let total = 0;
    document.querySelectorAll("[data-cart-row]").forEach((row) => {
      const price = Number(row.dataset.price || 0);
      const qtyElement = row.querySelector("[data-qty-value]");
      const qty = qtyElement ? Number(qtyElement.textContent || 0) : 0;
      const line = price * qty;
      const lineElement = row.querySelector("[data-line-price]");
      if (lineElement) {
        lineElement.textContent = App.money(line);
        lineElement.dataset.value = line;
      }
      total += line;
    });
    const totalElement = document.querySelector("[data-cart-total]");
    if (totalElement) totalElement.textContent = App.money(total);
    const linesElement = document.querySelector("[data-cart-lines]");
    if (linesElement) linesElement.textContent = document.querySelectorAll("[data-cart-row]").length;
    return total;
  }

  async function updateQuantity(button) {
    const row = button.closest("[data-cart-row]");
    if (!row) return;
    const conceptId = row.dataset.concept;
    const qtyElement = row.querySelector("[data-qty-value]");
    const current = qtyElement ? Number(qtyElement.textContent || 0) : 1;
    const next = current + Number(button.dataset.cartQty || 0);
    if (next <= 0) {
      if (!window.confirm("¿Quitar este producto del carrito?")) return;
      await removeCartRow(row);
      return;
    }
    button.disabled = true;
    try {
      const data = await App.api("/api/tienda/carrito/" + conceptId, {
        method: "PATCH",
        body: { cantidad: next },
      });
      if (qtyElement) qtyElement.textContent = data.cantidad;
      setCartCount(data.carrito_count);
      refreshTotalFromRows();
    } catch (error) {
      App.toast(error.message, "error");
    } finally {
      button.disabled = false;
    }
  }

  async function removeCartRow(row) {
    const conceptId = row.dataset.concept;
    try {
      const data = await App.api("/api/tienda/carrito/" + conceptId, { method: "DELETE" });
      row.remove();
      setCartCount(data.carrito_count);
      const remaining = document.querySelectorAll("[data-cart-row]").length;
      if (!remaining) {
        window.location.reload();
        return;
      }
      refreshTotalFromRows();
      App.toast("Producto eliminado.");
    } catch (error) {
      App.toast(error.message, "error");
    }
  }

  // ------------------------------------------------------------------
  // Checkout
  // ------------------------------------------------------------------
  function initCheckout() {
    const form = document.querySelector("[data-checkout-form]");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const data = App.formData(form);
      const metodo = form.querySelector('input[name="metodo"]:checked');
      if (!metodo) {
        App.toast("Selecciona un método de pago.", "error");
        return;
      }
      App.setLoading(button, true, "Procesando pago…");
      try {
        const result = await App.api("/api/tienda/checkout", {
          method: "POST",
          body: { metodo: metodo.value, referencia: data.referencia || "" },
        });
        setCartCount(0);
        App.toast("¡Pago confirmado! Redirigiendo a tu pedido…");
        window.setTimeout(() => {
          window.location.href = "/tienda/pedido/" + result.id_venta;
        }, 700);
      } catch (error) {
        App.toast(error.message, "error");
        App.setLoading(button, false);
      }
    });
  }

  // ------------------------------------------------------------------
  // Reservas
  // ------------------------------------------------------------------
  function initReservation() {
    const form = document.querySelector("[data-reservation-form]");
    if (!form) return;
    const dateField = form.querySelector('input[name="fecha"]');
    const timeField = form.querySelector('input[name="hora"]');
    if (dateField && !dateField.value) dateField.value = App.todayISO();
    if (timeField && !timeField.value) timeField.value = "09:00";

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const data = App.formData(form);
      if (!data.fecha || !data.hora) {
        App.toast("Selecciona la fecha y la hora de la cita.", "error");
        return;
      }
      data.fecha_ini = data.fecha + " " + data.hora;
      delete data.fecha;
      delete data.hora;
      if (data.servicio) {
        data.motivo = data.servicio;
        delete data.servicio;
      }
      App.setLoading(button, true, "Agendando…");
      try {
        await App.api("/api/tienda/reservas", { method: "POST", body: data });
        App.toast("Cita agendada. Te esperamos.");
        window.setTimeout(() => {
          window.location.href = "/tienda/cuenta?panel=reservas";
        }, 800);
      } catch (error) {
        App.toast(error.message, "error");
        App.setLoading(button, false);
      }
    });
  }

  // ------------------------------------------------------------------
  // Cuenta del cliente
  // ------------------------------------------------------------------
  function initAccountPanels() {
    const nav = document.querySelector(".account-nav");
    if (!nav) return;
    const params = new URLSearchParams(window.location.search);
    const panel = params.get("panel");
    if (!panel) return;
    const target = nav.querySelector('[data-tab="' + panel + '"]');
    if (target) target.click();
  }

  function initPetForm() {
    const form = document.querySelector("[data-pet-form]");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const data = App.formData(form);
      App.setLoading(button, true, "Guardando…");
      try {
        await App.api("/api/tienda/mis-mascotas", { method: "POST", body: data });
        App.toast("Mascota registrada.");
        window.setTimeout(() => window.location.reload(), 700);
      } catch (error) {
        App.toast(error.message, "error");
        App.setLoading(button, false);
      }
    });
  }

  function initProfileForm() {
    const form = document.querySelector("[data-profile-form]");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const data = App.formData(form);
      App.setLoading(button, true, "Guardando…");
      try {
        await App.api("/api/tienda/perfil", { method: "PATCH", body: data });
        App.toast("Datos actualizados.");
      } catch (error) {
        App.toast(error.message, "error");
      } finally {
        App.setLoading(button, false);
      }
    });
  }

  function initPasswordForm() {
    const form = document.querySelector("[data-password-form]");
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      const data = App.formData(form);
      if (data.nueva !== data.confirmar) {
        App.toast("La confirmación no coincide con la nueva contraseña.", "error");
        return;
      }
      delete data.confirmar;
      App.setLoading(button, true, "Actualizando…");
      try {
        await App.api("/api/perfil/contrasena", { method: "POST", body: data });
        form.reset();
        App.toast("Contraseña actualizada.");
      } catch (error) {
        App.toast(error.message, "error");
      } finally {
        App.setLoading(button, false);
      }
    });
  }

  // ------------------------------------------------------------------
  // Eventos globales
  // ------------------------------------------------------------------
  document.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-concept]");
    if (addButton) {
      event.preventDefault();
      addToCart(addButton);
      return;
    }
    const qtyButton = event.target.closest("[data-cart-qty]");
    if (qtyButton) {
      event.preventDefault();
      updateQuantity(qtyButton);
      return;
    }
    const removeButton = event.target.closest("[data-cart-remove]");
    if (removeButton) {
      event.preventDefault();
      const row = removeButton.closest("[data-cart-row]");
      if (row && window.confirm("¿Quitar este producto del carrito?")) removeCartRow(row);
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    setCartCount(currentCartCount());
    initCheckout();
    initReservation();
    initAccountPanels();
    initPetForm();
    initProfileForm();
    initPasswordForm();
  });
})();

(() => {
  function initToast() {
    const toast = document.querySelector("[data-toast]");
    if (!toast) {
      return;
    }

    let dismissed = false;

    function dismissToast() {
      if (dismissed) {
        return;
      }
      dismissed = true;
      toast.classList.add("is-dismissing");
      window.setTimeout(() => {
        toast.remove();
      }, 240);
    }

    toast.querySelector("[data-toast-close]")?.addEventListener("click", dismissToast);
    window.setTimeout(dismissToast, 3600);

    const url = new URL(window.location.href);
    if (url.searchParams.has("message")) {
      url.searchParams.delete("message");
      url.searchParams.delete("message_kind");
      const nextUrl = `${url.pathname}${url.searchParams.toString() ? `?${url.searchParams.toString()}` : ""}${url.hash}`;
      window.history.replaceState({}, "", nextUrl);
    }
  }

  function initConfirmModal() {
    const modalRoot = document.querySelector("[data-confirm-modal-root]");
    if (!modalRoot) {
      return;
    }

    const titleNode = modalRoot.querySelector("[data-confirm-modal-title]");
    const descriptionNode = modalRoot.querySelector("[data-confirm-modal-description]");
    const acceptButton = modalRoot.querySelector("[data-confirm-accept]");
    const cancelButton = modalRoot.querySelector("[data-confirm-cancel]");
    let activeForm = null;
    let previousFocus = null;

    function closeModal() {
      modalRoot.hidden = true;
      document.body.classList.remove("has-modal-open");
      activeForm = null;
      if (previousFocus instanceof HTMLElement) {
        previousFocus.focus();
      }
      previousFocus = null;
    }

    function submitConfirmedForm() {
      if (!(activeForm instanceof HTMLFormElement)) {
        closeModal();
        return;
      }
      activeForm.dataset.confirmBypassed = "true";
      closeModal();
      if (typeof activeForm.requestSubmit === "function") {
        activeForm.requestSubmit();
      } else {
        activeForm.submit();
      }
    }

    function openModal(form) {
      activeForm = form;
      previousFocus = document.activeElement;
      titleNode.textContent = form.dataset.confirmTitle || "Are you sure?";
      descriptionNode.textContent =
        form.dataset.confirmDescription || "This change will take effect immediately.";
      acceptButton.textContent = form.dataset.confirmAction || "Continue";
      cancelButton.textContent = form.dataset.confirmCancel || "Keep it";
      modalRoot.hidden = false;
      document.body.classList.add("has-modal-open");
      window.setTimeout(() => {
        acceptButton.focus();
      }, 0);
    }

    document.addEventListener(
      "submit",
      (event) => {
        const form = event.target instanceof HTMLFormElement ? event.target : null;
        if (!form || !form.dataset.confirmTitle) {
          return;
        }
        if (form.dataset.confirmBypassed === "true") {
          delete form.dataset.confirmBypassed;
          return;
        }
        event.preventDefault();
        openModal(form);
      },
      true,
    );

    acceptButton?.addEventListener("click", submitConfirmedForm);
    cancelButton?.addEventListener("click", closeModal);
    modalRoot.querySelectorAll("[data-confirm-close]").forEach((node) => {
      node.addEventListener("click", closeModal);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modalRoot.hidden) {
        closeModal();
      }
    });
  }

  initToast();
  initConfirmModal();
})();

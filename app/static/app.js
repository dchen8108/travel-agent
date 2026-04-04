(() => {
  const travelAgentApp = window.travelAgentApp || {};

  function readJsonScript(scriptId, fallbackValue = null) {
    const node = document.getElementById(scriptId);
    if (!node || !node.textContent) {
      return fallbackValue;
    }
    try {
      return JSON.parse(node.textContent);
    } catch (error) {
      console.error(`Could not parse JSON payload from #${scriptId}.`, error);
      return fallbackValue;
    }
  }

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
      const form = activeForm;
      form.dataset.confirmBypassed = "true";
      closeModal();
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit();
      } else {
        form.submit();
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

  function initCollectionOverflowToggles() {
    const clusters = Array.from(document.querySelectorAll("[data-collection-cluster]"));
    if (!clusters.length) {
      return;
    }

    const maxPreviewRows = 2;
    const controllers = [];

    clusters.forEach((cluster) => {
      if (!(cluster instanceof HTMLElement)) {
        return;
      }
      const preview = cluster.querySelector("[data-collection-preview]");
      const expandButton = cluster.querySelector("[data-collection-expand]");
      const collapseButton = cluster.querySelector("[data-collection-collapse]");
      if (
        !(preview instanceof HTMLElement) ||
        !(expandButton instanceof HTMLButtonElement) ||
        !(collapseButton instanceof HTMLButtonElement)
      ) {
        return;
      }

      const allPills = Array.from(preview.querySelectorAll("[data-collection-pill]"));
      let expanded = false;

      function rowCountForNodes(nodes) {
        const rowTops = [];
        nodes.forEach((node) => {
          const top = node.offsetTop;
          if (!rowTops.length || Math.abs(rowTops[rowTops.length - 1] - top) > 2) {
            rowTops.push(top);
          }
        });
        return rowTops.length;
      }

      function visibleCountWithExpandButton() {
        preview.replaceChildren(...allPills);
        if (rowCountForNodes(allPills) <= maxPreviewRows) {
          return allPills.length;
        }

        expandButton.hidden = false;
        for (let count = allPills.length - 1; count >= 0; count -= 1) {
          const overflowCount = allPills.length - count;
          expandButton.textContent = `+${overflowCount} more`;
          preview.replaceChildren(...allPills.slice(0, count), expandButton);
          if (rowCountForNodes(Array.from(preview.children)) <= maxPreviewRows) {
            return count;
          }
        }

        return 0;
      }

      function centerPreviewBlock() {
        preview.style.inlineSize = "";
        preview.style.marginInline = "";

        const children = Array.from(preview.children).filter(
          (node) => node instanceof HTMLElement && !node.hidden,
        );
        if (!children.length) {
          return;
        }

        const rows = [];
        children.forEach((node) => {
          const top = node.offsetTop;
          const left = node.offsetLeft;
          const right = left + node.offsetWidth;
          let row = rows.find((candidate) => Math.abs(candidate.top - top) <= 2);
          if (!row) {
            row = { top, left, right };
            rows.push(row);
            return;
          }
          row.left = Math.min(row.left, left);
          row.right = Math.max(row.right, right);
        });

        const widestRow = Math.max(...rows.map((row) => row.right - row.left));
        preview.style.inlineSize = `${Math.ceil(widestRow)}px`;
        preview.style.marginInline = "auto";
      }

      function render() {
        preview.replaceChildren();
        expandButton.hidden = true;
        collapseButton.hidden = true;
        expandButton.setAttribute("aria-expanded", expanded ? "true" : "false");
        collapseButton.setAttribute("aria-expanded", expanded ? "true" : "false");
        preview.style.inlineSize = "";
        preview.style.marginInline = "";

        if (!allPills.length) {
          return;
        }

        const visibleCount = visibleCountWithExpandButton();
        const previewPills = allPills.slice(0, visibleCount);
        const overflowPills = allPills.slice(visibleCount);

        if (!overflowPills.length) {
          expanded = false;
          preview.replaceChildren(...previewPills);
          centerPreviewBlock();
          return;
        }

        expandButton.textContent = `+${overflowPills.length} more`;
        expandButton.setAttribute("aria-expanded", expanded ? "true" : "false");

        if (expanded) {
          collapseButton.hidden = false;
          preview.replaceChildren(...allPills, collapseButton);
        } else {
          expandButton.hidden = false;
          preview.replaceChildren(...previewPills, expandButton);
        }
        centerPreviewBlock();
      }

      expandButton.addEventListener("click", () => {
        expanded = true;
        render();
      });

      collapseButton.addEventListener("click", () => {
        expanded = false;
        render();
      });

      controllers.push(render);
    });

    let resizeFrame = 0;
    const rerender = () => {
      controllers.forEach((render) => render());
    };
    window.requestAnimationFrame(rerender);
    window.addEventListener("resize", () => {
      if (resizeFrame) {
        window.cancelAnimationFrame(resizeFrame);
      }
      resizeFrame = window.requestAnimationFrame(() => {
        rerender();
        resizeFrame = 0;
      });
    });
  }

  travelAgentApp.readJsonScript = readJsonScript;
  window.travelAgentApp = travelAgentApp;

  initToast();
  initConfirmModal();
  initCollectionOverflowToggles();
})();

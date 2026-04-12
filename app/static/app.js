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

  function parseJsonText(text, fallbackValue = null) {
    if (!text) {
      return fallbackValue;
    }
    try {
      return JSON.parse(text);
    } catch (error) {
      console.error("Could not parse JSON payload.", error);
      return fallbackValue;
    }
  }

  function initBookingForms(root = document, attempt = 0) {
    const pickers = window.travelAgentPickers;
    const forms = [];
    if (root instanceof HTMLElement && root.matches("[data-booking-form]")) {
      forms.push(root);
    }
    if (root instanceof Document || root instanceof HTMLElement) {
      forms.push(...root.querySelectorAll("[data-booking-form]"));
    }
    if (!forms.length) {
      return;
    }
    if (!pickers) {
      if (attempt < 20) {
        window.setTimeout(() => initBookingForms(root, attempt + 1), 50);
      }
      return;
    }

    forms.forEach((form) => {
      if (!(form instanceof HTMLElement) || form.dataset.bookingFormInitialized === "true") {
        return;
      }
      const dataNode = form.querySelector("[data-booking-form-data]");
      const bookingState = parseJsonText(dataNode?.textContent || "", null);
      const catalogs = bookingState?.catalogs || {};
      form.querySelectorAll("[data-single-picker-field]").forEach((field) => {
        if (!(field instanceof HTMLElement)) {
          return;
        }
        const type = field.dataset.pickerType;
        const options = type === "airline" ? (catalogs.airlines || []) : (catalogs.airports || []);
        pickers.createSinglePicker({ field, options });
      });
      form.dataset.bookingFormInitialized = "true";
    });
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

  function initPanelModal() {
    const modalRoot = document.querySelector("[data-panel-modal-root]");
    if (!modalRoot) {
      return;
    }

    const contentNode = modalRoot.querySelector("[data-panel-modal-content]");
    let previousFocus = null;
    let restoreUrl = "";

    function dashboardUrlWithoutPanelParams() {
      const url = new URL(window.location.href);
      url.searchParams.delete("panel");
      url.searchParams.delete("trip_instance_id");
      url.searchParams.delete("booking_mode");
      url.searchParams.delete("booking_id");
      return `${url.pathname}${url.search ? url.search : ""}${url.hash}`;
    }

    function hydratePanelContent(root) {
      initBookingForms(root);
    }

    function closeModal() {
      modalRoot.hidden = true;
      document.body.classList.remove("has-modal-open");
      if (contentNode instanceof HTMLElement) {
        contentNode.innerHTML = "";
      }
      if (restoreUrl) {
        window.history.replaceState({}, "", restoreUrl);
      }
      if (previousFocus instanceof HTMLElement) {
        previousFocus.focus();
      }
      previousFocus = null;
      restoreUrl = "";
    }

    async function openModal(fetchUrl, historyUrl, { preserveHistory = false } = {}) {
      if (!(contentNode instanceof HTMLElement) || !fetchUrl) {
        return;
      }

      previousFocus = document.activeElement;
      restoreUrl = dashboardUrlWithoutPanelParams();
      modalRoot.hidden = false;
      document.body.classList.add("has-modal-open");
      contentNode.innerHTML = '<div class="panel-modal-loading">Loading…</div>';
      if (!preserveHistory && historyUrl) {
        window.history.replaceState({}, "", historyUrl);
      }

      try {
        const response = await window.fetch(fetchUrl, {
          headers: {
            "X-Requested-With": "fetch",
          },
        });
        if (!response.ok) {
          throw new Error(`Failed to load panel ${fetchUrl}`);
        }
        contentNode.innerHTML = await response.text();
        hydratePanelContent(contentNode);
      } catch (error) {
        console.error(error);
        contentNode.innerHTML = '<div class="compact-empty-state"><strong>Could not load this view.</strong><p>Try again in a moment.</p></div>';
      }
    }

    async function submitPanelForm(form) {
      if (!(contentNode instanceof HTMLElement)) {
        return;
      }
      const response = await window.fetch(form.action, {
        method: (form.method || "post").toUpperCase(),
        headers: {
          "X-Requested-With": "fetch",
        },
        body: new window.FormData(form),
      });
      const nextHistoryUrl = response.headers.get("X-Panel-History-Url");
      contentNode.innerHTML = await response.text();
      if (nextHistoryUrl) {
        window.history.replaceState({}, "", nextHistoryUrl);
      }
      hydratePanelContent(contentNode);
    }

    document.addEventListener("click", (event) => {
      const trigger = event.target instanceof Element ? event.target.closest("[data-panel-modal-url]") : null;
      if (!(trigger instanceof HTMLElement)) {
        return;
      }
      event.preventDefault();
      const fetchUrl = trigger.dataset.panelModalUrl || "";
      const historyUrl = trigger.dataset.panelHistoryUrl || "";
      void openModal(fetchUrl, historyUrl);
    });

    document.addEventListener(
      "submit",
      (event) => {
        const form = event.target instanceof HTMLFormElement ? event.target : null;
        if (!form || !form.matches("[data-panel-form]")) {
          return;
        }
        if (!form.closest("[data-panel-modal-content]")) {
          return;
        }
        event.preventDefault();
        void submitPanelForm(form);
      },
      true,
    );

    modalRoot.querySelectorAll("[data-panel-modal-close]").forEach((node) => {
      node.addEventListener("click", closeModal);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modalRoot.hidden) {
        closeModal();
      }
    });

    const url = new URL(window.location.href);
    const panel = url.searchParams.get("panel");
    const tripInstanceId = url.searchParams.get("trip_instance_id");
    if (panel && tripInstanceId && (panel === "bookings" || panel === "trackers")) {
      const panelParams = new URLSearchParams();
      if (panel === "bookings") {
        const bookingMode = url.searchParams.get("booking_mode");
        const bookingId = url.searchParams.get("booking_id");
        if (bookingMode) {
          panelParams.set("booking_mode", bookingMode);
        }
        if (bookingId) {
          panelParams.set("booking_id", bookingId);
        }
      }
      const fetchUrl = `/trip-instances/${tripInstanceId}/${panel}-panel${panelParams.toString() ? `?${panelParams.toString()}` : ""}`;
      void openModal(fetchUrl, "", { preserveHistory: true });
    }
  }

  travelAgentApp.readJsonScript = readJsonScript;
  travelAgentApp.initBookingForms = initBookingForms;
  window.travelAgentApp = travelAgentApp;

  initToast();
  initConfirmModal();
  initPanelModal();
  initCollectionOverflowToggles();
  initBookingForms();
})();

(() => {
  const scheduledFiltersState = window.travelAgentApp?.readJsonScript("scheduled-filters-data");
  const pickers = window.travelAgentPickers;
  if (!scheduledFiltersState || !pickers) {
    return;
  }

  const scheduledSearchDebounceMs = 90;
  let scheduledFilterRequestToken = 0;
  let scheduledFilterAbortController = null;

  function initScheduledFilters(scope = document) {
    const panel = scope.querySelector("[data-scheduled-panel]");
    const form = scope.querySelector("[data-scheduled-filter-form]");
    if (!panel || !form || form.dataset.bound === "true") {
      return;
    }
    form.dataset.bound = "true";

    const searchInput = form.querySelector("[data-filter-search]");
    const recurringRoot = form.querySelector("[data-recurring-filter-root]");
    const hiddenInputsRoot = form.querySelector("[data-recurring-hidden-inputs]");
    let resultsShell = panel.querySelector("[data-scheduled-results-shell]");
    const skippedToggle = form.querySelector("[data-skipped-toggle]");
    const skippedInput = form.querySelector("[data-skipped-input]");
    const clearLink = form.querySelector("[data-clear-filters]");
    let debounceTimer = null;

    if (!searchInput || !recurringRoot || !hiddenInputsRoot || !skippedToggle || !skippedInput) {
      return;
    }

    function selectedRecurringTripIds() {
      return Array.from(hiddenInputsRoot.querySelectorAll('input[name="recurring_trip_id"]'))
        .map((input) => input.value)
        .filter(Boolean);
    }

    function setSelectedRecurringTripIds(values) {
      hiddenInputsRoot.innerHTML = "";
      values.forEach((value) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "recurring_trip_id";
        input.value = value;
        hiddenInputsRoot.appendChild(input);
      });
    }

    function setSkippedState(enabled) {
      skippedInput.value = enabled ? "true" : "";
      skippedToggle.classList.toggle("is-on", enabled);
      skippedToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    }

    function buildQuery() {
      const params = new URLSearchParams();
      const query = (searchInput.value || "").trim();
      if (query) {
        params.set("q", query);
      }
      if (skippedInput.value) {
        params.set("show_skipped", "true");
      }
      selectedRecurringTripIds().forEach((value) => {
        params.append("recurring_trip_id", value);
      });
      return params;
    }

    async function refreshScheduledPanel(params, { preservePickerUi = false } = {}) {
      if (!preservePickerUi) {
        pickers.closeAllPickers();
      }
      if (!resultsShell) {
        window.location.assign(`/trips${params.toString() ? `?${params.toString()}` : ""}`);
        return;
      }
      const pageQuery = params.toString();
      const pageUrl = `/trips${pageQuery ? `?${pageQuery}` : ""}`;
      const partialParams = new URLSearchParams(params);
      partialParams.set("partial", "scheduled-results");
      const partialUrl = `/trips?${partialParams.toString()}`;
      const requestToken = scheduledFilterRequestToken + 1;
      scheduledFilterRequestToken = requestToken;
      scheduledFilterAbortController?.abort();
      scheduledFilterAbortController = new AbortController();

      try {
        const response = await fetch(partialUrl, {
          headers: { "X-Requested-With": "fetch" },
          signal: scheduledFilterAbortController.signal,
        });
        if (!response.ok) {
          throw new Error(`Unexpected response ${response.status}`);
        }
        if (requestToken !== scheduledFilterRequestToken) {
          return;
        }
        resultsShell.outerHTML = await response.text();
        resultsShell = panel.querySelector("[data-scheduled-results-shell]");
        window.history.replaceState({}, "", pageUrl);
      } catch (error) {
        if (error?.name === "AbortError") {
          return;
        }
        window.location.assign(pageUrl);
      }
    }

    function submitFilters({ debounce = false, preservePickerUi = false } = {}) {
      if (debounce) {
        window.clearTimeout(debounceTimer);
        debounceTimer = window.setTimeout(() => {
          refreshScheduledPanel(buildQuery(), { preservePickerUi });
        }, scheduledSearchDebounceMs);
        return;
      }
      window.clearTimeout(debounceTimer);
      refreshScheduledPanel(buildQuery(), { preservePickerUi });
    }

    pickers.createMultiPicker({
      root: recurringRoot,
      options: scheduledFiltersState.recurringOptions || [],
      values: selectedRecurringTripIds(),
      placeholder: "Search recurring trips",
      emptyText: "All recurring trips",
      compact: true,
      checkable: true,
      allowSelectAll: true,
      summaryFormatter(values, options, emptyText) {
        if (!values.length) {
          return emptyText;
        }
        if (values.length === 1) {
          return options.find((option) => option.value === values[0])?.label || values[0];
        }
        return `${values.length} recurring trips selected`;
      },
      onChange(values) {
        setSelectedRecurringTripIds(values);
        submitFilters({ preservePickerUi: true });
      },
    });

    searchInput.addEventListener("input", () => submitFilters({ debounce: true }));
    searchInput.addEventListener("search", () => submitFilters());
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        submitFilters();
      }
    });

    skippedToggle.addEventListener("click", () => {
      setSkippedState(!skippedInput.value);
      submitFilters();
    });

    clearLink?.addEventListener("click", (event) => {
      event.preventDefault();
      window.clearTimeout(debounceTimer);
      searchInput.value = "";
      setSelectedRecurringTripIds([]);
      setSkippedState(false);
      submitFilters();
    });
  }

  initScheduledFilters();
})();

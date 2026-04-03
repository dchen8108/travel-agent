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
    const groupRoot = form.querySelector("[data-group-filter-root]");
    const hiddenInputsRoot = form.querySelector("[data-group-hidden-inputs]");
    let resultsShell = panel.querySelector("[data-scheduled-results-shell]");
    const clearLink = form.querySelector("[data-clear-filters]");
    let debounceTimer = null;

    if (!searchInput || !groupRoot || !hiddenInputsRoot) {
      return;
    }

    function selectedTripGroupIds() {
      return Array.from(hiddenInputsRoot.querySelectorAll('input[name="trip_group_id"]'))
        .map((input) => input.value)
        .filter(Boolean);
    }

    function setSelectedTripGroupIds(values) {
      hiddenInputsRoot.innerHTML = "";
      values.forEach((value) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "trip_group_id";
        input.value = value;
        hiddenInputsRoot.appendChild(input);
      });
    }

    function buildQuery() {
      const params = new URLSearchParams();
      const query = (searchInput.value || "").trim();
      if (query) {
        params.set("q", query);
      }
      selectedTripGroupIds().forEach((value) => {
        params.append("trip_group_id", value);
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
      root: groupRoot,
      options: scheduledFiltersState.groupOptions || [],
      values: selectedTripGroupIds(),
      placeholder: "Search trip groups",
      emptyText: "All trip groups",
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
        return `${values.length} groups selected`;
      },
      onChange(values) {
        setSelectedTripGroupIds(values);
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

    clearLink?.addEventListener("click", (event) => {
      event.preventDefault();
      window.clearTimeout(debounceTimer);
      searchInput.value = "";
      setSelectedTripGroupIds([]);
      submitFilters();
    });
  }

  initScheduledFilters();
})();

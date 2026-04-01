(() => {
  const tripState = window.travelAgentTripForm;
  const bookingState = window.travelAgentBookingForm;
  const pickerRegistry = [];
  const scheduledSearchDebounceMs = 90;
  let scheduledFilterRequestToken = 0;
  let scheduledFilterAbortController = null;

  function pruneDetachedPickers() {
    for (let index = pickerRegistry.length - 1; index >= 0; index -= 1) {
      if (!pickerRegistry[index].root.isConnected) {
        pickerRegistry.splice(index, 1);
      }
    }
  }

  function registerPicker(root, close) {
    pruneDetachedPickers();
    for (let index = pickerRegistry.length - 1; index >= 0; index -= 1) {
      if (pickerRegistry[index].root === root) {
        pickerRegistry.splice(index, 1);
      }
    }
    pickerRegistry.push({ root, close });
  }

  function closeOtherPickers(currentRoot = null) {
    pruneDetachedPickers();
    pickerRegistry.forEach((picker) => {
      if (!currentRoot || picker.root !== currentRoot) {
        picker.close();
      }
    });
  }

  document.addEventListener("pointerdown", (event) => {
    pruneDetachedPickers();
    pickerRegistry.forEach((picker) => {
      if (!picker.root.contains(event.target)) {
        picker.close();
      }
    });
  });

  function buildSearchText(option) {
    return [option.value, option.label, option.keywords || ""].join(" ").toLowerCase();
  }

  function formatOption(option) {
    return option.label ? `${option.value} · ${option.label}` : option.value;
  }

  function createMultiPicker({
    root,
    options,
    values,
    placeholder,
    emptyText = "No selections",
    maxSelections = Number.POSITIVE_INFINITY,
    compact = false,
    checkable = false,
    allowSelectAll = false,
    summaryFormatter = null,
    onChange
  }) {
    const state = { values: Array.from(values || []) };
    if (!compact) {
      root.innerHTML = `
        <div class="multi-select">
          <div class="chip-list" data-chip-list></div>
          <div class="multi-select-control">
            <div class="multi-select-input-row">
              <input type="text" data-search placeholder="${placeholder}" autocomplete="off" spellcheck="false">
            </div>
            <div class="multi-select-menu" data-menu hidden></div>
          </div>
        </div>
      `;
      const chipList = root.querySelector("[data-chip-list]");
      const search = root.querySelector("[data-search]");
      const menu = root.querySelector("[data-menu]");
      let closeMenuTimer = null;

      function closeMenu() {
        if (closeMenuTimer) {
          window.clearTimeout(closeMenuTimer);
          closeMenuTimer = null;
        }
        menu.hidden = true;
      }

      function renderChips() {
        chipList.innerHTML = "";
        state.values.forEach((value, index) => {
          const option = options.find((item) => item.value === value);
          if (!option) return;
          const chip = document.createElement("span");
          chip.className = "chip";
          const text = document.createElement("span");
          text.textContent = formatOption(option);
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "chip-remove-button";
          remove.setAttribute("aria-label", `Remove ${formatOption(option)}`);
          remove.textContent = "×";
          remove.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            state.values = state.values.filter((_, itemIndex) => itemIndex !== index);
            renderChips();
            renderMenu(search.value);
            onChange(Array.from(state.values));
            search.focus();
          });
          chip.append(text, remove);
          chipList.appendChild(chip);
        });
        if (!state.values.length) {
          const empty = document.createElement("span");
          empty.className = "chip-empty";
          empty.textContent = emptyText;
          chipList.appendChild(empty);
        }
      }

      function renderMenu(query = "") {
        const normalized = query.trim().toLowerCase();
        menu.innerHTML = "";
        if (state.values.length >= maxSelections) {
          const empty = document.createElement("p");
          empty.className = "picker-empty-state";
          empty.textContent = `Maximum reached (${maxSelections}). Remove one to add another.`;
          menu.appendChild(empty);
          menu.hidden = false;
          return;
        }
        const matches = options
          .filter((option) => !state.values.includes(option.value))
          .filter((option) => !normalized || buildSearchText(option).includes(normalized))
          .slice(0, 10);
        if (!matches.length) {
          closeMenu();
          return;
        }
        matches.forEach((option) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "multi-select-option";
          button.textContent = formatOption(option);
          button.addEventListener("mousedown", (event) => {
            event.preventDefault();
            state.values = [...state.values, option.value];
            renderChips();
            onChange(Array.from(state.values));
            search.value = "";
            renderMenu("");
          });
          menu.appendChild(button);
        });
        menu.hidden = false;
      }

      renderChips();
      registerPicker(root, closeMenu);
      search.addEventListener("focus", () => {
        if (closeMenuTimer) {
          window.clearTimeout(closeMenuTimer);
          closeMenuTimer = null;
        }
        closeOtherPickers(root);
        renderMenu(search.value);
      });
      search.addEventListener("input", () => renderMenu(search.value));
      search.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          closeMenu();
          search.blur();
        }
      });
      search.addEventListener("blur", () => {
        closeMenuTimer = window.setTimeout(() => {
          closeMenu();
        }, 150);
      });
      return;
    }

    root.innerHTML = `
      <div class="picker ${compact ? "is-compact" : ""}">
        ${compact ? "" : '<div class="picker-selection" data-selection></div>'}
        <button type="button" class="picker-trigger" data-trigger aria-expanded="false"></button>
        <div class="picker-popover" data-popover hidden>
          <div class="picker-popover-header">
            <input type="text" data-search placeholder="${placeholder}" autocomplete="off" spellcheck="false">
            ${Number.isFinite(maxSelections) ? '<span class="picker-count" data-count></span>' : ""}
          </div>
          <div class="picker-menu" data-menu></div>
        </div>
      </div>
    `;
    const selection = root.querySelector("[data-selection]");
    const trigger = root.querySelector("[data-trigger]");
    const popover = root.querySelector("[data-popover]");
    const search = root.querySelector("[data-search]");
    const menu = root.querySelector("[data-menu]");
    const count = root.querySelector("[data-count]");
    const header = root.querySelector(".picker-popover-header");

    function renderTrigger() {
      if (compact) {
        if (summaryFormatter) {
          trigger.textContent = summaryFormatter(Array.from(state.values), options, emptyText);
        } else if (!state.values.length) {
          trigger.textContent = emptyText;
        } else {
          const selectedLabels = state.values
            .map((value) => options.find((item) => item.value === value)?.label || value)
            .filter(Boolean);
          if (selectedLabels.length <= 2) {
            trigger.textContent = selectedLabels.join(", ");
          } else {
            trigger.textContent = `${selectedLabels.slice(0, 2).join(", ")} +${selectedLabels.length - 2}`;
          }
        }
        trigger.classList.toggle("has-value", state.values.length > 0);
        trigger.classList.toggle("is-empty", state.values.length === 0);
        return;
      }
      trigger.textContent = state.values.length >= maxSelections
        ? `Maximum selected (${state.values.length}/${maxSelections})`
        : placeholder;
      trigger.classList.toggle("has-value", state.values.length > 0);
    }

    function closeMenu() {
      popover.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
    }

    function openMenu() {
      closeOtherPickers(root);
      popover.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      search.focus();
      renderMenu(search.value);
    }

    function renderSelection() {
      if (!selection) {
        return;
      }
      selection.innerHTML = "";
      state.values.forEach((value, index) => {
        const option = options.find((item) => item.value === value);
        if (!option) return;
        const chip = document.createElement("span");
        chip.className = "chip";
        const text = document.createElement("span");
        text.textContent = formatOption(option);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "chip-remove-button";
        remove.setAttribute("aria-label", `Remove ${formatOption(option)}`);
        remove.textContent = "×";
        remove.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          state.values = state.values.filter((_, itemIndex) => itemIndex !== index);
          renderSelection();
          renderTrigger();
          renderMenu(search.value);
          onChange(Array.from(state.values));
        });
        chip.append(text, remove);
        selection.appendChild(chip);
      });
      if (!state.values.length) {
        const empty = document.createElement("span");
        empty.className = "chip-empty";
        empty.textContent = emptyText;
        selection.appendChild(empty);
      }
    }

    function renderMenu(query = "") {
      const normalized = query.trim().toLowerCase();
      if (!compact && state.values.length >= maxSelections) {
        menu.innerHTML = "";
        if (count) {
          count.textContent = `${state.values.length}/${maxSelections}`;
        }
        const empty = document.createElement("p");
        empty.className = "picker-empty-state";
        empty.textContent = `Maximum reached (${maxSelections}). Remove one to add another.`;
        menu.appendChild(empty);
        return;
      }
      const matches = options
        .filter((option) => compact || !state.values.includes(option.value))
        .filter((option) => !normalized || buildSearchText(option).includes(normalized))
        .sort((left, right) => {
          if (!compact) return 0;
          return Number(state.values.includes(right.value)) - Number(state.values.includes(left.value));
        })
        .slice(0, 10);
      menu.innerHTML = "";
      const canSelectAll = allowSelectAll && compact && options.length > 1;
      if (count) {
        count.textContent = Number.isFinite(maxSelections)
          ? `${state.values.length}/${maxSelections}`
          : `${state.values.length}`;
      }
      if (header) {
        const existingActions = header.querySelector(".picker-actions");
        existingActions?.remove();
        if (canSelectAll) {
          const actions = document.createElement("div");
          actions.className = "picker-actions";

          const selectAllButton = document.createElement("button");
          selectAllButton.type = "button";
          selectAllButton.className = "picker-action";
          selectAllButton.textContent = "Select all";
          selectAllButton.disabled = state.values.length === options.length;
          selectAllButton.addEventListener("click", (event) => {
            event.preventDefault();
            state.values = options.map((option) => option.value);
            renderSelection();
            renderTrigger();
            renderMenu(search.value);
            onChange(Array.from(state.values));
          });

          const clearButton = document.createElement("button");
          clearButton.type = "button";
          clearButton.className = "picker-action";
          clearButton.textContent = "Clear";
          clearButton.disabled = state.values.length === 0;
          clearButton.addEventListener("click", (event) => {
            event.preventDefault();
            state.values = [];
            renderSelection();
            renderTrigger();
            renderMenu(search.value);
            onChange(Array.from(state.values));
          });

          actions.append(selectAllButton, clearButton);
          header.appendChild(actions);
        }
      }
      if (!matches.length) {
        const empty = document.createElement("p");
        empty.className = "picker-empty-state";
        empty.textContent = state.values.length >= maxSelections
          ? `Maximum reached (${maxSelections}). Remove one to add another.`
          : "No matching options.";
        menu.appendChild(empty);
        return;
      }
      matches.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "picker-option";
        const alreadySelected = state.values.includes(option.value);
        button.classList.toggle("is-selected", alreadySelected);
        button.setAttribute("aria-pressed", alreadySelected ? "true" : "false");
        if (checkable) {
          button.innerHTML = `
            <span class="picker-option-check" aria-hidden="true">${alreadySelected ? "✓" : ""}</span>
            <span class="picker-option-label">${formatOption(option)}</span>
          `;
        } else {
          button.textContent = formatOption(option);
        }
        button.addEventListener("click", (event) => {
          event.preventDefault();
          if (alreadySelected && compact) {
            state.values = state.values.filter((value) => value !== option.value);
          } else if (!alreadySelected && state.values.length < maxSelections) {
            state.values = [...state.values, option.value];
          }
          renderSelection();
          renderTrigger();
          renderMenu(search.value);
          onChange(Array.from(state.values));
          if (!compact) {
            search.value = "";
            renderMenu("");
          }
        });
        menu.appendChild(button);
      });
    }

    renderSelection();
    renderTrigger();

    registerPicker(root, closeMenu);
    trigger.addEventListener("click", () => {
      if (!popover.hidden) {
        closeMenu();
        return;
      }
      openMenu();
    });
    search.addEventListener("input", () => renderMenu(search.value));
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeMenu();
        trigger.focus();
      }
    });
  }

  function createSinglePicker({ field, options }) {
    const hidden = field.querySelector('input[type="hidden"]');
    const root = field.querySelector("[data-picker-root]");
    const pickerType = field.dataset.pickerType;
    const placeholder = pickerType === "airline" ? "Search airlines" : "Search airports";
    const state = { value: hidden.value || "" };
    root.innerHTML = `
      <div class="multi-select">
        <div class="chip-list" data-chip-list></div>
        <div class="multi-select-control">
          <div class="multi-select-input-row">
            <input type="text" data-search placeholder="${placeholder}" autocomplete="off" spellcheck="false">
          </div>
          <div class="multi-select-menu" data-menu hidden></div>
        </div>
      </div>
    `;
    const chipList = root.querySelector("[data-chip-list]");
    const search = root.querySelector("[data-search]");
    const menu = root.querySelector("[data-menu]");
    let closeMenuTimer = null;

    function closeMenu() {
      if (closeMenuTimer) {
        window.clearTimeout(closeMenuTimer);
        closeMenuTimer = null;
      }
      menu.hidden = true;
    }

    function renderChip() {
      chipList.innerHTML = "";
      const option = options.find((item) => item.value === state.value);
      if (!option) {
        const empty = document.createElement("span");
        empty.className = "chip-empty";
        empty.textContent = "No selection";
        chipList.appendChild(empty);
        return;
      }
      const chip = document.createElement("span");
      chip.className = "chip";
      const text = document.createElement("span");
      text.textContent = formatOption(option);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "chip-remove-button";
      remove.setAttribute("aria-label", `Remove ${formatOption(option)}`);
      remove.textContent = "×";
      remove.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        state.value = "";
        hidden.value = "";
        renderChip();
        renderMenu(search.value || "");
        search.focus();
      });
      chip.append(text, remove);
      chipList.appendChild(chip);
    }

    function renderMenu(query = "") {
      const normalized = query.trim().toLowerCase();
      const matches = options
        .filter((option) => !normalized || buildSearchText(option).includes(normalized))
        .slice(0, 10);
      menu.innerHTML = "";
      if (!matches.length) {
        const empty = document.createElement("p");
        empty.className = "picker-empty-state";
        empty.textContent = "No matching options.";
        menu.appendChild(empty);
        menu.hidden = false;
        return;
      }
      matches.forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "multi-select-option";
        button.textContent = formatOption(option);
        button.addEventListener("mousedown", (event) => {
          event.preventDefault();
          state.value = option.value;
          hidden.value = option.value;
          search.value = "";
          renderChip();
          closeMenu();
        });
        menu.appendChild(button);
      });
      menu.hidden = false;
    }

    renderChip();
    registerPicker(root, closeMenu);
    search.addEventListener("focus", () => {
      if (closeMenuTimer) {
        window.clearTimeout(closeMenuTimer);
        closeMenuTimer = null;
      }
      closeOtherPickers(root);
      renderMenu(search.value);
    });
    search.addEventListener("input", () => renderMenu(search.value));
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeMenu();
        search.blur();
      }
    });
    search.addEventListener("blur", () => {
      closeMenuTimer = window.setTimeout(() => {
        closeMenu();
      }, 150);
    });
  }

  if (tripState) {
    const form = document.querySelector("#trip-form");
    const root = form?.querySelector("[data-route-options]");
    const hidden = form?.querySelector('input[name="route_options_json"]');
    const tripKindSelect = form?.querySelector("[data-trip-kind]");
    const preferenceModeInputs = Array.from(form?.querySelectorAll('input[name="preference_mode"]') || []);
    const anchorWeekdaySelect = form?.querySelector("[data-anchor-weekday]");
    const anchorDateField = form?.querySelector("[data-anchor-date-field]");
    const anchorWeekdayField = form?.querySelector("[data-anchor-weekday-field]");
    const catalogs = tripState.catalogs || {};
    const airports = catalogs.airports || [];
    const airlines = catalogs.airlines || [];

    const weekdays = catalogs.weekdays || ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
    let routeOptions = Array.isArray(tripState.routeOptions) && tripState.routeOptions.length
      ? tripState.routeOptions
        : [{
          route_option_id: "",
          savings_needed_vs_previous: 0,
          origin_airports: [],
          destination_airports: [],
          airlines: [],
          day_offset: 0,
          start_time: "",
          end_time: "",
          fare_class_policy: "include_basic"
        }];

    function currentPreferenceMode() {
      return preferenceModeInputs.find((input) => input.checked)?.value || tripState.trip?.preference_mode || "equal";
    }

    function currentAnchorWeekday() {
      if (tripKindSelect.value === "weekly") {
        return anchorWeekdaySelect.value || "Monday";
      }
      const anchorDateValue = form.querySelector('input[name="anchor_date"]').value;
      if (!anchorDateValue) return "Monday";
      const date = new Date(`${anchorDateValue}T12:00:00`);
      return weekdays[(date.getDay() + 6) % 7];
    }

    function dayOptions(anchorWeekday) {
      const index = weekdays.indexOf(anchorWeekday);
      return [-1, 0, 1].map((offset) => ({
        value: offset,
        label: `${weekdays[(index + offset + weekdays.length) % weekdays.length]} (${offset === 0 ? "T" : `T${offset > 0 ? `+${offset}` : offset}`})`
      }));
    }

    function serialize() {
      hidden.value = JSON.stringify(routeOptions.map((option) => ({
        route_option_id: option.route_option_id || "",
        savings_needed_vs_previous: Number(option.savings_needed_vs_previous || 0),
        origin_airports: option.origin_airports,
        destination_airports: option.destination_airports,
        airlines: option.airlines,
        day_offset: Number(option.day_offset),
        start_time: option.start_time,
        end_time: option.end_time,
        fare_class_policy: option.fare_class_policy || "include_basic"
      })));
    }

    function syncKindVisibility() {
      const oneTime = tripKindSelect.value === "one_time";
      anchorDateField.classList.toggle("is-hidden", !oneTime);
      anchorWeekdayField.classList.toggle("is-hidden", oneTime);
      render();
    }

    function render() {
      root.innerHTML = "";
      const anchorWeekday = currentAnchorWeekday();
      const preferenceMode = currentPreferenceMode();
      const biasEnabled = preferenceMode === "ranked_bias";
      routeOptions.forEach((option, index) => {
        const pairwiseBias = index === 0 ? 0 : Number(option.savings_needed_vs_previous || 0);
        const card = document.createElement("article");
        card.className = "route-option-card";
        card.innerHTML = `
          <div class="card-header">
            <div>
              <strong>Option ${index + 1}</strong>
              <p class="muted">One tracker definition.</p>
            </div>
            <div class="inline-actions">
              <button type="button" class="button ghost" data-move-up ${index === 0 ? "disabled" : ""}>Up</button>
              <button type="button" class="button ghost" data-move-down ${index === routeOptions.length - 1 ? "disabled" : ""}>Down</button>
              <button type="button" class="button danger" data-remove>Remove</button>
            </div>
          </div>
          <div class="form-grid">
            <div class="field"><span>Origin airports</span><div data-field="origin_airports"></div></div>
            <div class="field"><span>Destination airports</span><div data-field="destination_airports"></div></div>
            <div class="field"><span>Airlines</span><div data-field="airlines"></div></div>
            <div class="field"><span>Relative day</span><select data-field="day_offset"></select></div>
            <div class="field"><span>Departure range start</span><input type="time" data-field="start_time" value="${option.start_time}"></div>
            <div class="field"><span>Departure range end</span><input type="time" data-field="end_time" value="${option.end_time}"></div>
            <div class="field full-width fare-policy-field">
              <span>Fare policy</span>
              <div class="fare-policy-grid" data-field="fare_class_policy">
                <label class="choice-card compact">
                  <input type="radio" name="fare_class_policy_${index}" value="include_basic" ${(!option.fare_class_policy || option.fare_class_policy === "include_basic") ? "checked" : ""}>
                  <span>
                    <strong>Include Basic</strong>
                    <small>Track the cheapest economy result even if it is a more restrictive basic fare.</small>
                  </span>
                </label>
                <label class="choice-card compact">
                  <input type="radio" name="fare_class_policy_${index}" value="exclude_basic" ${option.fare_class_policy === "exclude_basic" ? "checked" : ""}>
                  <span>
                    <strong>Exclude Basic</strong>
                    <small>Only compare standard-or-better economy fares.</small>
                  </span>
                </label>
              </div>
            </div>
            ${biasEnabled ? `
              <div class="field preference-threshold-field ${index === 0 ? "is-readonly" : ""}">
                <span>${index === 0 ? "Preference buffer" : `Savings needed vs option ${index}`}</span>
                ${
                  index === 0
                    ? '<p class="muted">Top preference. Lower-ranked options need savings to beat it.</p>'
                    : `<input type="number" min="0" step="1" data-field="savings_needed_vs_previous" value="${pairwiseBias}">
                       <small class="muted">Must be at least $${pairwiseBias} cheaper than option ${index}.</small>`
                }
              </div>
            ` : ""}
          </div>
        `;
        const daySelect = card.querySelector('[data-field="day_offset"]');
        dayOptions(anchorWeekday).forEach((choice) => {
          const optionEl = document.createElement("option");
          optionEl.value = String(choice.value);
          optionEl.textContent = choice.label;
          if (Number(option.day_offset) === choice.value) optionEl.selected = true;
          daySelect.appendChild(optionEl);
        });
        daySelect.addEventListener("change", () => {
          option.day_offset = Number(daySelect.value);
          serialize();
        });
        card.querySelector('[data-field="start_time"]').addEventListener("input", (event) => {
          option.start_time = event.target.value;
          serialize();
        });
        card.querySelector('[data-field="end_time"]').addEventListener("input", (event) => {
          option.end_time = event.target.value;
          serialize();
        });
        card.querySelectorAll(`input[name="fare_class_policy_${index}"]`).forEach((input) => {
          input.addEventListener("change", () => {
            if (!input.checked) {
              return;
            }
            option.fare_class_policy = input.value;
            serialize();
          });
        });
        const biasInput = card.querySelector('[data-field="savings_needed_vs_previous"]');
        if (biasInput) {
          biasInput.addEventListener("change", (event) => {
            const nextValue = Math.max(0, Number.parseInt(event.target.value || "0", 10) || 0);
            option.savings_needed_vs_previous = nextValue;
            event.target.value = String(nextValue);
            serialize();
            render();
          });
        } else {
          option.savings_needed_vs_previous = 0;
        }
        createMultiPicker({
          root: card.querySelector('[data-field="origin_airports"]'),
          options: airports,
          values: option.origin_airports,
          placeholder: "Search origins",
          maxSelections: 3,
          onChange(values) {
            option.origin_airports = values;
            serialize();
          }
        });
        createMultiPicker({
          root: card.querySelector('[data-field="destination_airports"]'),
          options: airports,
          values: option.destination_airports,
          placeholder: "Search destinations",
          maxSelections: 3,
          onChange(values) {
            option.destination_airports = values;
            serialize();
          }
        });
        createMultiPicker({
          root: card.querySelector('[data-field="airlines"]'),
          options: airlines,
          values: option.airlines,
          placeholder: "Search airlines",
          onChange(values) {
            option.airlines = values;
            serialize();
          }
        });
        card.querySelector("[data-remove]").addEventListener("click", () => {
          routeOptions = routeOptions.filter((_, itemIndex) => itemIndex !== index);
          if (!routeOptions.length) {
            routeOptions = [{
              route_option_id: "",
              savings_needed_vs_previous: 0,
              origin_airports: [],
              destination_airports: [],
              airlines: [],
              day_offset: 0,
              start_time: "",
              end_time: "",
              fare_class_policy: "include_basic"
            }];
          }
          render();
        });
        card.querySelector("[data-move-up]").addEventListener("click", () => {
          if (index === 0) return;
          [routeOptions[index - 1], routeOptions[index]] = [routeOptions[index], routeOptions[index - 1]];
          render();
        });
        card.querySelector("[data-move-down]").addEventListener("click", () => {
          if (index === routeOptions.length - 1) return;
          [routeOptions[index + 1], routeOptions[index]] = [routeOptions[index], routeOptions[index + 1]];
          render();
        });
        root.appendChild(card);
      });
      serialize();
    }

    document.querySelector("[data-add-route-option]").addEventListener("click", () => {
      routeOptions.push({
        route_option_id: "",
        savings_needed_vs_previous: 0,
        origin_airports: [],
        destination_airports: [],
        airlines: [],
        day_offset: 0,
        start_time: "",
        end_time: "",
        fare_class_policy: "include_basic"
      });
      render();
    });

    tripKindSelect.addEventListener("change", syncKindVisibility);
    preferenceModeInputs.forEach((input) => {
      input.addEventListener("change", () => {
        render();
      });
    });
    form.querySelector('input[name="anchor_date"]').addEventListener("change", render);
    anchorWeekdaySelect.addEventListener("change", render);
    syncKindVisibility();
  }

  if (bookingState) {
    const catalogs = bookingState.catalogs || {};
    document.querySelectorAll("[data-single-picker-field]").forEach((field) => {
      const type = field.dataset.pickerType;
      const options = type === "airline" ? (catalogs.airlines || []) : (catalogs.airports || []);
      createSinglePicker({ field, options });
    });
  }

  const scheduledFiltersState = window.travelAgentTripsFilters;

  function initScheduledFilters(scope = document) {
    const panel = scope.querySelector("[data-scheduled-panel]");
    const form = scope.querySelector("[data-scheduled-filter-form]");
    if (!panel || !form || !scheduledFiltersState || form.dataset.bound === "true") {
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
        closeOtherPickers();
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

    createMultiPicker({
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
      }
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

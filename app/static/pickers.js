(() => {
  const pickerRegistry = [];

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

  function closeAllPickers(currentRoot = null) {
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

  function isInternalIdentifier(value) {
    return /^(grp|trip|inst|book|ub|opt|fetch|tracker|mail|price)_[a-z0-9]+$/i.test(String(value || ""));
  }

  function formatOption(option) {
    if (option.label && (isInternalIdentifier(option.value) || option.hideValue || option.value === option.label)) {
      return option.label;
    }
    return option.label ? `${option.value} · ${option.label}` : option.value;
  }

  function createChipMultiPicker({
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
    onChange,
  }) {
    const state = { values: Array.from(values || []) };
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
        if (!option) {
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
          state.values = state.values.filter((_, itemIndex) => itemIndex !== index);
          renderChips();
          onChange(Array.from(state.values));
          closeMenu();
        });
        chip.append(text, remove);
        chipList.appendChild(chip);
      });
      if (!state.values.length) {
        chipList.hidden = true;
        return;
      }
      chipList.hidden = false;
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
        button.dataset.optionValue = option.value;
        button.textContent = formatOption(option);
        menu.appendChild(button);
      });
      menu.hidden = false;
    }

    menu.addEventListener("pointerdown", (event) => {
      const optionButton = event.target.closest(".multi-select-option");
      if (!optionButton) {
        return;
      }
      event.preventDefault();
      state.values = [...state.values, optionButton.dataset.optionValue];
      renderChips();
      onChange(Array.from(state.values));
      search.value = "";
      renderMenu("");
    });

    renderChips();
    registerPicker(root, closeMenu);
    search.addEventListener("focus", () => {
      if (closeMenuTimer) {
        window.clearTimeout(closeMenuTimer);
        closeMenuTimer = null;
      }
      closeAllPickers(root);
      renderMenu(search.value);
    });
    search.addEventListener("input", () => renderMenu(search.value));
    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        return;
      }
      if (event.key === "Escape") {
        closeMenu();
        search.blur();
      }
    });
    search.addEventListener("blur", () => {
      closeMenuTimer = window.setTimeout(() => {
        if (document.activeElement && menu.contains(document.activeElement)) {
          return;
        }
        closeMenu();
      }, 150);
    });
  }

  function createCompactMultiPicker({
    root,
    options,
    values,
    placeholder,
    emptyText = "No selections",
    maxSelections = Number.POSITIVE_INFINITY,
    checkable = false,
    allowSelectAll = false,
    summaryFormatter = null,
    onChange,
  }) {
    const state = { values: Array.from(values || []) };

    root.innerHTML = `
      <div class="picker is-compact">
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
    const trigger = root.querySelector("[data-trigger]");
    const popover = root.querySelector("[data-popover]");
    const search = root.querySelector("[data-search]");
    const menu = root.querySelector("[data-menu]");
    const count = root.querySelector("[data-count]");
    const header = root.querySelector(".picker-popover-header");

    function renderTrigger() {
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
    }

    function closeMenu() {
      popover.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
    }

    function openMenu() {
      closeAllPickers(root);
      popover.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      search.focus();
      renderMenu(search.value);
    }

    function renderMenu(query = "") {
      const normalized = query.trim().toLowerCase();
      const matches = options
        .filter((option) => !normalized || buildSearchText(option).includes(normalized))
        .sort((left, right) => Number(state.values.includes(right.value)) - Number(state.values.includes(left.value)))
        .slice(0, 10);
      menu.innerHTML = "";
      const canSelectAll = allowSelectAll && options.length > 1;
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
        empty.textContent = "No matching options.";
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
          if (alreadySelected) {
            state.values = state.values.filter((value) => value !== option.value);
          } else if (maxSelections === 1) {
            state.values = [option.value];
          } else if (state.values.length < maxSelections) {
            state.values = [...state.values, option.value];
          }
          renderTrigger();
          renderMenu(search.value);
          onChange(Array.from(state.values));
        });
        menu.appendChild(button);
      });
    }

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
      if (event.key === "Enter") {
        event.preventDefault();
        return;
      }
      if (event.key === "Escape") {
        closeMenu();
        trigger.focus();
      }
    });
  }

  function createMultiPicker(config) {
    if (config.compact) {
      createCompactMultiPicker(config);
      return;
    }
    createChipMultiPicker(config);
  }

  function createSinglePicker({ field, options }) {
    const hidden = field.querySelector('input[type="hidden"]');
    const root = field.querySelector("[data-picker-root]");
    const pickerType = field.dataset.pickerType;
    const placeholder = pickerType === "airline" ? "Search airlines" : "Search airports";
    createMultiPicker({
      root,
      options,
      values: hidden.value ? [hidden.value] : [],
      placeholder,
      emptyText: placeholder,
      compact: true,
      maxSelections: 1,
      summaryFormatter(values, pickerOptions, emptyText) {
        if (!values.length) {
          return emptyText;
        }
        const option = pickerOptions.find((item) => item.value === values[0]);
        return option ? formatOption(option) : values[0];
      },
      onChange(values) {
        hidden.value = values[0] || "";
      },
    });
  }

  window.travelAgentPickers = {
    closeAllPickers,
    createChipMultiPicker,
    createCompactMultiPicker,
    createMultiPicker,
    createSinglePicker,
  };
})();

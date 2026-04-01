(() => {
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
})();

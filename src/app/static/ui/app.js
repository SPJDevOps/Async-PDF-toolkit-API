(() => {
  const TOOLS = {
    ocr: { path: "/ocr", mode: "file", result: "blob", label: "OCR" },
    qr: { path: "/qr", mode: "file", result: "json", label: "QR" },
    split: { path: "/split", mode: "file", result: "blob", label: "Split" },
    merge: { path: "/merge", mode: "files", result: "blob", label: "Merge" },
    "extract-text": {
      path: "/extract-text",
      mode: "file",
      result: "json",
      label: "Extract text",
    },
  };

  const form = document.getElementById("job-form");
  const fileInput = document.getElementById("file-input");
  const filesInput = document.getElementById("files-input");
  const submitBtn = document.getElementById("submit-btn");
  const statusEl = document.getElementById("status");
  const resultEl = document.getElementById("result");
  const resultBody = document.getElementById("result-body");
  const apiKeyInput = document.getElementById("api-key");
  const toolButtons = [...document.querySelectorAll(".tool")];

  let activeTool = "ocr";
  let objectUrl = null;

  const KEY_STORAGE = "pdf-toolkit-api-key";

  function loadStoredKey() {
    try {
      const value = sessionStorage.getItem(KEY_STORAGE);
      if (value) apiKeyInput.value = value;
    } catch {
      /* ignore */
    }
  }

  function storeKey(value) {
    try {
      if (value) sessionStorage.setItem(KEY_STORAGE, value);
      else sessionStorage.removeItem(KEY_STORAGE);
    } catch {
      /* ignore */
    }
  }

  function setStatus(message, kind) {
    statusEl.textContent = message;
    statusEl.classList.remove("is-busy", "is-error", "is-ok");
    if (kind) statusEl.classList.add(kind);
  }

  function clearResult() {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
    resultBody.innerHTML = "";
    resultEl.classList.add("is-hidden");
  }

  function showResult(node) {
    resultBody.innerHTML = "";
    resultBody.appendChild(node);
    resultEl.classList.remove("is-hidden");
  }

  function syncToolUi() {
    const cfg = TOOLS[activeTool];
    toolButtons.forEach((btn) => {
      const on = btn.dataset.tool === activeTool;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });

    document.querySelectorAll("[data-show]").forEach((el) => {
      const show = el.dataset.show;
      const visible =
        (show === "single" && cfg.mode === "file") ||
        (show === "merge" && cfg.mode === "files");
      el.classList.toggle("is-hidden", !visible);
    });

    document.querySelectorAll("[data-options]").forEach((el) => {
      el.classList.toggle("is-hidden", el.dataset.options !== activeTool);
    });

    submitBtn.textContent = `Run ${cfg.label}`;
    clearResult();
    setStatus("");
  }

  function buildUrl() {
    const cfg = TOOLS[activeTool];
    const url = new URL(cfg.path, window.location.origin);
    if (activeTool === "ocr") {
      const language = document.getElementById("language").value.trim();
      const optimize = document.getElementById("optimize").value;
      if (language) url.searchParams.set("language", language);
      if (document.getElementById("deskew").checked) {
        url.searchParams.set("deskew", "true");
      }
      if (document.getElementById("force_ocr").checked) {
        url.searchParams.set("force_ocr", "true");
      }
      if (optimize !== "") url.searchParams.set("optimize", optimize);
      if (document.getElementById("rotate_pages").checked) {
        url.searchParams.set("rotate_pages", "true");
      }
      if (document.getElementById("skip_text").checked) {
        url.searchParams.set("skip_text", "true");
      }
      if (document.getElementById("clean").checked) {
        url.searchParams.set("clean", "true");
      }
      if (document.getElementById("remove_background").checked) {
        url.searchParams.set("remove_background", "true");
      }
    }
    if (activeTool === "extract-text") {
      url.searchParams.set(
        "join_pages",
        document.getElementById("join_pages").checked ? "true" : "false",
      );
    }
    return url;
  }

  function filenameFromDisposition(header, fallback) {
    if (!header) return fallback;
    const match = /filename\*?=(?:UTF-8''|")?([^\";]+)"?/i.exec(header);
    if (!match) return fallback;
    try {
      return decodeURIComponent(match[1].trim());
    } catch {
      return match[1].trim();
    }
  }

  async function parseError(response) {
    const fallback = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail
          .map((item) => item.msg || JSON.stringify(item))
          .join("; ");
      }
      return fallback;
    } catch {
      return fallback;
    }
  }

  toolButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      activeTool = btn.dataset.tool;
      syncToolUi();
    });
  });

  apiKeyInput.addEventListener("change", () => {
    storeKey(apiKeyInput.value.trim());
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const cfg = TOOLS[activeTool];
    const formData = new FormData();

    if (cfg.mode === "file") {
      const file = fileInput.files?.[0];
      if (!file) {
        setStatus("Choose a PDF file.", "is-error");
        return;
      }
      formData.append("file", file, file.name);
    } else {
      const files = [...(filesInput.files || [])];
      if (files.length < 2) {
        setStatus("Choose at least two PDF files to merge.", "is-error");
        return;
      }
      files.forEach((file) => formData.append("files", file, file.name));
    }

    const headers = {};
    const apiKey = apiKeyInput.value.trim();
    storeKey(apiKey);
    if (apiKey) headers["X-API-Key"] = apiKey;

    clearResult();
    submitBtn.disabled = true;
    setStatus("Working…", "is-busy");

    try {
      const response = await fetch(buildUrl(), {
        method: "POST",
        body: formData,
        headers,
      });

      if (!response.ok) {
        const detail = await parseError(response);
        setStatus(detail, "is-error");
        return;
      }

      if (cfg.result === "json") {
        const data = await response.json();
        const pre = document.createElement("pre");
        pre.textContent = JSON.stringify(data, null, 2);
        showResult(pre);
        setStatus("Done.", "is-ok");
        return;
      }

      const blob = await response.blob();
      objectUrl = URL.createObjectURL(blob);
      const fallback =
        activeTool === "split" ? "split-pages.zip" : `${activeTool}-output.pdf`;
      const name = filenameFromDisposition(
        response.headers.get("content-disposition"),
        fallback,
      );
      const link = document.createElement("a");
      link.className = "download";
      link.href = objectUrl;
      link.download = name;
      link.textContent = `Download ${name}`;
      showResult(link);
      setStatus("Done — download ready.", "is-ok");
    } catch (err) {
      setStatus(err?.message || "Network error.", "is-error");
    } finally {
      submitBtn.disabled = false;
    }
  });

  loadStoredKey();
  syncToolUi();
})();

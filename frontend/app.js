const urlInput = document.getElementById("url-input");
const infoBtn = document.getElementById("info-btn");
const preview = document.getElementById("preview");
const thumbnail = document.getElementById("thumbnail");
const videoTitle = document.getElementById("video-title");
const videoMeta = document.getElementById("video-meta");
const typeToggle = document.getElementById("type-toggle");
const qualityRow = document.getElementById("quality-row");
const qualitySelect = document.getElementById("quality-select");
const downloadBtn = document.getElementById("download-btn");
const progressBlock = document.getElementById("progress-block");
const progressBar = document.getElementById("progress-bar");
const progressLabel = document.getElementById("progress-label");
const resultBlock = document.getElementById("result-block");
const saveLink = document.getElementById("save-link");
const downloadError = document.getElementById("download-error");

let videoInfo = null;
let pollTimer = null;

function apiErrorMessage(data, fallback) {
  const detail = data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg || String(item)).join("; ");
  }
  if (typeof detail === "string") {
    return detail;
  }
  return fallback;
}

function showError(message) {
  downloadError.textContent = message;
  downloadError.hidden = false;
}

function clearError() {
  downloadError.hidden = true;
  downloadError.textContent = "";
}

function resetDownloadUi() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  progressBlock.hidden = true;
  resultBlock.hidden = true;
  progressBar.value = 0;
  progressLabel.textContent = "0%";
}

function selectedMediaType() {
  return document.querySelector('input[name="media-type"]:checked').value;
}

function updateQualityUi() {
  const isVideo = selectedMediaType() === "video";
  qualityRow.hidden = !isVideo;
  if (!isVideo || !videoInfo) {
    return;
  }
  qualitySelect.innerHTML = "";
  const qualities = videoInfo.available_qualities || [];
  if (qualities.length === 0) {
    const opt = document.createElement("option");
    opt.value = "best";
    opt.textContent = "Best available";
    qualitySelect.appendChild(opt);
    return;
  }
  for (const q of qualities) {
    const opt = document.createElement("option");
    opt.value = q;
    opt.textContent = `${q}p`;
    qualitySelect.appendChild(opt);
  }
}

function formatDuration(seconds) {
  if (seconds == null) {
    return "";
  }
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = {};
  try {
    data = await response.json();
  } catch {
    /* non-JSON body */
  }
  if (!response.ok) {
    throw new Error(apiErrorMessage(data, response.statusText));
  }
  return data;
}

infoBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    showError("Paste a YouTube URL first.");
    return;
  }

  clearError();
  resetDownloadUi();
  infoBtn.disabled = true;
  downloadBtn.disabled = true;

  try {
    videoInfo = await postJson("/api/info", { url });
    thumbnail.src = videoInfo.thumbnail || "";
    thumbnail.alt = videoInfo.title || "Video thumbnail";
    videoTitle.textContent = videoInfo.title || "Untitled";
    const parts = [];
    if (videoInfo.uploader) {
      parts.push(videoInfo.uploader);
    }
    if (videoInfo.duration != null) {
      parts.push(formatDuration(videoInfo.duration));
    }
    videoMeta.textContent = parts.join(" · ");
    preview.hidden = false;
    typeToggle.hidden = false;
    updateQualityUi();
    downloadBtn.disabled = false;
  } catch (err) {
    videoInfo = null;
    preview.hidden = true;
    typeToggle.hidden = true;
    qualityRow.hidden = true;
    showError(err.message || "Failed to fetch video info.");
  } finally {
    infoBtn.disabled = false;
  }
});

document.querySelectorAll('input[name="media-type"]').forEach((input) => {
  input.addEventListener("change", () => {
    updateQualityUi();
    resetDownloadUi();
    clearError();
  });
});

function pollJob(jobId) {
  pollTimer = setInterval(async () => {
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      const job = await response.json();
      if (!response.ok) {
        throw new Error(apiErrorMessage(job, "Job not found"));
      }

      if (job.progress != null) {
        progressBar.value = job.progress;
        progressLabel.textContent = `${Math.round(job.progress)}%`;
      }

      if (job.status === "done") {
        clearInterval(pollTimer);
        pollTimer = null;
        downloadBtn.disabled = false;
        infoBtn.disabled = false;
        if (job.result) {
          const filename = encodeURIComponent(job.result);
          saveLink.href = `/api/files/${filename}`;
          saveLink.download = job.result;
          resultBlock.hidden = false;
        }
      } else if (job.status === "error") {
        clearInterval(pollTimer);
        pollTimer = null;
        downloadBtn.disabled = false;
        infoBtn.disabled = false;
        showError(job.error || "Download failed.");
      }
    } catch (err) {
      clearInterval(pollTimer);
      pollTimer = null;
      downloadBtn.disabled = false;
      infoBtn.disabled = false;
      showError(err.message || "Failed to check job status.");
    }
  }, 1000);
}

downloadBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url || !videoInfo) {
    showError("Get video info before downloading.");
    return;
  }

  clearError();
  resetDownloadUi();
  downloadBtn.disabled = true;
  infoBtn.disabled = true;
  progressBlock.hidden = false;

  const mediaType = selectedMediaType();
  const body = { url, type: mediaType };
  if (mediaType === "video") {
    body.quality = qualitySelect.value || "best";
  }

  try {
    const { job_id: jobId } = await postJson("/api/download", body);
    pollJob(jobId);
  } catch (err) {
    downloadBtn.disabled = false;
    infoBtn.disabled = false;
    progressBlock.hidden = true;
    showError(err.message || "Failed to start download.");
  }
});

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

const fileSelect = document.getElementById("file-select");
const modelSelect = document.getElementById("model-select");
const transcribeBtn = document.getElementById("transcribe-btn");
const transcribeProgress = document.getElementById("transcribe-progress");
const transcribeStatus = document.getElementById("transcribe-status");
const transcriptOutput = document.getElementById("transcript-output");
const exportBlock = document.getElementById("export-block");
const transcribeError = document.getElementById("transcribe-error");

let videoInfo = null;
let downloadPollTimer = null;
let transcribePollTimer = null;
let transcribeJobId = null;

const MEDIA_FILE_PATTERN =
  /\.(mp3|mp4|m4a|webm|mkv|wav|ogg|opus|flac|aac|avi|mov|wma)$/i;

function isMediaFilename(name) {
  return MEDIA_FILE_PATTERN.test(name);
}

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

function showDownloadError(message) {
  downloadError.textContent = message;
  downloadError.hidden = false;
}

function clearDownloadError() {
  downloadError.hidden = true;
  downloadError.textContent = "";
}

function showTranscribeError(message) {
  transcribeError.textContent = message;
  transcribeError.hidden = false;
}

function clearTranscribeError() {
  transcribeError.hidden = true;
  transcribeError.textContent = "";
}

function resetDownloadUi() {
  if (downloadPollTimer) {
    clearInterval(downloadPollTimer);
    downloadPollTimer = null;
  }
  progressBlock.hidden = true;
  resultBlock.hidden = true;
  progressBar.value = 0;
  progressLabel.textContent = "0%";
}

function resetTranscribeResultUi() {
  if (transcribePollTimer) {
    clearInterval(transcribePollTimer);
    transcribePollTimer = null;
  }
  transcribeProgress.hidden = true;
  transcriptOutput.hidden = true;
  transcriptOutput.value = "";
  exportBlock.hidden = true;
  transcribeJobId = null;
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

async function loadFileList() {
  try {
    const response = await fetch("/api/files");
    const files = await response.json();
    if (!response.ok) {
      throw new Error(apiErrorMessage(files, "Failed to load files"));
    }

    const mediaFiles = files.filter((file) => isMediaFilename(file.name));

    fileSelect.innerHTML = "";
    if (!mediaFiles.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No media files — download audio or video first";
      fileSelect.appendChild(opt);
      transcribeBtn.disabled = true;
      return;
    }

    for (const file of mediaFiles) {
      const opt = document.createElement("option");
      opt.value = file.name;
      opt.textContent = file.name;
      fileSelect.appendChild(opt);
    }
    transcribeBtn.disabled = false;
  } catch (err) {
    fileSelect.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Could not load file list";
    fileSelect.appendChild(opt);
    transcribeBtn.disabled = true;
    showTranscribeError(err.message || "Failed to load files.");
  }
}

function pollDownloadJob(jobId) {
  downloadPollTimer = setInterval(async () => {
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
        clearInterval(downloadPollTimer);
        downloadPollTimer = null;
        downloadBtn.disabled = false;
        infoBtn.disabled = false;
        if (job.result) {
          const filename = encodeURIComponent(job.result);
          saveLink.href = `/api/files/${filename}`;
          saveLink.download = job.result;
          resultBlock.hidden = false;
        }
        loadFileList();
      } else if (job.status === "error") {
        clearInterval(downloadPollTimer);
        downloadPollTimer = null;
        downloadBtn.disabled = false;
        infoBtn.disabled = false;
        showDownloadError(job.error || "Download failed.");
      }
    } catch (err) {
      clearInterval(downloadPollTimer);
      downloadPollTimer = null;
      downloadBtn.disabled = false;
      infoBtn.disabled = false;
      showDownloadError(err.message || "Failed to check job status.");
    }
  }, 1000);
}

function pollTranscribeJob(jobId) {
  transcribePollTimer = setInterval(async () => {
    try {
      const response = await fetch(`/api/transcribe/${encodeURIComponent(jobId)}`);
      const job = await response.json();
      if (!response.ok) {
        throw new Error(apiErrorMessage(job, "Job not found"));
      }

      if (job.status === "running") {
        transcribeStatus.textContent = "Transcribing…";
      }

      if (job.status === "done") {
        clearInterval(transcribePollTimer);
        transcribePollTimer = null;
        transcribeProgress.hidden = true;
        transcribeBtn.disabled = false;
        fileSelect.disabled = false;
        modelSelect.disabled = false;

        transcriptOutput.value = job.result || "";
        transcriptOutput.hidden = false;
        exportBlock.hidden = false;
      } else if (job.status === "error") {
        clearInterval(transcribePollTimer);
        transcribePollTimer = null;
        transcribeProgress.hidden = true;
        transcribeBtn.disabled = false;
        fileSelect.disabled = false;
        modelSelect.disabled = false;
        showTranscribeError(job.error || "Transcription failed.");
      }
    } catch (err) {
      clearInterval(transcribePollTimer);
      transcribePollTimer = null;
      transcribeProgress.hidden = true;
      transcribeBtn.disabled = false;
      fileSelect.disabled = false;
      modelSelect.disabled = false;
      showTranscribeError(err.message || "Failed to check transcription status.");
    }
  }, 1000);
}

async function downloadExport(format) {
  if (!transcribeJobId) {
    showTranscribeError("Transcribe a file before exporting.");
    return;
  }

  const title = videoInfo?.title || fileSelect.value || null;
  const url = urlInput.value.trim() || null;

  const response = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_id: transcribeJobId,
      format,
      title,
      url,
    }),
  });

  if (!response.ok) {
    let data = {};
    try {
      data = await response.json();
    } catch {
      /* ignore */
    }
    throw new Error(apiErrorMessage(data, response.statusText));
  }

  const blob = await response.blob();
  let filename = `transcript.${format}`;
  const disposition = response.headers.get("Content-Disposition");
  if (disposition) {
    const match = /filename\*?=(?:UTF-8'')?"?([^";\n]+)"?/i.exec(disposition);
    if (match) {
      filename = decodeURIComponent(match[1]);
    }
  }

  const blobUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(blobUrl);
}

infoBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    showDownloadError("Paste a YouTube URL first.");
    return;
  }

  clearDownloadError();
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
    showDownloadError(err.message || "Failed to fetch video info.");
  } finally {
    infoBtn.disabled = false;
  }
});

document.querySelectorAll('input[name="media-type"]').forEach((input) => {
  input.addEventListener("change", () => {
    updateQualityUi();
    resetDownloadUi();
    clearDownloadError();
  });
});

downloadBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url || !videoInfo) {
    showDownloadError("Get video info before downloading.");
    return;
  }

  clearDownloadError();
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
    pollDownloadJob(jobId);
  } catch (err) {
    downloadBtn.disabled = false;
    infoBtn.disabled = false;
    progressBlock.hidden = true;
    showDownloadError(err.message || "Failed to start download.");
  }
});

transcribeBtn.addEventListener("click", async () => {
  const filename = fileSelect.value;
  if (!filename) {
    showTranscribeError("Select a downloaded file first.");
    return;
  }

  clearTranscribeError();
  resetTranscribeResultUi();
  transcribeBtn.disabled = true;
  fileSelect.disabled = true;
  modelSelect.disabled = true;
  transcribeProgress.hidden = false;
  transcribeStatus.textContent = "Starting…";

  try {
    const { job_id: jobId } = await postJson("/api/transcribe", {
      filename,
      model: modelSelect.value,
    });
    transcribeJobId = jobId;
    pollTranscribeJob(jobId);
  } catch (err) {
    transcribeProgress.hidden = true;
    transcribeBtn.disabled = false;
    fileSelect.disabled = false;
    modelSelect.disabled = false;
    showTranscribeError(err.message || "Failed to start transcription.");
  }
});

for (const [button, format] of [
  [document.getElementById("export-txt"), "txt"],
  [document.getElementById("export-pdf"), "pdf"],
  [document.getElementById("export-json"), "json"],
]) {
  button.addEventListener("click", async () => {
    clearTranscribeError();
    button.disabled = true;
    try {
      await downloadExport(format);
    } catch (err) {
      showTranscribeError(err.message || "Export failed.");
    } finally {
      button.disabled = false;
    }
  });
}

loadFileList();

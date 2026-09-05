<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api/client";
  import { currentUser } from "$lib/stores/auth";
  import { activeWorkspace } from "$lib/stores/workspace";
  import type { DocumentItem } from "$lib/api/types";

  let documents: DocumentItem[] = [];
  let nextCursor: string | null = null;
  let isLoading = false;
  let isLoadingMore = false;
  let isUploading = false;
  let isDeletingId: string | null = null;
  let isDownloadingId: string | null = null;

  let actionMessage = "";
  let actionError = "";

  // Upload Form State
  let selectedFile: File | null = null;
  let fileInput: HTMLInputElement;
  let isDragging = false;

  $: currentWorkspaceId = $activeWorkspace?.id;
  $: if (currentWorkspaceId) {
    loadDocuments(currentWorkspaceId, true);
  }

  async function loadDocuments(workspaceId: string, reset: boolean = false) {
    if (reset) {
      isLoading = true;
      actionError = "";
      actionMessage = "";
      documents = [];
      nextCursor = null;
    } else {
      isLoadingMore = true;
    }

    const res = await api.listDocuments(workspaceId, 20, reset ? undefined : nextCursor ?? undefined);

    if (reset) {
      isLoading = false;
    } else {
      isLoadingMore = false;
    }

    if (res.success && res.data) {
      if (reset) {
        documents = res.data.items;
      } else {
        documents = [...documents, ...res.data.items];
      }
      nextCursor = res.data.next_cursor;
    } else {
      actionError = res.error || "Failed to load documents.";
    }
  }

  function handleLoadMore() {
    if ($activeWorkspace) {
      loadDocuments($activeWorkspace.id, false);
    }
  }

  function handleFileSelect(e: Event) {
    const target = e.target as HTMLInputElement;
    if (target.files && target.files.length > 0) {
      setFile(target.files[0]);
    }
  }

  function setFile(file: File) {
    actionError = "";
    actionMessage = "";

    // Client-side extension validation
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!["pdf", "txt", "md", "docx"].includes(ext)) {
      actionError = `File extension '.${ext}' is unsupported. Only PDF, TXT, MD, and DOCX are allowed.`;
      selectedFile = null;
      return;
    }

    // Client-side size validation
    const maxBytes = ["txt", "md"].includes(ext) ? 10 * 1024 * 1024 : 20 * 1024 * 1024;
    if (file.size > maxBytes) {
      actionError = `File size exceeds the permitted limit (${maxBytes / (1024 * 1024)} MB).`;
      selectedFile = null;
      return;
    }

    if (file.size === 0) {
      actionError = "Selected file is empty (0 bytes).";
      selectedFile = null;
      return;
    }

    selectedFile = file;
  }

  async function handleUpload() {
    if (!selectedFile || !$activeWorkspace) return;
    isUploading = true;
    actionError = "";
    actionMessage = "";

    const res = await api.uploadDocument($activeWorkspace.id, selectedFile);
    isUploading = false;

    if (res.success && res.data) {
      actionMessage = `Document "${res.data.original_filename}" uploaded successfully.`;
      selectedFile = null;
      if (fileInput) fileInput.value = "";
      await loadDocuments($activeWorkspace.id, true);
    } else {
      actionError = res.error || "Failed to upload document.";
    }
  }

  async function handleDownload(doc: DocumentItem) {
    if (!$activeWorkspace) return;
    isDownloadingId = doc.id;
    actionError = "";

    const res = await api.downloadDocument($activeWorkspace.id, doc.id, doc.original_filename);
    isDownloadingId = null;

    if (!res.success) {
      actionError = res.error || "Failed to download document.";
    }
  }

  async function handleDelete(doc: DocumentItem) {
    if (!$activeWorkspace) return;
    const confirmed = confirm(`Are you sure you want to permanently delete "${doc.original_filename}"?`);
    if (!confirmed) return;

    isDeletingId = doc.id;
    actionError = "";
    actionMessage = "";

    const res = await api.deleteDocument($activeWorkspace.id, doc.id);
    isDeletingId = null;

    if (res.success) {
      actionMessage = `Document "${doc.original_filename}" deleted.`;
      documents = documents.filter((d) => d.id !== doc.id);
    } else {
      actionError = res.error || "Failed to delete document.";
    }
  }

  function formatBytes(bytes: number): string {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  function canDelete(doc: DocumentItem): boolean {
    if (!$activeWorkspace) return false;
    if ($activeWorkspace.role === "owner" || $activeWorkspace.role === "admin") {
      return true;
    }
    return doc.uploaded_by === $currentUser?.id;
  }
</script>

<div class="space-y-8">
  <!-- Page Header -->
  <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
    <div>
      <div class="flex items-center gap-2">
        <h1 class="text-2xl font-bold tracking-tight text-white">Documents</h1>
        {#if $activeWorkspace}
          <span class="text-xs px-2.5 py-0.5 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-300 font-mono">
            {$activeWorkspace.name}
          </span>
        {/if}
      </div>
      <p class="text-xs text-slate-400 mt-1">
        Tenant document repository. Stored securely in S3/MinIO with cryptographic SHA-256 deduplication.
      </p>
    </div>
  </div>

  <!-- Action Banners -->
  {#if actionMessage}
    <div class="p-3 rounded-lg bg-emerald-950/80 border border-emerald-800 text-emerald-300 text-xs">
      {actionMessage}
    </div>
  {/if}

  {#if actionError}
    <div class="p-3 rounded-lg bg-rose-950/80 border border-rose-800 text-rose-300 text-xs">
      {actionError}
    </div>
  {/if}

  <!-- Upload Area -->
  <div class="rounded-xl border border-slate-800 bg-slate-900/50 p-6 space-y-4">
    <h3 class="text-sm font-semibold text-white">Upload New Document</h3>
    <p class="text-xs text-slate-400">
      Supported formats: <strong>PDF</strong>, <strong>DOCX</strong> (max 20 MB), <strong>TXT</strong>, <strong>Markdown</strong> (max 10 MB).
    </p>

    <div
      role="region"
      aria-label="Document upload dropzone"
      class="border-2 border-dashed rounded-xl p-6 text-center transition-colors {isDragging ? 'border-cyan-500 bg-cyan-950/20' : 'border-slate-800 bg-slate-950/40 hover:border-slate-700'}"
      on:dragover|preventDefault={() => { isDragging = true; }}
      on:dragleave|preventDefault={() => { isDragging = false; }}
      on:drop|preventDefault={(e) => {
        isDragging = false;
        if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
          setFile(e.dataTransfer.files[0]);
        }
      }}
    >
      <input
        type="file"
        bind:this={fileInput}
        on:change={handleFileSelect}
        accept=".pdf,.txt,.md,.docx"
        class="hidden"
      />

      <div class="space-y-3">
        <div class="h-10 w-10 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center mx-auto text-lg">
          📄
        </div>
        {#if selectedFile}
          <div class="text-xs text-slate-200 font-medium">
            Selected: <span class="text-cyan-400">{selectedFile.name}</span> ({formatBytes(selectedFile.size)})
          </div>
        {:else}
          <div class="text-xs text-slate-400">
            Drag & drop your document here, or
            <button
              type="button"
              on:click={() => fileInput.click()}
              class="text-cyan-400 hover:text-cyan-300 underline font-medium ml-1"
            >
              browse files
            </button>
          </div>
        {/if}
      </div>
    </div>

    {#if selectedFile}
      <div class="flex items-center justify-end gap-3 pt-2">
        <button
          type="button"
          on:click={() => {
            selectedFile = null;
            if (fileInput) fileInput.value = "";
          }}
          disabled={isUploading}
          class="px-3 py-1.5 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          on:click={handleUpload}
          disabled={isUploading}
          class="px-4 py-1.5 text-xs rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium disabled:opacity-50 transition-all flex items-center gap-2 shadow-md shadow-cyan-600/20"
        >
          {#if isUploading}
            <span class="h-3 w-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
            Uploading...
          {:else}
            Upload Document
          {/if}
        </button>
      </div>
    {/if}
  </div>

  <!-- Documents Table -->
  <div class="rounded-xl border border-slate-800 bg-slate-900/40 p-6 space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h3 class="text-sm font-semibold text-white">Workspace Documents</h3>
        <p class="text-xs text-slate-400">All documents uploaded to this workspace isolation tenant.</p>
      </div>
    </div>

    {#if isLoading}
      <div class="flex flex-col items-center justify-center py-12 space-y-3">
        <div class="h-6 w-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
        <p class="text-xs text-slate-400">Loading documents...</p>
      </div>
    {:else if documents.length === 0}
      <div class="text-center py-12 space-y-3">
        <div class="h-10 w-10 rounded-full bg-slate-800 text-slate-500 flex items-center justify-center mx-auto text-lg">
          📂
        </div>
        <p class="text-sm font-medium text-slate-300">No documents found</p>
        <p class="text-xs text-slate-500 max-w-sm mx-auto">
          Upload PDF, DOCX, TXT, or Markdown documents to begin building your workspace knowledge repository.
        </p>
      </div>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs">
          <thead class="text-slate-400 border-b border-slate-800">
            <tr>
              <th class="py-2.5 px-3">Name</th>
              <th class="py-2.5 px-3">Type</th>
              <th class="py-2.5 px-3">Size</th>
              <th class="py-2.5 px-3">Status</th>
              <th class="py-2.5 px-3">Uploaded</th>
              <th class="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800/60">
            {#each documents as doc (doc.id)}
              <tr class="hover:bg-slate-900/30">
                <td class="py-3 px-3">
                  <div class="font-medium text-slate-200 flex items-center gap-2">
                    <span class="text-slate-400">📄</span>
                    <span class="truncate max-w-[240px] md:max-w-[340px]" title={doc.original_filename}>
                      {doc.original_filename}
                    </span>
                  </div>
                  <div class="text-[10px] text-slate-500 font-mono truncate max-w-[260px] mt-0.5">
                    sha256: {doc.checksum.substring(0, 16)}...
                  </div>
                </td>
                <td class="py-3 px-3 text-slate-400 font-mono text-[11px]">
                  {doc.original_filename.split(".").pop()?.toUpperCase() || "DOC"}
                </td>
                <td class="py-3 px-3 text-slate-400 font-mono text-[11px]">
                  {formatBytes(doc.file_size)}
                </td>
                <td class="py-3 px-3">
                  <span class="px-2 py-0.5 rounded-full text-[10px] font-mono uppercase bg-emerald-950 border border-emerald-800 text-emerald-400">
                    {doc.status}
                  </span>
                </td>
                <td class="py-3 px-3 text-slate-400 text-[11px]">
                  {new Date(doc.created_at).toLocaleDateString()}
                </td>
                <td class="py-3 px-3 text-right space-x-2">
                  <button
                    on:click={() => handleDownload(doc)}
                    disabled={isDownloadingId === doc.id}
                    class="text-cyan-400 hover:text-cyan-300 font-medium transition-colors disabled:opacity-50"
                  >
                    {isDownloadingId === doc.id ? "Downloading..." : "Download"}
                  </button>

                  {#if canDelete(doc)}
                    <button
                      on:click={() => handleDelete(doc)}
                      disabled={isDeletingId === doc.id}
                      class="text-rose-400 hover:text-rose-300 font-medium transition-colors disabled:opacity-50"
                    >
                      {isDeletingId === doc.id ? "Deleting..." : "Delete"}
                    </button>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <!-- Keyset Pagination Load More -->
      {#if nextCursor}
        <div class="pt-4 text-center">
          <button
            on:click={handleLoadMore}
            disabled={isLoadingMore}
            class="px-4 py-2 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition-colors disabled:opacity-50"
          >
            {isLoadingMore ? "Loading more..." : "Load More Documents"}
          </button>
        </div>
      {/if}
    {/if}
  </div>
</div>
